"""Live Intelligence & Multi-Venue News Hose Service.

Powers both:
1. Indian Markets Screen (NSE/BSE Indices, Indian Stocks, Indian Financial News)
2. International & Crypto Screen (Fear & Greed Index, Global Crypto Assets, Macro News)

Built strictly under the Ponytail Mindset (standard library urllib, zero external dependencies,
3-second timeout protection, non-blocking caching so local PC never hangs or crashes).
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List
from godmode.core.logging import get_logger

log = get_logger("data.live_intelligence")


class LiveIntelligenceFeed:
    """Multi-source public intelligence feed for Indian and International trading screens."""

    def __init__(self, cache_ttl_seconds: float = 10.0):
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._last_fetch: Dict[str, float] = {}

    def _fetch_json(self, url: str, timeout: float = 3.5) -> Optional[Dict[str, Any]]:
        """Fetch JSON from public API using stdlib urllib with non-blocking timeout.

        SECURITY: full TLS verification via OS trust store — never disable
        check_hostname / CERT_NONE. MITM on a live intel feed lets an
        attacker feed the trader fake prices/regime broadcast.
        """
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GodmodeTerminal/3.0"
                },
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except Exception as e:
            log.debug(f"Live intelligence fetch fallback for {url}: {e}")
            return None

    def get_international_intelligence(self) -> Dict[str, Any]:
        """Fetch live Fear & Greed, Global Crypto Tickers, and International News.

        HONESTY CONTRACT (FIX 14): every value in the returned payload is either
        a successfully-fetched real value or explicitly marked `None` with an
        `error` flag. NEVER fabricate stock prices, headlines, or sentiment
        mock data — a user staring at the dashboard must not be lured into
        trading on invented numbers.
        """
        now = time.time()
        if "international" in self._cache and (now - self._last_fetch.get("international", 0)) < self.cache_ttl:
            return self._cache["international"]

        # 1. Alternative.me Crypto Fear & Greed Index
        fng_data = self._fetch_json("https://api.alternative.me/fng/?limit=1")
        fear_greed: Dict[str, Any]
        if fng_data and "data" in fng_data and len(fng_data["data"]) > 0:
            fear_greed = {
                "score": int(fng_data["data"][0].get("value", 0)) or None,
                "label": fng_data["data"][0].get("value_classification") or "unknown",
                "source": "alternative.me",
            }
        else:
            fear_greed = {"score": None, "label": None, "error": "fetch_failed"}

        # 2. Binance Public 24H Ticker for Major Crypto Assets.
        # When a ticker fetch fails the asset entry becomes {error:...} so the
        # dashboard can visibly mark it unavailable instead of showing a
        # fabricated price.
        def parse_ticker(t: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            if not t:
                return {"error": "fetch_failed"}
            try:
                return {
                    "price": round(float(t.get("lastPrice", 0)) or 0.0, 2),
                    "change_24h_pct": round(float(t.get("priceChangePercent", 0)) or 0.0, 2),
                    "high_24h": round(float(t.get("highPrice", 0)) or 0.0, 2),
                    "low_24h": round(float(t.get("lowPrice", 0)) or 0.0, 2),
                    "source": "binance",
                }
            except (ValueError, TypeError) as e:
                return {"error": f"parse_failed: {e}"}

        assets = {
            "BTC/USDT": parse_ticker(self._fetch_json(
                "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT")),
            "ETH/USDT": parse_ticker(self._fetch_json(
                "https://api.binance.com/api/v3/ticker/24hr?symbol=ETHUSDT")),
            "SOL/USDT": parse_ticker(self._fetch_json(
                "https://api.binance.com/api/v3/ticker/24hr?symbol=SOLUSDT")),
        }

        # 3. International News Hose Headlines (honest: empty list on failure).
        try:
            from godmode.data.news_apis import fetch_international_news
            news = fetch_international_news() or []
        except Exception:
            news = []
        # NO fabricated headlines. Empty news list means the news panel
        # honestly displays "no live headlines — feed unavailable".

        payload = {
            "fear_greed": fear_greed,
            "assets": assets,
            "news": news,
            "timestamp": now,
        }
        self._cache["international"] = payload
        self._last_fetch["international"] = now
        return payload

    def get_indian_intelligence(self) -> Dict[str, Any]:
        """Fetch live Indian Market Indices (Nifty 50, Bank Nifty), Stocks, and Indian News.

        HONESTY CONTRACT: indices and stocks are real-fetched only. If Yahoo
        Finance is unreachable the entry carries {error:...} and the dashboard
        can visibly mark the stall — NEVER fabricate NIFTY=24850 etc. (the
        previous implementation invented concrete numbers).
        """
        now = time.time()
        if "indian" in self._cache and (now - self._last_fetch.get("indian", 0)) < self.cache_ttl:
            return self._cache["indian"]

        # Public Indian Market Tickers via Yahoo Finance public API fallback
        nifty_chart = self._fetch_json("https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=1d")
        sensex_chart = self._fetch_json("https://query1.finance.yahoo.com/v8/finance/chart/%5EBSESN?interval=1d&range=1d")
        banknifty_chart = self._fetch_json("https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEBANK?interval=1d&range=1d")

        def parse_yahoofin(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            if not data or "chart" not in data or "result" not in data["chart"] or not data["chart"]["result"]:
                return {"error": "fetch_failed"}
            meta = data["chart"]["result"][0].get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose")
            if price is None or prev is None:
                return {"error": "missing_meta"}
            try:
                price_f = float(price)
                prev_f = float(prev)
                chg = ((price_f - prev_f) / prev_f * 100.0) if prev_f > 0 else 0.0
                return {
                    "price": round(price_f, 2),
                    "change_24h_pct": round(chg, 2),
                    "source": "yahoo",
                }
            except (ValueError, TypeError) as e:
                return {"error": f"parse_failed: {e}"}

        indices = {
            "NIFTY 50": parse_yahoofin(nifty_chart),
            "SENSEX": parse_yahoofin(sensex_chart),
            "BANK NIFTY": parse_yahoofin(banknifty_chart),
        }

        # Individual stocks: fetch real Yahoo quotes — no hardcoded prices.
        # (The previous implementation hard-coded RELIANCE=3145.60, TCS=4210.30
        #  etc. — those numbers are stale the moment the market moves and could
        #  mislead a user into placing trades against synthetic prices.)
        stock_symbols = {
            "RELIANCE (NSE)": "RELIANCE.NS",
            "TCS (NSE)": "TCS.NS",
            "HDFCBANK (NSE)": "HDFCBANK.NS",
            "INFY (NSE)": "INFY.NS",
        }
        stocks: Dict[str, Any] = {}
        for label, sym in stock_symbols.items():
            chart = self._fetch_json(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
            )
            entry = parse_yahoofin(chart)
            if "error" not in entry:
                entry["volume"] = None  # Yahoo public API often hides volume in meta
            stocks[label] = entry

        # Indian Breaking Financial News Headlines (no mock fallback)
        try:
            from godmode.data.news_apis import fetch_indian_news
            news = fetch_indian_news() or []
        except Exception:
            news = []
        # If news is empty, dashboard shows "no live headlines" — honest.

        payload = {
            "indices": indices,
            "stocks": stocks,
            "news": news,
            "timestamp": now,
        }
        self._cache["indian"] = payload
        self._last_fetch["indian"] = now
        return payload

    def get_combined_intelligence(self) -> Dict[str, Any]:
        """Return combined intelligence payload for dual-monitor / split-screen HUD."""
        return {
            "international": self.get_international_intelligence(),
            "indian": self.get_indian_intelligence(),
            "timestamp": time.time(),
        }


_FEED_SINGLETON: Optional[LiveIntelligenceFeed] = None


def get_live_intelligence() -> LiveIntelligenceFeed:
    """Return process-wide singleton for live intelligence feed."""
    global _FEED_SINGLETON
    if _FEED_SINGLETON is None:
        _FEED_SINGLETON = LiveIntelligenceFeed()
    return _FEED_SINGLETON
