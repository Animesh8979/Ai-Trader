"""Canonical filesystem paths for the project.

Everything that needs to know where the repo root, config, data, db, logs, or the
kill-switch sentinel lives imports from here, so there is exactly one source of truth.
Override the repo root with the GODMODE_HOME environment variable if needed.
"""

from __future__ import annotations

import os
from pathlib import Path


def _detect_project_root() -> Path:
    override = os.environ.get("GODMODE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    # This file is <root>/src/godmode/core/paths.py -> parents[3] is <root>.
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT: Path = _detect_project_root()

CONFIG_DIR: Path = PROJECT_ROOT / "config"
DATA_DIR: Path = PROJECT_ROOT / "data"
LOGS_DIR: Path = DATA_DIR / "logs"

ENV_FILE: Path = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE: Path = PROJECT_ROOT / ".env.example"

CONFIG_FILE: Path = CONFIG_DIR / "config.yaml"
MODELS_FILE: Path = CONFIG_DIR / "models.yaml"

DB_PATH: Path = DATA_DIR / "godmode.sqlite3"
AUDIT_JSONL: Path = DATA_DIR / "audit.jsonl"
STOP_FILE: Path = DATA_DIR / "STOP"


def ensure_runtime_dirs() -> None:
    """Create the runtime data/log directories if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
