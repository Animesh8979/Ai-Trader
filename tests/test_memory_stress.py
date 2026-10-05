"""Hardened stress/regression tests for reflection memory and calibration.

Concurrency, corruption, validation and boundary checks. All offline; no
production database, exchange or LLM is touched.
"""
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from godmode.agents.brain import MultiAgentBrain
from godmode.agents.reflection_memory import ReflectionMemory
from godmode.agents.reflection_v2 import ReflectionAgentV2
from godmode.core.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "stress.sqlite3")
    yield database
    database.close()


@pytest.fixture
def memory(db):
    return ReflectionMemory(db)


def _reflect_with_fills(pnls, depth=None):
    db = MagicMock()
    db.query.return_value = [{"realized_pnl": p} for p in pnls]
    with patch("godmode.agents.reflection_v2.get_db", return_value=db):
        agent = ReflectionAgentV2(check_depth=depth or len(pnls))
        return agent.reflect()


def test_concurrent_duplicate_writes_dedupe(memory, db):
    errors = []

    def writer(i):
        try:
            memory.remember(symbol="BTC/USDT", run_id=1,
                            as_of="2026-09-17T12:00:00Z", observation={"thread": i})
        except Exception as exc:  # pragma: no cover - surfaced by assertion
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert db.query_one("SELECT COUNT(*) AS n FROM reflection_memory")["n"] == 1
    assert memory.latest(symbol="BTC/USDT", run_id=1,
                         as_of="2026-09-17T12:00:00Z")["observation"]["thread"] in range(16)


def test_concurrent_distinct_writes_all_persist(memory, db):
    errors = []

    def writer(i):
        try:
            memory.remember(symbol="BTC/USDT", run_id=1,
                            as_of=f"2026-09-17T12:00:{i:02d}Z", observation={"i": i})
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert db.query_one("SELECT COUNT(*) AS n FROM reflection_memory")["n"] == 16


def test_concurrent_mixed_readers_and_writers(memory, db):
    errors = []

    def writer(i):
        try:
            for j in range(4):
                minute = 10 + j // 2
                second = (j % 2) * 30 + i
                memory.remember(symbol="BTC/USDT", run_id=1,
                                as_of=f"2026-09-17T12:{minute:02d}:{second:02d}Z",
                                observation={"w": i, "j": j})
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    def reader():
        try:
            for _ in range(20):
                memory.latest(symbol="BTC/USDT", run_id=1, as_of="2026-09-17T23:59:59Z")
                memory.latest(symbol="ETH/USDT", run_id=1, as_of="2026-09-17T23:59:59Z")
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    threads += [threading.Thread(target=reader) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert db.query_one("SELECT COUNT(*) AS n FROM reflection_memory")["n"] == 32


def test_payload_size_boundary(memory):
    inner = "x" * 7991
    assert len(json.dumps({"n": inner})) == 8000
    memory.remember(symbol="BTC", run_id=1, as_of="2026-09-17T12:00:00Z",
                    observation={"n": inner})
    with pytest.raises(ValueError):
        memory.remember(symbol="BTC", run_id=1, as_of="2026-09-17T12:00:01Z",
                        observation={"n": inner + "x"})
    assert memory.count(symbol="BTC", run_id=1) == 1


@pytest.mark.parametrize("kwargs", [
    {"symbol": "", "run_id": 1},
    {"symbol": "BTC/USDT", "run_id": 0},
    {"symbol": "BTC/USDT", "run_id": None},
    {"symbol": "BTC/USDT", "run_id": "1"},
    {"symbol": "BTC/USDT", "run_id": True},
])
def test_scope_validation(memory, kwargs):
    with pytest.raises(ValueError):
        memory.remember(**kwargs, as_of="2026-09-17T12:00:00Z", observation={})


def test_offset_equivalent_timestamps_dedupe(memory, db):
    memory.remember(symbol="BTC", run_id=1, as_of="2026-09-17T12:00:00+00:00",
                    observation={"a": 1})
    memory.remember(symbol="BTC", run_id=1, as_of="2026-09-17T12:00:00Z",
                    observation={"b": 2})
    assert db.query_one("SELECT COUNT(*) AS n FROM reflection_memory")["n"] == 1
    snap = memory.latest(symbol="BTC", run_id=1, as_of="2026-09-17T12:00:00Z")
    assert snap["observation"] == {"a": 1}


def test_sql_metacharacters_in_symbol_are_inert(db):
    weird = "BTC'; DROP TABLE reflection_memory; --"
    memory = ReflectionMemory(db)
    memory.remember(symbol=weird, run_id=1, as_of="2026-09-17T12:00:00Z",
                    observation={"x": 1})
    snap = memory.latest(symbol=weird, run_id=1, as_of="2026-09-17T13:00:00Z")
    assert snap["observation"] == {"x": 1}
    assert db.query_one("SELECT COUNT(*) AS n FROM reflection_memory")["n"] == 1


def test_corrupted_payload_fail_soft(memory, db):
    memory.remember(symbol="BTC", run_id=1, as_of="2026-09-17T12:00:00Z",
                    observation={"ok": True})
    db.execute("UPDATE reflection_memory SET payload='not-json'")
    assert memory.latest(symbol="BTC", run_id=1, as_of="2026-09-17T13:00:00Z") is None
    db.execute("UPDATE reflection_memory SET payload='[1,2]'")
    assert memory.latest(symbol="BTC", run_id=1, as_of="2026-09-17T13:00:00Z") is None


def test_brain_recall_survives_corruption(tmp_path, monkeypatch):
    monkeypatch.setenv("GODMODE_REFLECTION_MEMORY", "1")
    db = Database(tmp_path / "corrupt.sqlite3")
    brain = MultiAgentBrain.__new__(MultiAgentBrain)
    try:
        ReflectionMemory(db).remember(symbol="BTC", run_id=1,
            as_of="2026-09-17T10:00:00Z",
            observation={"kind": "unvalidated_reflection",
                         "insight": {"win_rate_pct": 50.0, "total_pnl": 1.0,
                                     "consecutive_losses": 0}})
        db.execute("UPDATE reflection_memory SET payload='not-json'")
        with patch("godmode.agents.brain.get_db", return_value=db):
            assert brain._recall_reflection("BTC", 1, "2026-09-17T11:00:00Z") == ""
    finally:
        db.close()


def test_recall_rejects_boolean_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("GODMODE_REFLECTION_MEMORY", "1")
    db = Database(tmp_path / "bool.sqlite3")
    brain = MultiAgentBrain.__new__(MultiAgentBrain)
    try:
        ReflectionMemory(db).remember(symbol="BTC", run_id=1,
            as_of="2026-09-17T10:00:00Z",
            observation={"kind": "unvalidated_reflection",
                         "insight": {"win_rate_pct": True, "total_pnl": 1.0,
                                     "consecutive_losses": 0}})
        with patch("godmode.agents.brain.get_db", return_value=db):
            assert brain._recall_reflection("BTC", 1, "2026-09-17T11:00:00Z") == ""
    finally:
        db.close()


def test_prune_deletes_only_older_rows(memory, db):
    for i, ts in enumerate(["2026-09-16T00:00:00Z", "2026-09-17T00:00:00Z",
                            "2026-09-17T12:00:00Z"]):
        memory.remember(symbol="BTC", run_id=1, as_of=ts, observation={"i": i})
    memory.remember(symbol="ETH", run_id=1, as_of="2026-09-16T00:00:00Z",
                    observation={"i": 9})
    assert memory.prune(older_than="2026-09-17T00:00:00Z", symbol="BTC") == 1
    assert memory.count() == 3  # ETH row must survive the symbol-scoped prune
    assert memory.prune(older_than="2027-01-01T00:00:00Z") == 3
    assert memory.count() == 0


def test_prune_invalid_timestamp_is_rejected_and_deletes_nothing(memory, db):
    memory.remember(symbol="BTC", run_id=1, as_of="2026-09-17T12:00:00Z",
                    observation={"i": 1})
    with pytest.raises(ValueError):
        memory.prune(older_than="garbage")
    assert memory.count() == 1


def test_reflection_skips_garbage_and_nonfinite_pnl():
    insight = _reflect_with_fills(
        ["abc", "NaN", "Infinity", None, "", "-5", "10", "20", "30"])
    assert insight.total_pnl == 55.0
    assert insight.consecutive_losses == 1
    assert insight.win_rate_pct == 75.0
    assert insight.recommended_bias == "no_change"


def test_hundred_loss_streak_stays_symmetric():
    insight = _reflect_with_fills(["-1.0"] * 100)
    assert insight.consecutive_losses == 100
    assert insight.bull_weight_adjustment == insight.bear_weight_adjustment == -0.3
    assert insight.recommended_bias == "neutral"


def test_mixed_outcomes_keep_no_directional_signal():
    insight = _reflect_with_fills(["50.0", "-10.0", "60.0", "-10.0"])
    assert insight.win_rate_pct == 50.0
    assert insight.bull_weight_adjustment == 0.0
    assert insight.bear_weight_adjustment == 0.0
