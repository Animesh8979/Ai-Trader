"""Model-agnostic LLM layer.

Wraps LiteLLM so the rest of the system can call Claude, Gemini, OpenAI, or a local
Ollama model through one interface, choosing the model per agent *role* (cheap models
for analysts, strong models for the trader/risk roles). Adds retries, JSON-structured
output, cost tracking, and provider fallbacks.
"""

from godmode.llm.provider import LLMClient, LLMResponse, LLMError  # noqa: F401

__all__ = ["LLMClient", "LLMResponse", "LLMError"]
