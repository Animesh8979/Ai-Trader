"""Binance Mainnet Key Guard — startup safety enforcement.

Scans .env for mainnet keys and REFUSES to start if they are present.
This is a hard gate: no bypass, no override. All trading must be paper/testnet ONLY.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

FORBIDDEN_KEYS = [
    "BINANCE_MAINNET_API_KEY",
    "BINANCE_MAINNET_API_SECRET",
    "BYBIT_MAINNET_API_KEY",
    "BYBIT_MAINNET_API_SECRET",
    "SHOONYA_USER_ID",
    "SHOONYA_PASSWORD",
    "SHOONYA_API_SECRET",
    "SHOONYA_IMEI",
]


def audit_env(paths: list[str]) -> dict[str, list[str]]:
    triggered: list[str] = []
    for var in FORBIDDEN_KEYS:
        val = os.environ.get(var, "").strip()
        if val:
            triggered.append(var)
    for p in paths:
        dotenv_path = Path(p) / ".env"
        if dotenv_path.exists():
            content = dotenv_path.read_text(encoding="utf-8", errors="ignore")
            for var in FORBIDDEN_KEYS:
                if f"{var}=" in content and var not in triggered:
                    triggered.append(var)
    return {"forbidden_keys_present": triggered}


def enforce() -> None:
    result = audit_env([os.getcwd(), str(Path(__file__).resolve().parent.parent.parent)])
    forbidden = result["forbidden_keys_present"]
    if forbidden:
        msg = (
            "\n==============================================================\n"
            "  CRITICAL: MAINNET API KEYS DETECTED IN ENVIRONMENT\n"
            "  Godmode refuses to start with real-money exchange keys.\n"
            "  Keys found: " + ", ".join(forbidden) + "\n"
            "  ACTION REQUIRED:\n"
            "    1. Remove/comment those lines from your .env file\n"
            "    2. Use ONLY testnet keys (BINANCE_TESTNET_API_KEY etc.)\n"
            "==============================================================\n"
        )
        sys.stderr.write(msg)
        sys.exit(1)


if __name__ == "__main__":
    enforce()