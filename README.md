# Godmode Trading Engine (Institutional ML Edition)

A mathematically rigorous, zero-bloat, **institutional-grade quantitative trading system** engineered for absolute correctness and survivability. 

> **Non-coder?** Read [`START_HERE.md`](START_HERE.md) instead — it's step-by-step.

We have officially evolved beyond basic toy Reinforcement Learning frameworks (like TensorTrade) and standard OHLCV polling. This engine now utilizes the exact mathematical frameworks deployed by top multi-billion dollar quant hedge funds in 2026.

No returns are promised. The design priority order is: **Correctness → Survivability → Mathematical Edge → Returns.**

---

## 🧠 Institutional ML Architecture

This system operates a complete zero-bloat pipeline, relying primarily on `Polars` for extreme vectorized performance without heavy data science dependencies.

1. **Alpha Zoo (Feature Engineering):** Calculates advanced stationary metrics like Fractional Differentiation proxies, 60-period rolling volatility percentiles, and moving average dispersion.
2. **Hidden Markov Model (HMM) Regime Detection:** Mathematically classifies the market into dynamic regimes (Bull, Bear, Choppy). Automatically halts trend-following strategies during sideways chop to prevent algorithmic "whipsaw" losses.
3. **Statistical Arbitrage (Pairs Trading):** A purely market-neutral execution engine utilizing Engle-Granger cointegration logic. Trades the Z-score spread between highly correlated assets, rendering the strategy immune to directional market crashes.
4. **Level 2 Limit Order Book (LOB) Microstructure:** Bypasses slow 1-minute OHLCV candles to ingest tick-by-tick depth arrays, calculating precise Order Flow Imbalance (OFI) and microprices.
5. **Dynamic Kelly Sizing:** Eliminates static order sizes. Calculates the `Half-Kelly` fraction dynamically derived from the Deflated Sharpe P-Value.
6. **Adversarial Stress Testing & DSR:** Implements Marcos Lopez de Prado's Purged Walk-Forward cross-validation and Deflated Sharpe Ratio to mathematically prove the strategy is not overfit.

## LLM credentials and availability

`KeyRotator` loads operator-supplied environment credentials. Use only keys you own or are authorized to use; never harvest exposed credentials from GitHub. Provider free tiers have quotas and availability limits. Neither free inference nor permanent uptime is guaranteed.

## 🚀 Quick start (developers)

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

## 🛡️ Safety & Risk

- **Paper-first.** Live mode is gated behind explicit config + confirmations.
- **Kill Switch:** Survives restarts (a `data/STOP` sentinel file); enforced before every order.
- **Adversarial Hardened:** The risk engine has been rigorously stress-tested against synthetic liquidity vacuums and zero-variance flash crashes.
- **Decimal money math** everywhere; **append-only audit log** of every decision and order.

## ⚙️ Tech Stack

**The Ponytail Mindset:** Python 3.10+ · Polars · CCXT · Shoonya Zero-Brokerage API · LiteLLM · FastAPI (dashboard). *Zero bloat. Stdlib-first. No heavy ML frameworks.*

## 📜 License

MIT. **For research/education. Not financial advice. Trade at your own risk.**
