# Godmode Trading Agent

A precise, automated, reliable **multi-agent autonomous trading system**. Paper-first.

> **Non-coder?** Read [`START_HERE.md`](START_HERE.md) instead — it's step-by-step.

This project is inspired by [HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader) and the
multi-agent design of [TradingAgents](https://github.com/TauricResearch/TradingAgents), but
focuses on the parts those leave out: **execution correctness, a hard risk layer, rigorous
backtesting, and operational reliability** — the things that actually let an edge survive.

No returns are promised. The design priority order is: **correctness → survivability →
discipline → returns.**

---

## Architecture

```
LAYER 5  Control & Observability   dashboard (PnL, positions, agent reasoning, STOP), alerts
LAYER 4  Multi-Agent Brain         orchestrator -> analysts -> bull/bear debate -> trader -> risk
         (model-agnostic, LiteLLM)  each sub-agent has a narrow role => no hallucination drift
LAYER 3  Deterministic Risk Engine  HARD limits the LLM cannot override; circuit breakers; kill switch
LAYER 2  Execution & Backtest Core  NautilusTrader: same code backtest->paper->live, no look-ahead
LAYER 1  Venue & Data Adapters      crypto / prediction / equities / fx  +  market data, news
```

The LLM **proposes**; the deterministic risk engine **disposes**.

## Status

- **Phase 0 (this milestone): DONE** — foundations + a working, safe end-to-end pipe.
- Next: Phase 1 (backtester + risk engine), Phase 2 (multi-agent brain), Phase 3 (dashboard),
  Phase 4 (more markets), Phase 5 (gated go-live). See [`START_HERE.md`](START_HERE.md).

## Quick start (developers)

```powershell
# Windows, from the repo root:
./setup.ps1                 # venv + install + setup wizard
./run.ps1 smoke             # connectivity smoke test
```

Or manually with the `py` launcher:

```bash
py -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m godmode.cli setup
.venv/Scripts/python -m godmode.cli smoke
```

## CLI

```
godmode setup       interactive setup wizard (keys + free testnet)
godmode smoke       end-to-end connectivity smoke test
godmode status      mode + kill-switch + config
godmode stop        ENGAGE the kill switch (halt all trading)
godmode resume      clear the kill switch
godmode version
```

## Configuration

- `config/config.yaml` — app mode, **risk limits**, enabled markets. Non-secret.
- `config/models.yaml` — which LLM model each agent role uses (swap Claude↔Gemini here).
- `.env` — **secrets only** (API keys). Created by the wizard; never commit it.

## Project layout

```
src/godmode/
  core/        config, paths, logging, money (Decimal), sqlite db, audit log, kill switch
  llm/         model-agnostic LLM client (LiteLLM)
  execution/   venue adapters (Phase 0: ccxt connectivity; Phase 1: NautilusTrader)
  risk/        deterministic risk engine (Phase 1)
  agents/      multi-agent brain (Phase 2)
  desks/       per-market desks (Phase 2+)
  strategies/  deterministic quant strategies (Phase 1)
  backtest/    harness + metrics + reports (Phase 1)
  dashboard/   web UI (Phase 3)
  diagnostics.py / onboarding.py / cli.py
scripts/       setup_wizard.py, smoke_test.py
tests/         offline unit tests (money, config, db, kill switch, env, json)
```

## Testing

```bash
.venv/Scripts/python -m pytest -q
```

All Phase 0 tests run **offline** — no API keys or network required.

## Safety

- **Paper-first.** Live mode is gated behind explicit config + confirmations (Phase 5).
- **Kill switch** survives restarts (a `data/STOP` sentinel file); enforced before every order.
- **Decimal money math** everywhere; **append-only audit log** of every decision and order.

## Tech

Python 3.10+ · [NautilusTrader](https://nautilustrader.io/) · [LiteLLM](https://github.com/BerriAI/litellm) ·
ccxt · pydantic · loguru · FastAPI (dashboard).

## License

MIT. **For research/education. Not financial advice. Trade at your own risk.**
