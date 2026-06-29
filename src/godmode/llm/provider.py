"""Model-agnostic LLM client built on LiteLLM.

One `complete()` call routes to Claude, Gemini, OpenAI, or a local Ollama model based on
the role->model mapping in config/models.yaml. Features:
  * per-role model selection (cheap analysts, strong trader/risk)
  * automatic retries on transient errors (tenacity)
  * provider fallbacks, skipping any provider whose API key isn't configured
  * cost + token accounting recorded to the audit DB
  * tolerant JSON extraction for structured agent outputs

Swapping Claude -> Gemini is just editing model strings in models.yaml.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from godmode.core.config import Config, ModelsConfig, load_config
from godmode.core.db import get_db
from godmode.core.logging import get_logger
from godmode.core.timeutil import utcnow_iso

log = get_logger("llm")


class LLMError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
#  Response container + JSON parsing
# --------------------------------------------------------------------------- #
@dataclass
class LLMResponse:
    text: str
    model: str
    role: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    raw: Any = None

    def json(self) -> dict:
        return extract_json(self.text)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict:
    """Best-effort parse of a JSON object from an LLM response (handles code fences)."""
    if not text or not text.strip():
        raise LLMError("empty LLM response; no JSON to parse")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = _JSON_RE.search(cleaned)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"could not parse JSON from LLM response: {exc}")
    raise LLMError("no JSON object found in LLM response")


# --------------------------------------------------------------------------- #
#  Retry classification
# --------------------------------------------------------------------------- #
_RETRYABLE = ("ratelimit", "timeout", "serviceunavailable", "apiconnection",
              "internalserver", "overloaded", "503", "429")
_NONRETRYABLE = ("authentication", "permissiondenied", "notfound", "badrequest",
                 "invalidrequest", "contentpolicy")


def _is_retryable(exc: BaseException) -> bool:
    name = (type(exc).__name__ + " " + str(exc)).lower()
    if any(k in name for k in _NONRETRYABLE):
        return False
    return any(k in name for k in _RETRYABLE)


def _summarize(messages: list[dict], limit: int = 1500) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "?")
        content = str(m.get("content", ""))
        parts.append(f"[{role}] {content}")
    return (" | ".join(parts))[:limit]


# --------------------------------------------------------------------------- #
#  The client
# --------------------------------------------------------------------------- #
class LLMClient:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or load_config()
        self.models: ModelsConfig = self.config.models
        self._import_error: Optional[Exception] = None
        try:
            import litellm

            litellm.drop_params = True        # silently ignore params a provider can't take
            litellm.suppress_debug_info = True
            self._litellm = litellm
        except Exception as exc:  # noqa: BLE001
            self._litellm = None
            self._import_error = exc

    # -- model resolution ------------------------------------------------- #
    def model_for(self, role_or_model: str) -> str:
        """A string containing '/' is treated as a literal model; otherwise as a role."""
        if "/" in role_or_model:
            return role_or_model
        return self.models.model_for(role_or_model)

    def _provider_available(self, model: str) -> bool:
        s = self.config.secrets
        m = model.lower()
        if m.startswith(("anthropic/", "claude")):
            return bool(s.anthropic_api_key)
        if m.startswith(("gemini/", "google/")):
            return bool(s.gemini_api_key)
        if m.startswith(("openai/", "gpt", "o1", "o3")):
            return bool(s.openai_api_key)
        if m.startswith(("ollama/", "ollama_chat/")):
            return bool(s.ollama_api_base)
        if m.startswith(("nvidia/", "nvidia_nim/")):
            return bool(s.nvidia_api_key)
        return True  # unknown provider: assume the user set env another way

    def _candidates(self, role: str) -> list[str]:
        primary = self.model_for(role)
        chain = [primary] + [m for m in self.models.fallbacks if m and m != primary]
        return [m for m in chain if self._provider_available(m)]

    # -- params ----------------------------------------------------------- #
    def _params(self, temperature: Optional[float], max_tokens: Optional[int]):
        p = self.models.params or {}
        return (
            temperature if temperature is not None else p.get("temperature", 0.2),
            max_tokens if max_tokens is not None else p.get("max_tokens", 1500),
            p.get("timeout_seconds", 60),
        )

    # -- core call -------------------------------------------------------- #
    def complete(
        self,
        role: str,
        messages: list[dict],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        record: bool = False,
        cycle_id: Optional[str] = None,
        run_id: Optional[int] = None,
    ) -> LLMResponse:
        if self._litellm is None:
            raise LLMError(f"litellm is not importable: {self._import_error}")

        candidates = self._candidates(role)
        if not candidates:
            raise LLMError(
                f"No LLM model is available for role '{role}'. "
                f"Add an API key to .env (run `godmode setup`)."
            )

        temperature_val, max_tokens_val, timeout_val = self._params(temperature, max_tokens)
        last_err: Optional[Exception] = None

        for model in candidates:
            started = time.perf_counter()
            try:
                resp = self._call_with_retry(
                    model, messages, temperature_val, max_tokens_val, timeout_val, json_mode
                )
                out = self._to_response(resp, model, role)
                out.latency_ms = int((time.perf_counter() - started) * 1000)
                if record:
                    self._record(out, messages, cycle_id, run_id)
                return out
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                log.warning(f"LLM model {model} failed ({type(exc).__name__}): {exc}; trying next")
                continue

        raise LLMError(f"All LLM candidates failed for role '{role}': {last_err}")

    def _call_with_retry(self, model, messages, temperature, max_tokens, timeout, json_mode):
        from tenacity import (
            retry,
            retry_if_exception,
            stop_after_attempt,
            wait_exponential,
        )

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception(_is_retryable),
        )
        def _do():
            kwargs: dict[str, Any] = dict(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            if model.lower().startswith("ollama"):
                base = self.config.secrets.ollama_api_base
                if base:
                    kwargs["api_base"] = base
            return self._litellm.completion(**kwargs)

        return _do()

    def _to_response(self, resp, model: str, role: str) -> LLMResponse:
        try:
            text = resp.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            text = str(resp)
        usage = getattr(resp, "usage", None)
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = 0.0
        try:
            cost = float(self._litellm.completion_cost(completion_response=resp) or 0.0)
        except Exception:  # noqa: BLE001
            cost = 0.0
        return LLMResponse(
            text=text, model=model, role=role,
            tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost, raw=resp,
        )

    def _record(self, out: LLMResponse, messages, cycle_id, run_id) -> None:
        try:
            get_db().insert(
                "agent_messages",
                {
                    "run_id": run_id,
                    "ts": utcnow_iso(),
                    "cycle_id": cycle_id,
                    "role": out.role,
                    "model": out.model,
                    "input_summary": _summarize(messages),
                    "output_text": out.text[:8000],
                    "tokens_in": out.tokens_in,
                    "tokens_out": out.tokens_out,
                    "cost_usd": out.cost_usd,
                    "latency_ms": out.latency_ms,
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.debug(f"failed to record agent message: {exc}")

    # -- convenience ------------------------------------------------------ #
    def complete_json(self, role: str, system: str, user: str, **kw) -> dict:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self.complete(role, messages, json_mode=True, **kw).json()

    def ping(self, model_or_role: Optional[str] = None) -> LLMResponse:
        """Tiny round-trip used by the setup wizard / smoke test to validate a key."""
        role = model_or_role or "default"
        return self.complete(
            role,
            [{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=16,
            temperature=0,
        )
