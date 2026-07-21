"""Append-only audit log — the system's black box recorder.

Every meaningful event (agent message, proposal, risk verdict, order, fill, kill-switch
action) is written here, to both the SQLite `audit` table and a human-readable JSONL file.
The log is append-only and replayable: you can reconstruct exactly why the bot did what
it did. As defense-in-depth, anything that looks like a secret is redacted before writing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from godmode.core import paths
from godmode.core.db import Database, get_db
from godmode.core.timeutil import utcnow_iso

_SENSITIVE = re.compile(r"(api[_-]?key|secret|token|password|private[_-]?key)", re.IGNORECASE)
_REDACTED = "***redacted***"

# Defense-in-depth: scan string VALUES for common API key formats. Even when
# the key name is innocuous (e.g. "input_text" wrapping an LLM prompt),
# key-like substrings should never reach the audit log.
_VALUE_PATTERNS = [
    # Anthropic: sk-ant-api03-... / sk-ant-...
    re.compile(r"sk-ant-api\d{2}-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    # OpenAI: sk-proj-... / sk-... (long)
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{40,}"),
    # Generic Bearer tokens (case-insensitive prefix)
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}"),
    # Google API keys (AIzaSy...)
    re.compile(r"AIza[A-Za-z0-9_\-]{30,}"),
    # Groq tokens (gsk_...)
    re.compile(r"gsk_[A-Za-z0-9]{28,}"),
    # NVIDIA NIM keys (nvapi-...)
    re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
    # Generic JWT (eyJ...)
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    # Slack-style xoxb- tokens
    re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"),
    # GitHub PATs (ghp_, gho_, ghs_, ghu_, ghr_)
    re.compile(r"gh[opstur]_[A-Za-z0-9]{30,}"),
    # Long hex runs (>=32 chars) — covers most CLI tokens, TOTP secrets, etc.
    re.compile(r"\b[a-fA-F0-9]{40,}\b"),
]


def _redact_value(value: Any) -> Any:
    """Redact secrets embedded inside STRING values (defense-in-depth).
    Concatenating key-format patterns onto opaque strings catches leaked
    values that the recursive key-name scanner alone would miss.
    """
    if isinstance(value, str):
        out = value
        for pat in _VALUE_PATTERNS:
            out = pat.sub(_REDACTED, out)
        return out
    return value


def _redact(value: Any) -> Any:
    """Recursively redact values whose key name looks secret AND strip
    common API-key formats out of string values (defense-in-depth)."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and _SENSITIVE.search(k):
                out[k] = _REDACTED
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return _redact_value(value)


class AuditLog:
    def __init__(self, db: Optional[Database] = None, jsonl_path: Optional[Path] = None):
        self.db = db or get_db()
        self.jsonl_path = Path(jsonl_path) if jsonl_path else paths.AUDIT_JSONL
        paths.ensure_runtime_dirs()

    def log(self, event_type: str, payload: dict, cycle_id: Optional[str] = None) -> str:
        """Record an event. Returns the timestamp used."""
        ts = utcnow_iso()
        safe = _redact(payload)
        payload_json = json.dumps(safe, default=str, ensure_ascii=False)

        self.db.insert(
            "audit",
            {"ts": ts, "event_type": event_type, "cycle_id": cycle_id, "payload_json": payload_json},
        )

        line = json.dumps(
            {"ts": ts, "event_type": event_type, "cycle_id": cycle_id, "payload": safe},
            default=str,
            ensure_ascii=False,
        )
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

        return ts

    def tail(self, limit: int = 50, event_type: Optional[str] = None) -> list[dict]:
        """Return the most recent audit rows (newest first)."""
        if event_type:
            return self.db.query(
                "SELECT * FROM audit WHERE event_type=? ORDER BY id DESC LIMIT ?",
                (event_type, limit),
            )
        return self.db.query("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))


_AUDIT: Optional[AuditLog] = None


def get_audit() -> AuditLog:
    """Return the process-wide AuditLog singleton."""
    global _AUDIT
    if _AUDIT is None:
        _AUDIT = AuditLog()
    return _AUDIT
