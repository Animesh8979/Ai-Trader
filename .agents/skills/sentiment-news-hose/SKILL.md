---
name: "Sentiment News Hose"
description: "Streams real-time crypto headlines from APIs with fallback strategies."
---
# Sentiment News Hose Skill

This skill governs news stream pipelines and real-time sentiment extraction.

## News Hose Protocol
1. **API Credentials**: Check for Finnhub or Alpaca news API keys in env variables.
2. **Graceful Fallback**: If keys are missing, automatically fall back to simulated/mock news streams to prevent trading bot crashes.
3. **Debate Stream**: Inject news headlines into the Sentiment Agent to inform trading debates.
