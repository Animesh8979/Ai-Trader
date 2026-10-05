"""Policy Engine & Deterministic Risk Veto Layer.

Grounded in buberlo/jev-trader architecture:
AI judgments are treated as tactical proposals; hard deterministic code
enforces non-negotiable risk boundaries that cannot be overridden by AI.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from godmode.agents.jev_trader_engine import JevJudgments
from godmode.core.killswitch import get_kill_switch
from godmode.core.logging import get_logger

log = get_logger("risk.policy_veto")


def check_toxic_flow_welford(
    ofi_window: Union[List[float], np.ndarray],
    current_ofi: float,
    z_threshold: float = 2.5,
    min_sigma: float = 0.05
) -> Tuple[bool, float]:
    """Welford-normalized noise-gated OFI toxic flow detection.
    
    Prevents false-positive triggers on small sample percentiles and Gaussian noise ticks.
    Enforces a strict volatility floor (min_sigma) to avoid dividing by zero in quiet regimes.
    
    Returns:
        (is_toxic: bool, z_score: float)
    """
    if len(ofi_window) < 5:
        return False, 0.0

    count = 0
    mean = 0.0
    m2 = 0.0
    for x in ofi_window:
        count += 1
        delta = float(x) - mean
        mean += delta / count
        delta2 = float(x) - mean
        m2 += delta * delta2

    variance = m2 / (count - 1) if count > 1 else 0.0
    stdev = math.sqrt(max(0.0, variance))

    # Noise floor safeguard: never divide by near-zero variance
    effective_sigma = max(stdev, min_sigma)
    z = abs(float(current_ofi) - mean) / effective_sigma

    return bool(z > z_threshold), float(z)


@dataclass
class VetoVerdict:
    approved: bool
    reasons: List[str]
    allowed_qty: Decimal
    action: str  # EXECUTE | VETO | CLAMP


class PolicyVetoEngine:
    """Deterministic policy enforcement and veto layer."""

    def __init__(
        self,
        max_toxic_flow: float = 0.70,
        max_liquidity_stress: float = 0.80,
        max_spread_bps: float = 15.0,
        max_inventory_pressure: float = 4.0,
        min_confidence: float = 0.55,
        ofi_z_threshold: float = 2.5,
        ofi_min_sigma: float = 0.05,
    ):
        self.max_toxic_flow = max_toxic_flow
        self.max_liquidity_stress = max_liquidity_stress
        self.max_spread_bps = max_spread_bps
        self.max_inventory_pressure = max_inventory_pressure
        self.min_confidence = min_confidence
        self.ofi_z_threshold = ofi_z_threshold
        self.ofi_min_sigma = ofi_min_sigma

    def check(
        self,
        side: str,  # "buy" | "sell"
        proposed_qty: Decimal,
        judgments: JevJudgments,
        spread_bps: float,
        current_position: Decimal,
        max_position: Decimal,
        ofi_window: Optional[Union[List[float], np.ndarray]] = None,
        current_ofi: Optional[float] = None,
    ) -> VetoVerdict:
        """Evaluates trade against deterministic safety boundaries."""
        reasons: List[str] = []

        # 1. KillSwitch Pre-Flight Check
        ks = get_kill_switch()
        if ks.is_halted():
            return VetoVerdict(
                approved=False,
                reasons=[f"KillSwitch engaged: {ks.reason()}"],
                allowed_qty=Decimal("0.0"),
                action="VETO"
            )

        # 2. Toxic Flow Veto (Adverse selection protection)
        if judgments.toxic_flow > self.max_toxic_flow:
            reasons.append(f"Toxic flow probability ({judgments.toxic_flow:.2f}) exceeds threshold ({self.max_toxic_flow:.2f})")

        # 2b. Order Flow Imbalance (OFI) Welford Toxic Flow Check
        if ofi_window is not None and current_ofi is not None:
            is_ofi_toxic, z_score = check_toxic_flow_welford(
                ofi_window, current_ofi, self.ofi_z_threshold, self.ofi_min_sigma
            )
            if is_ofi_toxic:
                reasons.append(
                    f"OFI toxic flow detected: z-score {z_score:.2f} > threshold {self.ofi_z_threshold:.2f} (sigma_eff >= {self.ofi_min_sigma})"
                )

        # 3. Liquidity Vacuum Veto
        if judgments.liquidity_stressed > self.max_liquidity_stress:
            reasons.append(f"Liquidity stress ({judgments.liquidity_stressed:.2f}) exceeds threshold ({self.max_liquidity_stress:.2f})")

        # 4. Spread Blowout Veto
        if spread_bps > self.max_spread_bps:
            reasons.append(f"Spread ({spread_bps:.1f} bps) exceeds maximum allowed ({self.max_spread_bps:.1f} bps)")

        # 5. Low Confidence Veto
        if judgments.confidence < self.min_confidence:
            reasons.append(f"Decision confidence ({judgments.confidence:.2f}) below hurdle ({self.min_confidence:.2f})")

        # 6. Directional Conflict Veto
        if side == "buy" and judgments.direction == "SHORT":
            reasons.append("Directional conflict: Proposed BUY while Jev direction is SHORT")
        elif side == "sell" and judgments.direction == "LONG":
            reasons.append("Directional conflict: Proposed SELL while Jev direction is LONG")

        # 7. Inventory Pressure & Size Clamping
        is_increasing = (side == "buy" and current_position >= 0) or (side == "sell" and current_position <= 0)
        allowed_qty = proposed_qty

        if is_increasing:
            if judgments.inventory_pressure >= self.max_inventory_pressure:
                reasons.append(f"Inventory pressure ({judgments.inventory_pressure:.1f}) at capacity; new risk forbidden")
            
            # Position Limit Clamp
            projected_pos = abs(current_position + (proposed_qty if side == "buy" else -proposed_qty))
            if projected_pos > max_position:
                headroom = max_position - abs(current_position)
                if headroom > Decimal("0.0"):
                    allowed_qty = headroom
                    log.warning(f"[PolicyVeto] Order clamped from {proposed_qty} to {allowed_qty} due to max_position limit")
                else:
                    reasons.append(f"Projected position ({projected_pos}) exceeds max position ({max_position})")

        if reasons:
            log.warning(f"[PolicyVeto] Trade VETOED: {'; '.join(reasons)}")
            return VetoVerdict(
                approved=False,
                reasons=reasons,
                allowed_qty=Decimal("0.0"),
                action="VETO"
            )

        action = "CLAMP" if allowed_qty < proposed_qty else "EXECUTE"
        return VetoVerdict(
            approved=True,
            reasons=["All deterministic policy boundaries satisfied"],
            allowed_qty=allowed_qty,
            action=action
        )
