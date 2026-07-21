"""Master Autopilot Swarm Core for Godmode Terminal.

Zero-Knowledge Autonomous Trading Orchestrator:
- Integrates Live Market Data (NSE & Crypto)
- Sub-Second News Hose Feed
- Quant ML Alpha (KAMA, Supertrend, Markov Regimes)
- TensorTrade RL Strategy Discovery
- Purged Walk-Forward Evaluator (Deflated Sharpe Ratio)
- Shoonya Zero-Brokerage NSE Execution Adapter & CCXT Paper Engine
"""

from __future__ import annotations

import asyncio
import ssl
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from godmode.core.logging import get_logger
from godmode.core.timeutil import utcnow_iso
from godmode.data.live_intelligence import LiveIntelligenceFeed
from godmode.execution.shoonya_nse import ShoonyaNSEAdapter
from godmode.strategies.quant_ml_alpha import QuantMLAlphaEngine
from godmode.strategies.rl_tensortrade import TensorTradeRLEnvironment
from godmode.strategies.walk_forward_evaluator import QuantitativeStrategyEvaluator

log = get_logger("autopilot_swarm")


class AutopilotSwarmEngine:
    """Master Autonomous Trading Engine operating zero-knowledge autopilot execution."""

    def __init__(self, paper: bool = True) -> None:
        self.paper = paper
        self.shoonya_adapter = ShoonyaNSEAdapter(paper=paper)
        self.intelligence = LiveIntelligenceFeed(cache_ttl_seconds=3.0)
        self.is_running = False

    def run_market_scan(self, symbol: str = "RELIANCE.NS") -> Dict[str, Any]:
        """Perform institutional market scan, quant regime detection, and signal generation.

        BRUTAL HONESTY: If symbol is a crypto pair (BTCUSDT etc.), fetch via
        Binance public REST endpoints. If NSE, fetch via Shoonya/Yahoo.
        Returns real prices only — refuses to return fake values when the
        underlying fetch fails.
        """
        is_crypto = (
            symbol.upper().endswith("USDT")
            or "/" in symbol
            or symbol.upper().endswith("BTC")
        )

        if is_crypto:
            price, ohlcv = self._fetch_crypto_market(symbol)
            if price <= 0:
                return {
                    "symbol": symbol, "ltp": 0.0, "error": "crypto_fetch_failed",
                    "signal": "HOLD", "executed_order": None,
                    "timestamp": time.time(),
                }
        else:
            price = float(self.shoonya_adapter.fetch_price(symbol))
            ohlcv = self.shoonya_adapter.fetch_ohlcv(symbol, limit=30)

        # HONESTY: if OHLCV fetch failed, we cannot truthfully compute indicators
        # on fabricated candles. Skip straight to HOLD and surface the fetch failure.
        if not ohlcv or ohlcv[-1][4] <= 0:
            return {
                "symbol": symbol, "ltp": float(price),
                "error": "ohlcv_fetch_empty",
                "signal": "HOLD", "executed_order": None,
                "timestamp": time.time(),
                "kama": None, "supertrend": None, "regime": None,
            }

        closes = [c[4] for c in ohlcv]
        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]

        from godmode.data.alpha_zoo import AlphaZoo
        from godmode.strategies.hmm_regime import RegimeDetector
        import polars as pl

        # 1. Quant Indicators (KAMA/Supertrend)
        kama = QuantMLAlphaEngine.calculate_kama(closes, period=5)
        st = QuantMLAlphaEngine.calculate_supertrend(highs, lows, closes, period=5)

        # 2. Institutional ML Pivot (Alpha Zoo & Regime Detection)
        candles = ohlcv if is_crypto else self.shoonya_adapter.fetch_ohlcv(symbol, limit=200)
        if candles:
            df = pl.DataFrame(candles, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row")
            df_alpha = AlphaZoo.process_all(df)
            detector = RegimeDetector(df_alpha)
            df_regime = detector.apply_regime_labels()
            current_regime = df_regime["market_regime"].tail(1).item() if len(df_regime) > 0 else 0
            optimal_strategy = RegimeDetector.get_strategy_for_regime(current_regime)
        else:
            current_regime = 0
            optimal_strategy = "Trend_Following_Long"

        # 3. Deflated Sharpe & Purged Validation (Legacy compatibility).
        # HONESTY: empty/honest returns when only 1 candle — run_purged_walk_forward
        # will report not_statistically_robust on an empty series, which is the
        # truthful verdict. NEVER inject fabricated returns like [0.001] as a
        # placeholder (the previous code did exactly that).
        if len(closes) > 1:
            returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
        else:
            returns = []
        eval_res = QuantitativeStrategyEvaluator.run_purged_walk_forward(returns)

        # 4. Decision Logic (Governed by Regime)
        signal = "HOLD"
        if optimal_strategy == "Trend_Following_Long" and price > kama:
            signal = "BUY"
        elif optimal_strategy == "Trend_Following_Short":
            signal = "SELL"
        elif optimal_strategy == "Mean_Reversion_Band_Trading":
            signal = "HOLD"

        # 5. Execute — only NSE via paper Shoonya, crypto never executes (paper marker only)
        order_info: Optional[Dict[str, Any]] = None
        if signal in ("BUY", "SELL"):
            # Dynamic Kelly Criterion sizing
            p_val = eval_res.get("deflated_sharpe_p_value", 1.0)
            confidence = max(0.0, 1.0 - p_val)
            half_kelly = confidence * 0.5
            max_capital = 100000.0  # Max capital limit (e.g., 100k)
            dynamic_qty = max(1, int((max_capital * half_kelly) / price)) if price > 0 else 10

            if is_crypto:
                order_info = {
                    "id": f"PAPER_CRYPTO_{uuid4().hex[:8].upper()}",
                    "symbol": symbol, "side": signal.lower(),
                    "price": str(price), "qty": "0.01",
                    "status": "FILLED_PAPER", "venue": "BINANCE_PAPER",
                    "ts": utcnow_iso(),
                }
            else:
                order_info = self.shoonya_adapter.create_order(
                    symbol=symbol, type="MARKET", side=signal.lower(), amount=str(dynamic_qty),
                )

        return {
            "symbol": symbol,
            "ltp": price,
            "kama": kama,
            "supertrend": st,
            "regime": current_regime,
            "signal": signal,
            "statistically_robust": eval_res.get("is_statistically_robust", False),
            "deflated_sharpe_p_val": eval_res.get("deflated_sharpe_p_value", 0.0),
            "executed_order": order_info,
            "timestamp": time.time(),
        }

    def _fetch_crypto_market(self, symbol: str) -> tuple[float, list]:
        """Fetch LTP + 5m OHLCV from Binance public REST endpoints (no key required).
        Honesty: returns (0.0, []) on failure rather than fake numbers.
        """
        import json as _json
        import urllib.request as _u

        clean = symbol.replace("/", "").upper()
        try:
            ctx = ssl.create_default_context()
            req = _u.Request(
                f"https://api.binance.com/api/v3/ticker/price?symbol={clean}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with _u.urlopen(req, timeout=4.0, context=ctx) as r:
                price = float(_json.loads(r.read().decode())["price"])
        except Exception as exc:
            log.warning(f"Crypto price fetch failed for {symbol}: {exc}")
            return 0.0, []

        candles: list = []
        try:
            ctx = ssl.create_default_context()
            req = _u.Request(
                f"https://api.binance.com/api/v3/klines?symbol={clean}&interval=5m&limit=200",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with _u.urlopen(req, timeout=6.0, context=ctx) as r:
                rows = _json.loads(r.read().decode())
            for row in rows:
                candles.append([
                    int(row[0]),
                    float(row[1]),   # open
                    float(row[2]),   # high
                    float(row[3]),   # low
                    float(row[4]),   # close
                    float(row[5]),   # volume
                ])
        except Exception as exc:
            log.warning(f"Crypto klines fetch failed for {symbol}: {exc}")

        return price, candles

    def run_full_diagnostic(self) -> Dict[str, Any]:
        """Run complete institutional diagnostic across Indian and Global assets."""
        nifty_res = self.run_market_scan("RELIANCE.NS")
        crypto_res = self.run_market_scan("BTCUSDT")
        intl_intel = self.intelligence.get_international_intelligence()

        return {
            "status": "OPERATIONAL",
            "indian_equity_scan": nifty_res,
            "crypto_scan": crypto_res,
            "fear_and_greed": intl_intel.get("fear_and_greed", {}),
            "paper_inr_balance": float(self.shoonya_adapter.free_balance("INR")),
        }
