"""Typed configuration.

Two sources, clearly separated:
  * .env            -> SECRETS only (API keys, mode). Loaded via pydantic-settings.
  * config/*.yaml   -> safe, structured settings (risk limits, markets, model roles).

`load_config()` merges them into one validated `Config` object and also loads the
.env values into the process environment so LiteLLM and ccxt can read the keys directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from godmode.core import paths


# --------------------------------------------------------------------------- #
#  Secrets (from .env / environment only)
# --------------------------------------------------------------------------- #
class Secrets(BaseSettings):
    """API keys and the run mode. Never written to logs or the database."""

    model_config = SettingsConfigDict(
        env_file=str(paths.ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    mode: str = Field(default="paper", validation_alias="GODMODE_MODE")
    env: str = Field(default="dev", validation_alias="GODMODE_ENV")

    # LLM providers (only one is required to start)
    anthropic_api_key: Optional[str] = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    gemini_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")
    ollama_api_base: Optional[str] = Field(default=None, validation_alias="OLLAMA_API_BASE")
    nvidia_api_key: Optional[str] = Field(default=None, validation_alias="NVIDIA_API_KEY")

    # Crypto testnet venues
    binance_testnet_api_key: Optional[str] = Field(default=None, validation_alias="BINANCE_TESTNET_API_KEY")
    binance_testnet_api_secret: Optional[str] = Field(default=None, validation_alias="BINANCE_TESTNET_API_SECRET")
    bybit_testnet_api_key: Optional[str] = Field(default=None, validation_alias="BYBIT_TESTNET_API_KEY")
    bybit_testnet_api_secret: Optional[str] = Field(default=None, validation_alias="BYBIT_TESTNET_API_SECRET")

    # Optional alerts
    telegram_bot_token: Optional[str] = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, validation_alias="TELEGRAM_CHAT_ID")

    def has_any_llm_key(self) -> bool:
        return any(
            [self.anthropic_api_key, self.gemini_api_key, self.openai_api_key, self.ollama_api_base]
        )

    def configured_llm_providers(self) -> list[str]:
        out = []
        if self.anthropic_api_key:
            out.append("anthropic")
        if self.gemini_api_key:
            out.append("gemini")
        if self.openai_api_key:
            out.append("openai")
        if self.ollama_api_base:
            out.append("ollama")
        if self.nvidia_api_key:
            out.append("nvidia")
        return out

    def has_binance_testnet(self) -> bool:
        return bool(self.binance_testnet_api_key and self.binance_testnet_api_secret)

    def has_bybit_testnet(self) -> bool:
        return bool(self.bybit_testnet_api_key and self.bybit_testnet_api_secret)

    def has_crypto_testnet(self) -> bool:
        return self.has_binance_testnet() or self.has_bybit_testnet()


# --------------------------------------------------------------------------- #
#  Structured settings (from yaml)
# --------------------------------------------------------------------------- #
class RiskLimits(BaseModel):
    """Hard limits enforced by the deterministic risk engine. The LLM cannot exceed these."""

    model_config = ConfigDict(extra="ignore")

    max_position_pct: float = 10.0           # max % of equity in one position
    max_total_exposure_pct: float = 60.0     # max % of equity deployed at once
    max_daily_loss_pct: float = 3.0          # day-stop after this realised loss
    max_drawdown_pct: float = 15.0           # hard halt this far below equity peak
    max_consecutive_losses: int = 6          # cool-down after N losers in a row
    per_order_max_notional: float = 5000.0   # cap on a single order's notional
    min_order_notional: float = 10.0         # ignore dust orders
    max_open_positions: int = 8              # cap on concurrent positions
    default_stop_loss_pct: float = 5.0       # default protective stop if omitted
    cooldown_minutes_after_halt: int = 60    # wait after a circuit-breaker halt


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: str = "paper"                      # paper | backtest | live
    base_currency: str = "USDT"
    paper_starting_equity: float = 100_000.0
    decision_interval_seconds: int = 300
    timezone: str = "UTC"


class MarketConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    venue: str = ""
    quote_currency: str = "USDT"
    symbols: list[str] = Field(default_factory=list)
    candle_timeframe: str = "1h"


class ModelsConfig(BaseModel):
    """Maps each agent role to an LLM model string (provider routed by LiteLLM)."""

    model_config = ConfigDict(extra="ignore")

    default: str = "anthropic/claude-3-5-haiku-latest"
    roles: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)

    def model_for(self, role: str) -> str:
        return self.roles.get(role, self.default)

    @property
    def fallbacks(self) -> list[str]:
        fb = self.params.get("fallbacks", [])
        return list(fb) if isinstance(fb, (list, tuple)) else []


class Config(BaseModel):
    secrets: Secrets
    app: AppSettings
    risk: RiskLimits
    markets: dict[str, MarketConfig]
    models: ModelsConfig

    @property
    def mode(self) -> str:
        return self.app.mode

    @property
    def is_live(self) -> bool:
        return self.app.mode.lower() == "live"

    def enabled_markets(self) -> dict[str, MarketConfig]:
        return {name: m for name, m in self.markets.items() if m.enabled}


# --------------------------------------------------------------------------- #
#  Loading
# --------------------------------------------------------------------------- #
def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_CONFIG_CACHE: Optional[Config] = None


def load_config(reload: bool = False) -> Config:
    """Load (and cache) the merged configuration."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not reload:
        return _CONFIG_CACHE

    # Make .env values visible to LiteLLM / ccxt via os.environ.
    if paths.ENV_FILE.exists():
        load_dotenv(paths.ENV_FILE, override=False)

    secrets = Secrets()

    raw = _read_yaml(paths.CONFIG_FILE)
    app = AppSettings(**(raw.get("app") or {}))
    risk = RiskLimits(**(raw.get("risk") or {}))
    markets = {
        name: MarketConfig(**(cfg or {})) for name, cfg in (raw.get("markets") or {}).items()
    }

    models_raw = _read_yaml(paths.MODELS_FILE)
    models = ModelsConfig(**models_raw) if models_raw else ModelsConfig()

    # An explicit GODMODE_MODE in the environment overrides the yaml app.mode.
    env_mode = os.environ.get("GODMODE_MODE")
    if env_mode:
        app.mode = env_mode

    cfg = Config(secrets=secrets, app=app, risk=risk, markets=markets, models=models)
    _CONFIG_CACHE = cfg
    return cfg


def reset_config_cache() -> None:
    """Drop the cached Config singleton (testing helper). NEXT call to
    `load_config()` will re-read .env + yaml files.
    """
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
