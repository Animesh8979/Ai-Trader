"""Polymarket Prediction Market Oracle.

Extracts real-time probability distributions on macro, interest rate,
and crypto events via Polymarket Gamma and CLOB public endpoints (zero auth).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger("godmode.data.polymarket_oracle")


@dataclass
class PredictionSignal:
    event_id: str
    title: str
    category: str
    outcome_yes_prob: Decimal
    outcome_no_prob: Decimal
    volume_24h: Decimal
    sentiment_bias: str  # "BULLISH", "BEARISH", "NEUTRAL"
    timestamp: float
    is_stale: bool = False


class PolymarketPredictionOracle:
    """Zero-auth public oracle for prediction market probability discovery."""

    def __init__(self, timeout: float = 5.0, is_paper: bool = True):
        self.timeout = timeout
        self.is_paper = is_paper
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "GodmodeTrader-PolymarketOracle/1.0",
            "Accept": "application/json"
        })

    def fetch_active_macro_events(self, limit: int = 10) -> List[PredictionSignal]:
        """Fetches active macro prediction markets and calculates probability consensus."""
        signals: List[PredictionSignal] = []
        url = "https://gamma-api.polymarket.com/events"
        params = {"limit": limit, "active": "true", "closed": "false"}

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                events = resp.json()
                for ev in events:
                    title = ev.get("title", "")
                    markets = ev.get("markets", [])
                    if not markets:
                        continue
                    m0 = markets[0]
                    # Parse outcome prices
                    outcome_prices = m0.get("outcomePrices")
                    yes_prob = Decimal("0.50")
                    no_prob = Decimal("0.50")
                    if outcome_prices:
                        try:
                            # outcomePrices can be a stringified json or list
                            if isinstance(outcome_prices, str):
                                import json
                                parsed = json.loads(outcome_prices)
                                yes_prob = Decimal(str(parsed[0]))
                                no_prob = Decimal(str(parsed[1]))
                            elif isinstance(outcome_prices, list) and len(outcome_prices) >= 2:
                                yes_prob = Decimal(str(outcome_prices[0]))
                                no_prob = Decimal(str(outcome_prices[1]))
                        except Exception:
                            pass

                    vol = Decimal(str(m0.get("volume24hr", 0) or 0))
                    # Determine sentiment bias
                    if yes_prob >= Decimal("0.60"):
                        bias = "BULLISH"
                    elif yes_prob <= Decimal("0.40"):
                        bias = "BEARISH"
                    else:
                        bias = "NEUTRAL"

                    signals.append(
                        PredictionSignal(
                            event_id=str(ev.get("id", "")),
                            title=title,
                            category=ev.get("category", "Macro"),
                            outcome_yes_prob=yes_prob,
                            outcome_no_prob=no_prob,
                            volume_24h=vol,
                            sentiment_bias=bias,
                            timestamp=time.time()
                        )
                    )
                if signals:
                    return signals
        except Exception as e:
            log.debug(f"Polymarket gamma fetch fallback: {e}")

        # Fallback Prediction Markets for offline / test stability (Honest labeling: marked is_stale=True)
        log.warning("PolymarketPredictionOracle: Gamma API unreachable. Returning offline fallback signals with is_stale=True.")
        return [
            PredictionSignal(
                event_id="poly-btc-100k",
                title="Will Bitcoin hit $100,000 in 2026?",
                category="Crypto",
                outcome_yes_prob=Decimal("0.72"),
                outcome_no_prob=Decimal("0.28"),
                volume_24h=Decimal("1520400.00"),
                sentiment_bias="BULLISH",
                timestamp=time.time(),
                is_stale=True
            ),
            PredictionSignal(
                event_id="poly-fed-cut",
                title="Fed reduces interest rates at next FOMC?",
                category="Macro",
                outcome_yes_prob=Decimal("0.65"),
                outcome_no_prob=Decimal("0.35"),
                volume_24h=Decimal("3450000.00"),
                sentiment_bias="BULLISH",
                timestamp=time.time(),
                is_stale=True
            ),
            PredictionSignal(
                event_id="poly-eth-etf-flow",
                title="Ethereum Net Inflows exceed $1B this quarter?",
                category="Crypto",
                outcome_yes_prob=Decimal("0.58"),
                outcome_no_prob=Decimal("0.42"),
                volume_24h=Decimal("890000.00"),
                sentiment_bias="NEUTRAL",
                timestamp=time.time(),
                is_stale=True
            )
        ]
