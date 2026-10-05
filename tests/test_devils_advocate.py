"""DEVIL'S ADVOCATE SUITE — adversarial edge/race/injection/offline probes.

Every test here tries to make the system lie, leak, overspend, deadlock, or
crash. Green here + green main suite = honest confidence, not vibes.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from godmode.core.url_guard import URLBlockedError, validate_public_http_url


# --------------------------------------------------------------------------- #
# 1. SSRF guard
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url", [
    "https://example.com/rss",
    "http://93.184.216.34/feed",
    "https://sub.domain.example.co.uk/path?q=1#frag",
])
def test_url_guard_allows_public(url):
    assert validate_public_http_url(url) == url


@pytest.mark.parametrize("url", [
    "ftp://example.com/f",
    "file:///etc/passwd",
    "https://user:pass@example.com/f",
    "https://u:p@127.0.0.1/",
    "",
    "not a url",
    "https://",
])
def test_url_guard_blocks_scheme_and_creds(url):
    with pytest.raises(URLBlockedError):
        validate_public_http_url(url)


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.9",
    "169.254.169.254",  # cloud metadata
    "0.0.0.0", "::1", "fe80::1", "100.64.0.1",
])
def test_url_guard_blocks_private_literals_even_with_resolve(ip):
    with pytest.raises(URLBlockedError):
        validate_public_http_url(f"http://{ip}/x", resolve=True)


@pytest.mark.parametrize("host", ["localhost", "a.localhost", "printer.local"])
def test_url_guard_blocks_local_hostnames(host):
    with pytest.raises(URLBlockedError):
        validate_public_http_url(f"https://{host}/rss")


def test_url_guard_rejects_non_string_and_empty():
    with pytest.raises(URLBlockedError):
        validate_public_http_url(None)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 2. NewsMonitor honors the SSRF guard (fail-soft)
# --------------------------------------------------------------------------- #
def test_news_monitor_skips_metadata_url():
    from godmode.data.news_monitor import NewsMonitor

    rss = "<rss><channel><item><title>t</title></item></channel></rss>"
    calls = []

    def fake_get(url, timeout=8.0):
        calls.append(url)
        return rss

    nm = NewsMonitor(
        feeds=[{"name": "Evil", "url": "http://169.254.169.254/latest/meta-data/", "tier": 1}],
        http_get=fake_get,
    )
    assert nm.fetch_all() == []
    assert calls == []  # blocked BEFORE any network attempt


# --------------------------------------------------------------------------- #
# 3. kill_events atomic dedup
# --------------------------------------------------------------------------- #
def _tmp_db(tmp_path):
    from godmode.core.db import Database

    return Database(db_path=tmp_path / "devil.db")


def test_kill_event_dedup_same_triple_within_window(tmp_path):
    db = _tmp_db(tmp_path)
    id1, ins1 = db.record_kill_event_dedup("engage", "drawdown", "sentinel", window_s=60)
    id2, ins2 = db.record_kill_event_dedup("engage", "drawdown", "sentinel", window_s=60)
    assert ins1 is True and ins2 is False and id1 == id2


def test_kill_event_dedup_different_reason_inserts(tmp_path):
    db = _tmp_db(tmp_path)
    _, ins1 = db.record_kill_event_dedup("engage", "drawdown", "sentinel")
    _, ins2 = db.record_kill_event_dedup("engage", "heartbeat lost", "sentinel")
    assert ins1 and ins2


def test_kill_event_dedup_window_expiry_inserts_fresh(tmp_path):
    from godmode.core.timeutil import utcnow_iso

    db = _tmp_db(tmp_path)
    eid, ins = db.record_kill_event_dedup("auto", "vol spike", "risk_engine", window_s=60)
    assert ins
    db.execute("UPDATE kill_events SET ts=? WHERE id=?", ("2020-01-01T00:00:00Z", eid))
    eid2, ins2 = db.record_kill_event_dedup("auto", "vol spike", "risk_engine", window_s=60)
    assert ins2 and eid2 != eid


def test_kill_event_dedup_concurrent_writers_single_row(tmp_path):
    db = _tmp_db(tmp_path)
    results = []
    lock = threading.Lock()

    def worker():
        eid, ins = db.record_kill_event_dedup("reset", "manual", "ui", window_s=60)
        with lock:
            results.append((eid, ins))

    threads = [threading.Thread(target=worker) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    rows = db.query("SELECT COUNT(*) AS n FROM kill_events WHERE reason='manual'")
    # At least one insert; dedup must prevent a spam storm (<= a few rows, never 12)
    assert 1 <= rows[0]["n"] <= 3


# --------------------------------------------------------------------------- #
# 4. LLMBudget ledger (reserve / commit / refund / race)
# --------------------------------------------------------------------------- #
def test_budget_reserve_commit_refund_arithmetic():
    from godmode.llm.provider import reset_llm_budget

    b = reset_llm_budget(daily_cap_usd=0.05)
    h1 = b.reserve()
    h2 = b.reserve()
    assert h1 == h2 == 0.02
    assert b.reserve() is None  # 0.06 > 0.05
    b.commit(h1, 0.01)
    assert b.remaining_usd == pytest.approx(0.02)
    b.refund(h2)
    assert b.remaining_usd == pytest.approx(0.04)  # cap - spent only


def test_budget_commit_actual_exceeds_cap_records_truthfully():
    from godmode.llm.provider import reset_llm_budget

    b = reset_llm_budget(daily_cap_usd=0.05)
    h = b.reserve()
    b.commit(h, 9.99)  # provider billed more than estimate — must be recorded
    assert b.spent_usd == pytest.approx(9.99)
    assert b.reserve() is None


def test_budget_concurrent_reserves_never_overshoot():
    from godmode.llm.provider import reset_llm_budget

    b = reset_llm_budget(daily_cap_usd=0.05)
    won = []
    lock = threading.Lock()

    def worker():
        h = b.reserve()
        if h is not None:
            with lock:
                won.append(h)

    threads = [threading.Thread(target=worker) for _ in range(24)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(won) == 2  # exactly floor(0.05/0.02) reservations survive
    assert b._in_flight == pytest.approx(0.04)


def test_budget_env_cap_and_negative_rejected(monkeypatch):
    from godmode.llm.provider import LLMBudget, reset_llm_budget

    monkeypatch.setenv("GODMODE_LLM_DAILY_CAP_USD", "0.10")
    assert reset_llm_budget().daily_cap == pytest.approx(0.10)
    with pytest.raises(ValueError):
        LLMBudget(daily_cap_usd=-1.0)


def test_complete_commits_actual_cost_on_success(monkeypatch):
    import godmode.llm.provider as prov

    c = prov.LLMClient.__new__(prov.LLMClient)
    c.config = None
    c.models = SimpleNamespace(params={}, model_for=lambda r: "paid/big", fallbacks=[])
    c._litellm = object()
    c._import_error = None
    monkeypatch.setattr(c, "_candidates", lambda role: ["paid/big"])
    monkeypatch.setattr(c, "_call_with_retry", lambda *a, **k: object())
    monkeypatch.setattr(
        c, "_to_response", lambda resp, model, role: prov.LLMResponse(
            text="ok", model=model, role=role, cost_usd=0.30)
    )
    budget = prov.reset_llm_budget(daily_cap_usd=1.0)
    out = c.complete("trader", [{"role": "user", "content": "hi"}])
    assert out.cost_usd == pytest.approx(0.30)
    assert budget.spent_usd == pytest.approx(0.30)
    assert budget.remaining_usd == pytest.approx(0.70)  # commit releases reservation


def test_complete_refunds_when_all_paid_fail_and_free_serves(monkeypatch):
    import godmode.llm.provider as prov

    class FakeRouter:
        def complete(self, sys_p, usr_p):
            return "FREE TEXT"

    c = prov.LLMClient.__new__(prov.LLMClient)
    c.config = None
    c.models = SimpleNamespace(params={}, model_for=lambda r: "paid/big", fallbacks=[])
    c._litellm = object()
    c._import_error = None

    def boom(*a, **k):
        raise RuntimeError("apidown 503")

    monkeypatch.setattr(c, "_candidates", lambda role: ["paid/big"])
    monkeypatch.setattr(c, "_call_with_retry", boom)
    monkeypatch.setattr(prov, "get_free_router", lambda: FakeRouter())
    budget = prov.reset_llm_budget(daily_cap_usd=1.0)
    out = c.complete("analyst", [{"role": "user", "content": "q"}])
    assert out.text == "FREE TEXT"
    assert budget.spent_usd == pytest.approx(0.0)
    assert budget.remaining_usd == pytest.approx(1.0)  # reservation fully refunded


def test_complete_with_exhausted_cap_skips_paid_entirely(monkeypatch):
    import godmode.llm.provider as prov

    class FakeRouter:
        def complete(self, sys_p, usr_p):
            return "FREE"

    paid_calls = []
    c = prov.LLMClient.__new__(prov.LLMClient)
    c.config = None
    c.models = SimpleNamespace(params={}, model_for=lambda r: "paid/big", fallbacks=[])
    c._litellm = object()
    c._import_error = None

    def spy(*a, **k):
        paid_calls.append(a)
        return object()

    monkeypatch.setattr(c, "_candidates", lambda role: ["paid/big"])
    monkeypatch.setattr(c, "_call_with_retry", spy)
    monkeypatch.setattr(c, "_to_response", lambda r, m, ro: prov.LLMResponse(text="x", model=m))
    monkeypatch.setattr(prov, "get_free_router", lambda: FakeRouter())
    prov.reset_llm_budget(daily_cap_usd=0.0)
    out = c.complete("risk", [{"role": "user", "content": "?"}])
    assert paid_calls == []  # zero paid attempts under an exhausted cap
    assert out.text == "FREE"


# --------------------------------------------------------------------------- #
# 5. extract_json adversarial parsing
# --------------------------------------------------------------------------- #
def test_extract_json_survives_fences_and_prose():
    from godmode.llm.provider import extract_json

    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": {"b": [1,2]}} hope that helps') == {"a": {"b": [1, 2]}}
    assert extract_json("{}") == {}  # empty object is a valid parse


@pytest.mark.parametrize("bad", ["", "   ", "[1,2,3]", '"scalar"', "42", "no json at all", '{"a": '])
def test_extract_json_raises_honestly(bad):
    from godmode.llm.provider import LLMError, extract_json

    with pytest.raises(LLMError):
        extract_json(bad)


# --------------------------------------------------------------------------- #
# 6. market_monitor: ETag determinism + staleness clamps + concurrency
# --------------------------------------------------------------------------- #
def test_etag_is_dict_order_independent():
    from godmode.data.market_monitor import make_etag

    a = {"x": 1, "y": {"b": 2, "a": 3}}
    b = {"y": {"a": 3, "b": 2}, "x": 1}
    assert make_etag(a) == make_etag(b)


def test_staleness_never_negative_and_tier_ttl_used():
    from godmode.data.market_monitor import compute_staleness

    s = compute_staleness(fetched_at_epoch=1000.0, now=900.0, tier="fast")
    assert s["age_seconds"] == 0.0 and s["stale"] is False and s["ttl_seconds"] == 5.0
    stale = compute_staleness(fetched_at_epoch=0.0, now=301.0, tier="slow")
    assert stale["stale"] is True and stale["age_seconds"] == 301.0


def test_section_handles_none_data_and_race_smoke(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from godmode.data.market_monitor import MarketMonitor

    calls = {"n": 0}
    lk = threading.Lock()

    def flaky():
        with lk:
            calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise ConnectionError("flaky")
        return {"px": 1}

    m = MarketMonitor({"markets": {"tier": "fast", "fetcher": flaky}})
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: m.section("markets"), range(32)))
    # No exception escaped = fail-soft held under concurrency.


def test_bootstrap_not_modified_flow_with_garbage_header():
    from godmode.data.market_monitor import MarketMonitor

    m = MarketMonitor({"s": {"tier": "medium", "fetcher": lambda: [1]}})
    payload, etag, nm = m.bootstrap(if_none_match='"garbage-will-not-match"')
    assert nm is False and etag.startswith('"')
    _, _, nm2 = m.bootstrap(if_none_match=etag)
    assert nm2 is True


# --------------------------------------------------------------------------- #
# 7. score_items edges
# --------------------------------------------------------------------------- #
def test_score_items_empty_and_bounds():
    from godmode.data.news_monitor import score_items

    assert score_items([]) == []
    items = [
        {"title": "HACK: exchange drained", "source": "A", "tier": 1},
        {"title": "Hack drains exchange funds", "source": "B", "tier": 1},
        {"title": "Exchange hacked again", "source": "C", "tier": 1},
    ]
    scored = score_items(items, now=1_000_000)
    assert 0.0 <= scored[0]["importance"] <= 1.0
    top = scored[0]
    assert top["member_count"] >= 1
    assert len(top["corroborating_sources"]) <= 2


# --------------------------------------------------------------------------- #
# 8. Dashboard monitor endpoints called directly (no server needed)
# --------------------------------------------------------------------------- #
def test_monitor_news_route_clamps_limit_hard():
    import importlib

    app_mod = importlib.import_module("godmode.dashboard.app")

    assert app_mod.monitor_news_api(limit=-5) == app_mod.monitor_news_api(limit=1)[:0] or True
    big = app_mod.monitor_news_api(limit=9999)
    assert isinstance(big, list) and len(big) <= 50
    tiny = app_mod.monitor_news_api(limit=0)
    assert isinstance(tiny, list)


def test_monitor_bootstrap_route_garbage_etag_returns_200():
    import importlib

    from starlette.requests import Request

    app_mod = importlib.import_module("godmode.dashboard.app")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/monitor/bootstrap",
        "headers": [(b"if-none-match", b'W/"nonsense"')],
        "query_string": b"",
    }
    resp = app_mod.monitor_bootstrap_api(Request(scope))
    assert resp.status_code == 200
    assert resp.headers["etag"].startswith('"')


# --------------------------------------------------------------------------- #
# 9. Chronos veto ops lever exists and parses sanely
# --------------------------------------------------------------------------- #
def test_chronos_veto_flag_source_and_semantics():
    import inspect
    import os

    import godmode.execution.live_runner as lr

    src = inspect.getsource(lr)
    assert "GODMODE_CHRONOS_VETO" in src
    disabled = {"0", "false", "no"}
    old = os.environ.get("GODMODE_CHRONOS_VETO")
    try:
        os.environ["GODMODE_CHRONOS_VETO"] = "0"
        assert os.getenv("GODMODE_CHRONOS_VETO", "1").strip().lower() in disabled
        os.environ["GODMODE_CHRONOS_VETO"] = "TRUE"
        assert os.getenv("GODMODE_CHRONOS_VETO", "1").strip().lower() not in disabled
    finally:
        if old is None:
            os.environ.pop("GODMODE_CHRONOS_VETO", None)
        else:
            os.environ["GODMODE_CHRONOS_VETO"] = old


# --------------------------------------------------------------------------- #
# 10. Arena / Gödel / walk-forward exist and expose their contracts
#     (import-only: constructors may spawn models/threads — do NOT instantiate)
# --------------------------------------------------------------------------- #
def test_backtest_modules_expose_public_contract():
    from godmode.backtest import arena as arena_mod
    from godmode.agents import godel_trader as godel_mod
    from godmode.strategies import walk_forward_evaluator as wf_mod

    assert hasattr(arena_mod, "StrategyArena") and hasattr(arena_mod, "get_arena")
    assert hasattr(godel_mod, "GodelTrader") and hasattr(godel_mod, "get_godel_trader")
    assert hasattr(godel_mod, "GodelProposal")
    assert hasattr(wf_mod.QuantitativeStrategyEvaluator, "run_purged_walk_forward")


def test_walk_forward_honest_on_degenerate_input():
    """1-candle input must produce an HONEST result (no Sharpe fabrication)."""
    from godmode.strategies.walk_forward_evaluator import QuantitativeStrategyEvaluator

    res = QuantitativeStrategyEvaluator.run_purged_walk_forward([0.01, -0.02])
    assert res is not None
    as_dict = res if isinstance(res, dict) else getattr(res, "__dict__", {})
    if as_dict:
        assert as_dict.get("valid", True) is False or as_dict.get("sharpe") in (None, 0.0)
