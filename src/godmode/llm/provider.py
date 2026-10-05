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
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from godmode.core.config import Config, ModelsConfig, load_config
from godmode.core.db import get_db
from godmode.core.logging import get_logger
from godmode.llm.free_router import get_free_router
from godmode.core.timeutil import utcnow_iso

log = get_logger("llm")


class LLMError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
#  Daily spend ledger (ScrollCraft quota-refund pattern)
# --------------------------------------------------------------------------- #
DEFAULT_LLM_DAILY_CAP_USD = 5.0
_RESERVE_EST_USD = 0.02


class LLMBudget:
    """Thread-safe daily LLM spend ledger.

    reserve() -> handle | None when the cap is reached. commit(handle, actual)
    settles a billed call; refund(handle) releases the reservation when nothing
    was charged (all paid providers failed / free tier served). Prevents N
    concurrent agent cycles from collectively overshooting GODMODE_LLM_DAILY_CAP_USD.
    """

    def __init__(self, daily_cap_usd: Optional[float] = None):
        raw = os.getenv("GODMODE_LLM_DAILY_CAP_USD")
        if daily_cap_usd is not None:
            cap = float(daily_cap_usd)
        elif raw:
            cap = float(raw)
        else:
            cap = DEFAULT_LLM_DAILY_CAP_USD
        if cap < 0:
            raise ValueError("LLM daily cap must be >= 0")
        self.daily_cap = cap
        self.spent_usd = 0.0
        self._in_flight = 0.0
        self._lock = threading.Lock()

    def reserve(self) -> Optional[float]:
        with self._lock:
            if self.spent_usd + self._in_flight + _RESERVE_EST_USD > self.daily_cap + 1e-12:
                return None
            self._in_flight += _RESERVE_EST_USD
            return _RESERVE_EST_USD

    def commit(self, handle: float, actual_cost_usd: float) -> None:
        with self._lock:
            self._in_flight = max(0.0, self._in_flight - handle)
            self.spent_usd += max(0.0, float(actual_cost_usd))

    def refund(self, handle: float) -> None:
        with self._lock:
            self._in_flight = max(0.0, self._in_flight - handle)

    @property
    def remaining_usd(self) -> float:
        with self._lock:
            return max(0.0, round(self.daily_cap - self.spent_usd - self._in_flight, 6))


_budget_singleton: Optional[LLMBudget] = None


def get_llm_budget() -> LLMBudget:
    global _budget_singleton
    if _budget_singleton is None:
        _budget_singleton = LLMBudget()
    return _budget_singleton


def reset_llm_budget(daily_cap_usd: Optional[float] = None) -> LLMBudget:
    """Test seam: swap in a fresh ledger and return it."""
    global _budget_singleton
    _budget_singleton = LLMBudget(daily_cap_usd=daily_cap_usd)
    return _budget_singleton


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
    """Best-effort parse of a JSON OBJECT from an LLM response (handles code fences).

    Non-object JSON (arrays, scalars) raises LLMError — callers depend on the
    dict contract for .get()-style agent output handling.
    """
    if not text or not text.strip():
        raise LLMError("empty LLM response; no JSON to parse")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise LLMError(f"expected JSON object, got {type(parsed).__name__}")
        return parsed
    except LLMError:
        raise
    except Exception:
        pass
    match = _JSON_RE.search(cleaned)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if not isinstance(parsed, dict):
                raise LLMError(f"expected JSON object, got {type(parsed).__name__}")
            return parsed
        except LLMError:
            raise
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
        temperature_val, max_tokens_val, timeout_val = self._params(temperature, max_tokens)

        # Quota guard: reserve before paid calls, commit actual cost on success,
        # refund when nothing was charged (ScrollCraft quota-refund pattern).
        budget = get_llm_budget()
        handle = budget.reserve()
        if handle is None:
            log.warning(
                "LLM daily cap $%.2f reached — paid providers skipped; free fallback only",
                budget.daily_cap,
            )
            candidates = []
        settled = False
        try:
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
                    budget.commit(handle, out.cost_usd)
                    settled = True
                    return out
                except Exception as exc:  # noqa: BLE001
                    last_err = exc
                    log.warning(f"LLM model {model} failed ({type(exc).__name__}): {exc}; trying next")
                    continue

            # Fallback to FreeLLMRouter (OpenRouter Free / Groq Free / Gemini Free)
            log.info(f"Attempting free-tier LLM fallback for role '{role}'")
            sys_prompt = messages[0]["content"] if messages and messages[0].get("role") == "system" else ""
            usr_prompt = messages[-1]["content"] if messages else ""
            free_text = get_free_router().complete(sys_prompt, usr_prompt)
            if free_text:
                return LLMResponse(
                    model="free-tier-fallback",
                    role=role,
                    text=free_text,
                    tokens_in=len(usr_prompt) // 4,
                    tokens_out=len(free_text) // 4,
                    latency_ms=100,
                    cost_usd=0.0
                )
        finally:
            if handle is not None and not settled:
                budget.refund(handle)

        raise LLMError(f"All LLM candidates and free fallbacks failed for role '{role}': {last_err}")

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
