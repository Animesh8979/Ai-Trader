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
from godmode.agents.brain import MultiAgentBrain
from godmode.risk.engine import RiskEngine, OrderProposal, PortfolioState, Verdict

log = get_logger("execution.live_runner")


async def fetch_news(symbol: str) -> list[str]:
    """Fetch live news from Finnhub or fallback to dummy strings."""
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return [
            f"Dummy: Macroeconomic outlook remains stable amid interest rate expectations.",
            f"Dummy: Trading activity signals high volatility indicators for {symbol}.",
            f"Dummy: General consensus points to consolidation phase for {symbol}.",
        ]
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://finnhub.io/api/v1/news?category=crypto&token={api_key}"
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [item["headline"] for item in data[:3]]
                else:
                    return [f"News API returned status {resp.status}."]
    except Exception as exc:
        log.error(f"Failed to fetch news: {exc}")
        return ["News feed connection error."]

def compute_indicators(candles: list[list]) -> dict[str, float]:
    """Helper to compute fast/slow EMA, RSI, VWAP, and BBs using Polars (Rust)."""
    df = pl.DataFrame(candles, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row")
    
    # EMA
    df = df.with_columns([
        pl.col("close").ewm_mean(span=10, adjust=False).alias("ema_fast"),
        pl.col("close").ewm_mean(span=20, adjust=False).alias("ema_slow"),
    ])
    
    # RSI
    delta = pl.col("close").diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0).rolling_mean(window_size=14)
    loss = pl.when(delta < 0).then(-delta).otherwise(0).rolling_mean(window_size=14)
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    df = df.with_columns(rsi.alias("rsi"))

    # Bollinger Bands
    std = pl.col("close").rolling_std(window_size=20)
    df = df.with_columns([
        (pl.col("ema_slow") + (std * 2)).alias("bb_upper"),
        (pl.col("ema_slow") - (std * 2)).alias("bb_lower")
    ])

    # VWAP
    typical_price = (pl.col("high") + pl.col("low") + pl.col("close")) / 3
    vwap = (typical_price * pl.col("volume")).cum_sum() / (pl.col("volume").cum_sum() + 1e-9)
    df = df.with_columns(vwap.alias("vwap"))
    
    # Pivot Points
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
        "pivot": safe_float(last["pivot"], c),
        "r1": safe_float(last["r1"], c),
        "s1": safe_float(last["s1"], c),
    }


class LiveRunner:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or load_config()
        self.kill_switch = get_kill_switch()
        self.risk_engine = RiskEngine()
        self.brain = MultiAgentBrain()
        self._running = False
        self._run_id: Optional[int] = None
        self._peak_equity: Optional[Decimal] = None

    def start(self, note: str = "Live trading loop started") -> None:
        """Start the live trading thread pool/loop."""
        if self._running:
            log.warning("Live trading loop is already running.")
            return
        
        self._running = True
        self._run_id = get_db().start_run(mode=self.config.mode, note=note)
        log.info(f"Started live execution run {self._run_id} in {self.config.mode} mode.")

        # Spawn loop task
        asyncio.create_task(self._main_loop())

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
        
        adapter = CryptoCcxtAdapter(venue=venue, config=self.config)
        
        while self._running:
            try:
                # 1. Enforce physical stop switch
                if self.kill_switch.is_halted():
                    log.warning("Trading is HALTED. Skipping execution cycle.")
                    await asyncio.sleep(15.0)
                    continue

                log.info(f"Running execution tick for {symbol} on {venue}...")
                
                # 2. Fetch live data concurrently for 1m and 15m
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
                
                # Fetch balance and map base coin as position size
                balance = await asyncio.to_thread(adapter.fetch_balance)
                cash = Decimal(str(balance.get(quote_asset, {}).get("free", 0.0)))
                position_qty = Decimal(str(balance.get(base_asset, {}).get("total", 0.0)))
                
                current_equity = cash + (position_qty * current_price)
                if self._peak_equity is None or current_equity > self._peak_equity:
                    self._peak_equity = current_equity

                portfolio_state = {
                    "timestamp": utcnow_iso(),
                    "equity": float(current_equity),
                    "cash": float(cash),
                    "position_size": float(position_qty),
                }

                # 3. Formulate sentiment headlines
                news_feed = await fetch_news(symbol)

                # 4. Query the debate brain
                cycle_id = str(uuid4())
                proposal_data = await asyncio.to_thread(
                    self.brain.decide_trade,
                    symbol=symbol,
                    price_data=price_metrics,
                    portfolio_state=portfolio_state,
                    news_feed=news_feed,
                    cycle_id=cycle_id,
                    run_id=self._run_id
                )

                # 5. Enforce deterministic Risk Engine
                action = proposal_data.get("action", "hold").lower()
                if action != "hold":
                    qty_prop = Decimal(str(proposal_data.get("size", 0.0)))
                    
                    # Convert action to side and determine if reducing
                    side = "buy" if action == "buy" else "sell"
                    is_reducing = (side == "sell" and position_qty > 0) or (side == "buy" and position_qty < 0)
                    
                    proposal = OrderProposal(
                        symbol=symbol,
                        side=side,
                        qty=qty_prop,
                        price=current_price,
                        order_type="market",
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

                            # Place order on sandbox testnet
                            client_order_id = "gm-live-" + uuid4().hex[:12]
                            order_res = await asyncio.to_thread(
                                adapter.exchange.create_order,
                                symbol=symbol,
                                type="market",
                                side=side,
                                amount=str(qty_to_execute),
                                params={"clientOrderId": client_order_id}
                            )
                            
                            # Log details to SQLite database
                            order_db_id = db.insert("orders", {
                                "run_id": self._run_id,
                                "client_order_id": client_order_id,
                                "venue": venue,
                                "symbol": symbol,
                                "side": side,
                                "type": "market",
                                "qty": str(qty_to_execute),
                                "price": str(current_price),
                                "status": "filled",
                                "created_at": utcnow_iso(),
                                "updated_at": utcnow_iso(),
                                "raw_json": str(order_res)
                            })

                            # Log executed fill
                            db.insert("fills", {
                                "order_id": order_db_id,
                                "client_order_id": client_order_id,
                                "venue": venue,
                                "symbol": symbol,
                                "side": side,
                                "qty": str(qty_to_execute),
                                "price": str(current_price),
                                "fee": str(qty_to_execute * current_price * Decimal("0.001")),
                                "fee_ccy": quote_asset,
                                "realized_pnl": "0.0",
                                "ts": utcnow_iso()
                            })

                            # Update position record
                            new_qty = position_qty + qty_to_execute if side == "buy" else position_qty - qty_to_execute
                            db.upsert_position(venue, symbol, str(new_qty), str(current_price))

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
