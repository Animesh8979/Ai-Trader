import pytest

from godmode.core.audit import AuditLog
from godmode.core.db import Database
from godmode.core.killswitch import KillSwitch, KillSwitchEngaged


def _make_ks(tmp_path) -> KillSwitch:
    db = Database(tmp_path / "k.sqlite3")
    audit = AuditLog(db=db, jsonl_path=tmp_path / "audit.jsonl")
    return KillSwitch(
        db=db,
        audit=audit,
        stop_file=tmp_path / "STOP",
        heartbeat_file=tmp_path / "hb.txt",
    )


def test_engage_blocks_and_reset_clears(tmp_path):
    ks = _make_ks(tmp_path)
    assert not ks.is_halted()
    ks.check()  # must not raise when healthy

    ks.engage("circuit breaker tripped", source="risk_engine")
    assert ks.is_halted()
    assert ks.reason()["reason"] == "circuit breaker tripped"
    with pytest.raises(KillSwitchEngaged):
        ks.check()

    ks.reset()
    assert not ks.is_halted()
    ks.check()  # healthy again


def test_engage_is_idempotent_keeps_first_reason(tmp_path):
    ks = _make_ks(tmp_path)
    ks.engage("first", source="cli")
    ks.engage("second", source="cli")
    assert ks.reason()["reason"] == "first"


def test_heartbeat(tmp_path):
    ks = _make_ks(tmp_path)
    assert ks.heartbeat_age_seconds() is None
    ks.beat()
    age = ks.heartbeat_age_seconds()
    assert age is not None and age < 5
    assert not ks.is_stale(60)
