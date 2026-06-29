"""The kill switch — the single most important safety control.

It is intentionally simple and physical: a sentinel FILE on disk (`data/STOP`). If that
file exists, trading is halted. This means a halt survives crashes and restarts, can be
triggered five different ways (dashboard button, CLI, the risk engine, the heartbeat
watchdog, or just creating the file by hand), and the execution layer enforces it by
calling `check()` before every single order.

A heartbeat / dead-man's switch is included: the live loop calls `beat()` each cycle; if
the heartbeat goes stale, a watchdog can halt automatically (a frozen bot stops trading).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from filelock import FileLock

from godmode.core import paths
from godmode.core.audit import AuditLog, get_audit
from godmode.core.db import Database, get_db
from godmode.core.timeutil import utcnow, utcnow_iso

HEARTBEAT_FILE = paths.DATA_DIR / "heartbeat.txt"


class KillSwitchEngaged(RuntimeError):
    """Raised by `check()` when trading is halted."""


class KillSwitch:
    def __init__(
        self,
        db: Optional[Database] = None,
        audit: Optional[AuditLog] = None,
        stop_file: Optional[Path] = None,
        heartbeat_file: Optional[Path] = None,
    ):
        self.db = db or get_db()
        self.audit = audit or get_audit()
        self.stop_file = Path(stop_file) if stop_file else paths.STOP_FILE
        self.heartbeat_file = Path(heartbeat_file) if heartbeat_file else HEARTBEAT_FILE
        self.lock = FileLock(str(self.stop_file) + ".lock")
        paths.ensure_runtime_dirs()

    # -- halt state ------------------------------------------------------- #
    def is_halted(self) -> bool:
        return self.stop_file.exists()

    def reason(self) -> Optional[dict]:
        if not self.stop_file.exists():
            return None
        try:
            with self.lock:
                return json.loads(self.stop_file.read_text(encoding="utf-8"))
        except Exception:
            with self.lock:
                if self.stop_file.exists():
                    txt = self.stop_file.read_text(encoding="utf-8").strip()
                else:
                    txt = ""
            return {"reason": txt or "unknown"}

    def engage(self, reason: str, source: str = "cli") -> None:
        """Halt trading. Idempotent — re-engaging keeps the original reason."""
        with self.lock:
            if not self.stop_file.exists():
                self.stop_file.write_text(
                    json.dumps({"reason": reason, "source": source, "ts": utcnow_iso()}, indent=2),
                    encoding="utf-8",
                )
        self.db.record_kill_event("engage", reason, source)
        self.audit.log("kill_switch.engage", {"reason": reason, "source": source})

    def reset(self, source: str = "cli") -> None:
        """Clear the halt. Use deliberately."""
        with self.lock:
            existed = self.stop_file.exists()
            if existed:
                self.stop_file.unlink()
        self.db.record_kill_event("reset", "manual reset", source)
        self.audit.log("kill_switch.reset", {"source": source, "was_halted": existed})

    def check(self) -> None:
        """Raise if halted. Call this immediately before placing any order."""
        if self.is_halted():
            r = self.reason() or {}
            raise KillSwitchEngaged(f"Trading halted: {r.get('reason', '(no reason given)')}")

    # -- heartbeat / dead-man's switch ------------------------------------ #
    def beat(self) -> None:
        now = utcnow()
        if not hasattr(self, '_last_beat') or (now - self._last_beat).total_seconds() > 5.0:
            self.heartbeat_file.write_text(utcnow_iso(), encoding="utf-8")
            self._last_beat = now

    def heartbeat_age_seconds(self) -> Optional[float]:
        if not self.heartbeat_file.exists():
            return None
        try:
            ts = datetime.fromisoformat(self.heartbeat_file.read_text(encoding="utf-8").strip())
        except Exception:
            return None
        return (utcnow() - ts).total_seconds()

    def is_stale(self, max_age_seconds: float) -> bool:
        age = self.heartbeat_age_seconds()
        return age is not None and age > max_age_seconds

    def watchdog(self, max_age_seconds: float) -> bool:
        """If the heartbeat is stale, auto-halt. Returns True if it engaged."""
        if self.is_stale(max_age_seconds) and not self.is_halted():
            self.engage(
                f"heartbeat stale (> {max_age_seconds}s) — loop may be frozen",
                source="heartbeat",
            )
            return True
        return False

    def status(self) -> dict:
        return {
            "halted": self.is_halted(),
            "reason": self.reason(),
            "heartbeat_age_seconds": self.heartbeat_age_seconds(),
        }

    def start_isolated_watchdog(self, max_age_seconds: float = 15.0) -> None:
        """Spawns an OS-level isolated process to monitor the heartbeat outside the GIL."""
        import multiprocessing
        import time
        
        def watchdog_loop(max_age: float, stop_path: str, heartbeat_path: str):
            isolated_ks = KillSwitch(stop_file=Path(stop_path), heartbeat_file=Path(heartbeat_path))
            while True:
                if not isolated_ks.is_halted():
                    isolated_ks.watchdog(max_age)
                time.sleep(1.0)
                
        p = multiprocessing.Process(
            target=watchdog_loop, 
            args=(max_age_seconds, str(self.stop_file), str(self.heartbeat_file)),
            daemon=True,
            name="KillSwitchIsolatedWatchdog"
        )
        p.start()
        self.audit.log("kill_switch.watchdog_isolated_spawn", {"pid": p.pid, "max_age": max_age_seconds})


_KS: Optional[KillSwitch] = None


def get_kill_switch() -> KillSwitch:
    global _KS
    if _KS is None:
        _KS = KillSwitch()
    return _KS


# Module-level convenience wrappers.
def is_halted() -> bool:
    return get_kill_switch().is_halted()


def engage(reason: str, source: str = "cli") -> None:
    get_kill_switch().engage(reason, source)


def reset(source: str = "cli") -> None:
    get_kill_switch().reset(source)
