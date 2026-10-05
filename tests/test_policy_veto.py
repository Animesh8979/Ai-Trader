"""Tests for PolicyVetoEngine (Deterministic risk boundaries layer)."""

from decimal import Decimal
import pytest

from godmode.agents.jev_trader_engine import JevJudgments
from godmode.core.killswitch import get_kill_switch
from godmode.risk.policy_veto import PolicyVetoEngine, VetoVerdict


@pytest.fixture
def benign_judgments():
    return JevJudgments(
        regime="BULL_TREND",
        direction="LONG",
        toxic_flow=0.20,
        liquidity_stressed=0.15,
        quote_environment=4.5,
        inventory_pressure=1.0,
        confidence=0.85,
        latency_ms=1.2,
        is_fallback=True,
    )


def test_policy_veto_approved(benign_judgments):
    """Benign conditions must pass all policy boundaries."""
    engine = PolicyVetoEngine()
    verdict = engine.check(
        side="buy",
        proposed_qty=Decimal("0.5"),
        judgments=benign_judgments,
        spread_bps=2.0,
        current_position=Decimal("0.0"),
        max_position=Decimal("1.0"),
    )
    assert verdict.approved is True
    assert verdict.action == "EXECUTE"
    assert verdict.allowed_qty == Decimal("0.5")


def test_policy_veto_toxic_flow(benign_judgments):
    """Toxic flow exceeding threshold (>0.70) must trigger VETO."""
    engine = PolicyVetoEngine(max_toxic_flow=0.70)
    benign_judgments.toxic_flow = 0.75

    verdict = engine.check(
        side="buy",
        proposed_qty=Decimal("0.5"),
        judgments=benign_judgments,
        spread_bps=2.0,
        current_position=Decimal("0.0"),
        max_position=Decimal("1.0"),
    )
    assert verdict.approved is False
    assert verdict.action == "VETO"
    assert any("Toxic flow" in r for r in verdict.reasons)


def test_policy_veto_liquidity_stress(benign_judgments):
    """Liquidity stress exceeding threshold (>0.80) must trigger VETO."""
    engine = PolicyVetoEngine(max_liquidity_stress=0.80)
    benign_judgments.liquidity_stressed = 0.85

    verdict = engine.check(
        side="buy",
        proposed_qty=Decimal("0.5"),
        judgments=benign_judgments,
        spread_bps=2.0,
        current_position=Decimal("0.0"),
        max_position=Decimal("1.0"),
    )
    assert verdict.approved is False
    assert verdict.action == "VETO"
    assert any("Liquidity stress" in r for r in verdict.reasons)


def test_policy_veto_spread_blowout(benign_judgments):
    """Spread exceeding threshold (>15.0 bps) must trigger VETO."""
    engine = PolicyVetoEngine(max_spread_bps=15.0)

    verdict = engine.check(
        side="buy",
        proposed_qty=Decimal("0.5"),
        judgments=benign_judgments,
        spread_bps=18.5,
        current_position=Decimal("0.0"),
        max_position=Decimal("1.0"),
    )
    assert verdict.approved is False
    assert verdict.action == "VETO"
    assert any("Spread" in r for r in verdict.reasons)


def test_policy_veto_directional_conflict(benign_judgments):
    """Directional mismatch (BUY with SHORT judgment) must trigger VETO."""
    engine = PolicyVetoEngine()
    benign_judgments.direction = "SHORT"

    verdict = engine.check(
        side="buy",
        proposed_qty=Decimal("0.5"),
        judgments=benign_judgments,
        spread_bps=2.0,
        current_position=Decimal("0.0"),
        max_position=Decimal("1.0"),
    )
    assert verdict.approved is False
    assert verdict.action == "VETO"
    assert any("Directional conflict" in r for r in verdict.reasons)


def test_policy_veto_inventory_clamp(benign_judgments):
    """When proposed order exceeds max_position headroom, size must be CLAMPED."""
    engine = PolicyVetoEngine()

    verdict = engine.check(
        side="buy",
        proposed_qty=Decimal("0.8"),
        judgments=benign_judgments,
        spread_bps=2.0,
        current_position=Decimal("0.5"),
        max_position=Decimal("1.0"),
    )
    assert verdict.approved is True
    assert verdict.action == "CLAMP"
    assert verdict.allowed_qty == Decimal("0.5")  # Headroom is 1.0 - 0.5 = 0.5


def test_policy_veto_killswitch(benign_judgments, tmp_path):
    """KillSwitch halt must trigger immediate VETO."""
    import godmode.core.paths as paths
    import godmode.core.db as db_mod
    import godmode.core.killswitch as ks_mod
    import godmode.core.audit as audit_mod

    db_file = tmp_path / "test_ks.sqlite3"
    orig_db = paths.DB_PATH
    paths.DB_PATH = db_file

    db_mod.reset_db_singleton()
    ks_mod._KS = None
    audit_mod._AUDIT = None

    ks = get_kill_switch()
    orig_stop = ks.stop_file
    ks.stop_file = tmp_path / "STOP"
    try:
        ks.engage(reason="Test emergency halt", source="test")
        engine = PolicyVetoEngine()

        verdict = engine.check(
            side="buy",
            proposed_qty=Decimal("0.5"),
            judgments=benign_judgments,
            spread_bps=2.0,
            current_position=Decimal("0.0"),
            max_position=Decimal("1.0"),
        )
        assert verdict.approved is False
        assert verdict.action == "VETO"
        assert any("KillSwitch" in r for r in verdict.reasons)
    finally:
        ks.reset(source="test")
        ks.stop_file = orig_stop
        paths.DB_PATH = orig_db
        db_mod.reset_db_singleton()
        ks_mod._KS = None
        audit_mod._AUDIT = None


def test_welford_toxic_flow_detection():
    from godmode.risk.policy_veto import check_toxic_flow_welford
    
    # 1. Normal distribution around 0.0 with std ~ 1.0
    ofi_window = [-0.8, -0.2, 0.5, 0.1, -0.4, 0.6, -0.1, 0.3, 0.0, -0.5]
    
    # Mild OFI: z around 1.0 -> not toxic
    is_toxic, z = check_toxic_flow_welford(ofi_window, current_ofi=0.5, z_threshold=2.5)
    assert is_toxic is False
    assert z < 2.5
    
    # Extreme OFI: z > 2.5 -> toxic
    is_toxic, z = check_toxic_flow_welford(ofi_window, current_ofi=5.0, z_threshold=2.5)
    assert is_toxic is True
    assert z > 2.5
    
    # 2. Quiet regime: zero variation protected by min_sigma=0.05 noise floor
    flat_window = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    is_toxic, z = check_toxic_flow_welford(flat_window, current_ofi=0.01, min_sigma=0.05)
    assert is_toxic is False
    assert z == pytest.approx(0.2)  # 0.01 / 0.05 = 0.2, no division by zero or false trigger


def test_policy_veto_ofi_spike_veto(benign_judgments):
    engine = PolicyVetoEngine()
    ofi_window = [-0.1, 0.0, 0.1, -0.05, 0.05, 0.0, -0.1]
    
    # Massive toxic OFI spike
    verdict = engine.check(
        side="buy",
        proposed_qty=Decimal("0.5"),
        judgments=benign_judgments,
        spread_bps=2.0,
        current_position=Decimal("0.0"),
        max_position=Decimal("1.0"),
        ofi_window=ofi_window,
        current_ofi=3.5,
    )
    assert verdict.approved is False
    assert verdict.action == "VETO"
    assert any("OFI toxic flow detected" in r for r in verdict.reasons)

