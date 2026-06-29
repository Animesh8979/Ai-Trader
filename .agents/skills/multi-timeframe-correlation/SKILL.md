---
name: "Multi-Timeframe Correlation"
description: "Aligns market signals and news sentiment across multiple timeframes (1m, 15m, 1h)."
---
# Multi-Timeframe Correlation Skill

This skill governs multi-timeframe fetching and signal correlation inside the live runner loops.

## Correlation Protocol
1. **Concurrent Fetching**: Query OHLCV candles for multiple granularities (e.g. `1m` and `15m`) concurrently via `asyncio.gather`.
2. **Trend Alignment**: Match micro-timeframe breakout signals against macro-timeframe moving averages.
3. **Sentiment Integration**: Weight news sentiment higher if macro trend shows matching direction.
