"""Durable, scoped reflection snapshots. Storage is not model training.

Only structured performance observations are stored here, never raw prompts,
credentials or scraped instructions. Existing trade/audit tables are untouched.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from godmode.core.db import Database
from godmode.core.logging import get_logger
from godmode.core.timeutil import utcnow_iso

log = get_logger("agents.reflection_memory")


def canonical_timestamp(value: str) -> str:
    """Normalize timezone-aware timestamps for consistent SQLite comparisons."""
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Memory timestamps must include a timezone")
    return stamp.astimezone(timezone.utc).isoformat(timespec="microseconds")


class ReflectionMemory:
    def __init__(self, db: Database):
        self.db = db
        db.execute("""
            CREATE TABLE IF NOT EXISTS reflection_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                run_id INTEGER NOT NULL,
                as_of TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE(symbol, run_id, as_of)
            )
        """)

    def remember(self, *, symbol: str, run_id: int, as_of: str, observation: dict) -> None:
        """First observation at a decision boundary wins, including after restart."""
        if not symbol or not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
            raise ValueError("Memory requires a symbol and a positive run ID")
        payload = json.dumps(observation, sort_keys=True, allow_nan=False)
        if len(payload) > 8000:
            raise ValueError("Reflection observation exceeds 8000 characters")
        self.db.execute(
            "INSERT OR IGNORE INTO reflection_memory "
            "(symbol, run_id, as_of, recorded_at, payload) VALUES (?, ?, ?, ?, ?)",
            (symbol, run_id, canonical_timestamp(as_of), utcnow_iso(), payload),
        )

    def latest(self, *, symbol: str, run_id: int, as_of: str) -> dict | None:
        """Recall only this run/symbol, never an observation from the future."""
        row = self.db.query_one(
            "SELECT as_of, recorded_at, payload FROM reflection_memory "
            "WHERE symbol=? AND run_id=? AND as_of<=? ORDER BY as_of DESC LIMIT 1",
            (symbol, run_id, canonical_timestamp(as_of)),
        )
        if row is None:
            return None
        try:
            observation = json.loads(row["payload"])
        except (TypeError, ValueError):
            log.warning(
                f"Corrupted reflection payload for {symbol}/{run_id} "
                f"at {row['as_of']}; skipping"
            )
            return None
        if not isinstance(observation, dict):
            log.warning(
                f"Non-object reflection payload for {symbol}/{run_id} "
                f"at {row['as_of']}; skipping"
            )
            return None
        return {"as_of": row["as_of"], "recorded_at": row["recorded_at"],
                "observation": observation}

    def count(self, *, symbol: str | None = None, run_id: int | None = None) -> int:
        """Number of stored snapshots, optionally within one namespace."""
        sql = "SELECT COUNT(*) AS n FROM reflection_memory"
        params: list = []
        if symbol is not None or run_id is not None:
            clauses = []
            if symbol is not None:
                clauses.append("symbol=?")
                params.append(symbol)
            if run_id is not None:
                clauses.append("run_id=?")
                params.append(run_id)
            sql += " WHERE " + " AND ".join(clauses)
        return int(self.db.query_one(sql, params)["n"])

    def prune(self, *, older_than: str, symbol: str | None = None) -> int:
        """Delete snapshots strictly older than the timezone-aware cutoff."""
        cutoff = canonical_timestamp(older_than)
        if symbol is None:
            cur = self.db.execute(
                "DELETE FROM reflection_memory WHERE as_of < ?", (cutoff,))
        else:
            cur = self.db.execute(
                "DELETE FROM reflection_memory WHERE as_of < ? AND symbol=?",
                (cutoff, symbol))
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
