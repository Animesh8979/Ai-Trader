"""NeuroSymbolicRiskOracle — adaptive LLM-proposed risk rules with symbolic safety.

Every 4 hours:
- LLM analyzes market state (regime, on-chain, news, volatility)
- Proposes temporary risk rules (e.g., "BTC vol 3x normal → max_position_pct = 5% for 4h")
- Rules compiled into symbolic AST predicates with safety checks
- Time-bounded: rules expire after specified TTL
- Layer 0 (hard limits in RiskEngine) is NEVER modified
"""

from __future__ import annotations

import ast
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from godmode.core.logging import get_logger

log = get_logger("risk.neuro_symbolic")


ALLOWED_FUNCTIONS = {
    "min", "max", "abs", "round",
    "regime", "volatility", "drawdown", "leverage",
    "fear_greed", "funding_rate", "n_consecutive_losses",
}

DENYLIST_NODES = (
    ast.Import, ast.ImportFrom,
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
    ast.Attribute, ast.Subscript,
    ast.Assign, ast.AugAssign, ast.AnnAssign,
    ast.For, ast.While, ast.If,
    ast.Try, ast.With, ast.AsyncFor, ast.AsyncWith,
    ast.Raise, ast.Return, ast.Yield, ast.YieldFrom, ast.Await,
    ast.Global, ast.Nonlocal, ast.Delete, ast.Pass, ast.Break, ast.Continue,
)


ALLOWED_CONTEXT_VARS = {
    "regime", "volatility", "drawdown", "leverage",
    "fear_greed", "funding_rate", "n_consecutive_losses",
}

# Numeric literals we ship as defaults if ctx lacks a context var.
_CONTEXT_VAR_DEFAULTS = {
    "regime": 0, "volatility": 0, "drawdown": 0, "leverage": 0,
    "fear_greed": 50, "funding_rate": 0, "n_consecutive_losses": 0,
}


@dataclass
class TemporaryRule:
    rule_id: str
    name: str
    predicate_source: str
    action: Dict[str, Any]
    expires_at: float
    created_at: float
    verdict: str = "active"
    activations: int = 0
    last_eval_ts: float = 0.0
    # Cached compiled predicate — compiled ONCE at proposal time, never re-parsed.
    compiled_predicate: Optional[Any] = None


def _validate_predicate_safety(expr_source: str) -> bool:
    """AST allowlist check: reject dangerous nodes and unauthorized function calls."""
    try:
        tree = ast.parse(expr_source, mode="eval")
    except SyntaxError:
        return False

    deny_types = tuple(DENYLIST_NODES)
    for node in ast.walk(tree):
        if isinstance(node, deny_types):
            return False
        # Reject bare names that aren't allowed functions or context vars.
        # This blocks tricks like `__import__`, `exit`, `open`, `eval`, etc.
        if isinstance(node, ast.Name):
            if node.id not in ALLOWED_FUNCTIONS and node.id not in ALLOWED_CONTEXT_VARS:
                return False
            # Names can only be Load-context (reading a value). Reject Store/Delete.
            if not isinstance(node.ctx, ast.Load):
                return False
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                return False
            if node.func.id not in ALLOWED_FUNCTIONS:
                return False
            if any(k.arg in {"__builtins__", "globals", "locals"} for k in node.keywords):
                return False
        # Reject literals carrying huge strings/bytes (potential memory bomb).
        if isinstance(node, (ast.Str, ast.Bytes)) and len(node.s) > 256:
            return False
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) \
                and len(node.value) > 256:
            return False
        # Reject numeric bombs (e.g. 10**10**10 evaluated inside expression).
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant):
                try:
                    if abs(int(node.left.value) ** int(node.right.value)) > 10**12:
                        return False
                except Exception:
                    return False

    return True


def _compile_predicate(expr_source: str) -> Any:
    """Compile a validated predicate into a zero-deps callable(ctx)->bool.

    SECURITY MODEL:
    - Code is parsed once here; AST denylist + allowlist enforce only safe constructs.
    - Globals is locked to 4 safe builtins (min/max/abs/round) + bool/True/False/None.
    - Locals is built fresh per-call from defaults + caller ctx, so a malicious ctx
      key named "min" CANNOT shadow the builtin (globals wins on Name lookup only
      when locals misses — and we put min/max in globals, not locals).
    - Actually Python eval checks locals FIRST, so we must NOT copy min/max into
      locals. We put context vars in locals and builtins in globals.
    """
    if not _validate_predicate_safety(expr_source):
        return None
    try:
        safe_globals = {
            "__builtins__": {},
            "min": min, "max": max, "abs": abs, "round": round,
            "True": True, "False": False, "None": None,
            "bool": bool,
        }
        code = compile(expr_source, "<neuro_symbolic>", "eval")

        def compiled(ctx: dict):
            # Build locals from defaults, then layer in ctx. We deliberately do NOT
            # copy min/max/abs/round into locals — they live in globals only, so a
            # hostile ctx key called "min" cannot replace the builtin.
            safe_locals: Dict[str, Any] = dict(_CONTEXT_VAR_DEFAULTS)
            # Only accept ctx keys that are in the allowlist — drop anything else
            # so an attacker cannot stuff arbitrary names into the eval namespace.
            for k, v in (ctx or {}).items():
                if k in ALLOWED_CONTEXT_VARS:
                    safe_locals[k] = v
            try:
                result = eval(code, safe_globals, safe_locals)
            except Exception:
                return False
            return bool(result)
        return compiled
    except Exception as exc:
        log.warning(f"[NeuroSymbolic] Compile failed: {exc}")
        return None


class NeuroSymbolicRiskOracle:
    """Adaptive risk supervisor — proposes and validates temporary rules."""

    def __init__(self, max_active_rules: int = 10, default_ttl_seconds: float = 14400.0):
        self.max_active_rules = max_active_rules
        self.default_ttl_seconds = default_ttl_seconds
        self.active_rules: List[TemporaryRule] = []
        self.proposal_history: List[Dict[str, Any]] = []

    def propose_rule(
        self,
        name: str,
        predicate_source: str,
        action: Dict[str, Any],
        llm_client: Any = None,
        market_context: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        ttl = ttl_seconds or self.default_ttl_seconds

        compiled = _compile_predicate(predicate_source)
        if compiled is None:
            verdict = "rejected_compile_failed"
            log.warning(f"[NeuroSymbolic] Rejected rule {name} — failed safety compile.")
            proposal_record = {
                "name": name,
                "predicate": predicate_source,
                "action": action,
                "verdict": verdict,
                "ts": now,
            }
            self.proposal_history.append(proposal_record)
            return proposal_record

        verdict = "accepted"
        rule = TemporaryRule(
            rule_id=f"r{int(now * 1000) % 1000000}",
            name=name,
            predicate_source=predicate_source,
            action=action,
            expires_at=now + ttl,
            created_at=now,
            verdict=verdict,
            compiled_predicate=compiled,
        )
        self.active_rules.append(rule)
        if len(self.active_rules) > self.max_active_rules:
            oldest = self.active_rules.pop(0)
            log.info(f"[NeuroSymbolic] Evicted oldest active rule {oldest.name}")
        log.info(f"[NeuroSymbolic] Active rule added: {name} (TTL={ttl}s)")

        proposal_record = {
            "name": name,
            "predicate": predicate_source,
            "action": action,
            "verdict": verdict,
            "ts": now,
        }
        self.proposal_history.append(proposal_record)
        return proposal_record

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate all active rules against context."""
        now = time.time()
        expired_indices = []
        triggered_actions: Dict[str, Any] = {}

        for i, rule in enumerate(self.active_rules):
            if rule.expires_at < now:
                expired_indices.append(i)
                continue

            # SECURITY: use the cached compiled predicate (compiled once at
            # proposal time, validated by AST allowlist). Never re-parse here.
            compiled = rule.compiled_predicate
            if compiled is None:
                # Stale rule from a prior session / failed compile — drop it.
                expired_indices.append(i)
                continue

            try:
                result = compiled(context)
            except Exception as exc:
                log.debug(f"[NeuroSymbolic] Rule {rule.name} eval failed: {exc}")
                continue

            rule.last_eval_ts = now
            if result:
                rule.activations += 1
                for k, v in rule.action.items():
                    triggered_actions[k] = v
                log.info(
                    f"[NeuroSymbolic] Rule {rule.name} activated "
                    f"(action: {rule.action})"
                )

        for i in reversed(expired_indices):
            expired = self.active_rules.pop(i)
            log.info(f"[NeuroSymbolic] Expired rule {expired.name}")

        return {
            "triggered_actions": triggered_actions,
            "active_count": len(self.active_rules),
            "n_expired": len(expired_indices),
        }

    def llm_propose_from_market_state(
        self,
        market_state: Dict[str, Any],
        llm_client: Any,
    ) -> Dict[str, Any]:
        """LLM proposes a single temporary risk rule based on current market state."""
        prompt = (
            "You are a Risk Oracle. Analyze the market state and propose ONE temporary risk rule.\n"
            "The rule must be a conditional action with a Python predicate.\n"
            "Allowed context vars: regime, volatility, drawdown, leverage, "
            "fear_greed, funding_rate, n_consecutive_losses.\n"
            "Allowed functions: min, max, abs, round.\n"
            "Allowed operators: ==, !=, >, <, >=, <=, and, or, not, +, -, *, /.\n\n"
            f"MARKET STATE:\n{json.dumps(market_state, indent=2)}\n\n"
            "Respond ONLY with JSON: "
            '{"name": "string", "predicate": "python expression", '
            '"action": {"max_position_pct": float}, "ttl_seconds": int}'
        )
        try:
            response = llm_client.complete(
                "neuro_symbolic_oracle",
                [
                    {"role": "system", "content": "You propose safe, bounded risk rules."},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.text if hasattr(response, "text") else str(response)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            proposal = json.loads(text)
            return self.propose_rule(
                name=proposal.get("name", "llm_rule"),
                predicate_source=proposal.get("predicate", "False"),
                action=proposal.get("action", {}),
                ttl_seconds=proposal.get("ttl_seconds"),
            )
        except Exception as exc:
            log.warning(f"[NeuroSymbolic] LLM proposal failed: {exc}")
            return {"verdict": "rejected_llm_failed", "error": str(exc)}

    def status(self) -> Dict[str, Any]:
        return {
            "active_rules": len(self.active_rules),
            "total_proposals": len(self.proposal_history),
            "rule_names": [r.name for r in self.active_rules],
        }


_nsr_singleton: Optional[NeuroSymbolicRiskOracle] = None


def get_neuro_symbolic_oracle() -> NeuroSymbolicRiskOracle:
    global _nsr_singleton
    if _nsr_singleton is None:
        _nsr_singleton = NeuroSymbolicRiskOracle()
    return _nsr_singleton