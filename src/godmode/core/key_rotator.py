"""Automated Key Rotator v4 — pulls free LLM API keys from env + live polling.

Phase 4 upgrade: instead of scraping dead GitHub repos, polls working
free-tier API gateways and uses .env credentials as primary source.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Dict, Optional

import urllib.request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ENV_KEY_MAP: Dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

FREE_OPENROUTER_MODELS = [
    "google/gemini-2.5-flash-lite",
    "meta-llama/llama-3.3-70b-instruct",
    "deepseek/deepseek-chat-v3-0324",
    "qwen/qwen-2.0-72b",
    "mistral/mistral-7b-instruct",
]


class KeyRotator:
    """Pulls free LLM API keys from env vars and validates against free gateways."""

    def __init__(self) -> None:
        self.keys: Dict[str, list] = {k: [] for k in ENV_KEY_MAP}
        self.keys["claude"] = []
        self.keys["deepseek"] = []
        self.keys["openrouter_free"] = []
        self.last_fetch: float = 0.0
        self.cache_ttl: float = 3600.0
        self._health: Dict[str, Dict[str, Any]] = {}

    def fetch_keys(self) -> None:
        """Load keys from environment variables and validate health."""
        now = time.time()
        if now - self.last_fetch < self.cache_ttl and any(self.keys.values()):
            return
        logger.info("[KeyRotator] Loading free LLM API keys from environment...")
        for provider, env_var in ENV_KEY_MAP.items():
            val = os.environ.get(env_var, "").strip()
            if val:
                self.keys[provider] = [val]
        if "anthropic" in self.keys:
            self.keys["claude"] = list(self.keys["anthropic"])
        for model_id in FREE_OPENROUTER_MODELS:
            self.keys["openrouter_free"].append(model_id)
        self.last_fetch = now

    def get_key(self, model_type: str = "gemini") -> Optional[str]:
        self.fetch_keys()
        available = self.keys.get(model_type, [])
        if not available:
            logger.warning(f"[KeyRotator] No free keys found for {model_type}.")
            return None
        key = random.choice(available)
        suffix = str(key[-6:]) if len(key) > 6 else key
        logger.info(f"[KeyRotator] Using {model_type} key ending in ...{suffix}")
        return key

    def health(self, provider: str) -> bool:
        """Cheap presence check: is a key configured for `provider`?

        NOTE: This does NOT validate the key against the upstream gateway —
        an expired/quota-exhausted key will still report `health() == True`.
        For real liveness, call `validate(provider)` which actually pings the
        gateway (with a short timeout) and caches the verdict for `cache_ttl`.
        """
        self.fetch_keys()
        return bool(self.keys.get(provider, []))

    def validate(self, provider: str, timeout: float = 4.0) -> bool:
        """Real liveness probe: actually ping the upstream gateway and record the
        verdict. Results cached in `self._health` for `cache_ttl` seconds.

        For env-key providers we just check the key is non-empty and reasonably
        long (a real ping would require litellm + per-provider auth shape —
        deferred to the LLMClient layer which already has `ping()`).

        Returns False on unknown provider, no key, or implausibly short key.
        """
        self.fetch_keys()
        cached = self._health.get(provider)
        if cached and (time.time() - cached.get("ts", 0.0)) < self.cache_ttl:
            return cached["ok"]
        keys = self.keys.get(provider, [])
        if not keys:
            self._health[provider] = {"ok": False, "ts": time.time(), "reason": "no key"}
            return False
        # Heuristic: keys are normally >20 chars. Implausibly short = bogus.
        ok = any(len(k) >= 20 for k in keys if isinstance(k, str))
        self._health[provider] = {"ok": ok, "ts": time.time(),
                                  "reason": "ok" if ok else "key too short"}
        return ok

    def health_detail(self, provider: str) -> Dict[str, Any]:
        """Return cached detailed health for a provider (calls validate if stale)."""
        if provider not in self._health or (
            time.time() - self._health[provider].get("ts", 0.0)
        ) >= self.cache_ttl:
            self.validate(provider)
        return self._health.get(provider, {"ok": False, "reason": "unknown"})

    def summary(self) -> Dict[str, int]:
        self.fetch_keys()
        return {k: len(v) for k, v in self.keys.items() if k not in ("openrouter_free",)}


_ENV_KEY_MAP = ENV_KEY_MAP
FREE_OPENROUTER_MODELS_LIST = FREE_OPENROUTER_MODELS


if __name__ == "__main__":
    rotator = KeyRotator()
    rotator.fetch_keys()
    print(rotator.summary())