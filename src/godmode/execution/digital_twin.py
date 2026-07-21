"""Digital Twin — pre-trade simulated reality voting.

Before each live order: spawn 10 parallel simulated clones with randomized
latency/slippage/fill_rate/market_impact. Each twin runs a 24h mini-backtest
of the proposed order. Live order proceeds only if ≥6/10 twins are profitable.

No external deps — pure Python simulation engine.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from godmode.core.logging import get_logger

log = get_logger("digital_twin")


@dataclass
class TwinConfig:
    twin_id: int
    latency_ms: float
    slippage_bps: float
    fill_rate: float
    market_impact_bps: float
    vol_multiplier: float


@dataclass
class TwinVote:
    twin_id: int
    final_equity: float
    pnl_pct: float
    voted_yes: bool
    config: TwinConfig


def _make_twin_configs(n: int = 10) -> List[TwinConfig]:
    configs = []
    for i in range(n):
        configs.append(
            TwinConfig(
                twin_id=i,
                latency_ms=random.uniform(5, 200),
                slippage_bps=random.uniform(0.5, 5.0),
                fill_rate=random.uniform(0.85, 1.0),
                market_impact_bps=random.uniform(0.0, 3.0),
                vol_multiplier=random.uniform(0.8, 1.4),
            )
        )
    return configs


def _simulate_twin(
    candles: List[List[float]],
    side: str,
    entry_price: float,
    qty: float,
    config: TwinConfig,
    horizon_bars: int = 24,
) -> TwinVote:
    """Simulate one parallel reality outcome for the proposed order.

    HONEST MODEL (replaces the previous 'sample future closes' cheat):
    The twin does NOT peek at future closes. Instead it projects a forward
    price path from the most recent bar using bar-level realised volatility
    + the twin's vol_multiplier, then evaluates PnL against:
      - slippage on entry (bps, adverse)
      - market impact (bps * sqrt(qty / adv_proxy), adverse)
      - latency cost (extra bps proportional to latency_ms during volatile bars)
      - fill probability (twin rejects order if fill_rate draw fails)
    adv_proxy = mean(volume over last horizon_bars). sqroot impact follows
    Almgren-Chriss square-root law approximation.
    """
    if len(candles) < 2:
        return TwinVote(config.twin_id, 1.0, 0.0, False, config)

    # Bar elements: tolerant of [ts,o,h,l,c,v] OR [o,h,l,c,v]
    def bar_close(c): return c[4] if len(c) > 5 else (c[3] if len(c) > 3 else c[-1])
    def bar_vol(c): return c[5] if len(c) > 5 else (c[4] if len(c) > 4 else 0.0)
    def bar_high(c): return c[2] if len(c) > 2 else max(c)
    def bar_low(c): return c[3] if len(c) > 3 else min(c)

    recent = candles[-min(len(candles), max(2, horizon_bars)):]
    closes = [bar_close(b) for b in recent]
    vols = [bar_vol(b) for b in recent]
    highs = [bar_high(b) for b in recent]
    lows = [bar_low(b) for b in recent]

    adv_proxy = max(1.0, sum(vols) / max(1, len(vols)))
    # realized bar volatility from intrabar ranges (Garman-Klass proxy)
    bar_vars = []
    for i in range(1, len(recent)):
        h = highs[i]; lo = lows[i]; prev_c = closes[i-1]
        if prev_c > 0:
            hl = math.log(max(h, lo, prev_c) / max(min(h, lo, prev_c), 1e-9)) if (h > 0 and lo > 0) else 0
            bar_vars.append(hl * hl)
    rv = math.sqrt(sum(bar_vars) / max(1, len(bar_vars))) if bar_vars else 0.0

    # 1) Fill probability — twin rejects execution entirely if draw fails.
    if random.random() > config.fill_rate:
        return TwinVote(config.twin_id, 1.0, 0.0, False, config)

    # 2) Adverse slippage on entry (bps).
    slip_sign = 1 if side == "buy" else -1
    slipped_entry = entry_price * (1 + slip_sign * config.slippage_bps / 10000.0)

    # 3) Market impact — square-root law: impact_bps * sqrt(qty/adv).
    order_ratio = max(0.0, qty / adv_proxy)
    impact_bps = config.market_impact_bps * math.sqrt(order_ratio)
    impact_cost = entry_price * impact_bps / 10000.0

    # 4) Latency cost — extra adverse slippage proportional to latency during
    #    volatile bars (proxy: latency_ms * rv scaled to bps).
    latency_bps = (config.latency_ms / 1000.0) * (rv * 10000.0) * 0.5
    latency_cost = entry_price * latency_bps / 10000.0

    # 5) Forward price projection over horizon_bars using GBM with twin's
    #    vol_multiplier applied to realized vol. NO peeking at future closes.
    drift = 0.0  # twin assumes no drift (honest)
    sigma = rv * config.vol_multiplier
    price = entry_price
    dt = 1.0  # 1 bar
    for _ in range(horizon_bars):
        z = random.gauss(0.0, 1.0)
        price = price * math.exp((drift - 0.5 * sigma * sigma) * dt + sigma * math.sqrt(dt) * z)

    # PnL against projected exit price, minus impact + latency cost.
    raw_pnl = (price - slipped_entry) * qty * (1 if side == "buy" else -1)
    raw_pnl -= (impact_cost + latency_cost) * qty
    notional = entry_price * qty
    pnl_pct = raw_pnl / notional if notional > 0 else 0.0

    voted_yes = pnl_pct > 0
    return TwinVote(config.twin_id, 1.0 + pnl_pct, round(pnl_pct, 4), voted_yes, config)


class DigitalTwinVoter:
    """Pre-trade ensemble of simulated realities voting on execution."""

    def __init__(self, n_twins: int = 10, quorum: int = 6):
        self.n_twins = n_twins
        self.quorum = quorum

    def vote(
        self,
        candles: List[List[float]],
        side: str,
        entry_price: float,
        qty: float,
        horizon_bars: int = 24,
    ) -> Dict[str, Any]:
        configs = _make_twin_configs(self.n_twins)
        votes: List[TwinVote] = []
        for cfg in configs:
            vote = _simulate_twin(candles, side, entry_price, qty, cfg, horizon_bars)
            votes.append(vote)

        yes_votes = sum(1 for v in votes if v.voted_yes)
        approved = yes_votes >= self.quorum
        avg_pnl = sum(v.pnl_pct for v in votes) / max(1, len(votes))

        log.info(
            f"[DigitalTwin] vote on {side} qty={qty} @ {entry_price}: "
            f"{yes_votes}/{self.n_twins} YES, avg_pnl={avg_pnl:.4f} => "
            f"{'APPROVED' if approved else 'REJECTED'}"
        )

        return {
            "approved": approved,
            "yes_votes": yes_votes,
            "no_votes": self.n_twins - yes_votes,
            "quorum": self.quorum,
            "avg_projected_pnl_pct": round(avg_pnl, 4),
            "votes": [
                {
                    "twin_id": v.twin_id,
                    "pnl_pct": v.pnl_pct,
                    "voted": v.voted_yes,
                    "latency_ms": v.config.latency_ms,
                    "slippage_bps": v.config.slippage_bps,
                    "fill_rate": v.config.fill_rate,
                }
                for v in votes
            ],
        }


_twin_singleton: Optional[DigitalTwinVoter] = None


def get_digital_twin() -> DigitalTwinVoter:
    global _twin_singleton
    if _twin_singleton is None:
        _twin_singleton = DigitalTwinVoter()
    return _twin_singleton