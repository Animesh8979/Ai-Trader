"""Offline tests for the TTL-tiered MarketMonitor + dashboard monitor endpoints.

No network: fetchers are stubbed; the dashboard singleton is monkeypatched.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from godmode.data.market_monitor import (
    TTL_TIERS,
    MarketMonitor,
    compute_staleness,
    make_etag,
)

# NOTE: godmode/dashboard/__init__.py shadows the `.app` attribute with the
# FastAPI instance, so `import godmode.dashboard.app as x` yields the wrong
# object on py3.12. importlib.import_module always returns the real module.
dashboard_app = importlib.import_module("godmode.dashboard.app")
app = dashboard_app.app


@pytest.fixture
def client(tmp_path, monkeypatch):
    import godmode.core.db as db_mod
    import godmode.core.killswitch as ks_mod

    db_file = tmp_path / "monitor_test.sqlite3"
    import godmode.core.paths as paths
    orig_db_path = paths.DB_PATH
    paths.DB_PATH = db_file
    db_mod.reset_db_singleton()
    ks_mod._KS = None
    ks = __import__("godmode.core.killswitch", fromlist=["get_kill_switch"]).get_kill_switch()
    orig_stop_file = ks.stop_file
    ks.stop_file = tmp_path / "STOP"

    with TestClient(app) as test_client:
        yield test_client

    ks.stop_file = orig_stop_file
    paths.DB_PATH = orig_db_path
    db_mod.reset_db_singleton()
    ks_mod._KS = None


def test_ttl_tiers_values():
    assert TTL_TIERS["fast"] == 5.0
    assert TTL_TIERS["medium"] == 60.0
    assert TTL_TIERS["slow"] == 300.0


def test_compute_staleness_fresh_and_stale():
    badge = compute_staleness(fetched_at_epoch=1000.0, now=1010.0, tier="fast")
    assert badge["age_seconds"] == 10.0
    assert badge["ttl_seconds"] == 5.0
    assert badge["stale"] is True

    fresh = compute_staleness(fetched_at_epoch=1000.0, now=1002.0, tier="fast")
    assert fresh["stale"] is False

    clamped = compute_staleness(fetched_at_epoch=2000.0, now=1000.0, tier="slow")
    assert clamped["age_seconds"] == 0.0
    assert clamped["stale"] is False


def test_make_etag_stable_and_sensitive():
    a = {"x": 1}
    b = {"x": 2}
    ea1, ea2 = make_etag(a), make_etag(a)
    assert ea1 == ea2
    assert ea1.startswith('"') and ea1.endswith('"')
    assert make_etag(b) != ea1
    # key order must not matter (canonical serialization)
    assert make_etag({"a": 1, "b": 2}) == make_etag({"b": 2, "a": 1})


def _make_monitor(calls):
    def markets():
        calls["markets"] += 1
        return {"prices": {"BTC": 68000.0}}

    def bot_status():
        calls["bot"] += 1
        return {"halted": False}

    def news():
        calls["news"] += 1
        return [{"title": "t", "importance": 0.5}]

    return MarketMonitor({
        "markets": {"tier": "fast", "fetcher": markets},
        "bot_status": {"tier": "medium", "fetcher": bot_status},
        "news": {"tier": "medium", "fetcher": news},
    })


def test_section_caches_within_ttl_and_refreshes_after_expiry():
    calls = {"markets": 0, "bot": 0, "news": 0}
    monitor = _make_monitor(calls)

    s1 = monitor.section("markets", now=1000.0)
    s2 = monitor.section("markets", now=1002.0)
    assert s1["data"] == s2["data"]
    assert calls["markets"] == 1  # cached within fast TTL (5s)
    assert s2["meta"]["stale"] is False

    monitor.section("markets", now=1006.5)  # age 6.5s > 5s -> refresh
    assert calls["markets"] == 2


def test_refresh_fail_soft_records_error():
    def boom():
        raise RuntimeError("network down")

    monitor = MarketMonitor({"bad": {"tier": "fast", "fetcher": boom}})
    entry = monitor.refresh_section("bad", now=1000.0)
    assert entry["data"] == []
    assert "RuntimeError" in entry["meta"]["error"]
    # section() surfaces it without raising
    assert "error" in monitor.section("bad", now=1001.0)["meta"]


def test_bootstrap_etag_ignores_volatile_age_fields():
    calls = {"markets": 0, "bot": 0, "news": 0}
    monitor = _make_monitor(calls)

    p1, etag1, nm1 = monitor.bootstrap(now=1000.0)
    # same underlying data, later clock -> ages change but etag must not
    p2, etag2, nm2 = monitor.bootstrap(now=1003.0)
    assert etag1 == etag2
    assert p1["_generated_at"] != p2["_generated_at"]
    assert set(p2.keys()) >= {"markets", "bot_status", "news", "_generated_at"}

    _, _, hit = monitor.bootstrap(if_none_match=etag2, now=1004.0)
    assert hit is True
    _, _, miss = monitor.bootstrap(if_none_match='"deadbeef"', now=1005.0)
    assert miss is False
    assert nm1 is False and nm2 is False


def test_bootstrap_refreshes_expired_sections_in_payload():
    calls = {"markets": 0, "bot": 0, "news": 0}
    monitor = _make_monitor(calls)
    monitor.bootstrap(now=1000.0)
    assert calls == {"markets": 1, "bot": 1, "news": 1}
    monitor.bootstrap(now=1100.0)  # everything expired
    assert calls == {"markets": 2, "bot": 2, "news": 2}


def _stub_dashboard_monitor(monkeypatch):
    def markets():
        return {"prices": {"BTC": 100.0}}

    stub = MarketMonitor({
        "markets": {"tier": "fast", "fetcher": markets},
        "bot_status": {"tier": "medium", "fetcher": lambda: {"halted": False}},
        "news": {"tier": "medium", "fetcher": lambda: []},
    })
    monkeypatch.setattr(dashboard_app, "_market_monitor", stub)


def test_endpoint_bootstrap_then_304(client, monkeypatch):
    _stub_dashboard_monitor(monkeypatch)
    r1 = client.get("/api/monitor/bootstrap")
    assert r1.status_code == 200
    body = r1.json()
    for section in ("markets", "bot_status", "news"):
        assert section in body
        assert "data" in body[section] and "meta" in body[section]
        meta = body[section]["meta"]
        assert meta["tier"] in ("fast", "medium", "slow")
        assert isinstance(meta["stale"], bool)
    assert "_generated_at" in body

    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get("/api/monitor/bootstrap", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers.get("etag") == etag
    assert not r2.content


def test_endpoint_news_limit(client, monkeypatch):
    items = [
        {"title": "big story", "importance": 0.9},
        {"title": "small story", "importance": 0.4},
    ]
    monkeypatch.setattr(dashboard_app, "_monitor_news_fetcher", lambda limit=24: items)
    r = client.get("/api/monitor/news?limit=1")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["importance"] == 0.9
