---
name: smart-thinking
description: Multi-mode cognitive thinking framework with 19 modes (metacognitive, lateral, dialectical, systems, critical thinking, TRIZ, inversion, pre-mortem). Use when facing complex architecture, root-cause debugging, or when standard sequential reasoning is stuck and requires out-of-the-box or structured cognitive strategies. Front-load: smart thinking, lateral thinking, systems thinking, dialectical, metacognitive, cognitive modes.
---

# Smart Thinking (Multi-Mode Cognitive Framework)

## When to Trigger
Trigger this skill when:
- Standard sequential reasoning or simple deduction is stuck on an engineering deadlock or recurring bug.
- You need out-of-the-box **Lateral Thinking** to generate orthogonal hypotheses that bypass artificial constraints.
- You need **Systems Thinking** to map call graph feedback loops, cascade failures, or backpressure dynamics.
- You need **Dialectical Thinking** (Thesis vs. Antithesis → Synthesis) to resolve architectural trade-offs.
- You need **Metacognitive Monitoring** to audit reasoning bias and distinguish symptom patches from root cause invariants.
- You need **Inversion / Pre-Mortem** analysis to anticipate catastrophic failure modes before committing code.
- You need **Karl Popper Critical Falsification** to design tests that aggressively try to falsify code.

---

## The 19 Cognitive Modes & Execution Templates

| # | Cognitive Mode | Core Focus | Prompt / Thought Template |
|---|---|---|---|
| 1 | **Lateral Thinking** | Paradigm shift, non-linear alternatives | *"What if the core constraint is an illusion? What orthogonal approach bypasses this entirely?"* |
| 2 | **Systems Thinking** | Feedback loops, coupling, cascades | *"Map the call graph, data flow, and backpressure. Where do second-order feedback loops amplify errors?"* |
| 3 | **Dialectical Thinking** | Hegelian Thesis vs. Antithesis | *"State proposed solution (Thesis). Formulate strongest counter-argument (Antithesis). Synthesize superior architecture."* |
| 4 | **First-Principles** | Axiomatic decomposition | *"Strip all library dogma and existing assumptions. What physical/computational invariants must hold true?"* |
| 5 | **Metacognitive** | Self-reflection on reasoning bias | *"Why am I favoring this approach? Am I patching a symptom or addressing the root cause invariant?"* |
| 6 | **Inversion (Jacobi)** | Solving backwards | *"Invert, always invert. What would guarantee failure in this system? Eliminate those conditions."* |
| 7 | **Pre-Mortem Analysis** | Forward prospective hindsight | *"Assume this implementation completely crashed in production 2 weeks from now. What was the exact root cause?"* |
| 8 | **Critical Falsification** | Popperian empirical testing | *"What single test or edge condition would definitively prove this hypothesis false?"* |
| 9 | **Divergent Ideation** | Unconstrained candidate generation | *"Generate 4 distinct candidate implementations without evaluating feasibility yet."* |
| 10 | **Convergent Pruning** | Deterministic pruning | *"Filter candidate architectures against strict criteria: latency, VRAM footprint, complexity, failure modes."* |
| 11 | **Bayesian Updating** | Dynamic evidence calibration | *"What was my prior confidence? Given this error log or benchmark result, how does my posterior probability shift?"* |
| 12 | **TRIZ Contradiction** | Eliminating trade-offs | *"Feature A improves (speed) while Feature B degrades (memory). How can we resolve this without compromise?"* |
| 13 | **Analogical Mapping** | Cross-domain transfer | *"How is this problem solved in operating systems, game engines, or distributed hardware pipelines?"* |
| 14 | **Adversarial Red Team** | Exploiting hidden gaps | *"Act as an adversary attacking this protocol/API. Where are race conditions, unhandled exceptions, and injection vectors?"* |
| 15 | **Fermi / Slicing** | Order-of-magnitude estimation | *"Calculate memory, IOPS, and network throughput at 10x and 100x load before implementing."* |
| 16 | **Morphological Matrix** | Multi-dimensional configuration | *"Decompose into independent parameters (Transport, Storage, Serialization) and evaluate matrix combinations."* |
| 17 | **OODA Loop** | Rapid adaptive iteration | *"Observe runtime behavior -> Orient via stack trace -> Decide on atomic perturbation -> Act via test execution."* |
| 18 | **Counterfactual** | Branch exploration | *"If the upstream API did not provide feature X, how would the architecture adapt gracefully?"* |
| 19 | **Minimalist Razor** | Ponytail / Occam distillation | *"What is the absolute minimum code required to make this work reliably? Delete speculative abstractions."* |

---

## Execution Channels

### Channel 1: Native In-Context Reasoning (Preferred)
Directly instantiate the target cognitive mode during reasoning turns:
1. Announce active mode: `[COGNITIVE MODE: Dialectical]` or `[COGNITIVE MODE: Systems Thinking]`.
2. Apply the structured template to the active engineering problem.
3. Commit only verified outcomes that survive Popperian falsification.

### Channel 2: Deterministic Python Standard Library Engine
Execute the local CLI engine for structured cognitive decomposition and JSON analysis:

```bash
# Execute a specific mode (e.g. Mode 1: Lateral Thinking)
python scripts/smart_thinking_engine.py --mode 1 --problem "Resolve database lock contention during concurrent bulk insert"

# Execute Dialectical Thinking with JSON output
python scripts/smart_thinking_engine.py --mode 3 --problem "State synchronization between server and client" --json

# Run all 19 cognitive modes and save to file
python scripts/smart_thinking_engine.py --run-all --json --output D:\temp\smart_thinking_workspace\analysis.json
```

---

## Verification & Golden Test Suite
Execute the unit test suite before modifying or deploying:
```bash
python test_skill.py
```
Asserts 100% pass rate across all 19 cognitive modes, Bayesian calibration math, Fermi calculations, and CLI flags.

---

## Workspace & Storage Invariant
If generating cognitive diagrams, decision matrices, or extended logs, save them to `D:\temp\smart_thinking_workspace\`. Never write intermediate scratch files to `C:\`.
