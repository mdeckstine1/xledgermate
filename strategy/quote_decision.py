"""
Dynamic quote adjustments: inventory skew, min edge, adverse selection.

Decision flow (side permissions):
  L1 posture  — book mode, drift band, per-side fill quality (read-only)
  L2 intent   — solo accumulate on edge, two-sided skim, unload, hold off
  L3 edge     — gate: do not quote a side when capture is insufficient
  L4 bleed    — narrow pause on bleeding side only (replaces old _apply_self_bailout)
  L5 decision — sole authority on pause_bids / pause_asks

Spread, size, and touch policy are applied here after Layer 5 permissions.
No layer may pause one side and boost the opposite; bleed is side-local only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from core.dynamic_quoting_policy import (
    TOUCH_AT,
    TOUCH_NEAR,
    TOUCH_OFF,
    TOUCH_SPREAD,
    apply_dynamic_quoting_policy,
    resolve_dynamic_quoting_policy,
)
from core.market_conditions import (
    CONDITION_DEFENSIVE,
    CONDITION_FAVORABLE,
    CONDITION_HOSTILE,
    CONDITION_NEUTRAL,
    MarketAssessment,
)
from core.perception import Profile
from risk.inventory_limits import INVENTORY_MODE_MARKET_MAKE, INVENTORY_MODE_REBALANCE
from strategy.fill_quality import FillQualityState
from strategy.market_microstructure import (
    assess_book_pressure,
    assess_market_edge,
    classify_momentum,
)
from strategy.quote_decision_layers.decision import _append_circuit_breaker_notes
from strategy.quote_decision_layers.pipeline import run_layered_quote_decision

# Extra half-spread per side from inventory skew (percentage points, not fraction).
_MAX_INVENTORY_SPREAD_ADD_PCT = 1.5
_MAX_ANCHOR_SHIFT_PCT = 0.35
_MAX_DEFENSIVE_SIDE_SPREAD_ADD_PCT = 0.45


def _inventory_spread_add_pct(deviation: float, strength: float) -> float:
    """Cap skew so quotes stay near the book (deviation is ratio delta vs target)."""
    return min(_MAX_INVENTORY_SPREAD_ADD_PCT, abs(deviation) * 8.0 * max(0.5, min(2.0, strength)))


@dataclass
class QuoteAdjustments:
    spread_multiplier: float = 1.0
    size_multiplier: float = 1.0
    bid_spread_add_pct: float = 0.0
    ask_spread_add_pct: float = 0.0
    bid_size_multiplier: float = 1.0
    ask_size_multiplier: float = 1.0
    bid_anchor_shift_pct: float = 0.0
    ask_anchor_shift_pct: float = 0.0
    pause_bids: bool = False
    pause_asks: bool = False
    min_edge_met: bool = True
    market_edge_met: bool = True
    market_edge_pct: float = 0.0
    inventory_label: str = "balanced"
    adverse_selection_tier: str = "none"
    book_pressure_label: str = "balanced"
    fill_quality_score: float = 100.0
    join_touch: bool = False
    touch_backoff_pct: float = 0.0
    touch_mode: str = "spread_mid"
    max_worse_than_touch_pct: float = 0.0
    quoting_policy_label: str = ""
    decision_summary: str = ""
    posture_ops_line: str = ""


@dataclass
class InventoryState:
    xrp_ratio: float
    label: str
    bid_size_mult: float
    ask_size_mult: float
    bid_spread_add_pct: float
    ask_spread_add_pct: float
    bid_anchor_shift_pct: float
    ask_anchor_shift_pct: float


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
    abs_dev = abs(deviation)

    if abs_dev <= 0.03:
        label = "balanced"
    elif deviation > 0:
        label = "xrp_heavy" if abs_dev >= 0.08 else "slight_xrp_heavy"
    else:
        label = "rlusd_heavy" if abs_dev >= 0.08 else "slight_rlusd_heavy"

    spread_add = _inventory_spread_add_pct(deviation, strength)
    anchor = min(_MAX_ANCHOR_SHIFT_PCT, abs_dev * 0.45 * strength)

    if deviation > 0:
        bid_mult = max(0.25, 1.0 - abs_dev * 3.2 * strength)
        ask_mult = min(1.45, 1.0 + abs_dev * 2.0 * strength)
        bid_spread = spread_add
        ask_spread = max(0.0, spread_add * 0.15 - abs_dev * 0.8 * strength)
        bid_anchor = -anchor
        ask_anchor = -anchor * 0.55
    elif deviation < 0:
        bid_mult = min(1.45, 1.0 + abs_dev * 2.0 * strength)
        ask_mult = max(0.25, 1.0 - abs_dev * 3.2 * strength)
        bid_spread = max(0.0, spread_add * 0.15 - abs_dev * 0.8 * strength)
        ask_spread = spread_add
        bid_anchor = anchor * 0.55
        ask_anchor = anchor
    else:
        bid_mult = 1.0
        ask_mult = 1.0
        bid_spread = 0.0
        ask_spread = 0.0
        bid_anchor = 0.0
        ask_anchor = 0.0

    return InventoryState(
        xrp_ratio=ratio,
        label=label,
        bid_size_mult=bid_mult,
        ask_size_mult=ask_mult,
        bid_spread_add_pct=bid_spread,
        ask_spread_add_pct=ask_spread,
        bid_anchor_shift_pct=bid_anchor,
        ask_anchor_shift_pct=ask_anchor,
    )


def _apply_layer_permissions(
    adj: QuoteAdjustments,
    *,
    layer_summary: str,
    bid_allowed: bool,
    ask_allowed: bool,
    bid_size_mult: float,
    ask_size_mult: float,
    bid_pause_note: str,
    ask_pause_note: str,
    parts: list[str],
) -> None:
    """
    Layer 5 → QuoteAdjustments bridge.

    pause_bids / pause_asks are set ONLY here (plus operator override below).
    Pause attribution (edge | bleed | inventory | tape | intent) is logged
    via bid_pause_note / ask_pause_note for operator visibility.
    """
    adj.pause_bids = not bid_allowed
    adj.pause_asks = not ask_allowed
    if bid_allowed and bid_size_mult > 0:
        adj.bid_size_multiplier *= bid_size_mult
    if ask_allowed and ask_size_mult > 0:
        adj.ask_size_multiplier *= ask_size_mult
    parts.append(layer_summary)
    if bid_pause_note:
        parts.append(bid_pause_note)
    if ask_pause_note:
        parts.append(ask_pause_note)


def _apply_acquiring_rlusd_override(adj: QuoteAdjustments, parts: list[str]) -> None:
    """
    Operator mode: must sell XRP for RLUSD — force asks on.

    Does not change bid permissions; never a cross-side bailout from bid pause.
    """
    adj.ask_spread_add_pct = 0.0
    adj.ask_anchor_shift_pct = min(0.0, adj.ask_anchor_shift_pct)
    adj.pause_asks = False
    adj.spread_multiplier = min(adj.spread_multiplier, 1.05)
    parts.append("XRP-only mode → competitive asks until RLUSD balance builds")


def _profile_market_overlay(
    profile: Profile,
    assessment: MarketAssessment,
) -> tuple[float, float, list[str]]:
    """Profile market overlay only — base profile spread lives in compute_effective_spreads_pct."""
    parts: list[str] = []
    spread_mult = 1.0
    size_mult = profile.size_multiplier * profile.risk_multiplier

    if assessment.condition == CONDITION_FAVORABLE:
        spread_mult *= max(0.78, 1.0 - profile.aggression * 0.14)
        size_mult *= min(1.25, 1.0 + profile.aggression * 0.10)
        parts.append(f"{profile.name}: favorable → tighter competitive posture")
    elif assessment.condition == CONDITION_NEUTRAL:
        parts.append(f"{profile.name}: neutral → profile baseline")
    elif assessment.condition == CONDITION_DEFENSIVE:
        spread_mult *= 1.18 * profile.defensive_widen_mult
        size_mult *= 0.72
        parts.append(f"{profile.name}: defensive → wider + smaller")
    else:
        spread_mult *= 1.42 * profile.defensive_widen_mult
        size_mult *= 0.42
        parts.append(f"{profile.name}: hostile → capital preservation mode")

    return spread_mult, size_mult, parts


def build_quote_adjustments(
    *,
    profile: Profile,
    assessment: MarketAssessment,
    inventory: InventoryState,
    mid_momentum_pct: float,
    effective_spread_l1_pct: float,
    book_spread_pct: float,
    depth_imbalance: float,
    min_edge_pct: float,
    fill_quality: Optional[FillQualityState] = None,
    xrpl_fee_bps: float = 2.0,
    fund_with_xrp_only: bool = False,
    rlusd_balance: float = 0.0,
    min_order_xrp: float = 1.0,
    target_xrp_ratio: float = 0.55,
    inventory_max_deviation: float = 0.12,
    inventory_mode: str = "market_make",
    toxic_off_touch_latched: bool = False,
    peer_lane_empty: bool = False,
    peer_lane_count: int = 0,
    peer_intel_present: bool = False,
    peer_intel_stale: bool = False,
) -> QuoteAdjustments:
    """
    Combine profile, market, inventory, momentum, book pressure, and fill quality.

    Side permissions (pause_bids/pause_asks) flow through the layered QD stack:
      L1 posture → L2 intent → L3 edge filter → L4 bleed → L5 final decision.
    Spread/size/touch overlays remain here; only Layer 5 sets pauses.
    """
    adj = QuoteAdjustments(inventory_label=inventory.label)
    parts: list[str] = []
    acquiring_rlusd = fund_with_xrp_only and rlusd_balance <= min_order_xrp * 0.5

    spread_mult, size_mult, profile_parts = _profile_market_overlay(profile, assessment)
    parts.extend(profile_parts)
    adj.spread_multiplier = spread_mult
    adj.size_multiplier = size_mult

    adj.bid_size_multiplier = inventory.bid_size_mult
    adj.ask_size_multiplier = inventory.ask_size_mult
    adj.bid_spread_add_pct = inventory.bid_spread_add_pct
    adj.ask_spread_add_pct = inventory.ask_spread_add_pct
    adj.bid_anchor_shift_pct = inventory.bid_anchor_shift_pct
    adj.ask_anchor_shift_pct = inventory.ask_anchor_shift_pct
    if inventory.label != "balanced":
        parts.append(f"inventory {inventory.label} (XRP {inventory.xrp_ratio:.0%}) → steer quotes")

    mm_mode = (inventory_mode or INVENTORY_MODE_MARKET_MAKE).strip().lower() == INVENTORY_MODE_MARKET_MAKE
    mode_tag = "market make" if mm_mode else "rebalance"
    parts.append(f"operating mode: {mode_tag}")

    fq = fill_quality or FillQualityState()

    momentum_tier, momentum_note = classify_momentum(mid_momentum_pct)
    adj.adverse_selection_tier = momentum_tier.name
    if momentum_tier.name != "none":
        if mid_momentum_pct > 0:
            adj.bid_spread_add_pct += abs(mid_momentum_pct) * momentum_tier.spread_mult
            adj.bid_size_multiplier *= momentum_tier.size_mult
        elif mid_momentum_pct < 0 and not acquiring_rlusd:
            adj.ask_spread_add_pct += abs(mid_momentum_pct) * momentum_tier.spread_mult
            adj.ask_size_multiplier *= momentum_tier.size_mult
        elif mid_momentum_pct < 0 and acquiring_rlusd:
            adj.ask_size_multiplier *= max(0.75, momentum_tier.size_mult)
        parts.append(
            momentum_note
            if not acquiring_rlusd or mid_momentum_pct >= 0
            else "momentum falling → smaller asks (still quoting to acquire RLUSD)"
        )

    pressure = assess_book_pressure(
        depth_imbalance=depth_imbalance,
        sensitivity=profile.book_pressure_sensitivity,
    )
    adj.book_pressure_label = pressure.label
    if acquiring_rlusd:
        # Selling XRP for RLUSD — do not widen asks because the book is ask-heavy.
        adj.bid_spread_add_pct += pressure.bid_spread_add_pct
        adj.bid_size_multiplier *= pressure.bid_size_mult
        adj.ask_size_multiplier *= min(1.15, pressure.ask_size_mult)
        if pressure.label != "balanced":
            parts.append(f"{pressure.summary} (ask spread held — acquiring RLUSD)")
    else:
        adj.bid_spread_add_pct += pressure.bid_spread_add_pct
        adj.ask_spread_add_pct += pressure.ask_spread_add_pct
        adj.bid_size_multiplier *= pressure.bid_size_mult
        adj.ask_size_multiplier *= pressure.ask_size_mult
        if pressure.label != "balanced":
            parts.append(pressure.summary)

    adj.fill_quality_score = fq.score
    adj.size_multiplier *= fq.size_multiplier
    adj.spread_multiplier *= fq.spread_multiplier
    if fq.recent_fills:
        parts.append(fq.summary)

    market_edge = assess_market_edge(
        book_spread_pct=book_spread_pct,
        our_l1_spread_pct=effective_spread_l1_pct * adj.spread_multiplier,
        min_edge_pct=min_edge_pct,
        xrpl_fee_bps=xrpl_fee_bps,
    )
    adj.market_edge_met = market_edge.met
    adj.market_edge_pct = market_edge.capture_edge_pct
    parts.append(market_edge.summary)

    required_edge = min_edge_pct + xrpl_fee_bps / 100.0
    base_l1 = max(0.01, effective_spread_l1_pct)
    current_l1 = base_l1 * adj.spread_multiplier
    adj.min_edge_met = current_l1 >= required_edge

    bid_half = max(0.005, current_l1 / 2.0)
    ask_half = max(0.005, current_l1 / 2.0)

    # Edge gate uses min_edge_met / market_edge_met computed above (L3 input).
    low_book_pressure = pressure.label == "balanced" and abs(depth_imbalance) < 0.12

    layer = run_layered_quote_decision(
        xrp_ratio=inventory.xrp_ratio,
        inventory_label=inventory.label,
        fill_quality=fq,
        target_xrp_ratio=target_xrp_ratio,
        market_condition=assessment.condition,
        mid_momentum_pct=mid_momentum_pct,
        book_spread_pct=book_spread_pct,
        bid_half_spread_pct=bid_half,
        ask_half_spread_pct=ask_half,
        min_edge_pct=min_edge_pct,
        market_edge_met=market_edge.met,
        inventory_max_deviation=inventory_max_deviation,
        inventory_mode=inventory_mode,
        acquiring_rlusd=acquiring_rlusd,
        mm_mode=mm_mode,
        momentum_pause_vulnerable=momentum_tier.pause_vulnerable,
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        low_book_pressure=low_book_pressure,
        peer_intel_present=peer_intel_present,
        peer_intel_stale=peer_intel_stale,
        ops_path="engine",
    )
    adj.posture_ops_line = layer.posture_ops_line
    if layer.posture.book.solo:
        if peer_lane_empty:
            parts.append("solo lane active (peer_lane_empty=True)")
        elif peer_lane_count == 1:
            parts.append("solo lane active (sparse peer_lane_count=1)")
    _apply_layer_permissions(
        adj,
        layer_summary=layer.summary,
        bid_allowed=layer.bid.allowed,
        ask_allowed=layer.ask.allowed,
        bid_size_mult=layer.bid.size_mult,
        ask_size_mult=layer.ask.size_mult,
        bid_pause_note=layer.bid_pause_note,
        ask_pause_note=layer.ask_pause_note,
        parts=parts,
    )
    _append_circuit_breaker_notes(
        layer.posture,
        inventory_max_deviation=inventory_max_deviation,
        inventory_mode=inventory_mode,
        parts=parts,
    )

    rebalance_acquiring_xrp = not mm_mode and adj.pause_asks and not adj.pause_bids

    policy = resolve_dynamic_quoting_policy(
        profile=profile,
        assessment=assessment,
        book_spread_pct=book_spread_pct,
        effective_min_edge_pct=min_edge_pct,
        effective_spread_l1_pct=current_l1,
        xrpl_fee_bps=xrpl_fee_bps,
        fill_quality=fq,
        mm_mode=mm_mode,
        mid_momentum_pct=mid_momentum_pct,
        toxic_off_touch_latched=toxic_off_touch_latched,
    )
    apply_dynamic_quoting_policy(adj, policy, parts=parts)

    if rebalance_acquiring_xrp and mid_momentum_pct > 0:
        parts.append(
            f"momentum +{mid_momentum_pct:.2f}% (XRP rising) — rebalance keeps bid at touch"
        )

    if adj.pause_bids and adj.pause_asks:
        adj.join_touch = False
        adj.touch_backoff_pct = 0.0
    elif (adj.pause_bids or adj.pause_asks) and policy.touch_mode == TOUCH_OFF:
        adj.join_touch = False
        adj.touch_backoff_pct = 0.0

    if assessment.condition == CONDITION_FAVORABLE and market_edge.met:
        cap = market_edge.capture_edge_pct
        if cap > 0.12:
            tighten = min(0.12, cap * 0.12)
            adj.spread_multiplier *= max(0.85, 1.0 - tighten)
            parts.append(f"favorable + fat capture {cap:.2f}% → tighter spread ({tighten:.2f})")
        elif cap < -0.02:
            adj.spread_multiplier *= 1.06
            parts.append(f"favorable but thin capture {cap:.2f}% → slightly wider")

    rebalance_bid_touch = not mm_mode and adj.pause_asks and not adj.pause_bids
    if rebalance_bid_touch:
        adj.join_touch = True
        adj.touch_backoff_pct = 0.0
        adj.touch_mode = TOUCH_AT
        parts.append("rebalance → bid at touch")

    if mm_mode and assessment.condition in (CONDITION_FAVORABLE, CONDITION_NEUTRAL):
        if adj.touch_mode == TOUCH_NEAR:
            parts.append("MM → near-touch (visible queue, edge-aware backoff)")
        elif adj.touch_mode == TOUCH_AT and adj.join_touch:
            if adj.pause_bids and not adj.pause_asks:
                parts.append("MM one-sided → asks at touch (bid paused by layer)")
            elif adj.pause_asks and not adj.pause_bids:
                parts.append("MM one-sided → bids at touch (ask paused by layer)")
            elif not adj.pause_bids and not adj.pause_asks:
                parts.append("MM → two-sided at touch (spread via round trips)")
        elif adj.touch_mode in (TOUCH_SPREAD, TOUCH_OFF) and not adj.pause_bids and not adj.pause_asks:
            parts.append(
                f"MM → {adj.touch_mode} (≤{adj.max_worse_than_touch_pct * 100:.2f}% from touch)"
            )

    if not adj.join_touch and not adj.min_edge_met and adj.touch_mode != TOUCH_AT:
        needed_mult = (required_edge * 1.02) / base_l1
        adj.spread_multiplier = max(adj.spread_multiplier, needed_mult)
        adj.min_edge_met = True
        parts.append(
            f"edge guard: widened spread to {base_l1 * adj.spread_multiplier:.3f}% "
            f"(need {required_edge:.3f}%)"
        )

    if not adj.market_edge_met and not adj.join_touch:
        adj.spread_multiplier *= 1.08
        adj.bid_spread_add_pct += 0.04
        adj.ask_spread_add_pct += 0.04
        parts.append("market edge thin → widen both sides (+8% spread, +0.04% side add)")

    if (not adj.min_edge_met or not adj.market_edge_met) and not adj.join_touch:
        adj.size_multiplier *= 0.55 if acquiring_rlusd else 0.72
        parts.append("edge guard → reduced size (off touch, away from book)")

    adj.bid_spread_add_pct = min(_MAX_DEFENSIVE_SIDE_SPREAD_ADD_PCT, adj.bid_spread_add_pct)
    adj.ask_spread_add_pct = min(_MAX_DEFENSIVE_SIDE_SPREAD_ADD_PCT, adj.ask_spread_add_pct)

    if acquiring_rlusd:
        _apply_acquiring_rlusd_override(adj, parts)

    adj.decision_summary = "; ".join(parts)
    return adj


def apply_spread_adjustments(
    spreads_pct: Dict[int, float],
    adjustments: QuoteAdjustments,
) -> Dict[int, float]:
    """Apply market/profile spread multiplier only — inventory skew is per-side in OrderManager."""
    return {
        level: max(0.02, spread * adjustments.spread_multiplier)
        for level, spread in spreads_pct.items()
    }
