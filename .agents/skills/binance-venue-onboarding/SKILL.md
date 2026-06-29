---
name: "Binance Venue Onboarding"
description: "Safely configures and onboard API keys for Binance Testnet/Mainnet."
---
# Binance Venue Onboarding Skill

This skill governs the integration of Binance Testnet or Mainnet credentials without exposure risk.

## Onboarding Security
1. **API Key Isolation**: Write API key pairs to `.env` variables (`BINANCE_API_KEY` and `BINANCE_API_SECRET`).
2. **Testnet Safeguard**: Ensure Mainnet key sets are inactive during paper/test runs. Use Binance Testnet base URLs.
3. **Connection Verification**: Run connection check queries to verify API latency and credentials validity.
