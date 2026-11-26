# Ai-Trader

Paper-first quantitative risk, regime-detection, and crypto execution service written in Python. Orders proposed by strategies or LLM workflows pass through deterministic sizing clamps, circuit breakers, and a file-backed kill switch before reaching any venue adapter.

> **Default Safety Posture:** Runs in `paper` mode with simulated capital against public/testnet market data. A persistent `data/STOP` sentinel file halts all entry orders across process restarts.

## Architecture

| Layer | Module | Responsibility |
| :--- | :--- | :--- |
| **Deterministic Risk** | `src/godmode/risk/engine.py` | Position sizing clamps (`APPROVE` / `CLAMP` / `REJECT`), max drawdown halt, daily loss stop, consecutive-loss guard; risk-reducing exits bypass entry gates |
| **Tail Risk (VaR/FHS)** | `src/godmode/risk/var_models.py` | Pure-NumPy Cornish-Fisher Modified VaR with Jaschke-Chernozhukov monotonicity domain guard and Filtered Historical Simulation fallback |
| **Microstructure Policy** | `src/godmode/risk/policy_veto.py` | Welford online Order Flow Imbalance (OFI) z-score gate with a $\sigma_{\min} = 0.05$ quiet-market floor, spread cap, and inventory pressure check |
| **Regime Detection** | `src/godmode/strategies/cusum_regime.py` | Symmetric two-sided $O(1)$ Page-CUSUM filter over EWMA-standardized log returns (`BULL_BREAK` / `BEAR_BREAK`) |
| **Microstructure Scorer** | `src/godmode/agents/laya_engine.py`, `jev_trader_engine.py` | 12-feature microstructure extractor with vectorized NumPy linear/softmax scoring heads and optional ONNX model loading (`LAYA_MODEL_PATH`) |
| **Decision & Calibration** | `src/godmode/agents/brain.py`, `core/singularity_loop.py` | Optional multi-agent analyst/debate pipeline (`LiteLLM`), SQLite audit log, and Brier/Sharpe walk-forward parameter evaluation |
| **Backtesting** | `src/godmode/backtest/runner.py` | Deterministic CSV OHLCV EMA-crossover replay with explicit fee drag (`Decimal` arithmetic, SQLite run tracking) |
| **Execution Adapters** | `src/godmode/execution/` | CCXT sandbox/testnet connectivity (`Binance` / `Bybit`), post-only pegging helpers, Indian broker adapter scaffolding, and async live/paper loop |
| **Telemetry UI** | `src/godmode/dashboard/app.py`, `dashboard/streamlit_app.py` | FastAPI + WebSocket server (`/api/status`, `/api/stop`, `/api/resume`, `/api/backtest/run`, `/api/monte_carlo`) and optional Streamlit view |

## Deterministic Risk Controls

| Guard | Default Condition | Action |
| :--- | :--- | :--- |
| **Kill Switch** | `data/STOP` file present | Blocks entry orders across restarts (`POST /api/stop` / `godmode stop`) |
| **Max Drawdown** | Equity drops $\ge 15.0\%$ from peak | `REJECT` + triggers desk halt |
| **Daily Loss Stop** | Realized daily loss $\ge 3.0\%$ of equity | `REJECT` for new entries |
| **Exposure / Position Caps** | Order exceeds $10\%$ equity per symbol or $60\%$ gross exposure | `CLAMP` down to permitted notional, or `REJECT` if zero headroom |
| **Welford OFI Veto** | Standardized order-flow z-score $> 2.5\sigma$ ($\sigma_{\min} = 0.05$) | `VETO` adverse-selection entry |

## Quickstart

```powershell
git clone https://github.com/Animesh8979/Ai-Trader.git
cd Ai-Trader
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,dashboard]"
```

Configure optional API keys if testing live testnet feeds or LLM workflows:

```powershell
copy .env.example .env
```

Run the unit and integration test suite:

```powershell
$env:PYTHONIOENCODING="utf-8"
pytest tests/ -v
```

Start the FastAPI telemetry dashboard:

```powershell
uvicorn godmode.dashboard.app:app --host 127.0.0.1 --port 8000
```

## Limitations & Scope

- **Paper-First Validation:** Venue connectivity targets exchange sandboxes/testnets and simulated paper execution; live capital deployment requires explicit configuration and is not active by default.
- **Offline Microstructure Fallback:** `LayaEngine` uses lightweight deterministic 12-feature NumPy scoring weights unless an external `.onnx` artifact is explicitly supplied via `LAYA_MODEL_PATH`.

## License

MIT. Intended for quantitative research, backtesting, and educational use; not financial advice.
