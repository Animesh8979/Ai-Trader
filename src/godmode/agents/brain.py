"""Multi-agent brain pipeline v4 — Regime-routed Reflective Cortex.

Upgrades from the flat 5-step pipeline:
1. RegimeRouter classifies market state and picks strategy template
2. PositionAnalyzer feeds Bull/Bear debate with S/R, VWAP, pivot context
3. ChronosProphetV2 injects probabilistic forecast quantiles
4. ReflectionV2 dynamically calibrates Bull/Bear weights + injects insight block
5. SymbolSelector narrows candidate universe every 6h
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import uuid4

from godmode.core.db import get_db
from godmode.core.logging import get_logger
from godmode.llm.provider import LLMClient

log = get_logger("agents.brain")

from godmode.agents.mcp_client import MCPClient
from godmode.agents.regime_router import RegimeRouter, Regime, REGIME_STRATEGY_ROUTER
from godmode.agents.position_analyzer import PositionAnalyzer
from godmode.agents.reflection_v2 import get_reflection
from godmode.agents.tsfm_prophet import get_chronos_prophet


class MultiAgentBrain:
    """v4: Regime-routed Bull/Bear debate with reflection-injected calibration."""

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()
        # MCP spawning is expensive (each npx subprocess takes 1-3s) and
        # mostly fails in test/offline environments. Allow disabling via env.
        import os
        if os.environ.get("GODMODE_DISABLE_MCP") == "1":
            log.info("[Brain v4] MCP disabled via GODMODE_DISABLE_MCP=1")
            self.mcp_client = None
            self.mcp_tools = {}
        else:
            try:
                self.mcp_client = MCPClient()
                self.mcp_client.connect_all()
                self.mcp_tools = self.mcp_client.get_available_tools()
            except Exception as exc:
                log.warning(f"MCP client init failed, continuing without MCP: {exc}")
                self.mcp_client = None
                self.mcp_tools = {}

        self.regime_router = RegimeRouter()
        self.position_analyzer = PositionAnalyzer()
        self.reflection = get_reflection()
        self.chronos = get_chronos_prophet()

    def evaluate_macro_regime(
        self,
        symbol: str,
        price_data: dict[str, Any],
        portfolio_state: dict[str, Any],
        news_feed: list[str],
        ohlcv: Optional[list[list[float]]] = None,
        cycle_id: Optional[str] = None,
        run_id: Optional[int] = None,
    ) -> dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor

        cid = cycle_id or str(uuid4())
        log.info(f"Initiating v4 reflective debate cycle for {symbol} (Cycle: {cid})")

        # Stage 0: Regime classification
        regime_signal = None
        if ohlcv:
            regime_signal = self.regime_router.classify(ohlcv)
            regime_strategy = REGIME_STRATEGY_ROUTER.get(regime_signal.regime, {}).get("primary", "HOLD")
            log.info(
                f"[Brain v4] Regime={regime_signal.regime.name} "
                f"strategy={regime_strategy} confidence={regime_signal.confidence:.2f}"
            )
        else:
            from godmode.agents.regime_router import RegimeSignal
            regime_signal = RegimeSignal(Regime.UNKNOWN, 0.0, "HOLD", {})

        # Stage 0b: Position analysis
        position_ctx = None
        if ohlcv and len(ohlcv) > 5:
            position_ctx = self.position_analyzer.analyze(symbol, ohlcv)
            log.info(f"[Brain v4] Position: {position_ctx.summary}")

        # Stage 0c: Chronos probability forecast
        chronos_forecast = None
        if ohlcv:
            closes = [c[3] if len(c) > 3 else c[-1] for c in ohlcv]
            chronos_forecast = self.chronos.predict_distribution(closes)
            log.info(
                f"[Brain v4] Chronos: p10={chronos_forecast['p10']} "
                f"p50={chronos_forecast['p50']} p90={chronos_forecast['p90']} "
                f"unc={chronos_forecast['uncertainty']}"
            )

        # Stage 0d: Reflection injection
        reflection_insight = self.reflection.reflect()
        log.info(f"[Brain v4] Reflection: {reflection_insight.reason}")

        # Enrich price_data with all signals for downstream agents
        price_data_enriched = dict(price_data)
        price_data_enriched["regime"] = {
            "label": regime_signal.regime.name,
            "confidence": regime_signal.confidence,
            "strategy": regime_signal.strategy,
            "details": regime_signal.details,
        }
        if position_ctx:
            price_data_enriched["position_analysis"] = {
                "range_pct": position_ctx.range_pct,
                "nearest_level": position_ctx.nearest_level,
                "distance_pct": position_ctx.distance_to_level_pct,
                "vwap_distance_pct": position_ctx.vwap_distance_pct,
                "summary": position_ctx.summary,
            }
        if chronos_forecast:
            price_data_enriched["chronos_forecast"] = chronos_forecast
        price_data_enriched["reflection"] = reflection_insight.insight_block

        with ThreadPoolExecutor(max_workers=2) as executor:
            # Stage 1: Technical & Sentiment (parallel)
            tech_future = executor.submit(
                self._run_technical_analyst, symbol, price_data_enriched, cid, run_id
            )
            sent_future = executor.submit(
                self._run_sentiment_analyst, symbol, news_feed, cid, run_id
            )
            tech_report = tech_future.result()
            sentiment_report = sent_future.result()

            # Stage 2: Bull / Bear debate (parallel) — reflection-aware weights
            bull_weight = max(0.5, 1.0 + reflection_insight.bull_weight_adjustment)
            bear_weight = max(0.5, 1.0 + reflection_insight.bear_weight_adjustment)

            bull_future = executor.submit(
                self._run_bull_researcher,
                symbol, tech_report, sentiment_report, cid, run_id,
                position_ctx, chronos_forecast, regime_signal, bull_weight,
            )
            bear_future = executor.submit(
                self._run_bear_researcher,
                symbol, tech_report, sentiment_report, cid, run_id,
                position_ctx, chronos_forecast, regime_signal, bear_weight,
            )
            bull_case = bull_future.result()
            bear_case = bear_future.result()

        # Stage 3: Macro Council with reflection-injected insight
        macro_proposal = self._run_macro_council(
            symbol, tech_report, sentiment_report, bull_case, bear_case,
            portfolio_state, cid, run_id, reflection_insight, regime_signal, chronos_forecast,
            position_ctx,
        )

        # Stage 4: Risk critique
        risk_critique = self._run_risk_manager(symbol, macro_proposal, portfolio_state, cid, run_id)
        if risk_critique.get("verdict", "approve").lower() == "reject":
            macro_proposal["trade_bias"] = "neutral"
            macro_proposal["reason"] = f"Rejected by Risk Agent: {risk_critique.get('reason')}"

        # Stage 5: Regime-gated final override — if UNKNOWN regime, force neutral
        if regime_signal.regime == Regime.UNKNOWN:
            macro_proposal["trade_bias"] = "neutral"
            macro_proposal["reason"] = (
                macro_proposal.get("reason", "") + " | Forced neutral: regime UNKNOWN."
            )

        # Record decision
        try:
            get_db().insert(
                "decisions",
                {
                    "run_id": run_id,
                    "ts": portfolio_state.get("timestamp", ""),
                    "cycle_id": cid,
                    "desk": "crypto" if "/" in symbol else "nse",
                    "symbol": symbol,
                    "proposal_json": json.dumps(macro_proposal),
                    "risk_verdict": risk_critique.get("verdict", "approve").upper(),
                    "final_action": macro_proposal.get("regime", "ranging").upper(),
                    "reason": macro_proposal.get("reason", "") or risk_critique.get("reason", ""),
                },
            )
        except Exception as exc:
            log.debug(f"Failed to record decision in db: {exc}")

        return macro_proposal

    def _run_technical_analyst(self, symbol, price_data, cycle_id, run_id):
        system = (
            "You are a Technical Analyst Agent. Analyze OHLCV, RSI, EMA, regime, "
            "position analysis, and probabilistic forecast.\n"
            "Respond ONLY with JSON: "
            '{"outlook": "bullish"|"bearish"|"neutral", "indicators_summary": "string", '
            '"support": float, "resistance": float}'
        )
        user = f"Market: {symbol}\nPrice Data: {json.dumps(price_data)}"
        try:
            return self.client.complete_json("technical_analyst", system, user, cycle_id=cycle_id, run_id=run_id, record=True)
        except Exception as exc:
            log.warning(f"[Brain v4] technical_analyst LLM failed: {exc}")
            return {"outlook": "neutral", "indicators_summary": "LLM unavailable",
                    "support": 0.0, "resistance": 0.0}

    def _run_sentiment_analyst(self, symbol, news, cycle_id, run_id):
        system = (
            "You are a Sentiment Analyst Agent. Analyze news and assign sentiment.\n"
            "Respond ONLY with JSON: "
            '{"sentiment_score": float between -1.0 and 1.0, "impact_summary": "string"}'
        )
        user = f"Market: {symbol}\nNews headlines:\n" + "\n".join(f"- {n}" for n in news)
        try:
            return self.client.complete_json("sentiment_analyst", system, user, cycle_id=cycle_id, run_id=run_id, record=True)
        except Exception as exc:
            log.warning(f"[Brain v4] sentiment_analyst LLM failed: {exc}")
            return {"sentiment_score": 0.0, "impact_summary": "LLM unavailable"}

    def _run_bull_researcher(
        self, symbol, tech, sentiment, cycle_id, run_id,
        position_ctx=None, chronos=None, regime=None, weight=1.0,
    ):
        weight_hint = f"\nWEIGHT: Your argument carries {weight:.2f}x persuasive weight."
        ctx_block = ""
        if position_ctx:
            ctx_block += f"\nPosition: {position_ctx.summary}"
        if chronos:
            ctx_block += (
                f"\nChronos forecast: p10={chronos['p10']} p50={chronos['p50']} "
                f"p90={chronos['p90']} uncertainty={chronos['uncertainty']}"
            )
        if regime:
            ctx_block += f"\nRegime: {regime.regime.name} (strategy={regime.strategy})"

        system = (
            "You are a Bull Researcher Agent. Make the strongest possible BUY argument."
            f"{weight_hint}{ctx_block}\n"
            f"Available MCP tools: {json.dumps(self.mcp_tools)}\n"
            "Format your argument as concise bullet points."
        )
        user = (
            f"Market: {symbol}\n"
            f"Technical Analysis: {json.dumps(tech)}\n"
            f"Sentiment Analysis: {json.dumps(sentiment)}"
        )
        try:
            resp = self.client.complete("bull_researcher", [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ], cycle_id=cycle_id, run_id=run_id, record=True)
            return resp.text
        except Exception as exc:
            log.warning(f"[Brain v4] bull_researcher LLM failed: {exc}")
            return "[Bull Researcher LLM unavailable — no bull argument produced.]"

    def _run_bear_researcher(
        self, symbol, tech, sentiment, cycle_id, run_id,
        position_ctx=None, chronos=None, regime=None, weight=1.0,
    ):
        weight_hint = f"\nWEIGHT: Your argument carries {weight:.2f}x persuasive weight."
        ctx_block = ""
        if position_ctx:
            ctx_block += f"\nPosition: {position_ctx.summary}"
        if chronos:
            ctx_block += (
                f"\nChronos forecast: p10={chronos['p10']} p50={chronos['p50']} "
                f"p90={chronos['p90']} uncertainty={chronos['uncertainty']}"
            )
        if regime:
            ctx_block += f"\nRegime: {regime.regime.name} (strategy={regime.strategy})"

        system = (
            "You are a Bear Researcher Agent. Make the strongest possible SELL argument."
            f"{weight_hint}{ctx_block}\n"
            f"Available MCP tools: {json.dumps(self.mcp_tools)}\n"
            "Format your argument as concise bullet points."
        )
        user = (
            f"Market: {symbol}\n"
            f"Technical Analysis: {json.dumps(tech)}\n"
            f"Sentiment Analysis: {json.dumps(sentiment)}"
        )
        try:
            resp = self.client.complete("bear_researcher", [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ], cycle_id=cycle_id, run_id=run_id, record=True)
            return resp.text
        except Exception as exc:
            log.warning(f"[Brain v4] bear_researcher LLM failed: {exc}")
            return "[Bear Researcher LLM unavailable — no bear argument produced.]"

    def _run_macro_council(
        self, symbol, tech, sentiment, bull_case, bear_case, portfolio,
        cycle_id, run_id, reflection=None, regime=None, chronos=None,
        position_ctx=None,
    ):
        reflection_block = ""
        if reflection:
            reflection_block = (
                f"\n--- Reflection Agent v2 ---\n{reflection.insight_block}\n"
                f"Recommended bias: {reflection.recommended_bias}\n"
            )
        regime_block = ""
        if regime:
            regime_block = (
                f"\n--- Regime Classification ---\n"
                f"Regime: {regime.regime.name}, strategy={regime.strategy}, "
                f"confidence={regime.confidence:.2f}\n"
            )
        chronos_block = ""
        if chronos:
            chronos_block = (
                f"\n--- Chronos Forecast ---\n"
                f"p10={chronos['p10']} p50={chronos['p50']} p90={chronos['p90']} "
                f"uncertainty={chronos['uncertainty']} source={chronos['source']}\n"
            )
        position_block = ""
        if position_ctx:
            position_block = (
                f"\n--- Position Analysis ---\n"
                f"Position: {position_ctx.summary}\n"
            )

        system = (
            "You are the Macro Regime Council v4. Consolidate all analyst inputs, "
            "debate, reflection, regime, and Chronos forecast, then propose parameters.\n"
            f"Available MCP tools: {json.dumps(self.mcp_tools)}\n"
            "Respond ONLY with JSON: "
            '{"regime": "bull"|"bear"|"ranging", "rsi_oversold": int, "rsi_overbought": int, '
            '"trade_bias": "long"|"short"|"neutral", "reason": "string"}'
        )
        user = (
            f"Market: {symbol}\n"
            f"Technical outlook: {json.dumps(tech)}\n"
            f"Sentiment score: {json.dumps(sentiment)}\n"
            f"--- Debate arguments ---\n"
            f"BULL RESEARCH CASE:\n{bull_case}\n\n"
            f"BEAR RESEARCH CASE:\n{bear_case}\n"
            f"{reflection_block}{regime_block}{chronos_block}{position_block}"
            f"--- Portfolio State ---\n"
            f"Portfolio: {json.dumps(portfolio)}"
        )
        # BRUTAL FAULT TOLERANCE: if LLM is down (key expired, network outage,
        # rate limited, all free-fallbacks failed), do NOT crash the trader —
        # return a safe neutral plan so the risk engine + chronos gate refuse
        # to take new positions until the LLM recovers.
        try:
            return self.client.complete_json(
                "macro_council", system, user,
                cycle_id=cycle_id, run_id=run_id, record=True,
            )
        except Exception as exc:
            log.error(
                f"[Brain v4] Macro Council LLM call failed ({type(exc).__name__}: {exc}). "
                "Returning safe neutral plan — no new positions until LLM recovers."
            )
            return {
                "regime": "ranging",
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "trade_bias": "neutral",
                "reason": f"LLM unavailable: {type(exc).__name__} — refusing to take new positions.",
            }

    def _run_risk_manager(self, symbol, proposal, portfolio, cycle_id, run_id):
        system = (
            "You are a Risk Manager Agent. Critique proposed trade parameters.\n"
            "Reject if bias is too aggressive for current equity drawdown.\n"
            "Respond ONLY with JSON: "
            '{"verdict": "approve"|"reject", "reason": "string"}'
        )
        user = (
            f"Market: {symbol}\n"
            f"Proposed parameters: {json.dumps(proposal)}\n"
            f"Current portfolio state: {json.dumps(portfolio)}"
        )
        # FAIL-SAFE: when risk-manager LLM is down, default to REJECT to avoid
        # acting on unvetted proposals. (Even a long bias goes neutral, no harm.)
        try:
            return self.client.complete_json("risk_manager", system, user, cycle_id=cycle_id, run_id=run_id, record=True)
        except Exception as exc:
            log.warning(f"[Brain v4] risk_manager LLM failed: {exc}; defaulting to REJECT")
            return {"verdict": "reject", "reason": f"Risk LLM unavailable — refusing unvetted proposal: {exc}"}