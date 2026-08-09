"""
Quote decision pipeline — orchestrates Layers 1–5.

Single entry point for the new architecture. Call from pure_quote_path or
ws_pure_engine via quote_decision_adapter (shadow or active mode).
"""

from __future__ import annotations

from experimental.ws_feed.quote_decision.layer1_posture import build_posture_snapshot
from experimental.ws_feed.quote_decision.layer2_intent import select_quote_intent
from experimental.ws_feed.quote_decision.layer3_edge import evaluate_edge
from experimental.ws_feed.quote_decision.layer4_bleed import apply_bleed_protection
from experimental.ws_feed.quote_decision.layer5_decision import build_final_quoting_decision
from experimental.ws_feed.quote_decision.types import CycleQuoteInputs, QuotingDecision


def run_quote_decision_pipeline(inputs: CycleQuoteInputs) -> QuotingDecision:
    """
    Execute the full layered stack for one cycle.

    Flow:
      L1 posture (read-only)
      L3 edge preview (needed for L2 intent)
      L2 intent
      L4 bleed (side-local)
      L5 final permissions
    """
    posture = build_posture_snapshot(inputs)

    bid_edge = evaluate_edge(
        side="bid",
        l1_price=inputs.l1_bid_price,
        mid=inputs.mid,
        book_mode=posture.book.mode,
    )
    ask_edge = evaluate_edge(
        side="ask",
        l1_price=inputs.l1_ask_price,
        mid=inputs.mid,
        book_mode=posture.book.mode,
    )

    bid_side_viable = bid_edge.viable and inputs.reservation_allows_bid
    ask_side_viable = ask_edge.viable and inputs.reservation_allows_ask
    intent = select_quote_intent(
        posture,
        buy_edge_viable=bid_side_viable,
        sell_edge_viable=ask_side_viable,
        reservation_only_ask=ask_side_viable and not bid_side_viable,
    )

    bleed = apply_bleed_protection(posture)

    return build_final_quoting_decision(
        inputs,
        posture,
        intent,
        bid_edge,
        ask_edge,
        bleed,
    )


__all__ = ["run_quote_decision_pipeline"]
