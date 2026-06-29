---
name: crypto-whale-tracking
description: Correlating Verilex whale movements with CCXT orderbook imbalances.
---

# Crypto Whale Tracking

When querying the `verilexdata` MCP server:
1. **Wallet Tagging:** Focus only on known exchange hot wallets or tagged whale entities.
2. **Cross-reference:** Cross-reference any major on-chain movement against the Binance/Bybit orderbook liquidity.
3. **Threshold:** Only alert on transfers exceeding $10,000,000 USD equivalent.
