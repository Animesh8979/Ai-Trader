"""Offline persistence checks; no model, exchange or production DB required."""
from dataclasses import asdict
from unittest.mock import patch

import pytest

from godmode.agents.brain import MultiAgentBrain
from godmode.agents.reflection_memory import ReflectionMemory
from godmode.agents.reflection_v2 import ReflectionAgentV2
from godmode.core.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "memory.sqlite3")
    yield database
    database.close()


def test_brain_snapshot_survives_database_reopen(tmp_path):
    path = tmp_path / "restart.sqlite3"
    database = Database(path)
    insight = ReflectionAgentV2._default_insight()
    # Avoid constructing providers or optional models.
    brain = MultiAgentBrain.__new__(MultiAgentBrain)
    try:
        with patch("godmode.agents.brain.get_db", return_value=database):
            brain._remember_reflection("BTC/USDT", 1, insight)
    finally:
        database.close()
    reopened = Database(path)
    try:
        snapshot = ReflectionMemory(reopened).latest(
            symbol="BTC/USDT", run_id=1, as_of="9999-01-01T00:00:00Z")
        assert snapshot["observation"] == {
            "kind": "unvalidated_reflection", "source_scope": "global_recent_fills",
            "insight": asdict(insight),
        }
    finally:
        reopened.close()


def test_scoping_time_cutoff_and_idempotence(db):
    memory = ReflectionMemory(db)
    scope = {"symbol": "BTC/USDT", "run_id": 1}
    memory.remember(**scope, as_of="2026-09-17T12:00:00Z", observation={"n": 1})
    memory.remember(**scope, as_of="2026-09-17T14:00:00+02:00", observation={"n": 2})
    assert memory.latest(**scope, as_of="2026-09-17T11:59:59Z") is None
    assert memory.latest(**scope, as_of="2026-09-17T12:00:00Z")["observation"] == {"n": 1}
    assert memory.latest(symbol="ETH/USDT", run_id=1, as_of="2026-09-18T00:00:00Z") is None
    assert memory.latest(symbol="BTC/USDT", run_id=2, as_of="2026-09-18T00:00:00Z") is None
    assert db.query_one("SELECT COUNT(*) AS n FROM reflection_memory")["n"] == 1


@pytest.mark.parametrize("timestamp", ["invalid", "2026-09-17T12:00:00"])
def test_invalid_timestamps_rejected(db, timestamp):
    with pytest.raises(ValueError):
        ReflectionMemory(db).remember(symbol="BTC/USDT", run_id=1,
                                     as_of=timestamp, observation={})


def test_nonfinite_observation_rejected(db):
    with pytest.raises(ValueError):
        ReflectionMemory(db).remember(symbol="BTC/USDT", run_id=1,
            as_of="2026-09-17T12:00:00Z", observation={"pnl": float("nan")})


def test_memory_failure_does_not_crash_brain():
    brain = MultiAgentBrain.__new__(MultiAgentBrain)
    with patch("godmode.agents.brain.get_db", side_effect=OSError("disk unavailable")):
        brain._remember_reflection("BTC/USDT", 1, ReflectionAgentV2._default_insight())


def test_unscoped_call_does_not_open_database():
    brain = MultiAgentBrain.__new__(MultiAgentBrain)
    with patch("godmode.agents.brain.get_db") as get_db:
        brain._remember_reflection("BTC/USDT", None, ReflectionAgentV2._default_insight())
        get_db.assert_not_called()
