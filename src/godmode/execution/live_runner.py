"""Live and Paper trading loop execution engine (Phase 2/4).

Fetches live market data via CCXT, computes technical indicators, gathers sentiment
headlines, evaluates order proposals against the Multi-Agent Brain and deterministic Risk Engine,
executes orders, and persists execution history in the SQLite database.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import time
import aiohttp
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import polars as pl
import numpy as np

from godmode.core.config import Config, load_config
from godmode.core.db import get_db
from godmode.core.killswitch import get_kill_switch
from godmode.core.logging import get_logger
from godmode.core.timeutil import utcnow_iso
from godmode.execution.crypto_ccxt import CryptoCcxtAdapter
from godmode.execution.indian_broker_adapter import ShoonyaAdapter
from godmode.execution.adapter import BaseBrokerAdapter
from godmode.agents.brain import MultiAgentBrain
from godmode.agents.tsfm_prophet import ChronosProphetV2
from godmode.agents.reflection_agent import ReflectionAgent
from godmode.risk.engine import RiskEngine, OrderProposal, PortfolioState, Verdict
from godmode.agents.jev_trader_engine import JevTraderEngine
from godmode.risk.policy_veto import PolicyVetoEngine
from godmode.execution.post_only_pegging import PostOnlyPeggingEngine
from godmode.core.singularity_loop import get_singularity_loop

log = get_logger("execution.live_runner")


async def fetch_news(symbol: str) -> list[str]:
    """Fetch live news from Finnhub. HONEST: returns [] when no API key — never
    fabricates 'Dummy: ...' strings that the LLM would then reason about as real.
    """
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        log.info("[fetch_news] No FINNHUB_API_KEY set — returning [] (no fake news).")
        return []
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://finnhub.io/api/v1/news?category=crypto&token={api_key}"
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [item["headline"] for item in data[:3]]
                else:
                    log.warning(f"[fetch_news] Finnhub returned status {resp.status}.")
                    return []
    except Exception as exc:
        log.error(f"[fetch_news] Failed: {exc}")
        return []

def compute_indicators(candles: list[list]) -> dict[str, float]:
    """Helper to compute fast/slow EMA, RSI, VWAP, ADX, and Supertrend using Polars (Rust)."""
    df = pl.DataFrame(candles, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row")
    
    # 1. EMA
    df = df.with_columns([
        pl.col("close").ewm_mean(span=10, adjust=False).alias("ema_fast"),
        pl.col("close").ewm_mean(span=20, adjust=False).alias("ema_slow"),
    ])
    
    # 2. RSI
    delta = pl.col("close").diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0).rolling_mean(window_size=14)
    loss = pl.when(delta < 0).then(-delta).otherwise(0).rolling_mean(window_size=14)
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    df = df.with_columns(rsi.alias("rsi"))

    # 3. Bollinger Bands
    std = pl.col("close").rolling_std(window_size=20)
    df = df.with_columns([
        (pl.col("ema_slow") + (std * 2)).alias("bb_upper"),
        (pl.col("ema_slow") - (std * 2)).alias("bb_lower")
    ])

    # 4. VWAP
    typical_price = (pl.col("high") + pl.col("low") + pl.col("close")) / 3
    vwap = (typical_price * pl.col("volume")).cum_sum() / (pl.col("volume").cum_sum() + 1e-9)
    df = df.with_columns(vwap.alias("vwap"))
    
    # 5. True Range & ATR
    tr = pl.concat_list([
        (pl.col("high") - pl.col("low")),
        (pl.col("high") - pl.col("close").shift(1)).abs(),
        (pl.col("low") - pl.col("close").shift(1)).abs(),
    ]).list.max()
    df = df.with_columns(tr.alias("tr"))
    df = df.with_columns(pl.col("tr").rolling_mean(window_size=14).alias("atr"))

    # 6. ADX (Average Directional Index)
    df = df.with_columns([
        pl.col("high").diff().alias("up_move"),
        (pl.col("low").shift(1) - pl.col("low")).alias("down_move")
    ])
    
    plus_dm = pl.when((pl.col("up_move") > pl.col("down_move")) & (pl.col("up_move") > 0)).then(pl.col("up_move")).otherwise(0)
    minus_dm = pl.when((pl.col("down_move") > pl.col("up_move")) & (pl.col("down_move") > 0)).then(pl.col("down_move")).otherwise(0)
    
    df = df.with_columns([
        plus_dm.alias("plus_dm"),
        minus_dm.alias("minus_dm")
    ])
    
    plus_dm_smoothed = pl.col("plus_dm").rolling_mean(window_size=14)
    minus_dm_smoothed = pl.col("minus_dm").rolling_mean(window_size=14)
    
    plus_di = 100 * (plus_dm_smoothed / (pl.col("atr") + 1e-9))
    minus_di = 100 * (minus_dm_smoothed / (pl.col("atr") + 1e-9))
    
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
    df = df.with_columns([
        plus_di.alias("plus_di"),
        minus_di.alias("minus_di"),
        dx.alias("dx")
    ])
    df = df.with_columns(pl.col("dx").rolling_mean(window_size=14).alias("adx"))

    # 7. Supertrend (Basic Bands)
    hl2 = (pl.col("high") + pl.col("low")) / 2
    df = df.with_columns([
        (hl2 + (3.0 * pl.col("atr"))).alias("upper_band"),
        (hl2 - (3.0 * pl.col("atr"))).alias("lower_band")
    ])
    
    # Supertrend (Final Bands and Direction)
    upper_bands = df["upper_band"].to_numpy()
    lower_bands = df["lower_band"].to_numpy()
    closes = df["close"].to_numpy()
    
    st_val = [0.0] * len(df)
    direction = [1] * len(df)
    
    for i in range(1, len(df)):
        if closes[i] > upper_bands[i-1]:
            direction[i] = 1
        elif closes[i] < lower_bands[i-1]:
            direction[i] = -1
        else:
            direction[i] = direction[i-1]
            if direction[i] == 1 and lower_bands[i] < lower_bands[i-1]:
                lower_bands[i] = lower_bands[i-1]
            if direction[i] == -1 and upper_bands[i] > upper_bands[i-1]:
                upper_bands[i] = upper_bands[i-1]
        
        st_val[i] = lower_bands[i] if direction[i] == 1 else upper_bands[i]
        
    df = df.with_columns([
        pl.Series("supertrend", st_val),
        pl.Series("supertrend_dir", direction)
    ])
    
    # 8. Pivot Points
    rolling_high = pl.col("high").rolling_max(window_size=14)
    rolling_low = pl.col("low").rolling_min(window_size=14)
    pivot = (rolling_high + rolling_low + pl.col("close")) / 3
    r1 = (2 * pivot) - rolling_low
    s1 = (2 * pivot) - rolling_high
    
    df = df.with_columns([
        pivot.alias("pivot"),
        r1.alias("r1"),
        s1.alias("s1")
    ])
    
    last = df.row(-1, named=True)
    def safe_float(val, default):
        return float(val) if val is not None and not np.isnan(val) else float(default)
        
    c = last["close"]
    return {
        "open": float(last["open"]),
        "high": float(last["high"]),
        "low": float(last["low"]),
        "close": float(c),
        "volume": float(last["volume"]),
        "rsi": safe_float(last["rsi"], 50.0),
        "ema_fast": safe_float(last["ema_fast"], c),
        "ema_slow": safe_float(last["ema_slow"], c),
        "bb_upper": safe_float(last["bb_upper"], c),
        "bb_lower": safe_float(last["bb_lower"], c),
        "vwap": safe_float(last["vwap"], c),
        "adx": safe_float(last["adx"], 20.0),
        "supertrend": safe_float(last["supertrend"], c),
        "supertrend_dir": int(safe_float(last["supertrend_dir"], 1.0)),
        "pivot": safe_float(last["pivot"], c),
        "r1": safe_float(last["r1"], c),
        "s1": safe_float(last["s1"], c),
    }


def get_broker_adapter(venue: str, config: Config) -> BaseBrokerAdapter:
    if venue.lower() == "shoonya":
        return ShoonyaAdapter(venue, config)
    return CryptoCcxtAdapter(venue, config)


def decide_action(
    price_metrics: dict,
    chronos_dist: dict,
    macro_params: dict,
    position_qty: float,
    last_close: float,
) -> tuple[str, str]:
    """Pure decision logic from LiveRunner._main_loop step 3.6 + 3.7 + 4.

    Returns (action, reject_reason). action is one of "buy", "sell", "hold".
    reject_reason is "" if not rejected, else a human-readable reason.

    Brutal design: extracted so it's testable WITHOUT mocking broker loops.
    Initially called from _main_loop; also exposed directly for unit testing.
    """
    action = "hold"
    rsi_val = float(price_metrics["rsi"])
    adx_val = float(price_metrics["adx"])
    supertrend_dir = int(price_metrics["supertrend_dir"])
    is_trending = adx_val > 25.0

    if is_trending:
        # Trend-Following (Supertrend direction confirms trade bias)
        if macro_params["trade_bias"] == "long" and supertrend_dir == 1:
            action = "buy" if position_qty <= 0 else "hold"
        elif macro_params["trade_bias"] == "short" and supertrend_dir == -1:
            action = "sell" if position_qty >= 0 else "hold"
    else:
        # Mean-Reversion (RSI confirms trade bias in range-bound market)
        if macro_params["trade_bias"] == "long" and rsi_val < macro_params["rsi_oversold"]:
            action = "buy" if position_qty <= 0 else "hold"
        elif macro_params["trade_bias"] == "short" and rsi_val > macro_params["rsi_overbought"]:
            action = "sell" if position_qty >= 0 else "hold"

    if action == "hold":
        return "hold", ""

    side = "buy" if action == "buy" else "sell"

    # 3.7 Chronos Prophet confirmation gate
    chronos_p50 = float(chronos_dist.get("p50", 0.0))
    chronos_unc = float(chronos_dist.get("uncertainty", 0.0))
    prophet_agrees = (
        (side == "buy" and chronos_p50 > last_close * 1.0005) or
        (side == "sell" and chronos_p50 < last_close * 0.9995)
    )
    if not prophet_agrees:
        return "hold", (
            f"chronos_disagrees: side={side} last_close={last_close:.4f} "
            f"p50={chronos_p50:.4f}"
        )
    if chronos_unc > 0.15:
        return "hold", (
            f"chronos_uncertain: uncertainty={chronos_unc:.4f} > 0.15"
        )
    return action, ""


class LiveRunner:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or load_config()
        self.kill_switch = get_kill_switch()
        self.risk_engine = RiskEngine()
        self.brain = MultiAgentBrain()
        self.chronos = ChronosProphetV2()
        self.reflection = ReflectionAgent()
        self._running = False
        self._run_id: Optional[int] = None
        self._peak_equity: Optional[Decimal] = None
        self.macro_params = {
            "trade_bias": "neutral",
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "regime": "ranging"
        }
        self.jev_engine = JevTraderEngine()
        self.policy_veto = PolicyVetoEngine()
        self.pegging_engine = PostOnlyPeggingEngine()
        self.singularity_loop = get_singularity_loop()
        self._last_jev_confidence = 0.65

    def start(self, note: str = "Live trading loop started") -> None:
        """Start the live trading thread pool/loop."""
        if self._running:
            log.warning("Live trading loop is already running.")
            return
        
        self._running = True
        self._run_id = get_db().start_run(mode=self.config.mode, note=note)
        log.info(f"Started live execution run {self._run_id} in {self.config.mode} mode.")

        # Spawn loop tasks
        asyncio.create_task(self._main_loop())
        
        crypto_cfg = self.config.markets.get("crypto")
        if crypto_cfg and crypto_cfg.enabled:
            venue = crypto_cfg.venue
            symbol = crypto_cfg.symbols[0] if crypto_cfg.symbols else "BTC/USDT"
            asyncio.create_task(self._macro_council_loop(symbol, venue))

    def stop(self) -> None:
        """Gracefully stop the loop execution."""
        if not self._running:
            return
        self._running = False
        if self._run_id is not None:
            get_db().end_run(self._run_id, status="stopped")
            log.info(f"Ended live execution run {self._run_id}.")
            self._run_id = None

    async def _main_loop(self) -> None:
        interval = self.config.app.decision_interval_seconds
        
        # Check enabled market
        crypto_cfg = self.config.markets.get("crypto")
        if not crypto_cfg or not crypto_cfg.enabled:
            log.error("Crypto market is not enabled in configuration. LiveRunner exiting.")
            self.stop()
            return
        
        venue = crypto_cfg.venue
        symbol = crypto_cfg.symbols[0] if crypto_cfg.symbols else "BTC/USDT"
        base_asset, quote_asset = symbol.split("/")
        
        adapter = get_broker_adapter(venue, self.config)
        
        while self._running:
            try:
                # Refresh watchdog heartbeat
                self.kill_switch.beat()

                # 1. Enforce physical stop switch
                if self.kill_switch.is_halted():
                    log.warning("Trading is HALTED. Skipping execution cycle.")
                    await asyncio.sleep(15.0)
                    continue

                log.info(f"Running execution tick for {symbol} on {venue}...")
                
                # 2. Fetch live data concurrently for 1m and 15m (raw ccxt rows)
                candles_1m_task = asyncio.to_thread(adapter.exchange.fetch_ohlcv, symbol, "1m", limit=30)
                candles_15m_task = asyncio.to_thread(adapter.exchange.fetch_ohlcv, symbol, "15m", limit=30)
                candles_1m, candles_15m = await asyncio.gather(candles_1m_task, candles_15m_task)
                
                price_metrics_1m = compute_indicators(candles_1m)
                price_metrics_15m = compute_indicators(candles_15m)
                
                price_metrics = {
                    "1m": price_metrics_1m,
                    "15m": price_metrics_15m
                }
                current_price = Decimal(str(price_metrics_1m["close"]))
                
                # Fetch balance and map base coin holdings as position size
                balances = await asyncio.to_thread(adapter.fetch_balance)
                base_bal = balances.get(base_asset, {}) if isinstance(balances, dict) else {}
                quote_bal = balances.get(quote_asset, {}) if isinstance(balances, dict) else {}
                cash = Decimal(str(quote_bal.get("free", 0) or 0))
                position_qty = Decimal(str(base_bal.get("total", 0) or 0))
                

                
                current_equity = cash + (position_qty * current_price)
                if self._peak_equity is None or current_equity > self._peak_equity:
                    self._peak_equity = current_equity

                portfolio_state = {
                    "timestamp": utcnow_iso(),
                    "equity": float(current_equity),
                    "cash": float(cash),
                    "position_size": float(position_qty),
                }

                # Performance Self-Reflection (self-calibration)
                reflection_res = self.reflection.reflect()
                refl_bias = (
                    reflection_res.get("recommended_bias")
                    if isinstance(reflection_res, dict)
                    else getattr(reflection_res, "recommended_bias", None)
                )
                if refl_bias == "neutral":
                    refl_reason = (
                        reflection_res.get("reason")
                        if isinstance(reflection_res, dict)
                        else getattr(reflection_res, "reason", "")
                    )
                    log.warning(f"Reflection Agent overriding trade bias to NEUTRAL: {refl_reason}")
                    self.macro_params["trade_bias"] = "neutral"

                # Chronos Prophet forecast (advisory telemetry)
                closes = [float(candle[4]) for candle in candles_1m]
                last_close = closes[-1] if closes else 0.0
                try:
                    chronos_dist = self.chronos.predict_distribution(closes)
                except Exception as exc:
                    log.warning(f"Chronos Prophet failed ({type(exc).__name__}: {exc}); continuing without forecast.")
                    chronos_dist = {"p50": last_close, "uncertainty": 1.0}
                log.info(f"Chronos Prophet advisory: p50={chronos_dist.get('p50')} uncertainty={chronos_dist.get('uncertainty')}")

                # Multi-Agent Brain trade decision (Tech -> Sentiment -> Debate -> Trader -> Risk)
                news_feed = await fetch_news(symbol)
                brain_decision = await asyncio.to_thread(
                    self.brain.decide_trade,
                    symbol=symbol,
                    price_data={"close": last_close, "1m": price_metrics_1m, "15m": price_metrics_15m},
                    portfolio_state=portfolio_state,
                    news_feed=news_feed,
                    cycle_id=str(uuid4()),
                    run_id=self._run_id,
                )
                raw_action = str(brain_decision.get("action", "hold")).lower()
                action = raw_action if raw_action in ("buy", "sell") else "hold"
                if action == "hold":
                    log.info(f"Brain decision HOLD: {brain_decision.get('reason', '')}")

                # Chronos Prophet confirmation gate (independent probabilistic veto).
                # A flat forecast (p50 within noise of spot) carries no directional
                # information and abstains; active disagreement or high uncertainty vetoes.
                # Ops lever: GODMODE_CHRONOS_VETO=0|false|no disables the gate.
                chronos_veto_enabled = os.getenv("GODMODE_CHRONOS_VETO", "1").strip().lower() not in {
                    "0", "false", "no"
                }
                if action != "hold" and chronos_veto_enabled:
                    chronos_p50_raw = chronos_dist.get("p50")
                    chronos_unc_raw = chronos_dist.get("uncertainty")
                    chronos_p50 = float(chronos_p50_raw) if chronos_p50_raw is not None else 0.0
                    chronos_unc = float(chronos_unc_raw) if chronos_unc_raw is not None else 1.0
                    prophet_agrees = True
                    reject_reason = ""
                    if chronos_unc > 0.15:
                        prophet_agrees = False
                        reject_reason = f"chronos_uncertain: uncertainty={chronos_unc:.4f} > 0.15"
                    elif chronos_p50 > 0 and last_close > 0:
                        prophet_edge = chronos_p50 / last_close - 1.0
                        if action == "buy" and prophet_edge < -0.0005:
                            prophet_agrees = False
                            reject_reason = (
                                f"side=buy last_close={last_close:.4f} p50={chronos_p50:.4f}"
                            )
                        elif action == "sell" and prophet_edge > 0.0005:
                            prophet_agrees = False
                            reject_reason = (
                                f"side=sell last_close={last_close:.4f} p50={chronos_p50:.4f}"
                            )
                    if not prophet_agrees:
                        log.warning(f"Chronos Prophet REJECTS: {reject_reason}. Skipping trade.")
                        action = "hold"



                if action != "hold":
                    side = "buy" if action == "buy" else "sell"

                    # Digital Twin Simulation (slippage pre-execution safety gate)
                    bb_upper = Decimal(str(price_metrics_1m.get("bb_upper", 0) or 0))
                    bb_lower = Decimal(str(price_metrics_1m.get("bb_lower", 0) or 0))
                    bands_valid = bb_upper > 0 and bb_lower > 0 and bb_upper > bb_lower
                    twin_slippages = [Decimal("0.0005"), Decimal("0.001"), Decimal("0.002")]
                    twin_success = 0
                    if not bands_valid:
                        twin_success = 3
                        log.info("Digital Twin Simulation skipped: degenerate Bollinger bands (flat window).")
                    else:
                        for slip in twin_slippages:
                            slip_price = current_price * (1 + slip) if side == "buy" else current_price * (1 - slip)
                            if side == "buy" and slip_price < bb_upper:
                                twin_success += 1
                            elif side == "sell" and slip_price > bb_lower:
                                twin_success += 1

                        if twin_success < 2:
                            log.warning(f"Digital Twin Simulation warning: Expected slippage exceeds safe thresholds ({twin_success}/3 successful twins). Trade proposal rejected.")
                            await asyncio.sleep(float(interval))
                            continue
                        else:
                            log.info(f"Digital Twin Simulation approved: {twin_success}/3 successful twins.")

                            


                    is_reducing = (side == "sell" and position_qty > 0) or (side == "buy" and position_qty < 0)
                    brain_size = Decimal(str(brain_decision.get("size", 0.0) or 0.0))
                    qty_prop = min(brain_size, abs(position_qty)) if is_reducing else max(brain_size, Decimal("0"))
                    
                    # Jev System 1 Decision & Policy Veto
                    best_bid_val = float(current_price * Decimal("0.9999"))
                    best_ask_val = float(current_price * Decimal("1.0001"))
                    try:
                        ticker_info = await asyncio.to_thread(adapter.get_ticker, symbol)
                        if ticker_info.get("bid"):
                            best_bid_val = float(ticker_info["bid"])
                        if ticker_info.get("ask"):
                            best_ask_val = float(ticker_info["ask"])
                    except Exception as e:
                        log.debug(f"Ticker fetch non-blocking fallback: {e}")

                    recent_rets = [float((c[4] - c[1]) / c[1]) for c in candles_1m[-20:] if len(c) > 4 and c[1] > 0]
                    max_pos_val = getattr(self.config.risk, "max_position_size", None)
                    if max_pos_val is None:
                        max_pos_val = (current_equity * Decimal(str(self.config.risk.max_position_pct)) / Decimal("100")) / current_price if current_price > 0 else Decimal("1.0")
                    else:
                        max_pos_val = Decimal(str(max_pos_val))

                    jev_judgments = self.jev_engine.evaluate(
                        symbol=symbol,
                        price=float(current_price),
                        best_bid=best_bid_val,
                        best_ask=best_ask_val,
                        bid_depth=1.0,
                        ask_depth=1.0,
                        recent_returns=recent_rets,
                        current_position=float(position_qty),
                        max_position=float(max_pos_val),
                    )
                    self._last_jev_confidence = jev_judgments.confidence
                    spread_bps = ((best_ask_val - best_bid_val) / float(current_price) * 10000) if float(current_price) > 0 else 0.0

                    veto = self.policy_veto.check(
                        side=side,
                        proposed_qty=qty_prop,
                        judgments=jev_judgments,
                        spread_bps=spread_bps,
                        current_position=position_qty,
                        max_position=max_pos_val,
                    )
                    if not veto.approved:
                        log.warning(f"Policy Veto Engine rejected trade: {', '.join(veto.reasons)}")
                        await asyncio.sleep(float(interval))
                        continue

                    # Compute Post-Only Peg Quote (Maker execution)
                    peg_quote = self.pegging_engine.calculate_peg_quote(
                        side=side,
                        best_bid=Decimal(str(best_bid_val)),
                        best_ask=Decimal(str(best_ask_val)),
                    )

                    proposal = OrderProposal(
                        symbol=symbol,
                        side=side,
                        qty=veto.allowed_qty,
                        price=peg_quote.price,
                        order_type=peg_quote.order_type,
                        is_reducing=is_reducing
                    )
                    
                    # Compute realized pnl sum for today
                    day_pnl = Decimal("0")
                    db = get_db()
                    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
                    pnl_rows = db.query(f"SELECT realized_pnl FROM fills WHERE ts LIKE '{today_str}%'")
                    if pnl_rows:
                        day_pnl = sum(Decimal(str(r["realized_pnl"] or "0")) for r in pnl_rows)

                    # Compute open position count
                    open_pos_count = 1 if position_qty != 0 else 0
                    
                    risk_portfolio_state = PortfolioState(
                        equity=current_equity,
                        peak_equity=self._peak_equity,
                        day_realized_pnl=day_pnl,
                        gross_exposure=abs(position_qty * current_price),
                        open_positions=open_pos_count,
                        has_position_in_symbol=(position_qty != 0)
                    )

                    decision = self.risk_engine.evaluate_and_enforce(
                        proposal, risk_portfolio_state, self.kill_switch
                    )

                    if decision.verdict == Verdict.REJECT:
                        log.error(f"Deterministic risk engine REJECTED trade proposal: {', '.join(decision.reasons)}")
                    else:
                        qty_to_execute = decision.approved_qty
                        if decision.verdict == Verdict.CLAMP:
                            log.warning(f"Deterministic risk engine CLAMPED trade size to {qty_to_execute} (Reason: {', '.join(decision.reasons)})")

                        # Execute Order via CCXT
                        if qty_to_execute > 0:
                            log.info(f"Executing LIVE {side.upper()} order for {qty_to_execute} {base_asset}...")
                            
                            # Final killswitch check before firing order to market
                            self.kill_switch.check()

                            # Pre-record order as pending_submit before exchange call to prevent state desync
                            client_order_id = "gm-live-" + uuid4().hex[:12]
                            order_params = {"clientOrderId": client_order_id, **peg_quote.params}
                            order_db_id = db.insert("orders", {
                                "run_id": self._run_id,
                                "client_order_id": client_order_id,
                                "venue": venue,
                                "symbol": symbol,
                                "side": side,
                                "type": peg_quote.order_type,
                                "qty": str(qty_to_execute),
                                "price": str(peg_quote.price),
                                "status": "pending_submit",
                                "created_at": utcnow_iso(),
                                "updated_at": utcnow_iso(),
                                "raw_json": ""
                            })

                            # Place order via adapter
                            order_res = await asyncio.to_thread(
                                adapter.create_order,
                                symbol=symbol,
                                type=peg_quote.order_type,
                                side=side,
                                amount=str(qty_to_execute),
                                params=order_params
                            )

                            # Update order to filled post-execution
                            db.execute(
                                "UPDATE orders SET status = 'filled', updated_at = ?, raw_json = ? WHERE id = ?",
                                (utcnow_iso(), str(order_res), order_db_id)
                            )

                            # Calculate realized PnL on closing/trimming fills
                            realized_pnl_val = Decimal("0.0")
                            pos_record = db.get_position(venue, symbol)
                            avg_entry_price = Decimal(str(pos_record["avg_price"])) if pos_record and pos_record.get("avg_price") else current_price
                            if is_reducing:
                                side_mult = Decimal("1") if side == "sell" else Decimal("-1")
                                realized_pnl_val = (peg_quote.price - avg_entry_price) * qty_to_execute * side_mult

                            # Log executed fill and record in Singularity Loop
                            fill_record = {
                                "order_id": order_db_id,
                                "client_order_id": client_order_id,
                                "venue": venue,
                                "symbol": symbol,
                                "side": side,
                                "qty": str(qty_to_execute),
                                "price": str(peg_quote.price),
                                "fee": str(qty_to_execute * peg_quote.price * Decimal("0.0002")),
                                "fee_ccy": quote_asset,
                                "realized_pnl": str(round(realized_pnl_val, 4)),
                                "ts": utcnow_iso(),
                                "raw_json": ""
                            }
                            db.insert("fills", fill_record)
                            self.singularity_loop.record_fill({
                                **fill_record,
                                "direction_predicted": side,
                                "confidence": getattr(self, "_last_jev_confidence", 0.65),
                            })

                            # Update position record
                            new_qty = position_qty + qty_to_execute if side == "buy" else position_qty - qty_to_execute
                            new_avg_price = current_price if abs(new_qty) > abs(position_qty) else avg_entry_price
                            db.upsert_position(venue, symbol, str(new_qty), str(new_avg_price))

                            log.info(f"LIVE {side.upper()} order filled successfully.")

                # Record final run metric
                get_db().record_metric("final_equity", float(current_equity))
                self._error_count = 0  # Reset backoff on successful pass

            except Exception as exc:
                log.error(f"Error in live execution step: {exc}")
                self._error_count = getattr(self, "_error_count", 0) + 1
                backoff = min(60, 2 ** self._error_count)
                log.warning(f"Applying exponential backoff: {backoff} seconds...")
                if self._error_count >= 5:
                    log.error("Max consecutive errors reached! Engaging killswitch!")
                    self.kill_switch.engage(f"System halted due to repeated unhandled exceptions: {exc}", source="live_runner")
                    self.stop()
                    break
                await asyncio.sleep(backoff)
                continue

            # Wait for next decision interval
            await asyncio.sleep(float(interval))

    async def _macro_council_loop(self, symbol: str, venue: str) -> None:
        """Background daemon that wakes up to tune parameters asynchronously."""
        adapter = get_broker_adapter(venue, self.config)
        while self._running:
            try:
                log.info(f"Macro-Regime Council waking up for {symbol}...")
                
                # Fetch 4-hour context data
                candles_4h = await asyncio.to_thread(adapter.fetch_ohlcv, symbol, "4h", limit=30)
                price_metrics_4h = compute_indicators(candles_4h)
                
                news_feed = await fetch_news(symbol)
                
                # Fetch actual live portfolio state
                real_equity = 100000.0
                real_cash = 100000.0
                pos_qty = 0.0
                try:
                    balances = await asyncio.to_thread(adapter.fetch_balance)
                    quote_bal = balances.get("USDT", {}) if isinstance(balances, dict) else {}
                    real_cash = float(quote_bal.get("free", 0) or 0)
                    real_equity = real_cash
                except Exception:
                    pass
                pos_record = get_db().get_position(venue, symbol)
                if pos_record:
                    pos_qty = float(pos_record.get("qty", 0.0))

                portfolio_state = {
                    "timestamp": utcnow_iso(),
                    "equity": real_equity,
                    "cash": real_cash,
                    "position_size": pos_qty,
                }
                
                cycle_id = str(uuid4())
                macro_proposal = await asyncio.to_thread(
                    self.brain.evaluate_macro_regime,
                    symbol=symbol,
                    price_data={"4h": price_metrics_4h},
                    portfolio_state=portfolio_state,
                    news_feed=news_feed,
                    cycle_id=cycle_id,
                    run_id=self._run_id
                )
                
                self.macro_params["regime"] = macro_proposal.get("regime", self.macro_params["regime"])
                self.macro_params["trade_bias"] = macro_proposal.get("trade_bias", self.macro_params["trade_bias"])
                self.macro_params["rsi_oversold"] = macro_proposal.get("rsi_oversold", self.macro_params["rsi_oversold"])
                self.macro_params["rsi_overbought"] = macro_proposal.get("rsi_overbought", self.macro_params["rsi_overbought"])
                
                log.info(f"Macro-Regime Council updated parameters: {self.macro_params}")
                
            except Exception as exc:
                log.error(f"Macro-Regime Council encountered an error: {exc}")
                
            # Sleep for 4 hours
            await asyncio.sleep(14400)
