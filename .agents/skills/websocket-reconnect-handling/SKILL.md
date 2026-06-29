---
name: "WebSocket Reconnect Handling"
description: "Manages frontend WebSocket streams, reconnect intervals, and connection overlays."
---
# WebSocket Reconnect Handling Skill

This skill governs WebSocket streaming connection states on the dashboard frontend.

## State Logic
1. **Network Latency**: Measure client-to-server latency using HTTP header timestamps.
2. **Reconnection HUD**: Display a fullscreen severed connection warning if the socket closes.
3. **Reconnect Backoff**: Attempt reconnection every 5 seconds, restoring status telemetry upon open.
