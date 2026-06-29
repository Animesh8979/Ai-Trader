"""Tiny, shared time helpers. Always UTC, always timezone-aware."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def utcnow_ms() -> int:
    return int(utcnow().timestamp() * 1000)


def today_str() -> str:
    return utcnow().strftime("%Y-%m-%d")
