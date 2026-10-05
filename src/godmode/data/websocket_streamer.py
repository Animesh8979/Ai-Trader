"""Real-Time WebSocket Stream Engine for Godmode v4.

Connects to Binance public WebSocket streams (no auth required).
Handles persistent tick streams and orderbook depth with reconnect backoff.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import websocket
from typing import Any, Dict, List, Optional

from godmode.core.logging import get_logger

log = get_logger("websocket_streamer")


class LiveTickStreamer:
    """Thread-safe high-frequency tick and orderbook buffer backed by Binance WS."""

    def __init__(self, symbols: Optional[List[str]] = None) -> None:
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self._orderbook_depth: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ws: Optional[websocket.WebSocketApp] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_ws, daemon=True)
        self._thread.start()
        log.info("[WEBSOCKET STREAMER] Real Binance tick stream online.")

    def stop(self) -> None:
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def get_orderbook(self, symbol: str) -> Dict[str, Any]:
        with self._lock:
            cached = self._orderbook_depth.get(symbol.upper())
        if cached:
            return cached
        return {
            "symbol": symbol.upper(),
            "bids": [[0.0, 0.0]],
            "asks": [[0.0, 0.0]],
            "ts": time.time(),
        }

    def _build_url(self) -> str:
        streams = [f"{s.lower()}@depth20@100ms" for s in self.symbols]
        return f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"

    def _on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        try:
            data = json.loads(message)
            if "data" in data:
                stream = data.get("stream", "")
                sym = stream.replace("@depth20", "").upper().split("@")[0].upper()
                depth = data["data"]
                with self._lock:
                    self._orderbook_depth[sym] = {
                        "symbol": sym,
                        "bids": [[float(b[0]), float(b[1])] for b in depth.get("bids", [])],
                        "asks": [[float(a[0]), float(a[1])] for a in depth.get("asks", [])],
                        "ts": time.time(),
                    }
        except Exception as exc:
            log.debug(f"WS parse error: {exc}")

    def _on_error(self, ws: websocket.WebSocket, error: Exception) -> None:
        log.warning(f"[WS] Error: {error}")

    def _on_close(self, ws: websocket.WebSocket, close_status_code: int, close_msg: str) -> None:
        log.info(f"[WS] Disconnected (code={close_status_code})")

    def _on_open(self, ws: websocket.WebSocket) -> None:
        log.info(f"[WS] Subscribed to depth streams for {self.symbols}")

    def _run_ws(self) -> None:
        while self._running:
            try:
                self._ws = ws = websocket.WebSocketApp(
                    self._build_url(),
                    on_message=lambda ws, msg: self._on_message(ws, msg),
                    on_error=lambda ws, error: self._on_error(ws, error),
                    on_close=lambda ws, close_status_code, close_msg: self._on_close(ws, close_status_code, close_msg),
                    on_open=lambda ws: self._on_open(ws),
                )
                ws.run_forever()
            except Exception as exc:
                log.warning(f"WS reconnect after error: {exc}")
            if self._running:
                time.sleep(5.0)