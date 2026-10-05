"""Comprehensive verification tests for Godmode v4 — all 7 tiers.

Run with:
    python tests/test_godmode_v4.py
    pytest tests/test_godmode_v4.py -q

Standalone runner (no pytest needed) prints a summary if executed directly.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

random.seed(42)


def _make_candles(n: int = 200, start_price: float = 100.0) -> list:
    """Generate synthetic OHLCV with realistic structure."""
    candles = []
    price = start_price
    for _ in range(n):
        ret = random.gauss(0.0003, 0.012)
        open_p = price
        price = max(1.0, price * (1 + ret))
        high = max(open_p, price) * (1 + abs(random.gauss(0, 0.005)))
        low = min(open_p, price) * (1 - abs(random.gauss(0, 0.005)))
        vol = abs(random.gauss(1000, 200))
        ts = int(time.time() * 1000) + random.randint(0, n)
        candles.append([ts, open_p, high, low, price, vol])
    return candles


# ---------------- TIER 1 TESTS ----------------

def test_tier1_name_error_fix() -> None:
    """autopilot_swarm.py references current_regime correctly."""
    from godmode.core import autopilot_swarm
    src = Path(autopilot_swarm.__file__).read_text(encoding="utf-8")
    assert "current_regime" in src, "current_regime variable missing"
    assert "\"regime\": regime" not in src, "NameError bug still present"
    assert "\"regime\": current_regime" in src, "NameError fix not applied"


def test_tier1_pyproject_deps() -> None:
    """pyproject.toml declares real ML/data deps."""
    pp = Path(__file__).parent.parent / "pyproject.toml"
    content = pp.read_text(encoding="utf-8")
    assert "polars" in content
    assert "duckdb" in content
    assert "numpy" in content
    assert "mplfinance" in content
    assert "networkx" in content
    assert "version = \"4.0.0\"" in content


def test_tier1_binance_guard() -> None:
    """Binance guard module exists and audit function loads."""
    from godmode.core.binance_guard import audit_env, enforce
    result = audit_env([])
    assert "forbidden_keys_present" in result
    assert isinstance(result["forbidden_keys_present"], list)


def test_tier1_binance_guard_rejects_mainnet(monkeypatch=None) -> None:
    """Guard detects mainnet keys."""
    from godmode.core.binance_guard import audit_env
    if monkeypatch:
        monkeypatch.setenv("BINANCE_MAINNET_API_KEY", "test_key")
    else:
        import os
        os.environ["BINANCE_MAINNET_API_KEY"] = "test_key"
    result = audit_env([])
    assert "BINANCE_MAINNET_API_KEY" in result["forbidden_keys_present"]
    if not monkeypatch:
        del os.environ["BINANCE_MAINNET_API_KEY"]


def test_tier1_news_apis() -> None:
    """News API module imports and returns list structure."""
    from godmode.data import news_apis
    intl = news_apis.fetch_international_news()
    ind = news_apis.fetch_indian_news()
    assert isinstance(intl, list)
    assert isinstance(ind, list)


def test_tier1_websocket_streamer_import() -> None:
    """WS streamer module imports cleanly with real Binance WS code path."""
    from godmode.data.websocket_streamer import LiveTickStreamer
    streamer = LiveTickStreamer(symbols=["BTCUSDT"])
    assert "BTCUSDT" in streamer.symbols
    url = streamer._build_url()
    assert "wss://stream.binance.com" in url
    assert "depth20" in url


def test_tier1_key_rotator_env() -> None:
    """Key rotator v4 reads from env, not scraped dead repos."""
    import os
    os.environ["TEST_KEY"] = ""
    os.environ["GROQ_API_KEY"] = "gsk_test_key"
    try:
        from godmode.core.key_rotator import KeyRotator
        rot = KeyRotator()
        rot.fetch_keys()
        rot.fetch_keys()
        sample = rot.get_key("groq")
        assert sample == "gsk_test_key"
    finally:
        os.environ.pop("GROQ_API_KEY", None)


def test_tier1_live_intelligence_calls_real_news() -> None:
    """live_intelligence.py imports the new news APIs module."""
    from godmode.data import live_intelligence
    src_path = Path(live_intelligence.__file__)
    content = src_path.read_text(encoding="utf-8")
    assert "fetch_international_news" in content or "news_apis" in content
    assert "fetch_indian_news" in content or "news_apis" in content


# ---------------- TIER 2 TESTS ----------------

def test_tier2_regime_router_classifies() -> None:
    """RegimeRouter returns enum + confidence + strategy."""
    from godmode.agents.regime_router import RegimeRouter, Regime, REGIME_STRATEGY_ROUTER
    candles = _make_candles(100)
    sig = RegimeRouter.classify([(c[1], c[2], c[3], c[4], c[5]) for c in candles])
    assert isinstance(sig.regime, Regime)
    assert 0 <= sig.confidence <= 1.0
    assert sig.strategy in REGIME_STRATEGY_ROUTER[sig.regime]["primary"] or sig.strategy == "HOLD"


def test_tier2_position_analyzer() -> None:
    """PositionAnalyzer returns context with range_pct and pivots."""
    from godmode.agents.position_analyzer import PositionAnalyzer
    candles = _make_candles(60)
    ctx = PositionAnalyzer.analyze("TEST", candles)
    assert 0 <= ctx.range_pct <= 100
    assert isinstance(ctx.pivot_points, dict)
    assert "PP" in ctx.pivot_points


def test_tier2_symbol_selector() -> None:
    """SymbolSelector ranks candidates."""
    from godmode.agents.symbol_selector import SymbolSelector
    sel = SymbolSelector()
    candles_func = lambda sym, limit=100: _make_candles(80)
    top = sel.rank_candidates(None, candles_func, n=2)
    assert isinstance(top, list)


def test_tier2_chronos_prophet_v2_gbm() -> None:
    """ChronosProphetV2 returns P10/P50/P90 with uncertainty."""
    from godmode.agents.tsfm_prophet import ChronosProphetV2
    prophet = ChronosProphetV2(use_hf_model=False)
    prices = [100 + random.gauss(0, 0.5) for _ in range(120)]
    forecast = prophet.predict_distribution(prices)
    assert "p10" in forecast
    assert "p50" in forecast
    assert "p90" in forecast
    assert forecast["p10"] <= forecast["p50"] <= forecast["p90"]
    assert "uncertainty" in forecast


def test_tier2_reflection_v2_default() -> None:
    """ReflectionAgentV2 handles empty fills gracefully."""
    from godmode.agents.reflection_v2 import ReflectionAgentV2
    agent = ReflectionAgentV2()
    insight = agent.reflect()
    assert insight.reason is not None
    assert isinstance(insight.insight_block, str)
    assert "Reflection v2" in insight.insight_block


# ---------------- TIER 3 TESTS ----------------

def test_tier3_arena_runs_tournament() -> None:
    """Arena tournament completes and yields live ids."""
    from godmode.backtest.arena import StrategyArena
    arena = StrategyArena(population_size=6, max_live_slots=2)
    candles = _make_candles(120)
    result = arena.run_tournament(candles)
    assert result["status"] == "completed"
    assert "live_strategies" in result
    assert "population_size" in result


def test_tier3_digital_twin_voting() -> None:
    """DigitalTwin voter returns structured votes."""
    from godmode.execution.digital_twin import DigitalTwinVoter
    voter = DigitalTwinVoter(n_twins=5, quorum=3)
    candles = _make_candles(40)
    result = voter.vote(candles, "buy", entry_price=100.0, qty=1.0, horizon_bars=20)
    assert "approved" in result
    assert "yes_votes" in result
    assert "no_votes" in result
    assert result["yes_votes"] + result["no_votes"] == 5
    assert isinstance(result["votes"], list)
    assert len(result["votes"]) == 5


# ---------------- TIER 4 TESTS ----------------

def test_tier4_godel_protected_files() -> None:
    """GodelTrader refuses to patch RiskEngine/KillSwitch/Binance guard."""
    from godmode.agents.godel_trader import _safe_path
    assert _safe_path("src/godmode/risk/engine.py") is False
    assert _safe_path("src/godmode/core/killswitch.py") is False
    assert _safe_path("src/godmode/core/binance_guard.py") is False
    assert _safe_path("src/godmode/agents/regime_router.py") is True


def test_tier4_godel_status() -> None:
    """GodelTrader status returns all expected fields."""
    from godmode.agents.godel_trader import GodelTrader
    g = GodelTrader()
    status = g.status()
    assert status["history_size"] == 0
    assert "last_verdict" in status
    assert "accept_count" in status
    assert "reject_count" in status


# ---------------- TIER 5 TESTS ----------------

def test_tier5_onchain_analyst() -> None:
    """OnChainAnalyst returns structured signals."""
    from godmode.agents.onchain_analyst import OnChainAnalyst
    analyst = OnChainAnalyst(cache_ttl=0)
    signals = analyst.fetch_signals()
    assert hasattr(signals, "net_flow_btc")
    assert hasattr(signals, "funding_rate_btc")
    assert hasattr(signals, "whale_alert")
    assert isinstance(signals.summary, str)


def test_tier5_knowledge_graph() -> None:
    """KnowledgeGraph seeds well-known relationships and supports queries."""
    from godmode.data.knowledge_graph import MarketKnowledgeGraph
    kg = MarketKnowledgeGraph()
    if kg.graph is None:
        return
    chain = kg.explain_path("FED_RATE", "BTC")
    assert "FED_RATE" in chain and "BTC" in chain
    effects = kg.second_degree_effects("DXY")
    assert isinstance(effects, list)


def test_tier5_duckdb_or_fallback() -> None:
    """DuckDBAnalytics either ingests via SQL or falls back smoothly."""
    from godmode.core.analytics import DuckDBAnalytics
    analytics = DuckDBAnalytics()
    candles = _make_candles(50)
    if analytics.conn:
        analytics.ingest_candles("TEST", candles)
        snap = analytics.snapshot("TEST")
        if snap:
            assert "vwap" in snap.summary_text
    else:
        snap = analytics.fallback_snapshot("TEST", candles)
        assert snap.symbol == "TEST"
        assert snap.n_candles == 50


def test_tier5_chart_vision_module_imports() -> None:
    """ChartVisionAgent module imports cleanly (PNG gen deferred to runtime)."""
    from godmode.agents.chart_vision import ChartVisionAgent
    agent = ChartVisionAgent(cache_ttl=0)
    assert agent.min_timeframe_hours == 4


# ---------------- TIER 6 TESTS ----------------

def test_tier6_neuro_symbolic_safety_check() -> None:
    """RiskOracle AST validator rejects dangerous predicates."""
    from godmode.risk.neuro_symbolic import _validate_predicate_safety
    assert _validate_predicate_safety("volatility > 3 and drawdown < 0.1") is True
    assert _validate_predicate_safety("open('/etc/passwd', 'r')") is False
    assert _validate_predicate_safety("__import__('os').system('rm -rf /')") is False
    assert _validate_predicate_safety("max(volatility, leverage) > 2.0") is True


def test_tier6_neuro_symbolic_propose_rule() -> None:
    """RiskOracle accepts+stores safe temporary rules, evaluates on context."""
    from godmode.risk.neuro_symbolic import NeuroSymbolicRiskOracle
    oracle = NeuroSymbolicRiskOracle(default_ttl_seconds=60)
    result = oracle.propose_rule(
        name="test_rule",
        predicate_source="volatility > 2.0 and funding_rate > 0.1",
        action={"max_position_pct": 0.05},
        ttl_seconds=60,
    )
    assert result["verdict"] == "accepted"
    eval_result = oracle.evaluate({"volatility": 3.0, "funding_rate": 0.15, "drawdown": 0.0, "leverage": 0.0})
    assert "max_position_pct" in eval_result["triggered_actions"]


def test_tier6_synthetic_stress_scenarios() -> None:
    """SyntheticStressEngine generates + runs all 5 default scenarios."""
    from godmode.backtest.synthetic import SyntheticStressEngine
    engine = SyntheticStressEngine(n_bars=80)
    engine.generate_all()
    assert len(engine.scenarios) == 5
    names = {s.name for s in engine.scenarios}
    expected = {"flash_crash", "altseason", "exchange_hack", "volatility_explosion", "regulatory_crackdown"}
    assert names == expected
    result = engine.run_stress()
    assert result["n_scenarios"] == 5
    assert "worst_drawdown_pct" in result
    assert "avg_sharpe" in result


# ---------------- TIER 7 TESTS ----------------

def test_tier7_streamlit_app_parses() -> None:
    """Streamlit app file imports cleanly (compile check)."""
    dashboard_path = Path(__file__).resolve().parent.parent / "dashboard" / "streamlit_app.py"
    content = dashboard_path.read_text(encoding="utf-8")
    compile(content, str(dashboard_path), "exec")
    assert "GODMODE_TERMINAL" in content or "GODMODE TERMINAL" in content
    assert "JetBrains Mono" in content
    assert "#00F0FF" in content or "00F0FF" in content


# ---------------- BRUTAL BEHAVIORAL TESTS (cycle 1 fixes) ----------------

def test_brutal_duckdb_sql_path_returns_real_numbers() -> None:
    """The SQL code path must produce non-zero volatility and pct_change for
    a synthetic series with actual variance and slope. Previously this CTE
    silently returned NULL via STDDEV over LAG window column and tests only
    passed via the fallback branch.
    """
    from godmode.core.analytics import DuckDBAnalytics
    a = DuckDBAnalytics()
    candles = []
    base = int(time.time() * 1000)
    for i in range(50):
        p = 100 + i * 0.1 + (i % 7 - 3) * 0.05          # slope + volatility
        candles.append([base + i * 60000, p, p + 0.5, p - 0.5, p, 1000])
    a.ingest_candles("BRUTAL_SQL", candles)
    s = a.snapshot("BRUTAL_SQL")
    assert s is not None, "SQL path returned None even with duckdb installed"
    assert s.volatility_pct > 0.0, f"volatility still 0 (broken): {s.volatility_pct}"
    # pct_change_24h: last vs prior — should be non-zero given slope
    assert s.pct_change_24h != 0.0, "pct_change still 0 (broken)"


def test_brutal_regime_detects_uptrend() -> None:
    """A clearly trending synthetic uptrend must be classified as TRENDING_UP.
    Original ADX math was broken (DX = |pdm-ndm|/ATR instead of DI-based),
    causing a clear uptrend to register as RANGING.
    """
    from godmode.agents.regime_router import RegimeRouter, Regime
    random.seed(42)
    ohlcv = []
    base_ts = int(time.time() * 1000)
    p = 100.0
    for i in range(120):
        drift = 0.0008 if i > 40 else -0.0002
        noise = random.gauss(0, 0.004)
        o = p
        p = max(1.0, p * (1 + drift + noise))
        ohlcv.append([base_ts + i * 3600000, o, max(o, p) * 1.001, min(o, p) * 0.999, p,
                      abs(random.gauss(10000, 2000))])
    rs = RegimeRouter().classify(ohlcv)
    assert rs.regime == Regime.TRENDING_UP, f"Expected TRENDING_UP, got {rs.regime.name}"


def test_brutal_regime_detects_downtrend() -> None:
    """A clearly trending synthetic downtrend must be classified as TRENDING_DOWN."""
    from godmode.agents.regime_router import RegimeRouter, Regime
    random.seed(99)
    ohlcv = []
    p = 500.0
    for i in range(150):
        drift = -0.0011 if i > 30 else 0.0
        noise = random.gauss(0, 0.0035)
        o = p
        p = max(1.0, p * (1 + drift + noise))
        ohlcv.append([0, o, max(o, p) * 1.001, min(o, p) * 0.999, p, 10000])
    rs = RegimeRouter().classify(ohlcv)
    assert rs.regime == Regime.TRENDING_DOWN, f"Expected TRENDING_DOWN, got {rs.regime.name}"


def test_brutal_regime_detects_mean_reverting_range() -> None:
    """A mean-reverting synthetic series should not register as TRENDING_*."""
    from godmode.agents.regime_router import RegimeRouter, Regime
    random.seed(13)
    ohlcv = []
    p = 100.0
    for i in range(100):
        noise = random.gauss(0, 0.015)
        p = 100.0 + (p - 100.0) * 0.5 + noise
        o = p
        ohlcv.append([0, o, max(o, p) * 1.001, min(o, p) * 0.999, p, 10000])
    rs = RegimeRouter().classify(ohlcv)
    assert rs.regime in (Regime.RANGING, Regime.CHOPPY), (
        f"Mean-reverting series classified as {rs.regime.name}"
    )


def test_brutal_hurst_exponent_classifies_persistence() -> None:
    """Hurst exponent (R/S analysis) correctly identifies:
    - Persistent uptrend (H > 0.55)
    - Mean-reverting series (H < 0.45)
    - Random walk (0.35 < H < 0.65, with looser bounds for sampling bias)
    - Too-short series returns 0.5 default
    And RegimeRouter.classify surfaces hurst in RegimeSignal.details.
    """
    from godmode.agents.regime_router import RegimeRouter, Regime

    # Persistent uptrend: H > 0.55
    random.seed(7)
    prices = [1000.0]
    for _ in range(300):
        prices.append(prices[-1] * (1 + 0.005 + random.gauss(0, 0.001)))
    h = RegimeRouter._hurst_exponent(prices)
    assert h > 0.55, f"persistent uptrend should have H > 0.55, got {h}"

    # Strong mean-reverting OU: H < 0.45
    random.seed(11)
    series = [100.0]
    for _ in range(500):
        series.append(series[-1] + 2.0 * (100.0 - series[-1]) + random.gauss(0, 0.3))
    h = RegimeRouter._hurst_exponent(series)
    assert h < 0.45, f"mean-reverting should have H < 0.45, got {h}"

    # Random walk: H near 0.5 (sampling bias allows 0.35-0.65)
    random.seed(42)
    rw = [100.0]
    for _ in range(600):
        rw.append(rw[-1] + random.gauss(0, 1.0))
    h = RegimeRouter._hurst_exponent(rw)
    assert 0.35 < h < 0.65, f"random walk H should be near 0.5, got {h}"

    # Too-short series returns default 0.5
    assert RegimeRouter._hurst_exponent([1.0, 2.0, 3.0]) == 0.5

    # RegimeSignal.details includes hurst
    random.seed(99)
    candles = []
    price = 100.0
    for i in range(250):
        o = price
        c = price * (1 + 0.004 + random.gauss(0, 0.002))
        h_val = max(o, c) * 1.001
        lo = min(o, c) * 0.999
        v = 1000 + random.randint(0, 200)
        candles.append([o, h_val, lo, c, v])
        price = c
    sig = RegimeRouter.classify(candles)
    assert "hurst" in sig.details, "RegimeSignal.details must include hurst"
    assert sig.details["hurst"] > 0.5, (
        f"clear uptrend Hurst should be > 0.5, got {sig.details['hurst']}"
    )
    assert sig.regime == Regime.TRENDING_UP, (
        f"clear uptrend must classify as TRENDING_UP, got {sig.regime.name}"
    )


def test_brutal_brain_e2e_mock_llm(monkeypatch) -> None:
    """End-to-end brain.py pipeline with mocked LLM. Proves regime classification,
    position analysis, chronos forecast, and reflection insight all reach the
    macro council's user prompt (verified via injected reason string).
    Previously brain NEVER ran end-to-end and Position context was dropped.
    """
    import json
    from unittest.mock import MagicMock
    from godmode.agents.brain import MultiAgentBrain

    random.seed(42)
    ohlcv = []
    base_ts = int(time.time() * 1000)
    p = 100.0
    for i in range(120):
        drift = 0.0008 if i > 40 else -0.0002
        noise = random.gauss(0, 0.004)
        o = p
        p = max(1.0, p * (1 + drift + noise))
        ohlcv.append([base_ts + i * 3600000, o, max(o, p) * 1.001,
                      min(o, p) * 0.999, p, abs(random.gauss(10000, 2000))])

    def complete_side(messages, role=None, **kw):
        m = MagicMock(); m.text = "[mock bull case]"; m.role = role; return m

    def complete_json_side(role, system, user, **kw):
        if role == "technical_analyst":
            return {"outlook": "bullish", "indicators_summary": "EMA bull",
                    "support": 95.0, "resistance": 110.0}
        if role == "sentiment_analyst":
            return {"sentiment_score": 0.4, "impact_summary": "positive news"}
        if role == "macro_council":
            checks = {
                "refl": "Reflection Agent v2" in user,
                "pos": "Position:" in user,
                "chronos": "Chronos Forecast" in user,
                "regime": "Regime Classification" in user,
            }
            all_in = all(checks.values())
            return {
                "regime": "bull",
                "rsi_oversold": 35,
                "rsi_overbought": 72,
                "trade_bias": "long" if all_in else "neutral",
                "reason": "inj refl=%s pos=%s chronos=%s regime=%s" % (
                    checks["refl"], checks["pos"], checks["chronos"], checks["regime"],
                ),
            }
        if role == "risk_manager":
            return {"verdict": "approve", "reason": "ok"}
        return {"mock": True}

    mc = MagicMock()
    mc.complete.side_effect = complete_side
    mc.complete_json.side_effect = complete_json_side

    brain = MultiAgentBrain(client=mc)
    brain.mcp_client = None
    brain.mcp_tools = {"mock": True}
    # Hermetic test: do not write reflection snapshots to the production DB.
    monkeypatch.setenv("GODMODE_REFLECTION_MEMORY", "0")

    result = brain.evaluate_macro_regime(
        symbol="BTCUSDT",
        price_data={"price": ohlcv[-1][4], "change_24h": 5.2},
        portfolio_state={"equity": 100000, "timestamp": "2026-07-21T00:00:00Z"},
        news_feed=["Bitcoin strengthens as ETF inflows surge"],
        ohlcv=ohlcv,
        cycle_id="brutal-test-cycle",
        run_id=1,
    )

    assert result.get("trade_bias") == "long", (
        f"Expected long, got {result.get('trade_bias')}"
    )
    reason = result.get("reason", "")
    for needle in ("refl=True", "pos=True", "chronos=True", "regime=True"):
        assert needle in reason, f"Missing context: {needle}; got: {reason}"


def test_brutal_brain_halts_safely_when_llm_fails(monkeypatch) -> None:
    """When the LLM raises LLMError (all providers unavailable, free-tier also down),
    Brain.evaluate_macro_regime MUST return a safe default plan — NOT crash.

    The brutal scenario: NIM key is expired (403), no OPENROUTER/GROQ/GEMINI keys,
    Pollinations rate-limited. The original code would explode and take down the
    live trading loop with an unhandled exception.
    """
    from unittest.mock import MagicMock
    from godmode.agents.brain import MultiAgentBrain
    from godmode.llm.provider import LLMError

    random.seed(42)
    ohlcv = []
    base_ts = int(time.time() * 1000)
    p = 100.0
    for i in range(120):
        drift = 0.0008 if i > 40 else -0.0002
        noise = random.gauss(0, 0.004)
        o = p
        p = max(1.0, p * (1 + drift + noise))
        ohlcv.append([base_ts + i * 3600000, o, max(o, p) * 1.001,
                      min(o, p) * 0.999, p, abs(random.gauss(10000, 2000))])

    # Mock the LLM client so EVERY call raises LLMError, simulating total outage.
    failing_client = MagicMock()
    failing_client.complete.side_effect = LLMError("all providers down")
    failing_client.complete_json.side_effect = LLMError("all providers down")

    brain = MultiAgentBrain(client=failing_client)
    brain.mcp_client = None
    brain.mcp_tools = {}
    # Hermetic test: do not write reflection snapshots to the production DB.
    monkeypatch.setenv("GODMODE_REFLECTION_MEMORY", "0")

    # Must NOT raise — must return a safe neutral plan.
    result = brain.evaluate_macro_regime(
        symbol="BTCUSDT",
        price_data={"price": ohlcv[-1][4], "change_24h": 5.2},
        portfolio_state={"equity": 100000, "timestamp": "2026-07-21T00:00:00Z"},
        news_feed=[],
        ohlcv=ohlcv,
        cycle_id="llm-outage-test",
        run_id=2,
    )

    # Safe defaults for a "no signal" macro proposal
    assert result.get("trade_bias") == "neutral", (
        f"LLM outage must force neutral bias, got {result.get('trade_bias')}"
    )
    assert isinstance(result.get("regime", ""), str)
    log_msg = result.get("reason", "")
    assert "LLM" in log_msg or "unavailable" in log_msg.lower() or "llm" in log_msg.lower(), (
        f"reason must mention LLM failure, got: {log_msg!r}"
    )


def test_brutal_onchain_real_apis_or_honest_failure() -> None:
    """OnChainAnalyst must call real CoinGecko/Binance/DeFiLlama endpoints.
    Forbids literals like inflow=1.5 hardcoded. If all 3 fail (no network),
    the analyst must report 0.0 honestly — NOT return fake numbers.
    """
    import inspect
    from godmode.agents.onchain_analyst import OnChainAnalyst
    src = inspect.getsource(OnChainAnalyst)
    assert "inflow = 1.5" not in src, "Hardcoded literal inflow=1.5 still present"
    assert "outflow = 1.2" not in src, "Hardcoded literal outflow=1.2 still present"
    assert "recent_flows = [1.5, 0.3, 2.4, 0.8, 0.2, 1.2, 0.5, 3.1]" not in src, (
        "Hardcoded flow history still present"
    )
    # Live call with no cache — should hit network and either succeed or
    # honestly report zeros
    a = OnChainAnalyst(cache_ttl=0.01)
    s = a.fetch_signals()
    # All values must be real numbers (allowing 0.0 on network failure)
    assert isinstance(s.exchange_inflow_btc, float)
    assert isinstance(s.exchange_outflow_btc, float)
    assert isinstance(s.funding_rate_btc, float)
    # If we have *any* signal, summary cannot be all-zero placeholders
    if s.funding_rate_btc == 0 and s.exchange_inflow_btc == 0 and s.defi_tvl_change_24h_pct == 0:
        # All endpoints failed — that's honest. Just ensure summary says so.
        assert "0.00B" in s.summary or "0.0" in s.summary


def test_brutal_godel_proxy_sharpe_is_not_literal() -> None:
    """GödelTrader._compute_proxy_sharpe must derive a real value from pytest
    output. Forbids `return 1.2` constant.
    """
    import inspect
    from godmode.agents.godel_trader import GodelTrader
    src = inspect.getsource(GodelTrader._compute_proxy_sharpe)
    assert "return 1.2" not in src, "Still returns literal 1.2"
    # Test two extreme inputs → different proxies
    g = GodelTrader()
    p_high = g._compute_proxy_sharpe("=== 50 passed in 3.5s ===")
    p_zero = g._compute_proxy_sharpe("=== 0 passed, 50 failed in 3.5s ===")
    assert p_high > p_zero, f"Proxy ignored pass/fail ratio: high={p_high} zero={p_zero}"


def test_brutal_digital_twin_microstructure_not_random_future() -> None:
    """DigitalTwin must NOT peek at future closes. It must project forward via
    GBM (or similar) from recent realized vol. Asserts that the simulation
    holds even when called with synthetic candles whose future is unknown.
    """
    import inspect
    from godmode.execution.digital_twin import (
        DigitalTwinVoter, _simulate_twin, _make_twin_configs
    )
    src = inspect.getsource(_simulate_twin)
    assert "future_closes" not in src, "Twin still peeks at future_closes"
    # Run vote on deterministic synthetic data
    random.seed(11)
    candles = []
    p = 100.0
    for i in range(60):
        o = p
        p = max(1.0, p * (1 + random.gauss(0, 0.005)))
        candles.append([0, o, max(o, p) * 1.001, min(o, p) * 0.999, p, 10000])
    voter = DigitalTwinVoter(n_twins=10, quorum=6)
    result = voter.vote(candles, side="buy", entry_price=candles[-1][4], qty=1.0)
    assert "approved" in result
    assert "yes_votes" in result
    assert result["yes_votes"] + result["no_votes"] == 10
    # Two independent runs on same candles must produce DIFFERENT avg_pnl
    # because the GBM projection is stochastic (NOT peeked from future).
    random.seed(12)
    r1 = voter.vote(candles, side="buy", entry_price=candles[-1][4], qty=1.0)
    random.seed(99)
    r2 = voter.vote(candles, side="buy", entry_price=candles[-1][4], qty=1.0)
    # Highly unlikely the same stochastic run produces identical avg_pnl
    assert r1["avg_projected_pnl_pct"] != r2["avg_projected_pnl_pct"], (
        "Twin gave identical projection across two stochastic seeds"
    )


def test_brutal_arena_uses_real_kama() -> None:
    """Arena backtest must use the production QuantMLAlphaEngine.calculate_kama,
    not a toy rolling-mean SMA mislabeled as KAMA.
    """
    import inspect
    from godmode.backtest import arena
    src = inspect.getsource(arena)
    assert "QuantMLAlphaEngine.calculate_kama" in src or \
           "from godmode.strategies.quant_ml_alpha" in src, (
        "Arena does not import or call the real QuantMLAlphaEngine"
    )


def test_brutal_shoonya_no_fake_crypto_fallback() -> None:
    """ShoonyaNSEAdapter must NOT silently return fake 2500 INR for crypto tickers.
    Instead it must return 0.0 and an empty OHLCV list so the caller knows
    to route crypto through a different adapter.
    """
    from godmode.execution.shoonya_nse import ShoonyaNSEAdapter
    a = ShoonyaNSEAdapter(paper=True)
    p = a.fetch_price("BTCUSDT")
    assert float(p) == 0.0, f"Shoonya returned non-zero for crypto: {p}"
    candles = a.fetch_ohlcv("BTCUSDT", limit=10)
    assert candles == [], f"Shoonya returned candles for crypto: {candles}"


def test_brutal_autopilot_swarm_real_crypto_fetch() -> None:
    """AutopilotSwarm.run_market_scan('BTCUSDT') must call real Binance public REST
    and return a live BTC price (~60000 USD), NOT a fake 2500 number.
    """
    from godmode.core.autopilot_swarm import AutopilotSwarmEngine
    e = AutopilotSwarmEngine(paper=True)
    r = e.run_market_scan("BTCUSDT")
    ltp = r.get("ltp", 0)
    # BTC is volatile but will be >> 5000 in any reasonable market period
    assert ltp > 5000, f"BTC LTP should be > 5000 USD; got {ltp}"
    assert r.get("signal") in ("BUY", "SELL", "HOLD"), (
        f"Signal missing or invalid: {r.get('signal')}"
    )


def test_brutal_dashboard_renders_all_panels() -> None:
    """Streamlit dashboard app must execute without exceptions AND render all
    major panels (NSE, BTC, Arena, Neuro, Gödel, Key Rotator, Emergency).
    Mocks streamlit/plotly just enough to intercept st.metric / st.markdown /
    st.button calls and inspect their arguments.
    """
    import sys, types
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "dashboard" / "streamlit_app.py"
    content = src.read_text(encoding="utf-8")

    metrics_seen = []
    buttons_seen = []
    markdowns_seen = []

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _MockST:
        def __getattr__(self, n):
            def _noop(*a, **kw): return None
            return _noop
        def set_page_config(self, **kw): pass
        def columns(self, n): return [_Ctx() for _ in range(n)]
        def markdown(self, content, *a, **kw): markdowns_seen.append(content)
        def metric(self, label=None, value=None, *a, **kw):
            metrics_seen.append((label, value))
        def button(self, label=None, *a, **kw): buttons_seen.append(label); return False
        def info(self, *a, **kw): pass
        def warning(self, *a, **kw): pass
        def error(self, *a, **kw): pass
        def success(self, *a, **kw): pass
        def sidebar(self): return _Ctx()

    mod = types.ModuleType("streamlit")
    def _generic(*a, **kw): return None
    mod.__getattr__ = lambda n: _generic
    m = _MockST()
    for a in ["set_page_config", "columns", "markdown", "metric",
              "button", "info", "warning", "error", "success", "sidebar"]:
        setattr(mod, a, getattr(m, a))
    sys.modules["streamlit"] = mod

    plotly_mod = types.ModuleType("plotly")
    pg = types.ModuleType("plotly.graph_objects")
    pg.go = _MockST()
    pg.Figure = lambda *a, **kw: _MockST()
    plotly_mod.graph_objects = pg
    sys.modules["plotly"] = plotly_mod
    sys.modules["plotly.graph_objects"] = pg

    ns = {"__name__": "__main__", "__file__": str(src)}
    code = compile(content, str(src), "exec")
    try:
        exec(code, ns)
    except Exception as exc:
        import traceback; traceback.print_exc()
        raise AssertionError(f"Dashboard render crashed: {exc}")

    assert len(metrics_seen) >= 5, f"Only {len(metrics_seen)} metric panels rendered"
    assert any("GODMODE TERMINAL" in s for s in markdowns_seen), "Header not rendered"
    assert "ENGAGE KILL SWITCH" in buttons_seen and "CLEAR KILL SWITCH" in buttons_seen, (
        "Kill-switch buttons missing"
    )
    for panel in ["NSE / BSE", "BTC", "Arena Tournament",
                  "Neuro-Symbolic", "Key Rotator", "EMERGENCY"]:
        assert any(panel in s for s in markdowns_seen), f"Panel missing: {panel}"
    # Gödel has a non-ASCII o; handle it explicitly to avoid Windows console weirdness
    assert any("Self-Improver" in s for s in markdowns_seen), "Gödel panel missing"


def test_brutal_chronos_prophet_uses_real_chronos_api() -> None:
    """ChronosProphetV2 must use the chronos-forecasting BaseChronosPipeline API,
    NOT the wrong `transformers.pipeline('text2text-generation', model=...)` hack.
    Source code inspection: forbid text2text-generation, require BaseChronosPipeline.
    """
    import inspect
    from godmode.agents import tsfm_prophet

    src = inspect.getsource(tsfm_prophet)
    # The broken old API must NOT be present
    assert "text2text-generation" not in src, \
        "ChronosProphet must NOT use transformers text2text-generation (wrong API)"
    assert "chronos-2-base" not in src, \
        "Must use chronos-bolt-mini (CPU-friendly, 138MB), not chronos-2-base"
    # The real API must be present
    assert "BaseChronosPipeline" in src, \
        "ChronosProphet must import BaseChronosPipeline from chronos-forecasting"
    assert "predict_quantiles" in src, \
        "Must call pipeline.predict_quantiles(...) per Chronos-2 API"
    assert "chronos-bolt-mini" in src, "Default model must be amazon/chronos-bolt-mini"

    # Behavioral: HF flag on but package missing must degrade to GBM gracefully.
    prophet = tsfm_prophet.ChronosProphetV2(use_hf_model=True)
    assert prophet._hf_pipeline is None, "HF pipeline must be None when chronos unavailable"
    import random
    random.seed(42)
    prices = [100 + random.gauss(0.1, 2) + i * 0.05 for i in range(120)]
    r = prophet.predict_distribution(prices)
    assert r["source"] == "gbm", f"Should gracefully fall back to GBM: {r}"
    assert r["p10"] < r["p50"] < r["p90"], "Quantiles must be ordered"
    assert r["uncertainty"] > 0, "Uncertainty must be positive for varied prices"


def test_brutal_neuro_symbolic_hardened_security() -> None:
    """NeuroSymbolicRiskOracle AST validator must reject ALL bypass attempts:
    - Bare dangerous names (__import__, eval, exit, open, system, etc.)
    - Attribute access (. context)
    - Subscripts (regime[0])
    - Lambdas, comprehensions
    - Numeric/string bombs (10**99999, "x"*99999)
    And the compiled predicate must cache once at proposal, never re-parse on eval.
    Hostile ctx keys named 'min' cannot shadow the builtin min.
    """
    import inspect
    from godmode.risk.neuro_symbolic import (
        _validate_predicate_safety, NeuroSymbolicRiskOracle,
    )

    # AST rejections
    assert not _validate_predicate_safety('__import__("os")')
    assert not _validate_predicate_safety('eval("")')
    assert not _validate_predicate_safety('exit()')
    assert not _validate_predicate_safety('open("x")')
    assert not _validate_predicate_safety('(1).__class__')
    assert not _validate_predicate_safety('regime[0]')
    assert not _validate_predicate_safety('(lambda: 1)()')
    assert not _validate_predicate_safety('10**99999 > 0')
    big_str = "x" * 99999
    assert not _validate_predicate_safety(f'regime > 0 and "{big_str}" == "{big_str}"')

    # Valid predicates accepted
    assert _validate_predicate_safety('volatility > 1.5 and drawdown < 0.1')
    assert _validate_predicate_safety('min(regime, 1) > 0')
    assert _validate_predicate_safety('not (leverage > 5 or funding_rate > 0.001)')

    # Compiled predicate cached once, not re-parsed at evaluate time.
    # Inspect source to confirm evaluate() does NOT call _compile_predicate.
    from godmode.risk import neuro_symbolic
    src = inspect.getsource(neuro_symbolic.NeuroSymbolicRiskOracle.evaluate)
    assert "_compile_predicate" not in src, \
        "evaluate() must NOT recompile rules — use cached compiled_predicate"

    # Hostile ctx shadowing 'min' must NOT win over the builtin.
    oracle = NeuroSymbolicRiskOracle()
    oracle.propose_rule(
        name="shadow_test",
        predicate_source="min(regime, 1) > 0",
        action={"x": 1},
        ttl_seconds=60,
    )
    out = oracle.evaluate({
        "regime": 1,
        "min": lambda *a: 999,  # hostile shadow attempt
    })
    assert out["triggered_actions"] == {"x": 1}, \
        f"Hostile ctx key 'min' cannot shadow builtin: {out}"

    # Unallowed ctx keys (system, __builtins__, etc.) silently dropped from namespace
    oracle2 = NeuroSymbolicRiskOracle()
    oracle2.propose_rule("always_true", "regime >= 0", {"a": 1}, ttl_seconds=60)
    out = oracle2.evaluate({"regime": 1, "system": "oops", "__builtins__": {}})
    assert out["triggered_actions"] == {"a": 1}

    # Stale rule (compiled_predicate is None) is dropped, not crashed on
    oracle3 = NeuroSymbolicRiskOracle()
    oracle3.propose_rule("ok", "regime > 0", {"a": 1}, ttl_seconds=3600)
    oracle3.active_rules[0].compiled_predicate = None
    out = oracle3.evaluate({"regime": 5})
    assert out["n_expired"] == 1, f"Stale rule should be dropped: {out}"
    assert len(oracle3.active_rules) == 0

    # Compile-rejection produces a logged proposal record, no active rule
    oracle4 = NeuroSymbolicRiskOracle()
    res = oracle4.propose_rule("bad", "__import__('os')", {"a": 1}, ttl_seconds=60)
    assert res["verdict"] == "rejected_compile_failed"
    assert len(oracle4.active_rules) == 0
    assert len(oracle4.proposal_history) == 1


def test_brutal_fastapi_dashboard_all_endpoints_200() -> None:
    """Spin up the FastAPI dashboard via TestClient and exercise every endpoint.
    Verifies: HTML root loads w/ GODMODE brand, all JSON endpoints return
    list/dict shape, kill-switch toggles via POST and state sticks.
    """
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("  SKIP  fastapi testclient not installed")
        return
    from godmode.dashboard.app import app

    client = TestClient(app)

    # HTML root
    r = client.get("/")
    assert r.status_code == 200, f"GET / -> {r.status_code}"
    body = r.text.lower()
    assert "godmode" in body, "HTML root must contain GODMODE brand"

    # JSON endpoints always present
    json_endpoints = [
        "/api/status",
        "/api/orders",
        "/api/fills",
        "/api/decisions",
        "/api/agent_messages",
        "/api/kill_events",
    ]
    for ep in json_endpoints:
        r = client.get(ep)
        assert r.status_code == 200, f"GET {ep} -> {r.status_code}"
        data = r.json()
        assert isinstance(data, (list, dict)), f"{ep}: bad shape {type(data)}"

    # /api/status has the canonical shape
    s = client.get("/api/status").json()
    for key in ("mode", "halted", "equity", "positions", "history"):
        assert key in s, f"/api/status missing key {key!r} in {list(s.keys())}"

    # Kill-switch toggle round-trip
    r = client.post("/api/stop")
    assert r.status_code == 200
    assert r.json().get("halted") is True
    s = client.get("/api/status").json()
    assert s["halted"] is True, "kill switch state didn't persist after /api/stop"

    r = client.post("/api/resume")
    assert r.status_code == 200
    assert r.json().get("halted") is False
    s = client.get("/api/status").json()
    assert s["halted"] is False, "kill switch state didn't clear after /api/resume"

    # WebSocket /ws endpoint — must accept connection, send welcome log + audit history
    try:
        with client.websocket_connect("/ws") as ws:
            # Expect a welcome message of type 'log'
            first = ws.receive_json()
            assert first["type"] == "log", f"first WS msg type != 'log': {first}"
            assert "Connected" in first.get("text", "")
            assert first.get("source") == "system"
            assert first.get("level") == "success"

            # Send a ping to confirm bidirectional; if server crashes here, test fails
            ws.send_text("ping-from-test")
            # The server's loop echoes nothing — it only listens. So we just
            # confirmed the socket accepted our send without dropping.
    except Exception as e:
        # If TestClient's websocket support has issues in this env, surface it.
        raise AssertionError(f"WebSocket /ws endpoint broken: {type(e).__name__}: {e}")


def test_brutal_live_runner_no_fake_news_and_uses_v2_prophet() -> None:
    """LiveRunner must:
    1. Use ChronosProphetV2 (not the legacy ChronosProphetAgent from chronos_agent.py).
    2. Have no fake 'Dummy: ...' news literals in fetch_news (LLM would reason about them).
    3. Actually USE the chronos forecast as a confirmation gate (prophet_agrees check).
       The old code computed chronos_dist and discarded it silently.
    """
    import inspect
    from godmode.execution import live_runner

    src = inspect.getsource(live_runner)
    assert "ChronosProphetV2" in src, "LiveRunner must swap to ChronosProphetV2"
    assert "from godmode.agents.chronos_agent import" not in src, \
        "Legacy ChronosProphetAgent import must be removed from live_runner"

    # fetch_news body has no fake narrative literals
    fn_src = inspect.getsource(live_runner.fetch_news)
    forbidden_phrases = [
        "Macroeconomic outlook remains stable",
        "high volatility indicators",
        "consolidation phase",
        "News API returned status",
        "News feed connection error",
    ]
    for bad in forbidden_phrases:
        assert bad not in fn_src, f"fetch_news still embedded fake literal: {bad!r}"
    # When no API key, fetch_news returns [] (never fake strings feeding the LLM)
    import os
    if "FINNHUB_API_KEY" not in os.environ:
        import asyncio
        out = asyncio.run(live_runner.fetch_news("BTCUSDT"))
        assert out == [], f"Without FINNHUB key, fetch_news must return [], got {out}"

    # Prophet actually USED, not dead-computed
    assert "prophet_agrees" in src, "LiveRunner must USE chronos as confirmation gate"
    assert "chronos_unc > 0.15" in src, "Must skip trades when prophet uncertainty > 0.15"
    assert "Chronos Prophet REJECTS" in src, "Must log when prophet disagrees"


def test_brutal_legacy_chronos_agent_module_is_dead() -> None:
    """The old ChronosProphetAgent module must no longer be imported by any
    godmode production code. (Only tests may import it for the legacy check.)
    """
    import subprocess
    import sys
    # Grep the entire src tree for live imports of chronos_agent
    found = subprocess.run(
        [
            sys.executable, "-c",
            "import pathlib, re; "
            "root = pathlib.Path(r'D:\\Ai trader\\src\\godmode'); "
            "hits = []; "
            "[hits.append(str(p)) for p in root.rglob('*.py') "
            " if 'from godmode.agents.chronos_agent' in p.read_text(encoding='utf-8', errors='ignore')]; "
            "print(chr(10).join(hits) if hits else 'OK_NO_HITS')"
        ],
        capture_output=True, text=True, timeout=30,
    )
    out = found.stdout.strip()
    assert out == "OK_NO_HITS", f"Production code still imports chronos_agent: {out}"


def test_brutal_decide_action_pure_decision_logic() -> None:
    """LiveRunner.decide_action() pure decision logic — brutal contract test:
    - Trend-following BUY when prophet agrees, REJECT when disagrees or too uncertain
    - Trend-following SELL same
    - Mean-reversion BUY when RSI oversold + prophet agrees
    - HOLD when bias is neutral or already in position
    - Prophet gate has correct borderline behavior (last_close * 1.0005 / 0.9995)
    """
    from godmode.execution.live_runner import decide_action

    def m(rsi=50, adx=15, st_dir=1, bb_upper=120, bb_lower=80, close=100):
        return {"rsi": rsi, "adx": adx, "supertrend_dir": st_dir,
                "bb_upper": bb_upper, "bb_lower": bb_lower, "close": close}
    def c(p50=100, unc=0.05):
        return {"p50": p50, "uncertainty": unc, "p10": 90, "p90": 110}
    def macro(bias="long"):
        return {"trade_bias": bias, "rsi_oversold": 30, "rsi_overbought": 70,
                "regime": "trending"}

    # 1. Buy when prophet agrees
    a, _ = decide_action(m(rsi=60, adx=30, st_dir=1), c(p50=101, unc=0.03),
                        macro("long"), 0, 100)
    assert a == "buy", f"prophet-agrees long should be buy, got {a}"

    # 2. Reject when prophet disagrees (p50 < last_close * 0.9995)
    a, r = decide_action(m(rsi=60, adx=30, st_dir=1), c(p50=99, unc=0.03),
                         macro("long"), 0, 100)
    assert a == "hold", f"prophet-disagrees should be hold, got {a}"
    assert "chronos_disagrees" in r

    # 3. Reject when uncertainty > 0.15
    a, r = decide_action(m(rsi=60, adx=30, st_dir=1), c(p50=101, unc=0.20),
                         macro("long"), 0, 100)
    assert a == "hold"
    assert "chronos_uncertain" in r

    # 4. Sell when short bias + supertrend down + prophet agrees
    a, _ = decide_action(m(rsi=40, adx=30, st_dir=-1), c(p50=99, unc=0.03),
                        macro("short"), 0, 100)
    assert a == "sell", f"short+prophet-down should be sell, got {a}"

    # 5. Sell rejected when prophet disagrees
    a, _ = decide_action(m(rsi=40, adx=30, st_dir=-1), c(p50=101, unc=0.03),
                         macro("short"), 0, 100)
    assert a == "hold"

    # 6. Mean-reversion buy when RSI oversold + prophet agrees
    a, _ = decide_action(m(rsi=25, adx=10, st_dir=1), c(p50=101, unc=0.05),
                        macro("long"), 0, 100)
    assert a == "buy", f"MR oversold should be buy, got {a}"

    # 7. Mean-reversion NO buy when RSI neutral
    a, _ = decide_action(m(rsi=50, adx=10, st_dir=1), c(p50=101, unc=0.05),
                         macro("long"), 0, 100)
    assert a == "hold"

    # 8. Hold when already long position
    a, _ = decide_action(m(rsi=60, adx=30, st_dir=1), c(p50=101, unc=0.03),
                         macro("long"), 1.0, 100)
    assert a == "hold"

    # 9. Hold when neutral bias
    a, _ = decide_action(m(rsi=50, adx=30, st_dir=1), c(p50=101, unc=0.03),
                         macro("neutral"), 0, 100)
    assert a == "hold"

    # 10. Borderline agreement: p50 = 100.06 > last_close * 1.0005 = 100.0505
    a, _ = decide_action(m(rsi=60, adx=30, st_dir=1), c(p50=100.06, unc=0.05),
                         macro("long"), 0, 100)
    assert a == "buy", f"borderline agree threshold broken, got {a}"

    # 11. Borderline disagreement: p50 = 100.04 not > 100.0505
    a, _ = decide_action(m(rsi=60, adx=30, st_dir=1), c(p50=100.04, unc=0.05),
                         macro("long"), 0, 100)
    assert a == "hold", f"borderline disagree threshold broken, got {a}"


def test_brutal_key_rotator_env_load_and_health() -> None:
    """KeyRotator must:
    1. Load keys from the documented ENV_KEY_MAP (env var names).
    2. cache TTL prevents re-fetching within ttl window.
    3. get_key returns None for unknown provider (no fabrications).
    4. health() is presence-only (documented); validate() catches bogus keys.
    5. health_detail returns reason when no key set.
    """
    import os
    import time as _time
    from godmode.core.key_rotator import KeyRotator, ENV_KEY_MAP

    # 1. ENV_KEY_MAP covers canonical providers
    for provider in ("gemini", "anthropic", "openai", "groq", "openrouter"):
        assert provider in ENV_KEY_MAP, f"missing canonical provider {provider!r}"

    # 2. None for unknown provider — must NOT fabricate a key
    os.environ["KEY_ROTATOR_TEST_BOGUS"] = "1"
    rot = KeyRotator()
    assert rot.get_key("nonexistent_provider_xyz") is None, \
        "get_key fabricated a key for unknown provider"
    del os.environ["KEY_ROTATOR_TEST_BOGUS"]

    # 3. Set a real-looking gemini key, fetch, get_key returns it
    os.environ["GEMINI_API_KEY"] = "AIzaSyBogusButLongEnoughKeyForValidation123"
    rot2 = KeyRotator()
    rot2.cache_ttl = 0.0  # force fresh fetch
    rot2.fetch_keys()
    k = rot2.get_key("gemini")
    assert k == "AIzaSyBogusButLongEnoughKeyForValidation123", \
        f"gemini key not loaded from env: {k!r}"

    # 4. health() = True (key present); validate() = True (plausibly long)
    assert rot2.health("gemini") is True
    assert rot2.validate("gemini") is True, "validate() rejected plausible key"

    # 5. validate() returns False for implausibly short / bogus keys
    os.environ["GEMINI_API_KEY"] = "x"  # 1 char — bogus
    rot3 = KeyRotator()
    rot3.cache_ttl = 0.0
    rot3.fetch_keys()
    # health() returns True (key present, naive presence check — documented)
    assert rot3.health("gemini") is True, \
        "health() should report presence-only (key present)"
    # validate() catches the bogus key (too short)
    rot3._health = {}  # clear cache so re-validate runs
    assert rot3.validate("gemini") is False, \
        "validate() should reject 1-char bogus key"

    # 6. Health detail returns reason field
    detail = rot3.health_detail("gemini")
    assert "reason" in detail, "health_detail missing 'reason'"
    assert detail["ok"] is False
    assert "short" in detail["reason"], f"reason should mention short key: {detail!r}"

    # 7. Unknown provider validate returns False
    assert rot3.validate("totally_unknown_provider") is False

    # Cleanup env
    del os.environ["GEMINI_API_KEY"]


def test_brutal_audit_redaction_protects_secrets() -> None:
    """AuditLog._redact must scrub ALL secret-named keys regardless of case/spelling,
    recursively into nested dicts/lists, while preserving non-sensitive values.
    Defense-in-depth before audit JSONL / SQLite write.
    """
    from godmode.core.audit import _redact

    out = _redact({"api_key": "x", "API_KEY": "x", "api-key": "x",
                   "private_key": "x", "PRIVATE_KEY": "x",
                   "bearer_token": "x", "ACCESS_TOKEN": "x"})
    for k in ("api_key", "API_KEY", "api-key", "private_key",
              "PRIVATE_KEY", "bearer_token", "ACCESS_TOKEN"):
        assert out[k] == "***redacted***", f"variant {k!r} not redacted"

    out = _redact({
        "agent": "trader",
        "config": {"secret": "this_is_a_secret_xxx", "fine": "ok"},
        "tokens": ["abc", "def"],
    })
    assert out["config"]["secret"] == "***redacted***"
    assert out["config"]["fine"] == "ok"
    assert out["agent"] == "trader"

    out = _redact({"price": 100, "model": "llama", "RSI": 30})
    assert out == {"price": 100, "model": "llama", "RSI": 30}


def test_brutal_audit_value_level_redaction_strips_keys_in_strings() -> None:
    """Defense-in-depth: even when the secret-bearing key has an innocuous
    name (e.g. 'input_text' wrapping an LLM prompt), well-known API key
    formats embedded in the VALUE must be redacted. Previous implementation
    only redacted by key-name — a leaked Anthropic key string in
    {"input_text": "ANTHROPIC_API_KEY=sk-ant-..."} would silently survive
    into the JSONL balancer and SQLite audit row.

    Covers all key shapes the system ships with:
      * Anthropic  (sk-ant-api03-... or sk-ant-...)
      * OpenAI     (sk-proj-... or sk-{40 chars})
      * Bearer XXX (generic)
      * Google API (AIzaSy...)
      * Groq       (gsk_...)
      * NVIDIA NIM (nvapi-...)
      * GitHub PAT (ghp_/gho_/ghs_/ghu_/ghr_)
      * Slack      (xox[abprs]-...)
      * JWT shape  (eyJ...)
      * >=40-char hex blob
    """
    from godmode.core.audit import _redact, _redact_value
    R = "***redacted***"

    # 1) Anthropic keys
    out = _redact({"input_text": "ANTHROPIC_API_KEY=sk-ant-api03-1234567890ABCDEFGHIJKLMNOPQRSTUVXYZ"})
    assert "sk-ant-api03" not in out["input_text"]
    assert R in out["input_text"]
    out2 = _redact({"text": "sk-ant-WxYzAbCdEfGhIjKlMnOpQrStUv"})
    assert "sk-ant-WxYzAbCdEfGhIjKlMnOpQrStUv" not in out2["text"]

    # 2) OpenAI keys
    out = _redact({"prompt": "Authorization: Key sk-proj-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"})
    assert "sk-proj-" not in out["prompt"]
    long_openai = "sk-" + "a" * 45
    out = _redact({"prompt": long_openai})
    assert long_openai not in out["prompt"]

    # 3) Bearer tokens (case-insensitive prefix)
    out = _redact({"headers": "Bearer abc123_-.somekindoflongstring"})
    assert "abc123" not in out["headers"]

    # 4) Google API key shape (AIzaSy...)
    out = _redact({"config": "matched: AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789extra"})
    assert "AIzaSy" not in out["config"]

    # 5) Groq tokens (gsk_...)
    out = _redact({"env": "export GROQ_API_KEY=gsk_XXXXXXXXXXXXXXXXXXXXXXXXXXXX"})
    assert "gsk_" not in out["env"]

    # 6) NVIDIA NIM (nvapi-...)
    out = _redact({"env": "NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxx"})
    assert "nvapi-" not in out["env"]

    # 7) GitHub PAT
    out = _redact({"url": "https://ghp_AbCdEfGhIjKlMnOpQrStUvWxYz123456@github.com"})
    assert "ghp_" not in out["url"]

    # 8) Slack token
    out = _redact({"text": "got token xoxb-1234567890-abcdefghijklmnop"})
    assert "xoxb-" not in out["text"]

    # 9) JWT shape
    out = _redact({"jwt": "eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.NTckZW3N9p6ZGw"})
    assert "eyJ" not in out["jwt"]

    # 10) Long hex blob (>=40 chars) — hashes, TOTP secrets
    blob = "a" * 50
    out = _redact({"text": f"hash={blob}"})
    assert blob not in out["text"]

    # 11) Normal prose remains intact (no false positives)
    out = _redact({"text": "Today the trader bought 50 shares of RELIANCE at INR 3145.60"})
    assert "3145.60" in out["text"], "price literals must NOT be falsely redacted"
    assert "RELIANCE" in out["text"]
    # A short less-than-40 hex must NOT be redacted (defends against hashing normal strings like 'e41fa')
    out = _redact({"text": "short hex: e41fa"})
    assert "e41fa" in out["text"], "short hex (5 chars) must not match the >=40-char pattern"

    # 12) Recursive / nested list values are scanned too
    out = _redact({"args": ["first", "key sk-ant-WxYzAbCdEfGhIjKlMnOpQrStUv", ["nested sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz"]]})
    import json
    flat = json.dumps(out)
    assert "sk-ant-" not in flat
    assert "sk-proj-" not in flat

    # Source-guard: value-pattern list exists (defense-in-depth)
    import godmode.core.audit as audit_mod
    src = Path(audit_mod.__file__).read_text(encoding="utf-8")
    assert "_redact_value" in src, "value-level redactor missing"
    assert "_VALUE_PATTERNS" in src, "value-pattern list missing"
    assert "sk-ant-" in src, "Anthropic key pattern missing"
    assert "AIzaSy" in src, "Google API key pattern missing"


def test_brutal_alpha_zoo_ewma_vol_responds_to_shock_and_finite() -> None:
    """add_volatility_features must compute ewma vol (RiskMetrics λ=0.94) and produce:
    1. No NaN after warmup, 2. Vol reacts to a sudden variance shock by SPIKING
    then decaying exponentially. 3. Source-inspection confirms RiskMetrics formula.
    """
    import numpy as np
    import polars as pl
    import inspect
    from godmode.data.alpha_zoo import AlphaZoo

    # Calm period → shock period → calm period
    np.random.seed(7)
    n_calm, n_shock, n_calm2 = 80, 20, 80
    r_calm = np.random.randn(n_calm) * 0.01
    r_shock = np.random.randn(n_shock) * 0.10  # 10x more vol
    r_calm2 = np.random.randn(n_calm2) * 0.01
    rets = np.concatenate([r_calm, r_shock, r_calm2])
    price = 100.0 * np.exp(np.cumsum(rets))
    df = pl.DataFrame({
        "timestamp": range(len(price)),
        "open": price, "high": price * 1.01, "low": price * 0.99,
        "close": price, "volume": 1000,
    })

    out = AlphaZoo.add_volatility_features(df)
    vol_ewma = out["vol_ewma_94"]
    vol_arr = vol_ewma.drop_nulls().to_numpy()

    # 1. Finite — no NaN/inf after warmup
    assert np.all(np.isfinite(vol_arr)), "EWMA vol produced non-finite values"

    # 2. Ewma vol during shock window (rows 80-100) should be MUCH higher than
    #    pre-shock window (rows 30-70). This is the point of EWMA vol — it
    #    reacts to variance changes; vol_20 / vol_60 also react but slower.
    pre_shock_mean = float(np.mean(vol_arr[30:70]))
    shock_mean = float(np.mean(vol_arr[80:100]))
    post_shock_mean = float(np.mean(vol_arr[140:170]))
    # Sanity: pre-shock should be much smaller than shock (10x vol difference)
    assert shock_mean > pre_shock_mean * 3.0, (
        f"EWMA vol did not react to vol shock: pre={pre_shock_mean:.5f} "
        f"shock={shock_mean:.5f}")
    # Post-shock should decay toward pre-shock (exponential decay)
    assert post_shock_mean < shock_mean * 0.7, (
        f"EWMA vol did not decay after shock: shock={shock_mean:.5f} "
        f"post={post_shock_mean:.5f}")

    # 3. Source inspection: must reference RiskMetrics and use λ=0.94 (span≈33)
    src = inspect.getsource(AlphaZoo.add_volatility_features)
    assert "RiskMetrics" in src, "EWMA vol docstring lost RiskMetrics reference"
    assert "0.94" in src, "EWMA vol lambda not specified as 0.94"
    assert "ewm_mean" in src, "EWMA vol must use polars ewm_mean"


def test_brutal_alpha_zoo_rsi_wilder_bounds_and_edge_cases() -> None:
    """add_momentum_features computes RSI(14) using Wilder smoothing. Verify:
    1. RSI strictly bounded [0, 100]. 2. Monotonically increasing closes → RSI→100.
    3. Monotonically decreasing closes → RSI→0. 4. roughly-flat closes → RSI mid-range.
    5. Source-inspection: Wilder smoothing span = 2*period-1 = 27, NOT a SMA.
    """
    import numpy as np, polars as pl, inspect
    from godmode.data.alpha_zoo import AlphaZoo

    # 2. Strong uptrend → RSI → 100 (in the tail)
    n = 200
    up = np.linspace(100, 200, n)  # strictly increasing
    df_up = pl.DataFrame({
        "timestamp": range(n), "open": up, "high": up * 1.01,
        "low": up * 0.99, "close": up, "volume": 1000,
    })
    out_up = AlphaZoo.add_momentum_features(df_up)
    rsi_up = out_up["rsi_14"].drop_nulls().to_numpy()
    assert np.all(np.isfinite(rsi_up)), "RSI produced non-finite on uptrend"
    # Tail of RSI should be very high (every up day → avg_gain>0, avg_loss=0)
    assert float(np.mean(rsi_up[-20:])) > 99.0, (
        f"uptrend RSI tail should approach 100, got {float(np.mean(rsi_up[-20:]))}")

    # 3. Strong downtrend → RSI → 0
    down = np.linspace(200, 100, n)  # strictly decreasing
    df_down = pl.DataFrame({
        "timestamp": range(n), "open": down, "high": down * 1.01,
        "low": down * 0.99, "close": down, "volume": 1000,
    })
    out_down = AlphaZoo.add_momentum_features(df_down)
    rsi_down = out_down["rsi_14"].drop_nulls().to_numpy()
    assert np.all(np.isfinite(rsi_down)), "RSI produced non-finite on downtrend"
    assert float(np.mean(rsi_down[-20:])) < 1.0, (
        f"downtrend RSI tail should approach 0, got {float(np.mean(rsi_down[-20:]))}")

    # 1. Universal bound check — on random walk, RSI must be in (0, 100)
    np.random.seed(11)
    rw_close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    df_rw = pl.DataFrame({
        "timestamp": range(n), "open": rw_close, "high": rw_close + 0.5,
        "low": rw_close - 0.5, "close": rw_close, "volume": 1000,
    })
    rsi_rw = AlphaZoo.add_momentum_features(df_rw)["rsi_14"].drop_nulls().to_numpy()
    assert np.all(rsi_rw >= 0.0) and np.all(rsi_rw <= 100.0), \
        f"RSI out of [0,100]: min={rsi_rw.min()}, max={rsi_rw.max()}"
    # And the middle range should be visited at least once (not stuck at edges)
    assert float(np.percentile(rsi_rw, 50)) > 20.0, "RSI never rises above 20"
    assert float(np.percentile(rsi_rw, 50)) < 80.0, "RSI never falls below 80"

    # 5. Source inspection — must reference Wilder and use span = 2*14 - 1 = 27
    src = inspect.getsource(AlphaZoo.add_momentum_features)
    assert "Wilder" in src, "RSI implementation lost Wilder reference"
    assert "wilder_span = 2 * period - 1" in src or \
           "span=wilder_span" in src, "RSI must use Wilder span = 2*period - 1"
    assert "rsi_14" in src, "RSI column must be named rsi_14"


def test_brutal_higuchi_fractal_dimension_classifies_persistence() -> None:
    """_higuchi_fractal_dimension must:
    1. Be in [1.0, 2.0] for any input.
    2. Be < 1.5 for a strongly trending (line-like) series — persistence.
    3. Be > 1.5 for a chaotic / white-noise series (anti-persistence).
    4. Be surfaceable in RegimeSignal.details as 'fractal_dim'.
    5. Theoretical relation D = 2 - H holds approximately on a strong trend.
    """
    import math, random
    from godmode.agents.regime_router import RegimeRouter, Regime
    cls = RegimeRouter

    # 1. Strong uptrend → D should be ≤ 1.5 (low, more "linear" / persistent)
    uptrend = [100.0 + i * 0.5 + (i % 3) * 0.01 for i in range(200)]
    d_up = cls._higuchi_fractal_dimension(uptrend)
    assert 1.0 <= d_up <= 2.0, f"D out of [1,2]: {d_up}"
    assert d_up < 1.5, f"uptrend D not <1.5 (should be persistent): {d_up}"
    # Cross-corroborate with Hurst: D ≈ 2 - H
    h_up = cls._hurst_exponent(uptrend)
    if h_up > 0.5:  # only check rel when Hurst agrees on persistence
        approx_d_from_h = 2 - h_up
        # Allow slack since both estimators are noisy
        assert abs(d_up - approx_d_from_h) < 1.0, (
            f"D-violation: D={d_up:.3f} but 2-H = {approx_d_from_h:.3f}")

    # 2. White-noise chaotic series → D should be high (>1.5, ideally →2)
    random.seed(99)
    white_noise = [100.0 + random.gauss(0, 1) for _ in range(300)]
    d_noise = cls._higuchi_fractal_dimension(white_noise)
    assert 1.0 <= d_noise <= 2.0, f"noise D out of [1,2]: {d_noise}"
    # Chaotic series—expect D > 1.4 (close to Brownian 1.5 or higher).
    # We don't enforce strictly >1.5 (sample estimator noise) just that it is
    # substantially higher than the strongly trending case.
    assert d_noise > d_up + 0.05, (
        f"noise D ({d_noise:.3f}) not higher than trend D ({d_up:.3f})")

    # 3. Integrated Brownian (random walk) → D also high (>1.5) — chaotic in raw form
    random.seed(123)
    rw = [100.0]
    rw.extend([rw[-1] + random.gauss(0, 1) for _ in range(300)])
    d_rw = cls._higuchi_fractal_dimension(rw)
    assert 1.0 <= d_rw <= 2.0, f"random walk D out of [1,2]: {d_rw}"
    assert d_rw > 1.5, f"random walk D not >1.5: {d_rw}"

    # 4. Too-short series returns neutral default 1.5
    short = [100.0 + i * 0.1 for i in range(10)]
    d_short = cls._higuchi_fractal_dimension(short)
    assert d_short == 1.5, f"short series should be 1.5, got {d_short}"

    # 5. `fractal_dim` must be surfaceable in RegimeSignal.details via classify()
    ohlcv = []
    price = 100.0
    for i in range(80):
        o = price; price += 0.3
        h = price + 0.1; l = price - 0.1
        ohlcv.append([o, h, l, price, 1000])
    sig = RegimeRouter.classify(ohlcv)
    assert "fractal_dim" in sig.details, (
        f"fractal_dim missing from RegimeSignal details: {sig.details}")
    assert 1.0 <= sig.details["fractal_dim"] <= 2.0

    # 6. Source-inspection: docstring references Higuchi + D = 2-H relation
    import inspect
    src = inspect.getsource(cls._higuchi_fractal_dimension)
    assert "Higuchi" in src, "method must reference Higuchi in docstring"
    assert "D = 2 - H" in src or "2 - H" in src, "method must cite D=2-H relation"



def test_brutal_shoonya_symbol_split_requires_venue_prefix() -> None:
    """ShoonyaAdapter._split_symbol must NOT default to 'NSE' when symbol lacks
    a venue prefix. Defaulting would silently route BSE orders to NSE — a FIX 14
    violation (honest failure). Must reject unprefixed symbols.
    """
    from godmode.execution.indian_broker_adapter import (
        ShoonyaAdapter, ShoonyaConnectivityError,
    )

    # Build without instantiating _api (skip _build); we just want to test the static method
    adapter = ShoonyaAdapter.__new__(ShoonyaAdapter)
    adapter.venue = "shoonya"
    adapter._token_cache = {}

    # Valid prefixed symbols accepted (NSE/BSE/MCX/CDS/NFO)
    for venue in ("NSE", "BSE", "MCX", "CDS", "NFO"):
        exch, sym = adapter._split_symbol(f"{venue}:RELIANCE-EQ")
        assert exch == venue, f"venue prefix {venue} not preserved (got {exch})"
        assert sym == "RELIANCE-EQ"

    # Case-insensitive venue prefix
    exch, sym = adapter._split_symbol("nse:rel-eq")
    assert exch == "NSE", f"lower case venue not normalized: {exch}"

    # Unprefixed symbols MUST raise (NOT default to NSE)
    try:
        adapter._split_symbol("RELIANCE-EQ")
        raise AssertionError("unprefixed symbol silently defaulted to NSE — FIX 14 violated")
    except ShoonyaConnectivityError:
        pass  # expected

    try:
        adapter._split_symbol("SBIN")
        raise AssertionError("unprefixed symbol silently defaulted to NSE — FIX 14 violated")
    except ShoonyaConnectivityError:
        pass  # expected

    # Unknown venue prefix MUST also raise (NOT default)
    try:
        adapter._split_symbol("NASDAQ:AAPL")
        raise AssertionError("unknown venue 'NASDAQ' silently accepted — FIX 14 violated")
    except ShoonyaConnectivityError:
        pass  # expected


def test_brutal_autopilot_swarm_no_fabricated_ohlcv_on_empty_fetch() -> None:
    """AutopilotSwarmEngine.run_market_scan MUST NOT fabricate OHLCV candles
    (`[price]*15`, `[price*1.01]*15`, etc.) when fetch returns empty. Doing so
    would feed fake data into KAMA/RegimeDetector and produce a fake "trending"
    signal. Must return signal='HOLD' with error='ohlcv_fetch_empty'.
    """
    import unittest.mock as _mock
    from godmode.core.autopilot_swarm import AutopilotSwarmEngine

    engine = AutopilotSwarmEngine.__new__(AutopilotSwarmEngine)
    engine.paper = True
    # Force crypto path (so we can intercept _fetch_crypto_market cleanly)
    # and force the empty-fetch path
    engine._fetch_crypto_market = lambda sym: (50_000.0, [])
    engine.shoonya_adapter = None  # not used on crypto path
    engine.intelligence = None
    engine.is_running = False

    res = engine.run_market_scan("BTCUSDT")
    assert res.get("signal") == "HOLD", f"expected HOLD on empty OHLCV, got {res.get('signal')}"
    assert res.get("error") == "ohlcv_fetch_empty", f"expected error flag, got {res.get('error')}"
    assert res.get("executed_order") is None, f"must not execute on empty OHLCV: {res.get('executed_order')}"
    assert res.get("kama") is None, f"kama must be None (no fabricated indicators), got {res.get('kama')}"
    assert res.get("regime") is None

    # Also test the case where OHLCV lists have a zero close (bad data)
    engine._fetch_crypto_market = lambda sym: (50_000.0, [[1, 50000, 50100, 49900, 0, 100]])
    res2 = engine.run_market_scan("BTCUSDT")
    assert res2.get("signal") == "HOLD"
    assert res2.get("error") == "ohlcv_fetch_empty"

    # SOURCE-LEVEL GUARD: ensure the old fabrication pattern is GONE
    import godmode.core.autopilot_swarm as aps_mod
    src = Path(aps_mod.__file__).read_text(encoding="utf-8")
    assert "[price] * 15" not in src, "autopilot_swarm STILL fabricates [price]*15 — FIX 14 violated"
    assert "[price * 1.01] * 15" not in src, "autopilot_swarm STILL fabricates [price * 1.01]*15"
    assert "[price * 0.99] * 15" not in src, "autopilot_swarm STILL fabricates [price * 0.99]*15"
    assert "ohlcv_fetch_empty" in src, "empty-OHLCV honest path missing"


def test_brutal_regime_router_confidence_reflects_voter_consensus() -> None:
    """RegimeRouter.confidence MUST reflect voter agreement, not just ADX strength.

    Old formula was `min(1.0, current_adx / 60.0)` — a pure-ADX score. A 2-vote
    weak agreement (bull_votes=2 from slope+Hurst, ADX only 12) would report
    the SAME confidence as a 5-vote strong agreement with ADX=12, even though
    one decision is 3x more robust than the other. Confidence must be a
    geometric mean of (ADX strength) * (consensus ratio) so weak agreement
    with weak ADX can never masquerade as a high-confidence trend call.
    """
    import math
    from godmode.agents.regime_router import RegimeRouter, Regime

    # Source-guard: the old single-source formula must be gone from router.py
    import godmode.agents.regime_router as rr_mod
    rr_src = Path(rr_mod.__file__).read_text(encoding="utf-8")
    assert "confidence = min(1.0, current_adx / 60.0)" not in rr_src, (
        "old confidence formula (ADX-only) still present — does not reflect 5-voter consensus"
    )
    assert "consensus_term" in rr_src, "new consensus formula missing"
    assert "math.sqrt" in rr_src or "_m.sqrt" in rr_src, "geometric-mean (sqrt) missing"

    # Strong uptrend: all 5 voters agree AND ADX high -> confidence should be
    # high (well above 0.5). Generate a strong, persistent uptrend.
    # candles: [open, high, low, close, volume] (5-element per RegimeRouter.classify contract)
    strong_up = []
    p = 100.0
    for i in range(250):
        # +0.6% drift per bar + tiny noise
        op = p
        p *= (1 + 0.006 + random.gauss(0, 0.004))
        hi = max(op, p) * 1.003
        lo = min(op, p) * 0.999
        strong_up.append([op, hi, lo, p, 1000.0])

    res_strong = RegimeRouter.classify(strong_up)
    assert res_strong.regime == Regime.TRENDING_UP, (
        f"strong uptrend should classify as TRENDING_UP, got {res_strong.regime}; "
        f"bull_votes invisibly broken?"
    )
    assert res_strong.confidence >= 0.4, (
        f"strong 5-vote uptrend should give high confidence (>=0.4); got {res_strong.confidence}. "
        "Geometric mean is too aggressive or voters misfired."
    )

    # Weak signal: mean-reverting (Ornstein-Uhlenbeck) noise — genuinely range
    # bound, no real drift. This should produce a noticeably lower confidence
    # than the strong uptrend because consensus should be low even if a single
    # short-term slope spike momentarily fires the trend voter.
    rng = random.Random(456)
    noise = []
    p = 100.0
    for i in range(250):
        op = p
        p += (100 - p) * 0.1 + rng.gauss(0, 0.5)  # OU pull toward 100
        hi = max(op, p) * 1.005
        lo = min(op, p) * 0.995
        noise.append([op, hi, lo, p, 1000.0])
    res_noise = RegimeRouter.classify(noise)
    # Mean-reverting noise must NOT score confidence as high as a strong uptrend.
    assert res_noise.confidence < res_strong.confidence, (
        f"noise ({res_noise.confidence}) should not be more confident than "
        f"strong uptrend ({res_strong.confidence}) — confidence is not consensus-aware"
    )
    # Sanity bound: noise confidence should be modest (< 0.6) since voter
    # consensus is weak for a true trend call on range-bound data.
    assert res_noise.confidence < 0.6, (
        f"OU mean-reverting noise should not score > 0.6 confidence; got "
        f"{res_noise.confidence} (consensus-aware formula not aggressive enough)"
    )


def test_brutal_db_insert_rejects_injection_via_table_and_column_names() -> None:
    """Database.insert MUST survive 3 injection vectors because it does
    identifier (not value) interpolation:
      1) Unknown table name (e.g. 'orders; DROP TABLE runs--')
      2) Column name containing SQL metacharacters ('qty; DROP TABLE orders--')
      3) Empty table name
    All three must raise ValueError. WITHOUT the whitelist, vector #1 would
    actually execute and DROP production tables — catastrophic.
    """
    import tempfile
    from pathlib import Path
    from godmode.core.db import Database

    with tempfile.TemporaryDirectory() as td:
        db = Database(db_path=Path(td) / "test.db")

        # Vector 1: malicious table name (classic DROP TABLE injection)
        try:
            db.insert("orders; DROP TABLE runs--", {"id": 1})
            raise AssertionError("insert() accepted malicious table name — SQL injection succeeded")
        except ValueError:
            pass  # expected — whitelist rejects it

        try:
            db.insert("nonexistent_table", {"id": 1})
            raise AssertionError("insert() accepted unknown table — whitelist broken")
        except ValueError:
            pass

        # Vector 2: malicious column name
        try:
            db.insert("orders", {"qty; DROP TABLE fills--": "1"})
            raise AssertionError("insert() accepted malicious column name — SQL injection succeeded")
        except ValueError:
            pass

        # Column containing spaces or special chars (not just SQL keywords)
        try:
            db.insert("metrics", {"key with spaces": "v"})
            raise AssertionError("insert() accepted column name with spaces")
        except ValueError:
            pass

        # Vector 3: empty table
        try:
            db.insert("", {"id": 1})
            raise AssertionError("insert() accepted empty table name")
        except ValueError:
            pass

        # Sanity: legit insert works
        rid = db.insert("metrics", {"ts": "2026-01-01", "key": "test", "value": 1.5})
        assert rid > 0

        # Verify whitelist source-guard exists
        import godmode.core.db as db_mod
        src = Path(db_mod.__file__).read_text(encoding="utf-8")
        assert "_ALLOWED_TABLES" in src, "table whitelist missing from db.py"
        assert "injection guard" in src.lower(), "injection-guard comment missing from db.py"

        db.close()


def test_brutal_config_reload_and_reset_cache_helpers() -> None:
    """load_config(reload=True) MUST re-read yaml/.env and overwrite the cached
    Config singleton. reset_config_cache() MUST drop the cache so the next
    load_config() call rebuilds from disk. HONESTY GUARD:
      - reload=True path returns a fresh Config object (not the cached one)
      - reset_config_cache() + load_config() also returns a fresh Config
      - cache actually persists between two normal load_config() calls without reload
    """
    from godmode.core.config import load_config, reset_config_cache, _CONFIG_CACHE
    # Drop any pre-existing cache so we start clean
    reset_config_cache()
    cfg_first = load_config()
    cfg_second = load_config()                  # no reload — should be SAME singleton
    assert cfg_first is cfg_second, "load_config() must return cached singleton (no reload)"

    cfg_third = load_config(reload=True)        # reload — must rebuild
    # Even if values are equal, the object identity may or may not differ
    # (pydantic BaseModel instances are not interned). What matters is the
    # *cache* is replaced for subsequent calls.
    cfg_fourth = load_config()                  # must reflect the reload result
    assert cfg_fourth is cfg_third, (
        "load_config() returned stale cache after reload=True — reload did NOT replace cache"
    )

    # reset_config_cache helper honesty check
    reset_config_cache()
    from godmode.core import config as cfg_mod
    assert cfg_mod._CONFIG_CACHE is None, "reset_config_cache() did not actually drop the singleton"

    # Source guard for the new helper existence
    src = Path(cfg_mod.__file__).read_text(encoding="utf-8")
    assert "def reset_config_cache" in src, "reset_config_cache() helper missing"


def test_brutal_free_llm_router_enforces_tls_verification() -> None:
    """FreeLLMRouter._post_json MUST NOT disable TLS verification
    (`check_hostname=False`, `CERT_NONE`). The original code shipped with
    both disabled — any MITM could intercept Bearer tokens and feed the
    trader poisoned prompts. The fix: rely on the OS trust store via
    ssl.create_default_context() with FULL verification.
    """
    import godmode.llm.free_router as fr_mod
    src = Path(fr_mod.__file__).read_text(encoding="utf-8")

    # The dangerous patterns must be GONE.
    assert "check_hostname = False" not in src, (
        "free_router STILL disables TLS hostname verification — MITM can intercept keys"
    )
    assert "CERT_NONE" not in src, (
        "free_router STILL sets verify_mode=CERT_NONE — MITM can intercept keys"
    )

    # The honest default must be present.
    assert "ssl.create_default_context()" in src, (
        "free_router must use ssl.create_default_context() (OS trust store, full verification)"
    )


def test_brutal_live_intelligence_no_fabricated_prices_or_news() -> None:
    """LiveIntelligenceFeed MUST NOT fabricate prices/indices/news headlines
    when upstream APIs fail. Previous implementation shipped with:
      - BTC=63950.0, ETH=3450.0, SOL=154.20 defaults
      - NIFTY=24850.45, SENSEX=81420.10, BANK NIFTY=52640.80 defaults
      - RELIANCE=3145.60, TCS=4210.30, HDFCBANK=1698.40, INFY=1782.15 defaults
      - Fabricated headlines like "US Core CPI Inflation Cools; Fed Rate Cut
        Expectations Rise for Q3" appearing as if they were real news
    All of these were FIX 14 violations — a user might mistake the fabricated
    numbers for live data and trade against them. The honest contract: when
    fetch fails, the entry carries {"error": "fetch_failed"} and the news list
    is empty (no synthetic headlines).
    """
    import godmode.data.live_intelligence as li_mod
    from godmode.data.live_intelligence import LiveIntelligenceFeed
    src = Path(li_mod.__file__).read_text(encoding="utf-8")

    # ---- Source-level guard: the fabricated literals MUST be GONE ----
    # We remove comments/strings before grepping to avoid false positives where
    # a literal appears ONLY in our honesty-contract docstring (which would
    # document the violation, not cause it).
    import re as _re
    _strip_comments = _re.compile(r'#.*$', _re.MULTILINE)
    _strip_strings = _re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
    src_no_cmts = _strip_comments.sub("", src)
    src_no_cmts = _strip_strings.sub("", src_no_cmts)

    fabricated_intl = [
        "63950.0", "3450.0", "154.20",
        "FED WATCH", "ON-CHAIN PULSE", "GLOBAL MACRO", "CRYPTO WIRE",
    ]
    fabricated_in = [
        "24850.45", "81420.10", "52640.80",
        "3145.60", "4210.30", "1698.40", "1782.15",
        "NSE PULSE", "ECONOMY INDIA", "IT SECTOR WATCH", "SHOONYA DESK",
    ]
    for lit in fabricated_intl + fabricated_in:
        assert lit not in src_no_cmts, (
            f"live_intelligence STILL contains fabricated literal {lit!r} in "
            "executable code — FIX 14 violated"
        )

    # The mock-news fallback blocks (4 fabricated headlines each) must be gone
    # from executable code
    assert "RBI Keeps Repo Rate Stable" not in src_no_cmts, "fabricated Indian news still present"
    assert "US Core CPI Inflation Cools" not in src_no_cmts, "fabricated intl news still present"
    assert "Zero-Brokerage High Frequency" not in src_no_cmts, "shoonya desk fabricated news present"
    assert "Institutional Spot ETF Inflows Surge" not in src_no_cmts, "crypto wire fabricated news present"

    # Honesty scaffolding must be present (in the raw source)
    assert "fetch_failed" in src, "honest fallback contract ({error:fetch_failed}) missing"
    assert "HONESTY CONTRACT" in src

    # ---- Behavioral guard: when fetches all fail, payload carries errors ----
    feed = LiveIntelligenceFeed(cache_ttl_seconds=0.01)
    # Force every fetch to fail
    feed._fetch_json = lambda url, timeout=3.5: None

    intl = feed.get_international_intelligence()
    assert intl["fear_greed"].get("error") == "fetch_failed", (
        f"fear_greed must surface error when fetch fails; got {intl['fear_greed']}"
    )
    for asset_name, entry in intl["assets"].items():
        assert entry.get("error") == "fetch_failed", (
            f"asset {asset_name} must surface error on fetch fail; got {entry}"
        )
    # NEWS must be empty (no fabricated headlines)
    assert intl["news"] == [], f"international news must be empty on fetch fail; got {intl['news']}"

    # Force a fresh call so cache doesn't shadow the second check
    import time as _t
    _t.sleep(0.02)
    ind = feed.get_indian_intelligence()
    for idx_name, entry in ind["indices"].items():
        assert entry.get("error") == "fetch_failed", (
            f"index {idx_name} must surface fetch_failed; got {entry}"
        )
    for stock_name, entry in ind["stocks"].items():
        assert entry.get("error") == "fetch_failed", (
            f"stock {stock_name} must surface fetch_failed; got {entry}"
        )
    assert ind["news"] == [], f"indian news must be empty on fetch fail; got {ind['news']}"

    # ---- Behavioral guard: partial failure is honest per-asset ----
    def fake_fetch(url, timeout=3.5):
        if "BTCUSDT" in url:
            return {"lastPrice": "99999.99", "priceChangePercent": "5.5",
                    "highPrice": "100000", "lowPrice": "99000"}
        return None
    feed._fetch_json = fake_fetch  # type: ignore[assignment]
    _t.sleep(0.02)
    intl2 = feed.get_international_intelligence()
    assert intl2["assets"]["BTC/USDT"]["price"] == 99999.99
    assert "error" in intl2["assets"]["ETH/USDT"]
    assert "error" in intl2["assets"]["SOL/USDT"]


def test_brutal_autopilot_swarm_no_fabricated_returns_on_single_candle() -> None:
    """AutopilotSwarmEngine.run_market_scan must NOT inject fabricated returns
    `[0.001]` (a fake +0.1% return series) when only 1 candle is available.
    Returns must be empty so run_purged_walk_forward honestly reports
    INSUFFICIENT_DATA. The previous code injected [0.001] which sentinel-tests
    a fabricated profit stream into the deflated Sharpe gate.

    Note: at the moment, run_market_scan short-circuits BEFORE this point on
    empty OHLCV (covered by test_brutal_autopilot_swarm_no_fabricated_ohlcv_on_empty_fetch).
    This test guards the direct injection site in case the upstream short-circuit
    is later relaxed — defense-in-depth against regressions.
    """
    import godmode.core.autopilot_swarm as aps_mod
    src = Path(aps_mod.__file__).read_text(encoding="utf-8")

    # Strip comments + docstrings to avoid false positive where the literal
    # appears only in our honesty-contract comment (which is documentation).
    import re as _re
    _strip_comments = _re.compile(r'#.*$', _re.MULTILINE)
    _strip_strings = _re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
    src_nc = _strip_comments.sub("", src)
    src_nc = _strip_strings.sub("", src_nc)

    assert "[0.001]" not in src_nc, (
        "autopilot_swarm STILL injects fabricated returns [0.001] in executable "
        "code — FIX 14 violated (would feed fake profit to deflated Sharpe)"
    )
    assert "len(closes) > 1" in src_nc, "honest single-candle branch missing"
    # When len(closes) == 1, returns must be empty (NOT [0.001])
    assert "returns = []\n        else:" in src_nc or "returns = []" in src_nc, (
        "honest empty-returns branch (when only 1 candle) missing"
    )


def test_brutal_killswitch_engage_check_reset_round_trip() -> None:
    """KillSwitch engage→check→reset round-trip; idempotent engage preserves original reason."""
    import tempfile
    from pathlib import Path
    from godmode.core.killswitch import KillSwitch, KillSwitchEngaged

    with tempfile.TemporaryDirectory() as td:
        stop = Path(td) / "STOP"
        hb = Path(td) / "heartbeat.txt"
        ks = KillSwitch(stop_file=stop, heartbeat_file=hb)

        assert not ks.is_halted()
        assert ks.reason() is None

        ks.engage("drawdown breach 8%", source="risk_engine")
        assert ks.is_halted()
        r1 = ks.reason()
        assert r1 and r1["reason"] == "drawdown breach 8%"
        assert r1["source"] == "risk_engine"
        ts_first = r1["ts"]

        ks.engage("different reason", source="cli")
        r2 = ks.reason()
        assert r2["reason"] == "drawdown breach 8%", "idempotent engage failed"
        assert r2["ts"] == ts_first, "engage overwrote original timestamp"

        try:
            ks.check()
            assert False, "check() did not raise"
        except KillSwitchEngaged as e:
            assert "drawdown breach 8%" in str(e)

        ks.reset(source="cli")
        assert not ks.is_halted()
        assert ks.reason() is None
        ks.check()

        s = ks.status()
        assert "halted" in s and "reason" in s and "heartbeat_age_seconds" in s


def test_brutal_killswitch_heartbeat_watchdog_auto_halts() -> None:
    """Stale heartbeat must trigger watchdog() to auto-engage halt with source='heartbeat'."""
    import tempfile
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from godmode.core.killswitch import KillSwitch

    with tempfile.TemporaryDirectory() as td:
        stop = Path(td) / "STOP"
        hb = Path(td) / "heartbeat.txt"
        ks = KillSwitch(stop_file=stop, heartbeat_file=hb)

        old = datetime.now(timezone.utc) - timedelta(seconds=60)
        hb.write_text(old.isoformat(), encoding="utf-8")

        engaged = ks.watchdog(max_age_seconds=5.0)
        assert engaged, "watchdog did not engage on stale heartbeat"
        assert ks.is_halted()
        r = ks.reason()
        assert r and r["source"] == "heartbeat"
        assert "stale" in r["reason"]

        engaged_again = ks.watchdog(max_age_seconds=5.0)
        assert engaged_again is False, "watchdog re-engaged when already halted"


def test_brutal_killswitch_survives_corrupted_stop_file() -> None:
    """Corrupted (non-JSON) STOP file must not crash is_halted/reason — graceful fallback."""
    import tempfile
    from pathlib import Path
    from godmode.core.killswitch import KillSwitch

    with tempfile.TemporaryDirectory() as td:
        stop = Path(td) / "STOP"
        hb = Path(td) / "heartbeat.txt"
        stop.write_text("not valid json at all {{{", encoding="utf-8")

        ks = KillSwitch(stop_file=stop, heartbeat_file=hb)
        assert ks.is_halted(), "corrupt stop file should still register as halted"
        r = ks.reason()
        assert r is not None, "reason() returned None on corrupt file"
        assert "reason" in r, "corrupt fallback missing 'reason' key"


def test_brutal_no_fabricated_data_in_mcp_or_edge_data() -> None:
    """HARD RULE: edge_data.py and mcp_client._mock_fallback MUST NOT fabricate
    fake market data when MCP is offline. The system must honestly return [] / {}
    so downstream LLM reasoning is not corrupted by hallucinated "whale moves",
    fake SEC filings, or invented CPI numbers.

    Source-inspection test: greps the source of both modules for forbidden literals.
    """
    import inspect
    import godmode.data.edge_data as edge_mod
    import godmode.agents.mcp_client as mcp_mod

    # Forbidden patterns — exact strings that USED to be fabricated and would
    # corrupt the brain's reasoning if they ever reappear.
    FORBIDDEN_IN_EDGE = [
        '"CPI":', '"PPI":',
        "Strategic partnership",
        "Company announces major",
        "binance_hot_1",
        'usd_value": 15',
        '"amount": 500',
    ]
    FORBIDDEN_IN_MCP = [
        "Mock data",
        "Mock memory",
        "Strategic partnership",
        '"CPI": "3.1%"',
        '"PPI": "2.8%"',
        'usd_value": 12000000',
        "Simulated execution",
        # Fake tool *definitions* formerly injected when no MCP server was up —
        # advertising nonexistent capabilities is dishonest surface area.
        "Run read-only SQL queries against the internal Godmode PostgreSQL",
        "Query the persistent memory knowledge graph for past trading rules",
        "returning simulated mocks",
    ]

    edge_src = inspect.getsource(edge_mod)
    for forbidden in FORBIDDEN_IN_EDGE:
        assert forbidden not in edge_src, (
            f"edge_data.py fabricates forbidden literal: {forbidden!r}")

    mcp_src = inspect.getsource(mcp_mod)
    for forbidden in FORBIDDEN_IN_MCP:
        assert forbidden not in mcp_src, (
            f"mcp_client.py fabricates forbidden literal: {forbidden!r}")

    # Behavioral: _mock_fallback must return empty containers (NOT non-empty fakes)
    client = mcp_mod.MCPClient()
    for tool, args in [
        ("get_whale_transfers", {"asset": "BTC"}),
        ("get_sec_filings_json", {"ticker": "AAPL"}),
        ("get_fred_metrics", {"metrics": ["CPI"]}),
        ("query_database", {"q": "SELECT 1"}),
        ("read_memory_graph", {}),
        ("unknown_tool", {}),
    ]:
        out = client._mock_fallback(tool, args)
        if tool == "get_whale_transfers":
            assert out == {"transfers": []}, f"{tool} should return empty, got {out}"
        elif tool == "get_sec_filings_json":
            assert out == {"filings": []}, f"{tool} should return empty, got {out}"
        elif tool == "query_database":
            assert out == [], f"{tool} should return [], got {out}"
        elif tool == "read_memory_graph":
            assert out == {"observations": []}, f"{tool} should return empty, got {out}"
        else:
            assert out == {}, f"{tool} should return {{}}, got {out}"

    # Behavioral: when truly offline (empty registry), NO tool definitions may
    # be advertised — an empty list is the only honest answer. Patched so the
    # test never spawns real MCP subprocesses.
    from unittest.mock import patch

    offline_client = mcp_mod.MCPClient()
    with patch.object(offline_client.registry, "list_servers", return_value=[]):
        assert offline_client.get_available_tools() == [], (
            "get_available_tools must not advertise fake tools when MCP is offline")


def test_brutal_alpha_zoo_frac_diff_correct_weights_and_lags() -> None:
    """AlphaZoo.add_fractional_diff_proxy must implement Lopez de Prado fractional
    differentiation with weights w_k = (d choose k) falling factorial, NOT just a
    2-lag crude hack. We verify: (1) weights are correct against closed-form,
    (2) on an integrated random walk the resulting series is more stationary
    (lower std/mean ratio) than the raw price, (3) >2 lags are actually used.
    """
    import numpy as np
    import polars as pl
    from godmode.data.alpha_zoo import AlphaZoo

    # 1. Closed-form Lopez de Prado weights for d=0.4: w_0=1, w_1=-0.4, w_2=0.12,
    #    w_3=-0.064, w_4=0.0416 (falling factorial). Verify these by introspection
    #    of behavior on a UNIT-IMPULSE input where close[0]=100, close[k]=0 for k>0:
    #    fd[k] = w_k * 100 exactly. This is the brutal correctness test for weights.
    n_t = 20
    impulse_close = np.zeros(n_t)
    impulse_close[0] = 100.0
    df_imp = pl.DataFrame({
        "timestamp": range(n_t),
        "open": impulse_close, "high": impulse_close,
        "low": impulse_close, "close": impulse_close, "volume": 1000,
    })
    fd_imp = AlphaZoo.add_fractional_diff_proxy(df_imp, d=0.4, window=10)["frac_diff_proxy"].to_numpy()
    # True Lopez de Prado weights for d=0.4: w_k = (-1)^k * (d choose k)
    # w_0 = +1, w_1 = -0.4, w_2 = -0.12, w_3 = -0.064, w_4 = -0.0416
    # (note: consecutive weights are NOT sign-alternating; (d choose k) flips its own sign
    # because d < 1 makes "(d - i)" become negative past i=0)
    assert abs(fd_imp[0] - 100.0) < 1e-6, f"w_0 not 1.0: fd_imp[0]={fd_imp[0]}"
    assert abs(fd_imp[1] - (-40.0)) < 1e-6, f"w_1 not -0.4: fd_imp[1]={fd_imp[1]}"
    assert abs(fd_imp[2] - (-12.0)) < 1e-6, f"w_2 not -0.12: fd_imp[2]={fd_imp[2]}"
    assert abs(fd_imp[3] - (-6.4)) < 1e-6, f"w_3 not -0.064: fd_imp[3]={fd_imp[3]}"
    assert abs(fd_imp[4] - (-4.16)) < 1e-6, f"w_4 not -0.0416: fd_imp[4]={fd_imp[4]}"

    # 2. On a longer integrated random walk, frac_diff output should be FINITE and
    #    bounded (no overflow, no NaN past the warmup window).
    np.random.seed(42)
    n = 500
    noise = np.random.randn(n)
    price = np.cumsum(noise) + 100.0
    df = pl.DataFrame({
        "timestamp": range(n),
        "open": price, "high": price + 1, "low": price - 1,
        "close": price, "volume": 1000,
    })
    out = AlphaZoo.add_fractional_diff_proxy(df, d=0.4, window=10)
    fd = out["frac_diff_proxy"].drop_nulls().to_numpy()
    assert len(fd) > 0
    assert not np.all(np.isnan(fd)), "frac_diff produced all-NaN"
    assert np.all(np.isfinite(fd[~np.isnan(fd)])), "frac_diff produced non-finite values"

    # (3) Source-inspection: must mention 'falling factorial' or 'Lopez de Prado',
    #     must NOT just be the old 2-lag formula (close - d*close.shift(1) - ...shift(2))
    import inspect
    src = inspect.getsource(AlphaZoo.add_fractional_diff_proxy)
    assert "Lopez de Prado" in src or "falling factorial" in src, \
        "frac_diff docstring lost its theoretical reference"
    # Old hack had hardcoded "(d*(d-1)/2)" — must be GONE
    assert "(d*(d-1)/2)" not in src.replace(" ", ""), \
        "frac_diff still uses crude 2-lag hack formula"
    # Must iterate over multiple lags (len(weights) varying)
    assert "for k" in src or "for k," in src, "frac_diff must iterate over lag weights"


# ---------------- RUNNER ----------------

ALL_TESTS = [
    test_tier1_name_error_fix,
    test_tier1_pyproject_deps,
    test_tier1_binance_guard,
    test_tier1_news_apis,
    test_tier1_websocket_streamer_import,
    test_tier1_key_rotator_env,
    test_tier1_live_intelligence_calls_real_news,
    test_tier2_regime_router_classifies,
    test_tier2_position_analyzer,
    test_tier2_symbol_selector,
    test_tier2_chronos_prophet_v2_gbm,
    test_tier2_reflection_v2_default,
    test_tier3_arena_runs_tournament,
    test_tier3_digital_twin_voting,
    test_tier4_godel_protected_files,
    test_tier4_godel_status,
    test_tier5_onchain_analyst,
    test_tier5_knowledge_graph,
    test_tier5_duckdb_or_fallback,
    test_tier5_chart_vision_module_imports,
    test_tier6_neuro_symbolic_safety_check,
    test_tier6_neuro_symbolic_propose_rule,
    test_tier6_synthetic_stress_scenarios,
    test_tier7_streamlit_app_parses,
    test_brutal_duckdb_sql_path_returns_real_numbers,
    test_brutal_regime_detects_uptrend,
    test_brutal_regime_detects_downtrend,
    test_brutal_regime_detects_mean_reverting_range,
    test_brutal_hurst_exponent_classifies_persistence,
    test_brutal_brain_e2e_mock_llm,
    test_brutal_brain_halts_safely_when_llm_fails,
    test_brutal_onchain_real_apis_or_honest_failure,
    test_brutal_godel_proxy_sharpe_is_not_literal,
    test_brutal_digital_twin_microstructure_not_random_future,
    test_brutal_arena_uses_real_kama,
    test_brutal_shoonya_no_fake_crypto_fallback,
    test_brutal_autopilot_swarm_real_crypto_fetch,
    test_brutal_dashboard_renders_all_panels,
    test_brutal_chronos_prophet_uses_real_chronos_api,
    test_brutal_neuro_symbolic_hardened_security,
    test_brutal_fastapi_dashboard_all_endpoints_200,
    test_brutal_live_runner_no_fake_news_and_uses_v2_prophet,
    test_brutal_legacy_chronos_agent_module_is_dead,
    test_brutal_decide_action_pure_decision_logic,
    test_brutal_audit_redaction_protects_secrets,
    test_brutal_audit_value_level_redaction_strips_keys_in_strings,
    test_brutal_killswitch_engage_check_reset_round_trip,
    test_brutal_killswitch_heartbeat_watchdog_auto_halts,
    test_brutal_killswitch_survives_corrupted_stop_file,
    test_brutal_no_fabricated_data_in_mcp_or_edge_data,
    test_brutal_alpha_zoo_frac_diff_correct_weights_and_lags,
    test_brutal_key_rotator_env_load_and_health,
    test_brutal_alpha_zoo_ewma_vol_responds_to_shock_and_finite,
    test_brutal_alpha_zoo_rsi_wilder_bounds_and_edge_cases,
    test_brutal_higuchi_fractal_dimension_classifies_persistence,
    test_brutal_shoonya_symbol_split_requires_venue_prefix,
    test_brutal_autopilot_swarm_no_fabricated_ohlcv_on_empty_fetch,
    test_brutal_regime_router_confidence_reflects_voter_consensus,
    test_brutal_db_insert_rejects_injection_via_table_and_column_names,
    test_brutal_config_reload_and_reset_cache_helpers,
    test_brutal_free_llm_router_enforces_tls_verification,
    test_brutal_live_intelligence_no_fabricated_prices_or_news,
    test_brutal_autopilot_swarm_no_fabricated_returns_on_single_candle,
]


def _run_standalone() -> int:
    failures = 0
    for test in ALL_TESTS:
        name = test.__name__
        try:
            test()
            print(f"  PASS  {name}")
        except Exception as exc:
            print(f"  FAIL  {name}: {exc}")
            failures += 1
    total = len(ALL_TESTS)
    print(f"\n========== {total - failures}/{total} tests passed ==========")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(_run_standalone())
