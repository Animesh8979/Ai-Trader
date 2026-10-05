"""WorldMonitor-style market intelligence monitor (free feeds only).

Sections are cached per TTL tier ("fast" 5s / "medium" 60s / "slow" 300s),
carry staleness badges (age_seconds, stale flag), and the combined bootstrap
payload ships with an ETag so clients revalidate cheaply:
If-None-Match matching the current data hash -> 304 Not Modified.

The ETag intentionally hashes only stable inputs (section data + fetch epochs +
tier) — NOT the volatile age/stale fields — so a client polling within a TTL
window gets a real 304 instead of a spurious 200.

Every fetcher is injectable and fails soft: a raising section yields an empty
data payload plus meta.error instead of an exception escaping into the route.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

TTL_TIERS: Dict[str, float] = {
    "fast": 5.0,     # prices / ticks
    "medium": 60.0,  # news, bot status
    "slow": 300.0,   # macro series, quakes
}

Fetcher = Callable[[], Any]


def utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_staleness(fetched_at_epoch: float, now: float, tier: str = "medium") -> Dict[str, Any]:
    """Freshness badge fields for a section relative to `now`."""
    ttl = TTL_TIERS.get(tier, TTL_TIERS["medium"])
    age = max(0.0, now - fetched_at_epoch)
    return {
        "tier": tier,
        "ttl_seconds": ttl,
        "age_seconds": round(age, 3),
        "stale": age > ttl,
    }


def make_etag(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return '"' + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32] + '"'


class MarketMonitor:
    """TTL-tiered section cache producing one bootstrap payload + ETag/304."""

    def __init__(self, sections: Dict[str, Dict[str, Any]]):
        # sections: name -> {"tier": str, "fetcher": callable}
        self._config = sections
        self._cache: Dict[str, Dict[str, Any]] = {}

    def refresh_section(self, name: str, now: Optional[float] = None) -> Dict[str, Any]:
        cfg = self._config[name]
        tier = cfg.get("tier", "medium")
        ts = time.time() if now is None else now
        error: Optional[str] = None
        try:
            data = cfg["fetcher"]()
        except Exception as exc:
            data = []
            error = f"{type(exc).__name__}: {exc}"
        entry: Dict[str, Any] = {
            "data": data,
            "meta": {
                "fetched_at_epoch": ts,
                "fetched_at": utc_iso(ts),
                **compute_staleness(ts, ts, tier),
            },
        }
        if error:
            entry["meta"]["error"] = error
        self._cache[name] = entry
        return entry

    def section(self, name: str, now: Optional[float] = None) -> Dict[str, Any]:
        now = time.time() if now is None else now
        cached = self._cache.get(name)
        tier = self._config[name].get("tier", "medium")
        if (
            cached is None
            or compute_staleness(cached["meta"]["fetched_at_epoch"], now, tier)["stale"]
        ):
            return self.refresh_section(name, now)
        meta = dict(cached["meta"])
        meta.update(compute_staleness(cached["meta"]["fetched_at_epoch"], now, tier))
        return {"data": cached["data"], "meta": meta}

    def bootstrap(
        self,
        if_none_match: Optional[str] = None,
        now: Optional[float] = None,
    ):
        """Return (payload, etag, not_modified). Refreshes expired sections."""
        now = time.time() if now is None else now
        sections = {name: self.section(name, now) for name in self._config}
        etag_source = {
            name: {
                "data": s["data"],
                "fetched_at": s["meta"]["fetched_at_epoch"],
                "tier": s["meta"]["tier"],
            }
            for name, s in sections.items()
        }
        etag = make_etag(etag_source)
        not_modified = bool(if_none_match) and if_none_match.strip() == etag
        payload = dict(sections)
        payload["_generated_at"] = utc_iso(now)
        return payload, etag, not_modified
