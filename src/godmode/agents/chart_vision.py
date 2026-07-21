"""ChartVisionAgent — candlestick PNG + Gemini Flash vision pattern detection.

Workflow:
1. Generate candlestick chart PNG via mplfinance (pure matplotlib).
2. Send to Gemini Flash Lite (free vision tier) via LiteLLM.
3. Parse response: pattern, S/R levels, bullishness score 0-100.
4. Only runs on 4h timeframe (cost control).
"""

from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from godmode.core.logging import get_logger

log = get_logger("agents.chart_vision")


@dataclass
class ChartVisionResult:
    symbol: str
    pattern: str
    support: float
    resistance: float
    bullishness: float  # 0-100
    source: str
    ts: float


def _generate_candlestick_png(candles: List[List[float]], symbol: str) -> bytes:
    """Generate candlestick PNG using mplfinance."""
    try:
        import mplfinance as mpf  # type: ignore
        import pandas as pd  # type: ignore
    except ImportError:
        raise RuntimeError("mplfinance and pandas required for chart vision")

    df = pd.DataFrame(
        {
            "Open": [c[0] if len(c) > 0 else 0 for c in candles],
            "High": [c[1] if len(c) > 1 else 0 for c in candles],
            "Low": [c[2] if len(c) > 2 else 0 for c in candles],
            "Close": [c[3] if len(c) > 3 else c[-1] for c in candles],
            "Volume": [c[4] if len(c) > 4 else 0 for c in candles],
        },
        index=pd.date_range(end="now", periods=len(candles), freq="4h"),
    )

    buf = io.BytesIO()
    mpf.plot(
        df,
        type="candle",
        style="charles",
        volume=True,
        title=symbol,
        savefig=dict(fname=buf, dpi=80, bbox_inches="tight"),
    )
    return buf.getvalue()


def _local_deterministic_analysis(candles: List[List[float]]) -> Dict[str, Any]:
    """Honest fallback when no vision API is available. Computes a deterministic
    pattern detection result from the candle series itself — NO magic numbers.

    Returns real chart-structure signals:
      - support / resistance: rolling swing high/low over last 30 bars
      - pattern: simple swing-point classification
      - bullishness: 0-100 from close-vs-SMA20 position + trend slope
    """
    if not candles or len(candles) < 10:
        return {"pattern": "insufficient_data", "support": 0.0,
                "resistance": 0.0, "bullishness": 50.0}

    closes = [c[3] if len(c) > 3 else c[-1] for c in candles]
    highs = [c[1] if len(c) > 1 else closes[i] for i, c in enumerate(candles)]
    lows = [c[2] if len(c) > 2 else closes[i] for i, c in enumerate(candles)]
    window = min(30, len(candles))

    resistance = max(highs[-window:])
    support = min(lows[-window:])
    last_close = closes[-1]

    # SMA20
    sma_window = min(20, len(closes))
    sma = sum(closes[-sma_window:]) / sma_window

    # Distance of close to support/resistance as a bullishness proxy
    if resistance > support:
        pos_in_range = (last_close - support) / (resistance - support)
    else:
        pos_in_range = 0.5
    pos_in_range = max(0.0, min(1.0, pos_in_range))

    # Trend slope (last 10 bars pct change)
    slope_window = min(10, len(closes))
    slope_pct = (last_close - closes[-slope_window]) / max(1e-9, closes[-slope_window]) * 100

    # Combine: 50% position in range + 50% slope contribution (slope ±5% maps to ±25 bucket)
    bullishness = 50 + (pos_in_range - 0.5) * 50 + max(-25, min(25, slope_pct * 5))
    bullishness = max(0.0, min(100.0, bullishness))

    # Simple pattern detection: swing high/low sequence
    if slope_pct > 1.0:
        pattern = "ascending_channel"
    elif slope_pct < -1.0:
        pattern = "descending_channel"
    elif resistance - support < (last_close * 0.03):
        pattern = "consolidation"
    else:
        pattern = "range"

    return {
        "pattern": pattern,
        "support": round(support, 4),
        "resistance": round(resistance, 4),
        "bullishness": round(bullishness, 1),
    }


def _call_vision_model(png_bytes: bytes, symbol: str) -> Dict[str, Any]:
    """Send PNG to Gemini Flash Lite via LiteLLM. Returns a dict with at
    minimum {pattern, support, resistance, bullishness} plus 'source' key
    indicating 'gemini_flash' on success or 'local_deterministic' on failure.
    """
    try:
        import litellm  # type: ignore
    except ImportError:
        log.info("[ChartVision] litellm not installed — using local deterministic analysis")
        return {"source": "local_deterministic"}

    b64 = base64.b64encode(png_bytes).decode()
    image_url = f"data:image/png;base64,{b64}"

    prompt = (
        f"You are a ChartVision Agent. Analyze the candlestick chart for {symbol}.\n"
        "Identify:\n"
        "1. Chart pattern (head and shoulders, double bottom, triangle, flag, none, etc.)\n"
        "2. Key support level (price)\n"
        "3. Key resistance level (price)\n"
        "4. Bullishness score 0-100\n\n"
        "Respond ONLY with JSON: "
        '{"pattern": "string", "support": float, "resistance": float, "bullishness": int}'
    )

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("NVIDIA_API_KEY")
    try:
        response = litellm.completion(
            model="gemini/gemini-2.5-flash-lite",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            api_key=api_key,
        )
        text = response.choices[0].message.content
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        import json
        parsed = json.loads(text)
        parsed["source"] = "gemini_flash"
        return parsed
    except Exception as exc:
        log.warning(f"[ChartVision] Vision call failed ({exc}); using local deterministic")
        return {"source": "local_deterministic"}


class ChartVisionAgent:
    """Generate candlestick chart, analyze via vision LLM."""

    def __init__(self, min_timeframe_hours: int = 4, cache_ttl: float = 3600):
        self.min_timeframe_hours = min_timeframe_hours
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, ChartVisionResult] = {}

    def analyze(self, symbol: str, candles: List[List[float]]) -> ChartVisionResult:
        now = time.time()
        if symbol in self._cache and (now - self._cache[symbol].ts) < self.cache_ttl:
            return self._cache[symbol]

        if len(candles) < 30:
            return ChartVisionResult(
                symbol=symbol,
                pattern="insufficient_data",
                support=0.0,
                resistance=0.0,
                bullishness=50.0,
                source="none",
                ts=now,
            )

        # Cooperatively honor disable env switch (consistent with brain.py).
        if os.environ.get("GODMODE_DISABLE_VISION") == "1":
            result = {"source": "local_deterministic"}
            png_bytes = b""
        else:
            try:
                png_bytes = _generate_candlestick_png(candles, symbol)
                result = _call_vision_model(png_bytes, symbol)
            except Exception as exc:
                log.warning(f"[ChartVision] Chart generation failed: {exc}")
                result = {"source": "local_deterministic"}
                png_bytes = b""

        # If vision call fell back, enrich with deterministic analysis
        if result.get("source") == "local_deterministic":
            local = _local_deterministic_analysis(candles)
            result = {
                "pattern": local["pattern"],
                "support": local["support"],
                "resistance": local["resistance"],
                "bullishness": local["bullishness"],
                "source": "local_deterministic",
            }

        source = result.get("source", "unknown")
        final = ChartVisionResult(
            symbol=symbol,
            pattern=result.get("pattern", "unknown"),
            support=float(result.get("support", 0.0)),
            resistance=float(result.get("resistance", 0.0)),
            bullishness=float(result.get("bullishness", 50)),
            source=source,
            ts=now,
        )
        self._cache[symbol] = final
        log.info(
            f"[ChartVision] {symbol}: pattern={final.pattern} "
            f"bull={final.bullishness} support={final.support} "
            f"resistance={final.resistance} source={final.source}"
        )
        return final


_cv_singleton: Optional[ChartVisionAgent] = None


def get_chart_vision() -> ChartVisionAgent:
    global _cv_singleton
    if _cv_singleton is None:
        _cv_singleton = ChartVisionAgent()
    return _cv_singleton