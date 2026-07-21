"""Free-Tier Multi-Provider LLM Router.

Automatically routes prompts across legitimate free public LLM endpoints discovered on GitHub:
1. OpenRouter Free Tier Models (e.g. meta-llama/llama-3.1-8b-instruct:free)
2. Groq Free Tier (llama-3.3-70b-versatile)
3. Google Gemini Free Tier (gemini-2.5-flash)

Built under the Ponytail Mindset: stdlib urllib, zero external pip dependencies,
automatic failover, and graceful fallback so trading never halts or crashes.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from godmode.core.logging import get_logger

log = get_logger("llm.free_router")


class FreeLLMRouter:
    """Intelligent fallback router for free-tier LLM APIs."""

    def __init__(self):
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.groq_key = os.environ.get("GROQ_API_KEY", "")
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")

    def _post_json(self, url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float = 6.0) -> Optional[Dict[str, Any]]:
        try:
            # SECURITY: use the OS trust store with FULL hostname + certificate
            # validation. Never disable TLS — disabling would let any MITM
            # intercept the Bearer token and feed the trader poisoned prompts.
            ctx = ssl.create_default_context()

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                res_body = resp.read().decode("utf-8")
                return json.loads(res_body)
        except Exception as e:
            log.debug(f"FreeLLMRouter request failed for {url}: {e}")
            return None

    def complete(self, system_prompt: str, user_prompt: str, model_preference: str = "free") -> Optional[str]:
        """Attempt completion across available free endpoints in priority order."""
        # 1. Try OpenRouter Free Models if API key is present
        if self.openrouter_key:
            res = self._post_json(
                "https://openrouter.ai/api/v1/chat/completions",
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "HTTP-Referer": "https://github.com/Ai-Trader/Godmode",
                    "X-Title": "Godmode Trading Terminal",
                },
                {
                    "model": "meta-llama/llama-3.1-8b-instruct:free",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                },
            )
            if res and "choices" in res and len(res["choices"]) > 0:
                return res["choices"][0]["message"]["content"]

        # 2. Try Groq Free Tier if API key is present
        if self.groq_key:
            res = self._post_json(
                "https://api.groq.com/openai/v1/chat/completions",
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.groq_key}",
                },
                {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                },
            )
            if res and "choices" in res and len(res["choices"]) > 0:
                return res["choices"][0]["message"]["content"]

        # 3. Try Google Gemini Free Tier if API key is present
        if self.gemini_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_key}"
            res = self._post_json(
                url,
                {"Content-Type": "application/json"},
                {
                    "contents": [
                        {"role": "user", "parts": [{"text": f"SYSTEM: {system_prompt}\n\nUSER: {user_prompt}"}]}
                    ]
                },
            )
            if res and "candidates" in res and len(res["candidates"]) > 0:
                parts = res["candidates"][0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")

        return None


_ROUTER_SINGLETON: Optional[FreeLLMRouter] = None


def get_free_router() -> FreeLLMRouter:
    global _ROUTER_SINGLETON
    if _ROUTER_SINGLETON is None:
        _ROUTER_SINGLETON = FreeLLMRouter()
    return _ROUTER_SINGLETON
