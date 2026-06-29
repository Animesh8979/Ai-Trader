"""Multi-agent brain pipeline.

Defines the roles, prompts, and orchestration loop for technical/sentiment analysts,
bull/bear researchers, trader proposals, and risk critique agents.
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

class MultiAgentBrain:
    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()
        self.mcp_client = MCPClient()
        self.mcp_client.connect_all()
        self.mcp_tools = self.mcp_client.get_available_tools()

    def decide_trade(
        self,
        symbol: str,
        price_data: dict[str, Any],
        portfolio_state: dict[str, Any],
        news_feed: list[str],
        cycle_id: Optional[str] = None,
        run_id: Optional[int] = None,
    ) -> dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor

        cid = cycle_id or str(uuid4())
        log.info(f"Initiating multi-agent debate cycle for {symbol} (Cycle: {cid})")

        with ThreadPoolExecutor(max_workers=2) as executor:
            # 1. Technical & Sentiment Analysis (Parallel)
            tech_future = executor.submit(self._run_technical_analyst, symbol, price_data, cid, run_id)
            sent_future = executor.submit(self._run_sentiment_analyst, symbol, news_feed, cid, run_id)
            
            tech_report = tech_future.result()
            log.info(f"Technical Analyst completed. Outlook: {tech_report.get('outlook')}")
            
            sentiment_report = sent_future.result()
            log.info(f"Sentiment Analyst completed. Sentiment Score: {sentiment_report.get('sentiment_score')}")

            # 2. Bull / Bear Debate (Parallel)
            bull_future = executor.submit(self._run_bull_researcher, symbol, tech_report, sentiment_report, cid, run_id)
            bear_future = executor.submit(self._run_bear_researcher, symbol, tech_report, sentiment_report, cid, run_id)
            
            bull_case = bull_future.result()
            bear_case = bear_future.result()
            log.info("Bull vs Bear debate arguments prepared.")

        # 3. Trader Decision
        trade_proposal = self._run_trader(
            symbol, tech_report, sentiment_report, bull_case, bear_case, portfolio_state, cid, run_id
        )
        log.info(f"Trader proposed action: {trade_proposal.get('action')} (Size: {trade_proposal.get('size')})")

        # 5. Risk Critique
        if trade_proposal.get("action", "hold").lower() != "hold":
            risk_critique = self._run_risk_manager(symbol, trade_proposal, portfolio_state, cid, run_id)
            log.info(f"LLM Risk Manager verdict: {risk_critique.get('verdict')}")
            
            # If Risk Manager rejects, override action to hold
            if risk_critique.get("verdict", "approve").lower() == "reject":
                trade_proposal["action"] = "hold"
                trade_proposal["reason"] = f"Rejected by Risk Agent: {risk_critique.get('reason')}"
        else:
            risk_critique = {"verdict": "approve", "reason": "No action proposed by trader"}

        # Record decision in database
        try:
            get_db().insert(
                "decisions",
                {
                    "run_id": run_id,
                    "ts": portfolio_state.get("timestamp", ""),
                    "cycle_id": cid,
                    "desk": "crypto",
                    "symbol": symbol,
                    "proposal_json": json.dumps(trade_proposal),
                    "risk_verdict": risk_critique.get("verdict", "approve").upper(),
                    "final_action": trade_proposal.get("action", "hold").upper(),
                    "reason": trade_proposal.get("reason", "") or risk_critique.get("reason", ""),
                },
            )
        except Exception as exc:
            log.debug(f"Failed to record decision in db: {exc}")

        return trade_proposal

    def _run_technical_analyst(self, symbol: str, price_data: dict, cycle_id: str, run_id: Optional[int]) -> dict:
        system = (
            "You are a Technical Analyst Agent. Analyze the OHLCV candles, RSI, and EMA values.\n"
            "Respond ONLY with a JSON object containing the following keys:\n"
            '{"outlook": "bullish"|"bearish"|"neutral", "indicators_summary": "string description", '
            '"support": float, "resistance": float}'
        )
        user = f"Market: {symbol}\nPrice Data: {json.dumps(price_data)}"
        return self.client.complete_json("technical_analyst", system, user, cycle_id=cycle_id, run_id=run_id, record=True)

    def _run_sentiment_analyst(self, symbol: str, news: list[str], cycle_id: str, run_id: Optional[int]) -> dict:
        system = (
            "You are a Sentiment Analyst Agent. Analyze the news feed headlines and evaluate market sentiment.\n"
            "Respond ONLY with a JSON object containing the following keys:\n"
            '{"sentiment_score": float between -1.0 and 1.0, "impact_summary": "string description"}'
        )
        user = f"Market: {symbol}\nNews headlines:\n" + "\n".join(f"- {n}" for n in news)
        return self.client.complete_json("sentiment_analyst", system, user, cycle_id=cycle_id, run_id=run_id, record=True)

    def _run_bull_researcher(
        self, symbol: str, tech: dict, sentiment: dict, cycle_id: str, run_id: Optional[int]
    ) -> str:
        system = (
            "You are a Bull Researcher Agent. Your task is to analyze the data and make the strongest possible argument to BUY.\n"
            f"You have the following MCP tools available: {json.dumps(self.mcp_tools)}\n"
            "CRITICAL: You MUST use the `network_ai` blackboard MCP tool to post your atomic updates and read the Bear's counter-arguments in real-time. Follow the blackboard-negotiation skill rules.\n"
            "Format your argument as concise bullet points."
        )
        user = (
            f"Market: {symbol}\n"
            f"Technical Analysis: {json.dumps(tech)}\n"
            f"Sentiment Analysis: {json.dumps(sentiment)}"
        )
        resp = self.client.complete("bull_researcher", [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ], cycle_id=cycle_id, run_id=run_id, record=True)
        return resp.text

    def _run_bear_researcher(
        self, symbol: str, tech: dict, sentiment: dict, cycle_id: str, run_id: Optional[int]
    ) -> str:
        system = (
            "You are a Bear Researcher Agent. Your task is to analyze the data and make the strongest possible argument to SELL.\n"
            f"You have the following MCP tools available: {json.dumps(self.mcp_tools)}\n"
            "CRITICAL: You MUST use the `network_ai` blackboard MCP tool to post your atomic updates and read the Bull's counter-arguments in real-time. Follow the blackboard-negotiation skill rules.\n"
            "Format your argument as concise bullet points."
        )
        user = (
            f"Market: {symbol}\n"
            f"Technical Analysis: {json.dumps(tech)}\n"
            f"Sentiment Analysis: {json.dumps(sentiment)}"
        )
        resp = self.client.complete("bear_researcher", [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ], cycle_id=cycle_id, run_id=run_id, record=True)
        return resp.text

    def _run_trader(
        self,
        symbol: str,
        tech: dict,
        sentiment: dict,
        bull_case: str,
        bear_case: str,
        portfolio: dict,
        cycle_id: str,
        run_id: Optional[int],
    ) -> dict:
        system = (
            "You are a Trader Agent. Consolidate analyst inputs and debate arguments, and propose a trading action.\n"
            "Respond ONLY with a JSON object containing the following keys:\n"
            '{"action": "buy"|"sell"|"hold", "size": float, "stop_loss_pct": float, "take_profit_pct": float, '
            '"reason": "string explanation"}'
        )
        user = (
            f"Market: {symbol}\n"
            f"Technical outlook: {json.dumps(tech)}\n"
            f"Sentiment score: {json.dumps(sentiment)}\n"
            f"--- Debate arguments ---\n"
            f"BULL RESEARCH CASE:\n{bull_case}\n\n"
            f"BEAR RESEARCH CASE:\n{bear_case}\n"
            f"--- Portfolio State ---\n"
            f"Portfolio: {json.dumps(portfolio)}"
        )
        return self.client.complete_json("trader", system, user, cycle_id=cycle_id, run_id=run_id, record=True)

    def _run_risk_manager(
        self, symbol: str, proposal: dict, portfolio: dict, cycle_id: str, run_id: Optional[int]
    ) -> dict:
        system = (
            "You are a Risk Manager Agent. Critique the proposed trade against the portfolio state.\n"
            "Respond ONLY with a JSON object containing the following keys:\n"
            '{"verdict": "approve"|"reject", "reason": "string risk critique details"}'
        )
        user = (
            f"Market: {symbol}\n"
            f"Proposed trade: {json.dumps(proposal)}\n"
            f"Current portfolio state: {json.dumps(portfolio)}"
        )
        return self.client.complete_json("risk_manager", system, user, cycle_id=cycle_id, run_id=run_id, record=True)
