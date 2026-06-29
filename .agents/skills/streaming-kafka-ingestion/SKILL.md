---
name: streaming-kafka-ingestion
description: Handling live WebSocket/Kafka tick data via Timeplus without dropping packets.
---

# Streaming Kafka Ingestion

When querying the `timeplus` MCP server:
1. **Query Windows:** Always use bounding time windows (e.g., `WHERE time > NOW() - INTERVAL 5 MINUTE`) to prevent massive stream dumps.
2. **Aggregations:** Prefer returning aggregated OHLCV bars rather than raw tick data to conserve token context.
3. **Topic Inspection:** Always inspect available Kafka topics before attempting to read them to ensure the schema matches.
