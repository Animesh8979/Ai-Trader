from godmode.core.config import ModelsConfig, RiskLimits, load_config


def test_load_config_has_sane_defaults():
    cfg = load_config(reload=True)
    assert cfg.mode in ("paper", "backtest", "live")
    assert cfg.risk.max_position_pct > 0
    assert cfg.risk.max_daily_loss_pct > 0
    assert "crypto" in cfg.markets


def test_risk_limits_defaults():
    r = RiskLimits()
    assert r.max_total_exposure_pct >= r.max_position_pct
    assert r.min_order_notional < r.per_order_max_notional


def test_models_role_resolution():
    mc = ModelsConfig(default="anthropic/default-model", roles={"trader": "anthropic/strong"})
    assert mc.model_for("trader") == "anthropic/strong"
    assert mc.model_for("unknown_role") == "anthropic/default-model"


def test_models_fallbacks_list():
    mc = ModelsConfig(params={"fallbacks": ["gemini/x", "openai/y"]})
    assert mc.fallbacks == ["gemini/x", "openai/y"]
