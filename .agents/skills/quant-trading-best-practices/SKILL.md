---
name: quant-trading-best-practices
description: "Architectural rules for quantitative algorithmic trading. Enforces mathematical precision and API safety."
---

# Quantitative Trading Architecture Laws

You are connected to the `Ai trader` project. All code modifications must strictly adhere to these financial and mathematical rules. Failure to do so will result in structural financial losses.

## 1. Absolute Mathematical Precision
- **NEVER use standard floats (`float`) for any financial calculation.**
- You MUST use the Python `decimal` module (`from decimal import Decimal`).
- Why: Floating-point precision errors (e.g., `0.1 + 0.2 = 0.30000000000000004`) in order-sizing logic will trigger API rejections or fractional compounding losses.

## 2. Environment Segregation
- You must strictly separate Backtesting logic from Live Execution logic.
- Before committing any live API trigger, you must ensure the logic is guarded by a `is_paper_trading` or `is_backtesting` boolean flag that defaults to `True`.

## 3. Rate Limit Defenses
- Assume all exchange APIs will rate-limit you heavily.
- You must implement **Exponential Backoff and Retry** logic on every single network request.
- Never write aggressive `while True` loops for polling order books without explicit `asyncio.sleep` jittering.
