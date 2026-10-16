#!/usr/bin/env python3
"""
Smart Thinking Engine (smart_thinking_engine.py)
Multi-mode cognitive reasoning framework implementing 19 structured thinking modes.
Pure Python 3.10+ standard library. Zero external dependencies.
"""

import sys
import json
import math
import argparse
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ModeResult:
    mode_id: int
    mode_name: str
    focus: str
    prompt_template: str
    analysis: Dict[str, Any]
    actionable_verdict: str


class SmartThinkingEngine:
    MODES = {
        1: ("Lateral Thinking", "Paradigm shift, orthogonal alternatives, bypassing illusions"),
        2: ("Systems Thinking", "Feedback loops, causal cascades, emergent backpressure"),
        3: ("Dialectical Thinking", "Hegelian Thesis vs. Antithesis -> Sublation / Synthesis"),
        4: ("First-Principles", "Axiomatic deconstruction, invariants vs. cultural dogma"),
        5: ("Metacognitive", "Audit of reasoning bias, symptom vs. root cause invariant"),
        6: ("Inversion (Jacobi)", "Solving backwards, eliminating catastrophic failure states"),
        7: ("Pre-Mortem Analysis", "Prospective hindsight, anticipating post-deployment crashes"),
        8: ("Critical Falsification", "Karl Popper empirical falsification and red-team tests"),
        9: ("Divergent Ideation", "Unconstrained generation of distinct candidate architectures"),
        10: ("Convergent Pruning", "Deterministic multi-criteria scoring and candidate pruning"),
        11: ("Bayesian Updating", "Dynamic prior-to-posterior probability belief calibration"),
        12: ("TRIZ Contradiction", "Eliminating trade-offs without mutual compromise"),
        13: ("Analogical Mapping", "Cross-domain kernel transfer from OS, biology, distributed systems"),
        14: ("Adversarial Red Team", "Exploiting hidden edge cases, race conditions, injection"),
        15: ("Fermi / Slicing", "Order-of-magnitude scaling, resource bounds, IOPS/VRAM estimation"),
        16: ("Morphological Matrix", "Zwicky multi-dimensional parameter matrix decomposition"),
        17: ("OODA Loop", "Observe -> Orient -> Decide -> Act deterministic state machine"),
        18: ("Counterfactual", "What-if dependency degradation and fault mitigation"),
        19: ("Minimalist Razor", "Ponytail / Karpathy nanoGPT Occam distillation (Decision Ladder)")
    }

    def __init__(self):
        pass

    def run_mode(self, mode_id: int, problem: str, context: Optional[Dict[str, Any]] = None) -> ModeResult:
        if mode_id not in self.MODES:
            raise ValueError(f"Invalid mode_id {mode_id}. Must be between 1 and 19.")

        mode_name, focus = self.MODES[mode_id]
        context = context or {}

        dispatcher = {
            1: self._lateral_thinking,
            2: self._systems_thinking,
            3: self._dialectical_thinking,
            4: self._first_principles,
            5: self._metacognitive,
            6: self._inversion,
            7: self._pre_mortem,
            8: self._critical_falsification,
            9: self._divergent_ideation,
            10: self._convergent_pruning,
            11: self._bayesian_updating,
            12: self._triz_contradiction,
            13: self._analogical_mapping,
            14: self._adversarial_red_team,
            15: self._fermi_slicing,
            16: self._morphological_matrix,
            17: self._ooda_loop,
            18: self._counterfactual,
            19: self._minimalist_razor
        }

        template, analysis, verdict = dispatcher[mode_id](problem, context)
        return ModeResult(
            mode_id=mode_id,
            mode_name=mode_name,
            focus=focus,
            prompt_template=template,
            analysis=analysis,
            actionable_verdict=verdict
        )

    # 1. Lateral Thinking
    def _lateral_thinking(self, problem: str, ctx: Dict[str, Any]):
        template = "What if the apparent constraint is an illusion? What orthogonal approach bypasses this entirely?"
        analysis = {
            "apparent_constraint": f"Direct sequential confrontation of '{problem}'",
            "orthogonal_inversions": [
                "Invert synchronous polling to push-based reactive notification or event interrupt",
                "Decouple state persistence from transient execution memory",
                "Shift computation from runtime hot-path to static compile/pre-generation"
            ],
            "bypassed_dogma": "Assuming sequential synchronous execution is necessary."
        }
        verdict = "Discard the direct collision path; route via asynchronous event interrupt or zero-copy buffer."
        return template, analysis, verdict

    # 2. Systems Thinking
    def _systems_thinking(self, problem: str, ctx: Dict[str, Any]):
        template = "Map the call graph, data flow, and backpressure. Where do second-order feedback loops amplify errors?"
        analysis = {
            "feedback_loops": [
                {"type": "Reinforcing", "loop": "Error retry storm -> downstream queue saturation -> timeout cascade"},
                {"type": "Balancing", "loop": "Circuit breaker trips -> traffic sheds -> downstream recovers"}
            ],
            "bottlenecks": ["Shared database lock contention", "Blocking socket IO in event loop"],
            "cascade_risk_score": 0.78
        }
        verdict = "Introduce bounded exponential backoff with full jitter and an isolated bulkhead partition."
        return template, analysis, verdict

    # 3. Dialectical Thinking
    def _dialectical_thinking(self, problem: str, ctx: Dict[str, Any]):
        template = "State the proposed solution (Thesis). Formulate the strongest counter-argument (Antithesis). Synthesize superior architecture."
        analysis = {
            "thesis": f"Implement immediate aggressive caching for '{problem}' to achieve minimum latency.",
            "antithesis": "Aggressive caching causes stale state reads, race conditions on eviction, and memory bloat.",
            "synthesis": "Version-stamped immutable append-only WAL with invalidation pulses via lightweight pub/sub."
        }
        verdict = "Adopt immutable versioned snapshots with optimistic read validation instead of mutable cache."
        return template, analysis, verdict

    # 4. First-Principles
    def _first_principles(self, problem: str, ctx: Dict[str, Any]):
        template = "Strip all library dogma and existing assumptions. What physical/computational invariants must hold true?"
        analysis = {
            "physical_invariants": [
                "CPU cores can only execute instructions sequentially or via SIMD/multithreading",
                "RAM transfer is bounded by memory bus bandwidth (~40-60 GB/s)",
                "Disk IO requires syscall boundaries unless memory-mapped"
            ],
            "cultural_dogmas": [
                "Must wrap everything in microservices or heavy ORM frameworks",
                "Must use external Redis when local SQLite WAL handles 100K ops/s"
            ],
            "fundamental_kernel": f"Directly compute minimal bytes for '{problem}' using contiguous memory."
        }
        verdict = "Eliminate intermediate serializations; implement zero-copy memoryview and local memory buffer."
        return template, analysis, verdict

    # 5. Metacognitive
    def _metacognitive(self, problem: str, ctx: Dict[str, Any]):
        template = "Why am I favoring this approach? Am I patching a symptom or addressing the root cause invariant?"
        analysis = {
            "detected_biases": [
                "Availability Heuristic (reaching for familiar external pip package)",
                "Sunk Cost (persisting with flawed ctypes approach instead of clean standard library)"
            ],
            "root_cause_vs_symptom": {
                "symptom": f"Error triggered when processing '{problem}'",
                "root_cause": "Contract mismatch or unverified state assumption at the system boundary"
            }
        }
        verdict = "Halt symptom patching. Verify the boundary contract and assert invariants deterministically."
        return template, analysis, verdict

    # 6. Inversion (Jacobi)
    def _inversion(self, problem: str, ctx: Dict[str, Any]):
        template = "Invert, always invert. What would guarantee failure in this system? Eliminate those conditions."
        analysis = {
            "failure_guarantees": [
                "Unbounded queue growth with no memory ceiling",
                "Holding file handles across asynchronous process boundaries on Windows",
                "Swallowing exceptions silently with blank try/except passes"
            ],
            "inversion_prescriptions": [
                "Bound all queues and buffers strictly",
                "Guarantee atomic file closing with RAII context managers and retry backoff",
                "Fail visibly and immediately with concrete error diagnostics"
            ]
        }
        verdict = "Enforce hard bounds and explicit error propagation; eradicate silent exception swallowing."
        return template, analysis, verdict

    # 7. Pre-Mortem Analysis
    def _pre_mortem(self, problem: str, ctx: Dict[str, Any]):
        template = "Assume this implementation crashed in production 2 weeks from now. What was the exact root cause?"
        analysis = {
            "postulated_disaster": f"Complete system halt under heavy workload for '{problem}'",
            "probable_root_causes": [
                {"cause": "Windows file lock contention on SQLite WAL or temp image", "probability": 0.45},
                {"cause": "Memory leak due to circular references in long-running daemon", "probability": 0.30},
                {"cause": "Deadlock in threadpool due to nested blocking calls", "probability": 0.25}
            ],
            "preventative_guards": [
                "Implement file lock retry guardian with jitter",
                "Run gc.collect() checkpoints and weakref tracking",
                "Audit call graph for zero re-entrant sync locks"
            ]
        }
        verdict = "Install defensive timeouts, lock guards, and automated process supervisor before merge."
        return template, analysis, verdict

    # 8. Critical Falsification
    def _critical_falsification(self, problem: str, ctx: Dict[str, Any]):
        template = "What single test or edge condition would definitively prove this hypothesis false?"
        analysis = {
            "hypothesis": f"Proposed architecture for '{problem}' maintains correctness under concurrency.",
            "popperian_falsification_tests": [
                "Inject 1,000 parallel worker threads attempting simultaneous atomic state mutation",
                "Simulate sudden SIGKILL / process crash midway through disk write",
                "Pass malformed Unicode payloads with null bytes, emojis, and maximum integer overflows"
            ],
            "falsification_oracle": "Must physically trigger red failure on unpatched code and green on patched code."
        }
        verdict = "Run adversarial fuzzing and mutation tests. Code is unverified until it kills mutants."
        return template, analysis, verdict

    # 9. Divergent Ideation
    def _divergent_ideation(self, problem: str, ctx: Dict[str, Any]):
        template = "Generate 4 distinct candidate implementations without evaluating feasibility yet."
        analysis = {
            "candidates": [
                {"id": "Alpha", "paradigm": "Pure in-memory lock-free ring buffer (ultra-low latency)"},
                {"id": "Beta", "paradigm": "SQLite WAL append-only ledger (crash-resilient durable)"},
                {"id": "Gamma", "paradigm": "Zero-dependency generator pipeline with streaming backpressure"},
                {"id": "Delta", "paradigm": "Actor model with unidirectional mailbox messages"}
            ]
        }
        verdict = "Proceed to Convergent Pruning to score candidate paradigms against physical constraints."
        return template, analysis, verdict

    # 10. Convergent Pruning
    def _convergent_pruning(self, problem: str, ctx: Dict[str, Any]):
        template = "Filter candidate architectures against strict criteria: latency, VRAM, complexity, reliability."
        analysis = {
            "criteria": ["Latency", "Memory Footprint", "Simplicity (LOC)", "Windows Reliability"],
            "evaluations": [
                {"candidate": "Alpha (Lock-Free Ring)", "score": 8.5, "verdict": "Fast but complex recovery"},
                {"candidate": "Beta (SQLite WAL)", "score": 9.4, "verdict": "Winner: atomic, durable, zero extra deps"},
                {"candidate": "Gamma (Generator)", "score": 8.0, "verdict": "Good for stream, lacks random access"},
                {"candidate": "Delta (Actor)", "score": 7.2, "verdict": "Over-engineered for single node"}
            ]
        }
        verdict = "Select Candidate Beta (SQLite WAL): optimal balance of durability, speed, and simplicity."
        return template, analysis, verdict

    # 11. Bayesian Updating
    def _bayesian_updating(self, problem: str, ctx: Dict[str, Any]):
        prior = ctx.get("prior", 0.5)
        likelihood_ratio = ctx.get("likelihood_ratio", 4.0)
        # Odds form: Posterior Odds = Prior Odds * Likelihood Ratio
        prior_odds = prior / (1.0 - prior) if prior < 1.0 else 999.0
        post_odds = prior_odds * likelihood_ratio
        posterior = post_odds / (1.0 + post_odds)

        template = "What was my prior confidence? Given new error logs or test data, how does posterior shift?"
        analysis = {
            "prior_probability": round(prior, 4),
            "likelihood_ratio_evidence": round(likelihood_ratio, 4),
            "posterior_probability": round(posterior, 4),
            "interpretation": "Strong confirmation" if posterior > 0.8 else "Inconclusive or refuted"
        }
        verdict = f"Confidence calibrated to {round(posterior * 100, 1)}% based on empirical test receipts."
        return template, analysis, verdict

    # 12. TRIZ Contradiction
    def _triz_contradiction(self, problem: str, ctx: Dict[str, Any]):
        template = "Parameter A improves while Parameter B degrades. Eliminate trade-off without compromise."
        analysis = {
            "contradiction": f"Speed / throughput improves while memory footprint or consistency worsens in '{problem}'",
            "triz_principles_applied": [
                {"principle_id": 1, "name": "Segmentation", "application": "Chunk data into fixed-size micro-pages"},
                {"principle_id": 10, "name": "Prior Action", "application": "Pre-index and pre-compile static assets"},
                {"principle_id": 19, "name": "Periodic Action", "application": "Batch updates rather than continuous writes"}
            ]
        }
        verdict = "Apply TRIZ Principle 10 (Prior Action) and Principle 19 (Periodic Action) to eliminate tradeoff."
        return template, analysis, verdict

    # 13. Analogical Mapping
    def _analogical_mapping(self, problem: str, ctx: Dict[str, Any]):
        template = "How is this problem solved in operating systems, game engines, or hardware architectures?"
        analysis = {
            "source_domain": "Operating System Virtual Memory & Copy-On-Write (COW)",
            "mapped_mechanism": "Pages remain shared read-only until a modification occurs; only the modified page is copied.",
            "target_application": f"Apply copy-on-write immutability to configuration state for '{problem}'."
        }
        verdict = "Adopt Copy-On-Write (COW) data structures to enable zero-copy reads with atomic mutation."
        return template, analysis, verdict

    # 14. Adversarial Red Team
    def _adversarial_red_team(self, problem: str, ctx: Dict[str, Any]):
        template = "Act as an adversary attacking this protocol/API. Where are race conditions and injection vectors?"
        analysis = {
            "attack_vectors": [
                {"vector": "Path Traversal", "surface": "..\\\\..\\\\Windows\\\\System32 injection in file params"},
                {"vector": "Resource Exhaustion", "surface": "Submitting 100MB JSON payload triggering memory DOS"},
                {"vector": "Race Condition (TOCTOU)", "surface": "Checking file existence before open without atomic lock"}
            ],
            "hardening_patch": "Strict whitelist validation, Path.resolve().is_relative_to(), and atomic open."
        }
        verdict = "Harden input boundaries with strict whitelists and atomic OS-level operations."
        return template, analysis, verdict

    # 15. Fermi / Slicing
    def _fermi_slicing(self, problem: str, ctx: Dict[str, Any]):
        template = "Calculate memory, IOPS, and network throughput at 10x and 100x load before implementing."
        items = ctx.get("items", 10000)
        item_size_bytes = ctx.get("item_size_bytes", 256)
        total_ram_mb = (items * item_size_bytes) / (1024 * 1024)
        total_ram_100x_mb = total_ram_mb * 100

        analysis = {
            "baseline_items": items,
            "item_size_bytes": item_size_bytes,
            "baseline_ram_mb": round(total_ram_mb, 2),
            "scale_100x_ram_mb": round(total_ram_100x_mb, 2),
            "vram_headroom_gtx1650_mb": 4096,
            "verdict_feasibility": "Safe" if total_ram_100x_mb < 2048 else "Requires streaming"
        }
        verdict = f"Memory load is {round(total_ram_mb, 2)} MB baseline ({round(total_ram_100x_mb, 2)} MB at 100x). In-memory operation is viable."
        return template, analysis, verdict

    # 16. Morphological Matrix
    def _morphological_matrix(self, problem: str, ctx: Dict[str, Any]):
        template = "Decompose into independent parameters and evaluate matrix combinations."
        analysis = {
            "parameters": {
                "Transport": ["In-Memory SPSC", "Named Pipe", "TCP Loopback", "SQLite WAL"],
                "Serialization": ["Raw Bytes / Struct", "JSON UTF-8", "FlatBuffers", "Pickle (Banned)"],
                "Concurrency": ["Single-Thread Event Loop", "Worker Process Pool", "Thread Pool"]
            },
            "optimal_combination": {
                "Transport": "SQLite WAL",
                "Serialization": "JSON UTF-8 (Native stdlib)",
                "Concurrency": "Single-Thread Event Loop + Task Queues"
            }
        }
        verdict = "Deploy SQLite WAL + standard library JSON + async event loop for maximum stability."
        return template, analysis, verdict

    # 17. OODA Loop
    def _ooda_loop(self, problem: str, ctx: Dict[str, Any]):
        template = "Observe runtime behavior -> Orient via stack trace -> Decide on atomic perturbation -> Act via test."
        analysis = {
            "observe": f"Capture exit code, terminal stderr, and process tree status for '{problem}'",
            "orient": "Isolate innermost failing frame; classify into OS lock, contract break, or timeout",
            "decide": "Formulate single-variable perturbation (Delta = 1)",
            "act": "Execute test suite and measure exit code delta immediately"
        }
        verdict = "Execute atomic single-variable perturbation and confirm state transition via exit code."
        return template, analysis, verdict

    # 18. Counterfactual
    def _counterfactual(self, problem: str, ctx: Dict[str, Any]):
        template = "If the upstream API or primary component failed completely, how does system degrade gracefully?"
        analysis = {
            "counterfactual_scenario": f"External dependency for '{problem}' completely offline or timing out",
            "degraded_fallback_mode": "Fall back to cached local snapshot with explicit stale indicator",
            "user_experience_impact": "Read-only access preserved; mutations queued locally with retry ledger"
        }
        verdict = "Install circuit-breaking fallback queue so outages degrade to graceful read-only operation."
        return template, analysis, verdict

    # 19. Minimalist Razor
    def _minimalist_razor(self, problem: str, ctx: Dict[str, Any]):
        template = "What is the absolute minimum code required to make this work reliably? Delete speculative abstractions."
        analysis = {
            "decision_ladder_eval": [
                {"step": 1, "question": "Does this need to exist at all?", "result": "Yes, core functionality required"},
                {"step": 2, "question": "Already in this codebase?", "result": "Reuse existing utility modules"},
                {"step": 3, "question": "Standard library does it?", "result": "Use Python stdlib pathlib/json/sqlite3"},
                {"step": 4, "question": "Native platform feature covers it?", "result": "Use native Windows cmdlets / OS file APIs"},
                {"step": 5, "question": "Already installed dependency solves it?", "result": "Zero new pip packages permitted"},
                {"step": 6, "question": "Can it be one line?", "result": "Condense logic; eliminate factory boilerplate"},
                {"step": 7, "question": "Minimum code that actually works", "result": "Write clean, hackable, direct implementation"}
            ]
        }
        verdict = "Enforce Ponytail standard: zero external dependencies, minimal lines, standard library only."
        return template, analysis, verdict

    def run_all(self, problem: str, context: Optional[Dict[str, Any]] = None) -> List[ModeResult]:
        results = []
        for mode_id in sorted(self.MODES.keys()):
            results.append(self.run_mode(mode_id, problem, context))
        return results


def main():
    parser = argparse.ArgumentParser(description="Smart Thinking Multi-Mode Cognitive Engine")
    parser.add_argument("--mode", type=int, help="Mode ID (1 to 19)")
    parser.add_argument("--problem", type=str, default="Resolve complex systems deadlock and eliminate latency spikes",
                        help="Problem statement or architectural challenge")
    parser.add_argument("--run-all", action="store_true", help="Execute all 19 cognitive modes")
    parser.add_argument("--json", action="store_true", help="Output results in structured JSON")
    parser.add_argument("--output", type=str, help="Save output to file path")
    args = parser.parse_args()

    engine = SmartThinkingEngine()

    if args.run_all or not args.mode:
        results = engine.run_all(args.problem)
        data = [asdict(r) for r in results]
    else:
        result = engine.run_mode(args.mode, args.problem)
        data = asdict(result)

    if args.json:
        formatted = json.dumps(data, indent=2)
    else:
        if isinstance(data, list):
            lines = [f"=== SMART THINKING ENGINE: 19 COGNITIVE MODES ===", f"Problem: {args.problem}\n"]
            for item in data:
                lines.append(f"[{item['mode_id']:02d}] {item['mode_name']} ({item['focus']})")
                lines.append(f"     Prompt: {item['prompt_template']}")
                lines.append(f"     Verdict: {item['actionable_verdict']}\n")
            formatted = "\n".join(lines)
        else:
            formatted = (
                f"=== SMART THINKING: MODE {data['mode_id']} ({data['mode_name']}) ===\n"
                f"Focus: {data['focus']}\n"
                f"Template: {data['prompt_template']}\n"
                f"Analysis: {json.dumps(data['analysis'], indent=2)}\n"
                f"Verdict: {data['actionable_verdict']}"
            )

    print(formatted)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(formatted, encoding="utf-8")
        print(f"\n[SAVED] Output saved to {out_path}")


if __name__ == "__main__":
    main()
