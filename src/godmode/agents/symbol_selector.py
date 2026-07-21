"""SymbolSelector Agent — Ranked candidate screening via 2-stage backtest.

Every 6 hours: sweeps 30-40 candidate symbols, runs lightweight backtest,
ranks by performance metrics (Sharpe, drawdown, hit rate), returns top 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time


@dataclass
class SymbolScore:
    symbol: str
    venue: str
    sharpe: float
    max_dd: float
    hit_rate: float
    score: float
    last_evaluated: float = field(default_factory=time.time)


class SymbolSelector:
    """Scores candidate symbols via parameter-light backtest."""

    NSE_CANDIDATES = [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
        "ICICIBANK.NS", "TATAMOTORS.NS", "SBIN.NS", "BAJFINANCE.NS",
        "HINDUNILVR.NS", "BHARTIARTL.NS", "KOTAKBANK.NS", "ITC.NS",
        "WIPRO.NS", "MARUTI.NS", "SUNPHARMA.NS", "AXISBANK.NS",
        "ASIANPAINT.NS", "NESTLEIND.NS", "ULTRACEMCO.NS", "ADANIGREEN.NS",
    ]

    CRYPTO_CANDIDATES = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
        "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
        "MATIC/USDT", "DOT/USDT", "LINK/USDT", "UNI/USDT",
    ]

    def __init__(self, cache_ttl: float = 21600.0):
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}

    def rank_candidates(self, data_getter, ohlcv_func, n: int = 2) -> List[str]:
        now = time.time()
        if "selected" in self._cache and now - self._cache.get("_ts", 0) < self.cache_ttl:
            return self._cache.get("selected", [])

        scored: List[SymbolScore] = []
        all_candidates = self.NSE_CANDIDATES + self.CRYPTO_CANDIDATES

        for sym in all_candidates:
            try:
                candles = ohlcv_func(sym, limit=100)
                score = self._score(candles)
                if score:
                    scored.append(SymbolScore(symbol=sym, venue="crypto" if "/" in sym else "nse", **score))
            except Exception:
                continue

        scored.sort(key=lambda x: x.score, reverse=True)
        top_n = [s.symbol for s in scored[:n]]
        self._cache = {"selected": top_n, "_ts": now}
        return top_n

    @staticmethod
    def _score(candles: List[List[float]]) -> Optional[Dict[str, float]]:
        if len(candles) < 50:
            return None
        closes = [c[4] if len(c) > 4 else c[3] for c in candles]
        log_returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))
        ]
        if len(log_returns) < 10:
            return None
        mean_ret = sum(log_returns) / len(log_returns)
        variance = sum((r - mean_ret) ** 2 for r in log_returns) / len(log_returns)
        std = variance**0.5
        sharpe = mean_ret / std if std > 0 else 0.0

        peak = closes[0]
        max_dd = 0.0
        for c in closes:
            peak = max(peak, c)
            dd = (c - peak) / peak if peak > 0 else 0
            max_dd = min(max_dd, dd)

        hits = sum(1 for r in log_returns if r > 0)
        hit_rate = hits / len(log_returns) if log_returns else 0.0

        score = sharpe - 3 * abs(max_dd) + hit_rate * 1.5
        return {
            "sharpe": round(sharpe, 3),
            "drawdown": round(max_dd, 4),
            "hit_rate": round(hit_rate, 3),
            "score": round(score, 4),
        }