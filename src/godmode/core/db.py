"""SQLite persistence — zero-config, file-based, WAL mode for durability.

Monetary columns (qty, price, fees, pnl) are stored as TEXT so Decimal precision is
never lost to float. A single connection guarded by a re-entrant lock keeps writes safe
across the async loop and the dashboard thread.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from godmode.core import paths
from godmode.core.timeutil import utcnow_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    mode        TEXT NOT NULL,
    note        TEXT,
    status      TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER,
    client_order_id TEXT UNIQUE,            -- idempotency key (dedupe retries)
    venue           TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    type            TEXT NOT NULL,
    qty             TEXT NOT NULL,
    price           TEXT,
    status          TEXT NOT NULL DEFAULT 'new',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    raw_json        TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(venue, symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

CREATE TABLE IF NOT EXISTS fills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER,
    client_order_id TEXT,
    venue           TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    qty             TEXT NOT NULL,
    price           TEXT NOT NULL,
    fee             TEXT,
    fee_ccy         TEXT,
    realized_pnl    TEXT,
    ts              TEXT NOT NULL,
    raw_json        TEXT
);
CREATE INDEX IF NOT EXISTS idx_fills_symbol ON fills(venue, symbol);

CREATE TABLE IF NOT EXISTS positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    venue       TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    qty         TEXT NOT NULL,
    avg_price   TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(venue, symbol)
);

CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER,
    ts            TEXT NOT NULL,
    cycle_id      TEXT,
    desk          TEXT,
    symbol        TEXT,
    proposal_json TEXT,
    risk_verdict  TEXT,
    final_action  TEXT,
    reason        TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_cycle ON decisions(cycle_id);

CREATE TABLE IF NOT EXISTS agent_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER,
    ts            TEXT NOT NULL,
    cycle_id      TEXT,
    role          TEXT,
    model         TEXT,
    input_summary TEXT,
    output_text   TEXT,
    tokens_in     INTEGER,
    tokens_out    INTEGER,
    cost_usd      REAL,
    latency_ms    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_msgs_cycle ON agent_messages(cycle_id);

CREATE TABLE IF NOT EXISTS metrics (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT NOT NULL,
    key   TEXT NOT NULL,
    value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_key ON metrics(key, ts);

CREATE TABLE IF NOT EXISTS kill_events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     TEXT NOT NULL,
    action TEXT NOT NULL,            -- engage | reset | auto
    reason TEXT,
    source TEXT                      -- ui | cli | sentinel | risk_engine | heartbeat
);

CREATE TABLE IF NOT EXISTS audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    cycle_id     TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit(event_type, ts);
"""


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else paths.DB_PATH
        paths.ensure_runtime_dirs()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
        self.init_schema()

    # -- schema ----------------------------------------------------------- #
    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # -- low level -------------------------------------------------------- #
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql: str, seq: Sequence[Sequence[Any]]) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.executemany(sql, seq)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[dict]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # Hard whitelist of insertable tables. The `insert()` method below does
    # table-name interpolation (SQLite does not support parameterized table
    # names), so we must GUARD against injection — only the canonical
    # production tables are permitted.
    _ALLOWED_TABLES = frozenset({
        "runs", "orders", "fills", "positions", "decisions",
        "agent_messages", "metrics", "kill_events", "audit",
        "ohlcv",
    })

    def insert(self, table: str, data: dict) -> int:
        if table not in self._ALLOWED_TABLES:
            raise ValueError(
                f"insert(): table {table!r} not in whitelist. Refusing to "
                f"interpolate unknown table names into SQL (injection guard)."
            )
        # Column names are also interpolated (SQLite doesn't parameterize them),
        # so validate against the strict identifier regex [A-Za-z_][A-Za-z0-9_]*.
        import re as _re
        _ident_re = _re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
        for col in data.keys():
            if not _ident_re.match(col):
                raise ValueError(
                    f"insert(): column name {col!r} is not a valid SQL identifier "
                    f"(injection guard)."
                )
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        cur = self.execute(sql, tuple(data.values()))
        return int(cur.lastrowid)

    # -- convenience ------------------------------------------------------ #
    def start_run(self, mode: str, note: str = "") -> int:
        return self.insert(
            "runs", {"started_at": utcnow_iso(), "mode": mode, "note": note, "status": "running"}
        )

    def end_run(self, run_id: int, status: str = "stopped") -> None:
        self.execute(
            "UPDATE runs SET ended_at=?, status=? WHERE id=?", (utcnow_iso(), status, run_id)
        )

    def record_metric(self, key: str, value: float, ts: Optional[str] = None) -> int:
        return self.insert("metrics", {"ts": ts or utcnow_iso(), "key": key, "value": float(value)})

    def record_kill_event(self, action: str, reason: str, source: str) -> int:
        return self.insert(
            "kill_events",
            {"ts": utcnow_iso(), "action": action, "reason": reason, "source": source},
        )

    def get_position(self, venue: str, symbol: str) -> Optional[Dict[str, Any]]:
        rows = self.query("SELECT * FROM positions WHERE venue = ? AND symbol = ?", (venue, symbol))
        return dict(rows[0]) if rows else None

    def upsert_position(self, venue: str, symbol: str, qty: str, avg_price: str) -> None:
        self.execute(
            """
            INSERT INTO positions (venue, symbol, qty, avg_price, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(venue, symbol) DO UPDATE SET
                qty=excluded.qty, avg_price=excluded.avg_price, updated_at=excluded.updated_at
            """,
            (venue, symbol, str(qty), str(avg_price), utcnow_iso()),
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_DB: Optional[Database] = None


def get_db() -> Database:
    """Return the process-wide Database singleton."""
    global _DB
    if _DB is None:
        _DB = Database()
    return _DB


def reset_db_singleton() -> None:
    """Testing helper: drop the cached singleton so a new path can be used."""
    global _DB
    if _DB is not None:
        _DB.close()
    _DB = None
