"""
Quote decision pipeline — orchestrates Layers 1–5 for the sacred engine path.

Use profitable edges to grow inventory on solo books; narrow bleed protection
pauses only the bleeding side; Layer 5 is the sole authority on pause_bids/pause_asks.
"""

from __future__ import annotations

from strategy.fill_quality import FillQualityState
from strategy.quote_decision_layers.bleed import apply_bleed_protection
from strategy.quote_decision_layers.decision import build_layer_decision
from strategy.quote_decision_layers.edge import (
    SOLO_EDGE_ABSOLUTE_FLOOR_PCT,
    SOLO_EDGE_MULT,
    evaluate_side_edge,
)
from strategy.quote_decision_layers.intent import select_intent
from strategy.quote_decision_layers.ops_log import (
    log_posture_ops,
    maybe_log_heavy_drift_l5_deferred,
    maybe_log_inventory_unload_intent,
    maybe_log_solo_accumulate,
)
from strategy.quote_decision_layers.posture import build_posture
from strategy.quote_decision_layers.types import LayerQuotingDecision


def run_layered_quote_decision(
    *,
    xrp_ratio: float,
    inventory_label: str,
    fill_quality: FillQualityState,
    target_xrp_ratio: float,
    market_condition: str,
    mid_momentum_pct: float,
    book_spread_pct: float,
    bid_half_spread_pct: float,
    ask_half_spread_pct: float,
    min_edge_pct: float,
    market_edge_met: bool,
    inventory_max_deviation: float,
    inventory_mode: str,
    acquiring_rlusd: bool,
    mm_mode: bool,
    momentum_pause_vulnerable: bool,
    peer_lane_empty: bool = False,
    peer_lane_count: int = 0,
    low_book_pressure: bool = False,
    peer_intel_present: bool = True,
    peer_intel_stale: bool = False,
    ops_path: str = "",
    solo_edge_mult: float | None = None,
    solo_edge_absolute_floor_pct: float | None = None,
) -> LayerQuotingDecision:
    """
    Execute the full layered stack for one cycle.

    Flow:
      L1 posture (read-only)
      L3 edge preview (needed for L2 intent)
      L2 intent
      L4 bleed (side-local overrides, applied inside L5)
      L5 final permissions (**sole** ``allowed`` authority)
    """
    posture = build_posture(
        xrp_ratio=xrp_ratio,
        inventory_label=inventory_label,
        fill_quality=fill_quality,
        target_xrp_ratio=target_xrp_ratio,
        market_condition=market_condition,
        mid_momentum_pct=mid_momentum_pct,
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        low_book_pressure=low_book_pressure,
    )
    posture_ops_line = log_posture_ops(
        posture=posture,
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        intel_present=peer_intel_present,
        low_book_pressure=low_book_pressure,
        intel_stale=peer_intel_stale,
        path=ops_path,
    )

    edge_mult = SOLO_EDGE_MULT if solo_edge_mult is None else solo_edge_mult
    edge_floor = (
        SOLO_EDGE_ABSOLUTE_FLOOR_PCT
        if solo_edge_absolute_floor_pct is None
        else solo_edge_absolute_floor_pct
    )

    bid_edge = evaluate_side_edge(
        side="bid",
        book_spread_pct=book_spread_pct,
        our_half_spread_pct=bid_half_spread_pct,
        profile_min_edge_pct=min_edge_pct,
        book_mode=posture.book.mode,
        market_edge_met=market_edge_met,
        solo_edge_mult=edge_mult,
        solo_edge_absolute_floor_pct=edge_floor,
    )
    ask_edge = evaluate_side_edge(
        side="ask",
        book_spread_pct=book_spread_pct,
        our_half_spread_pct=ask_half_spread_pct,
        profile_min_edge_pct=min_edge_pct,
        book_mode=posture.book.mode,
        market_edge_met=market_edge_met,
        solo_edge_mult=edge_mult,
        solo_edge_absolute_floor_pct=edge_floor,
    )

    intent = select_intent(
        posture,
        buy_edge_viable=bid_edge.viable,
        sell_edge_viable=ask_edge.viable,
    )
    maybe_log_solo_accumulate(
        intent.intent,
        posture=posture,
        buy_edge_viable=bid_edge.viable,
        sell_edge_viable=ask_edge.viable,
        bid_edge_pct=bid_edge.implied_edge_pct,
        ask_edge_pct=ask_edge.implied_edge_pct,
        path=ops_path,
    )
    maybe_log_inventory_unload_intent(
        intent.intent,
        posture=posture,
        intent_reason=intent.reason,
        favor_bid=intent.favor_bid,
        favor_ask=intent.favor_ask,
        buy_edge_viable=bid_edge.viable,
        sell_edge_viable=ask_edge.viable,
        path=ops_path,
    )
    maybe_log_heavy_drift_l5_deferred(
        posture=posture,
        selected_intent=intent.intent,
        buy_edge_viable=bid_edge.viable,
        sell_edge_viable=ask_edge.viable,
        path=ops_path,
    )

    bleed = apply_bleed_protection(posture)

    decision = build_layer_decision(
        posture,
        intent,
        bid_edge,
        ask_edge,
        bleed,
        inventory_max_deviation=inventory_max_deviation,
        inventory_mode=inventory_mode,
        acquiring_rlusd=acquiring_rlusd,
        mm_mode=mm_mode,
        momentum_pause_vulnerable=momentum_pause_vulnerable,
        ops_path=ops_path,
    )
    return LayerQuotingDecision(
        bid=decision.bid,
        ask=decision.ask,
        intent=decision.intent,
        posture=decision.posture,
        summary=decision.summary,
        bid_pause_note=decision.bid_pause_note,
        ask_pause_note=decision.ask_pause_note,
        trace=decision.trace,
        posture_ops_line=posture_ops_line,
    )
