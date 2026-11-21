"""
Layer 5 — Final quoting decision.

Sole authority on bid/ask allowed + size_mult. Combines intent, edge filter,
bleed protection, and reservation posture. No inventory pause_bids/pause_asks.
"""

from __future__ import annotations

from experimental.ws_feed.quote_decision.layer2_intent import IntentSelection
from experimental.ws_feed.quote_decision.layer3_edge import edge_size_mult
from experimental.ws_feed.quote_decision.layer4_bleed import (
    BleedAdjustment,
    merge_bleed_into_permission,
)
from experimental.ws_feed.quote_decision.types import (
    CycleQuoteInputs,
    EdgeViability,
    LayerTrace,
    PostureSnapshot,
    QuotingDecision,
    QuoteIntent,
    SidePermission,
)


def _intent_allows_side(
    intent: IntentSelection,
    *,
    side: str,
    edge: EdgeViability,
) -> tuple[bool, str]:
    if not edge.viable:
        return False, edge.reason or "no_edge"

    if intent.intent == QuoteIntent.HOLD_OFF:
        return False, "hold_off"

    if side == "bid":
        if intent.favor_bid:
            return True, ""
        if intent.allow_two_sided:
            return True, ""
        return False, f"intent={intent.intent.value} no_bid"

    if intent.favor_ask:
        return True, ""
    if intent.allow_two_sided:
        return True, ""
    return False, f"intent={intent.intent.value} no_ask"


def _base_permission(
    *,
    side: str,
    allowed: bool,
    edge: EdgeViability,
    posture: PostureSnapshot,
    reservation_ok: bool,
) -> SidePermission:
    if not reservation_ok:
        return SidePermission(
            allowed=False,
            size_mult=0.0,
            implied_edge_bps=edge.implied_edge_bps,
            block_reason="reservation_blocks_side",
        )
    if not allowed:
        return SidePermission(
            allowed=False,
            size_mult=0.0,
            implied_edge_bps=edge.implied_edge_bps,
            block_reason=edge.reason or "intent_blocked",
        )
    mult = edge_size_mult(
        edge_bps=edge.implied_edge_bps,
        book_mode=posture.book.mode,
    )
    return SidePermission(
        allowed=True,
        size_mult=mult,
        implied_edge_bps=edge.implied_edge_bps,
        block_reason="",
    )


def build_final_quoting_decision(
    inputs: CycleQuoteInputs,
    posture: PostureSnapshot,
    intent: IntentSelection,
    bid_edge: EdgeViability,
    ask_edge: EdgeViability,
    bleed: BleedAdjustment,
) -> QuotingDecision:
    """Merge all layers into the final quoting decision."""
    bid_ok, bid_block = _intent_allows_side(intent, side="bid", edge=bid_edge)
    ask_ok, ask_block = _intent_allows_side(intent, side="ask", edge=ask_edge)

    if not bid_ok and bid_block:
        bid_edge = EdgeViability(
            implied_edge_bps=bid_edge.implied_edge_bps,
            min_edge_bps=bid_edge.min_edge_bps,
            viable=False,
            reason=bid_block,
        )
    if not ask_ok and ask_block:
        ask_edge = EdgeViability(
            implied_edge_bps=ask_edge.implied_edge_bps,
            min_edge_bps=ask_edge.min_edge_bps,
            viable=False,
            reason=ask_block,
        )

    bid = _base_permission(
        side="bid",
        allowed=bid_ok,
        edge=bid_edge,
        posture=posture,
        reservation_ok=inputs.reservation_allows_bid,
    )
    ask = _base_permission(
        side="ask",
        allowed=ask_ok,
        edge=ask_edge,
        posture=posture,
        reservation_ok=inputs.reservation_allows_ask,
    )

    bid = merge_bleed_into_permission(
        bid,
        bleed_mult=bleed.bid_size_mult,
        allowed_override=bleed.bid_allowed_override,
        bleed_note=bleed.bid_note,
    )
    ask = merge_bleed_into_permission(
        ask,
        bleed_mult=bleed.ask_size_mult,
        allowed_override=bleed.ask_allowed_override,
        bleed_note=bleed.ask_note,
    )

    would_quote = (bid.allowed and bid.size_mult > 0) or (
        ask.allowed and ask.size_mult > 0
    )

    sides = []
    if bid.allowed:
        bps = bid.implied_edge_bps
        edge_s = f"{bps:.1f}bps" if bps is not None else "?bps"
        sides.append(f"bid@{edge_s}×{bid.size_mult:.2f}")
    if ask.allowed:
        bps = ask.implied_edge_bps
        edge_s = f"{bps:.1f}bps" if bps is not None else "?bps"
        sides.append(f"ask@{edge_s}×{ask.size_mult:.2f}")
    summary = (
        f"QD {intent.intent.value}: {', '.join(sides) or 'off'}"
        f" | book={posture.book.mode.value} drift={posture.inventory.band.value}"
    )

    trace = LayerTrace(
        intent=intent.intent,
        intent_reason=intent.reason,
        bid_edge=bid_edge,
        ask_edge=ask_edge,
        bid_bleed_note=bleed.bid_note,
        ask_bleed_note=bleed.ask_note,
    )

    return QuotingDecision(
        bid=bid,
        ask=ask,
        intent=intent.intent,
        posture=posture,
        trace=trace,
        summary=summary,
        would_quote=would_quote,
    )


__all__ = ["build_final_quoting_decision"]
