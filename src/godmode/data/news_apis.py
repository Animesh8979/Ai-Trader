"""Real-world news API aggregator — replaces hardcoded mock headlines.

Supports Finnhub (60 calls/min free), NewsAPI (100 req/day free),
CryptoPanic (free), and Yahoo Finance as fallback.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import ssl
from typing import Any, Dict, List, Optional

from godmode.core.logging import get_logger

log = get_logger("data.news_apis")

_FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
_NEWSAPI_KEY = os.environ.get("NEWSAPI_API_KEY", "")
_CRYPTOPANIC_KEY = os.environ.get("CRYPTOPANIC_API_KEY", "")


def _fetch_json(url: str, timeout: float = 3.5, extra_headers: Optional[Dict[str, str]] = None) -> Optional[Any]:
    try:
        ctx = ssl.create_default_context()
        headers = {"User-Agent": "GodmodeTerminal/4.0"}
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.debug(f"News fetch failed for {url[:60]}: {e}")
        return None


def fetch_international_news() -> List[Dict[str, Any]]:
    """Fetch real international/crypto news headlines from free APIs."""
    headlines: List[Dict[str, Any]] = []

    if _FINNHUB_KEY:
        data = _fetch_json("https://finnhub.io/api/v1/news?category=general", extra_headers={"X-Finnhub-Token": _FINNHUB_KEY})
        if data and isinstance(data, list):
            for item in data[:8]:
                headlines.append({
                    "source": item.get("source", "FINNHUB"),
                    "headline": item.get("headline", ""),
                    "sentiment": "NEUTRAL",
                    "ts": "FINNHUB",
                })

    if _CRYPTOPANIC_KEY:
        data = _fetch_json(f"https://cryptopanic.com/api/v1/posts/?auth_token={_CRYPTOPANIC_KEY}&public=true&filter=trending")
        if data and "results" in data:
            for item in data["results"][:8]:
                sentiment_map = {"positive": "BULLISH", "negative": "BEARISH", "neutral": "NEUTRAL"}
                currencies = item.get("currencies") or [{}]
                if not currencies:
                    currencies = [{}]
                headlines.append({
                    "source": "CRYPTOPANIC",
                    "headline": item.get("title", ""),
                    "sentiment": sentiment_map.get(currencies[0].get("status", "neutral"), "NEUTRAL"),
                    "ts": time.time(),
                })

    if _NEWSAPI_KEY:
        data = _fetch_json("https://newsapi.org/v2/top-headlines?category=business&language=en&pageSize=5", extra_headers={"X-Api-Key": _NEWSAPI_KEY})
        if data and "articles" in data:
            for article in data["articles"][:5]:
                headlines.append({
                    "source": article.get("source", {}).get("name", "NEWSAPI"),
                    "headline": article.get("title", ""),
                    "sentiment": "NEUTRAL",
                    "ts": article.get("publishedAt", ""),
                })

    return headlines


def fetch_indian_news() -> List[Dict[str, Any]]:
    """Fetch Indian market news from NewsAPI with India domain filtering."""
    headlines: List[Dict[str, Any]] = []

    if _NEWSAPI_KEY:
        data = _fetch_json("https://newsapi.org/v2/top-headlines?country=in&category=business&pageSize=5", extra_headers={"X-Api-Key": _NEWSAPI_KEY})
        if data and "articles" in data:
            for article in data["articles"]:
                headlines.append({
                    "source": article.get("source", {}).get("name", "NEWSAPI IN"),
                    "headline": article.get("title", ""),
                    "sentiment": "NEUTRAL",
                    "ts": article.get("publishedAt", ""),
                })

    return headlines