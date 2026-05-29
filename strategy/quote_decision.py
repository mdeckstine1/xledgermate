"""Dynamic quote adjustments: inventory skew, min edge, adverse selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from core.market_conditions import (
    CONDITION_DEFENSIVE,
    CONDITION_FAVORABLE,
    CONDITION_HOSTILE,
    CONDITION_NEUTRAL,
    MarketAssessment,
)
from core.perception import Profile


@dataclass
class QuoteAdjustments:
    spread_multiplier: float = 1.0
    size_multiplier: float = 1.0
    bid_spread_add_pct: float = 0.0
    ask_spread_add_pct: float = 0.0
    bid_size_multiplier: float = 1.0
    ask_size_multiplier: float = 1.0
    pause_bids: bool = False
    pause_asks: bool = False
    min_edge_met: bool = True
    inventory_label: str = "balanced"
    decision_summary: str = ""


@dataclass
class InventoryState:
    xrp_ratio: float
    label: str
    bid_size_mult: float
    ask_size_mult: float
    bid_spread_add_pct: float
    ask_spread_add_pct: float


def compute_mid_momentum_pct(price_history: list, lookback: int = 5) -> float:
    """Positive = mid rising (RLUSD per XRP up), negative = falling."""
    if len(price_history) < lookback + 1:
        return 0.0
    recent = price_history[-1].get("mid")
    older = price_history[-1 - lookback].get("mid")
    if recent is None or older is None or float(older) <= 0:
        return 0.0
    return ((float(recent) - float(older)) / float(older)) * 100.0


def assess_inventory(
    *,
    xrp_balance: float,
    rlusd_balance: float,
    mid_price: float,
    target_xrp_ratio: float,
    skew_strength: float,
) -> InventoryState:
    total = xrp_balance + (rlusd_balance / mid_price if mid_price > 0 else 0.0)
    ratio = xrp_balance / total if total > 0 else 1.0
    deviation = ratio - target_xrp_ratio
    strength = max(0.5, min(2.0, skew_strength))

    if deviation > 0.12:
        label = "xrp_heavy"
        bid_mult = max(0.35, 1.0 - deviation * 2.5 * strength)
        ask_mult = min(1.35, 1.0 + deviation * 1.5 * strength)
        bid_spread = deviation * 40.0 * strength
        ask_spread = 0.0
    elif deviation < -0.12:
        label = "rlusd_heavy"
        bid_mult = min(1.35, 1.0 + abs(deviation) * 1.5 * strength)
        ask_mult = max(0.35, 1.0 - abs(deviation) * 2.5 * strength)
        bid_spread = 0.0
        ask_spread = abs(deviation) * 40.0 * strength
    else:
        label = "balanced"
        bid_mult = 1.0
        ask_mult = 1.0
        bid_spread = 0.0
        ask_spread = 0.0

    return InventoryState(
        xrp_ratio=ratio,
        label=label,
        bid_size_mult=bid_mult,
        ask_size_mult=ask_mult,
        bid_spread_add_pct=bid_spread,
        ask_spread_add_pct=ask_spread,
    )


def build_quote_adjustments(
    *,
    profile: Profile,
    assessment: MarketAssessment,
    inventory: InventoryState,
    mid_momentum_pct: float,
    effective_spread_l1_pct: float,
    min_edge_pct: float,
    xrpl_fee_bps: float = 2.0,
) -> QuoteAdjustments:
    """Combine profile, market, inventory, and momentum into quoting posture."""
    adj = QuoteAdjustments(inventory_label=inventory.label)
    parts: list[str] = []

    # Market condition sizing / spread posture.
    if assessment.condition == CONDITION_FAVORABLE:
        adj.spread_multiplier = max(0.85, 1.0 - (profile.aggression * 0.12))
        adj.size_multiplier = min(1.15, profile.size_multiplier * (1.0 + profile.aggression * 0.08))
        parts.append("favorable market → slightly tighter/wider size")
    elif assessment.condition == CONDITION_NEUTRAL:
        adj.spread_multiplier = 1.0
        adj.size_multiplier = profile.size_multiplier
        parts.append("neutral market → profile baseline")
    elif assessment.condition == CONDITION_DEFENSIVE:
        adj.spread_multiplier = 1.15
        adj.size_multiplier = profile.size_multiplier * 0.75
        parts.append("defensive market → wider + smaller")
    else:  # hostile
        adj.spread_multiplier = 1.35
        adj.size_multiplier = profile.size_multiplier * 0.5
        parts.append("hostile market → much wider + half size")

    # Inventory skew.
    adj.bid_size_multiplier = inventory.bid_size_mult
    adj.ask_size_multiplier = inventory.ask_size_mult
    adj.bid_spread_add_pct = inventory.bid_spread_add_pct
    adj.ask_spread_add_pct = inventory.ask_spread_add_pct
    if inventory.label != "balanced":
        parts.append(f"inventory {inventory.label} → skew bids/asks")

    # Adverse selection: strong mid move → protect vulnerable side.
    momentum_threshold = 0.06
    if mid_momentum_pct > momentum_threshold:
        adj.bid_spread_add_pct += abs(mid_momentum_pct) * 0.35
        adj.bid_size_multiplier *= 0.7
        parts.append(f"mid rising +{mid_momentum_pct:.2f}% → protect bids")
    elif mid_momentum_pct < -momentum_threshold:
        adj.ask_spread_add_pct += abs(mid_momentum_pct) * 0.35
        adj.ask_size_multiplier *= 0.7
        parts.append(f"mid falling {mid_momentum_pct:.2f}% → protect asks")

    # Minimum edge after estimated ledger fee (bps on notional).
    required_edge = min_edge_pct + xrpl_fee_bps / 100.0
    adj.min_edge_met = effective_spread_l1_pct >= required_edge
    if not adj.min_edge_met:
        adj.size_multiplier *= 0.5
        adj.spread_multiplier *= 1.2
        parts.append(
            f"edge thin (L1 {effective_spread_l1_pct:.3f}% < need {required_edge:.3f}%) → conservative"
        )

    if assessment.condition == CONDITION_HOSTILE and not adj.min_edge_met:
        adj.pause_bids = inventory.label == "xrp_heavy"
        adj.pause_asks = inventory.label == "rlusd_heavy"
        if adj.pause_bids or adj.pause_asks:
            parts.append("hostile + weak edge → pause vulnerable side")

    adj.decision_summary = "; ".join(parts)
    return adj


def apply_spread_adjustments(
    spreads_pct: Dict[int, float],
    adjustments: QuoteAdjustments,
) -> Dict[int, float]:
    """Apply global and side-specific spread adjustments."""
    out: Dict[int, float] = {}
    for level, spread in spreads_pct.items():
        base = spread * adjustments.spread_multiplier
        # Level 1 uses side adds; deeper levels inherit fraction.
        side_scale = 1.0 / max(1, level)
        bid_add = adjustments.bid_spread_add_pct * side_scale
        ask_add = adjustments.ask_spread_add_pct * side_scale
        # Store symmetric widen as average for level (order manager splits bid/ask).
        out[level] = max(0.05, base + (bid_add + ask_add) / 2.0)
    return out
