"""Free RSS news ingestion with importance scoring (no paid APIs).

importance = 0.55*severity + 0.20*source_tier + 0.15*corroboration + 0.10*recency

- severity: keyword heuristics over the headline (hack/bankruptcy > surge/rally > routine)
- source_tier: credibility of the feed (1 = wire/mainstream, 2 = major crypto-native, 3 = blog)
- corroboration: same/similar story reported by multiple distinct sources
- recency: exponential decay with a 12h half-life; unknown dates score a neutral 0.5

The network layer is injectable and fails soft: any feed error yields no items
from that feed, never an exception into the caller.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional

from godmode.core.url_guard import validate_public_http_url

WEIGHTS = {"severity": 0.55, "tier": 0.20, "corroboration": 0.15, "recency": 0.10}

BASE_SEVERITY = 0.35
MID_SEVERITY = 0.70
HIGH_SEVERITY = 1.00

HIGH_SEVERITY_KEYWORDS = [
    "hack", "hacked", "hacking", "exploit", "breach", "stolen", "drain",
    "bankrupt", "bankruptcy", "insolven", "default", "fraud", "lawsuit",
    "sues", "charged", "arrest", "sanction", "emergency", "collapse",
    "depeg", "liquidat",
]
MID_SEVERITY_KEYWORDS = [
    "crash", "plunge", "plunges", "tumble", "sink", "surge", "surges",
    "rally", "record high", "all-time", "ath", "halving", "approval",
    "approved", "launch", "ban", "bans", "outage", "inflation", "rate cut",
    "rate hike",
]

SIMILARITY_THRESHOLD = 0.6
RECENCY_HALF_LIFE_HOURS = 12.0

_ATOM = "{http://www.w3.org/2005/Atom}"

DEFAULT_FEEDS: List[Dict[str, Any]] = [
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "tier": 2},
    {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss", "tier": 2},
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "tier": 1},
]


def tier_credibility(tier: int) -> float:
    """Map source tier (1=best) to a 0..1 credibility score."""
    return {1: 1.0, 2: round(2 / 3, 4), 3: round(1 / 3, 4)}.get(int(tier), round(1 / 3, 4))


def severity_score(text: str) -> float:
    t = (text or "").lower()
    if any(k in t for k in HIGH_SEVERITY_KEYWORDS):
        return HIGH_SEVERITY
    if any(k in t for k in MID_SEVERITY_KEYWORDS):
        return MID_SEVERITY
    return BASE_SEVERITY


def recency_score(published_epoch: Optional[float], now: float) -> float:
    """Exponential decay; half-life 12h. Unknown publish time -> neutral 0.5."""
    if published_epoch is None:
        return 0.5
    age_hours = max(0.0, now - published_epoch) / 3600.0
    return round(0.5 ** (age_hours / RECENCY_HALF_LIFE_HOURS), 4)


def _parse_date(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)  # RFC 822 (RSS pubDate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        pass
    try:
        iso = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)  # RFC 3339 (Atom updated/published)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def parse_feed(xml_text: str) -> List[Dict[str, Any]]:
    """Parse RSS 2.0 or Atom XML into item dicts. Fails soft to []."""
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return []

    items: List[Dict[str, Any]] = []

    def _clean(text: Optional[str]) -> str:
        return re.sub(r"\s+", " ", text).strip() if text else ""

    if root.tag == f"{_ATOM}feed":
        entries = root.findall(f"{_ATOM}entry")
        for e in entries:
            link_el = e.find(f"{_ATOM}link")
            items.append({
                "title": _clean(e.findtext(f"{_ATOM}title")),
                "link": (link_el.get("href") if link_el is not None else "") or "",
                "summary": _clean(e.findtext(f"{_ATOM}summary")),
                "published_epoch": _parse_date(
                    e.findtext(f"{_ATOM}updated") or e.findtext(f"{_ATOM}published")
                ),
            })
    else:
        for it in root.iter("item"):
            items.append({
                "title": _clean(it.findtext("title")),
                "link": _clean(it.findtext("link")),
                "summary": _clean(it.findtext("description")),
                "published_epoch": _parse_date(it.findtext("pubDate")),
            })

    return [i for i in items if i["title"]]


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def title_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def group_correlated(items: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Greedy clustering of near-duplicate headlines across sources."""
    clusters: List[List[Dict[str, Any]]] = []
    ordered = sorted(items, key=lambda x: -(x.get("severity") or 0.0))
    for item in ordered:
        placed = False
        for cluster in clusters:
            rep = cluster[0]
            if title_similarity(item["title"], rep["title"]) >= SIMILARITY_THRESHOLD:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    return clusters


def score_items(items: List[Dict[str, Any]], now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Attach severity/tier/recency/corroboration components and importance."""
    now = now if now is not None else time.time()
    enriched: List[Dict[str, Any]] = []
    for it in items:
        e = dict(it)
        e["severity"] = severity_score(e.get("title", ""))
        e["tier_score"] = tier_credibility(e.get("tier", 3))
        e["recency"] = recency_score(e.get("published_epoch"), now)
        enriched.append(e)

    scored: List[Dict[str, Any]] = []
    for cluster in group_correlated(enriched):
        rep = cluster[0]
        distinct_sources = len({m.get("source", "?") for m in cluster})
        corroboration = min(max(distinct_sources - 1, 0) / 2.0, 1.0)
        importance = round(
            WEIGHTS["severity"] * rep["severity"]
            + WEIGHTS["tier"] * rep["tier_score"]
            + WEIGHTS["corroboration"] * corroboration
            + WEIGHTS["recency"] * rep["recency"],
            4,
        )
        scored.append({
            "title": rep.get("title", ""),
            "link": rep.get("link", ""),
            "source": rep.get("source", "unknown"),
            "published_epoch": rep.get("published_epoch"),
            "importance": importance,
            "components": {
                "severity": rep["severity"],
                "tier": rep["tier_score"],
                "corroboration": round(corroboration, 4),
                "recency": rep["recency"],
            },
            "member_count": len(cluster),
            "corroborating_sources": sorted({
                m.get("source", "?") for m in cluster
                if m.get("source", "?") != rep.get("source", "?")
            }),
        })

    scored.sort(key=lambda x: -x["importance"])
    return scored


HttpGet = Callable[..., str]


class NewsMonitor:
    """Fetches all configured feeds, scores, dedups, ranks. Fails soft."""

    def __init__(
        self,
        feeds: Optional[List[Dict[str, Any]]] = None,
        http_get: Optional[HttpGet] = None,
    ):
        self.feeds = feeds if feeds is not None else DEFAULT_FEEDS
        self._http_get = http_get or self._default_http_get

    @staticmethod
    def _default_http_get(url: str, timeout: float = 8.0) -> str:
        import httpx
        resp = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "godmode-monitor/4.0 (+paper-trading-research)"},
        )
        resp.raise_for_status()
        return resp.text

    def fetch_feed(self, feed: Dict[str, Any]) -> List[Dict[str, Any]]:
        # SSRF guard (static): reject non-http(s) schemes, credentialed URLs,
        # localhost-style hosts and private/link-local literal IPs before any
        # network call. Raises -> caught by fetch_all's fail-soft wrapper.
        validate_public_http_url(feed["url"])
        text = self._http_get(feed["url"])
        items = parse_feed(text)
        for it in items:
            it["source"] = feed.get("name", "unknown")
            it["tier"] = feed.get("tier", 3)
        return items

    def fetch_all(self, max_per_feed: int = 20) -> List[Dict[str, Any]]:
        """Fetch all feeds concurrently (thread pool), score, dedup, rank."""
        collected: List[Dict[str, Any]] = []
        from concurrent.futures import ThreadPoolExecutor

        def _safe_fetch(feed: Dict[str, Any]) -> List[Dict[str, Any]]:
            try:
                return self.fetch_feed(feed)[:max_per_feed]
            except Exception:
                return []  # fail soft: skip dead feeds entirely

        with ThreadPoolExecutor(max_workers=max(1, len(self.feeds))) as pool:
            for result in pool.map(_safe_fetch, self.feeds):
                collected.extend(result)
        return score_items(collected)
