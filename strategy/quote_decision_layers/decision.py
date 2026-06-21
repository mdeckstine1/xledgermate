"""
Layer 5 — Final quoting decision.

Sole authority on bid/ask allowed flags (mapped to pause_bids/pause_asks).
Combines intent, edge filter, bleed protection, inventory circuit breakers,
and adverse tape guards.
"""

from __future__ import annotations

from core.market_conditions import CONDITION_HOSTILE
from strategy.quote_decision_layers.bleed import BleedAdjustment, merge_bleed
from strategy.quote_decision_layers.edge import edge_size_mult
from strategy.quote_decision_layers.ops_log import log_inventory_cb_skipped_solo
from strategy.quote_decision_layers.types import (
    BookMode,
    DriftBand,
    EdgeViability,
    IntentSelection,
    LayerQuotingDecision,
    LayerTrace,
    Posture,
    QuoteIntent,
    SidePermission,
)


def _intent_allows(
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
        if intent.favor_bid or intent.allow_two_sided:
            return True, ""
        return False, f"intent={intent.intent.value} no_bid"

    if intent.favor_ask or intent.allow_two_sided:
        return True, ""
    return False, f"intent={intent.intent.value} no_ask"


def _inventory_circuit_breaker(
    posture: Posture,
    *,
    side: str,
    inventory_max_deviation: float,
    inventory_mode: str,
    acquiring_rlusd: bool,
) -> tuple[bool, str]:
    """
    Hard pause on crowded books when drift exceeds max_deviation.

    Solo books defer to intent (accumulate on edge when drifted).
    """
    if posture.book.mode == BookMode.SOLO:
        return True, ""

    if acquiring_rlusd and side == "ask":
        return True, ""

    cap = max(0.05, float(inventory_max_deviation))
    dev = posture.inventory.deviation
    mm = (inventory_mode or "market_make").strip().lower() == "market_make"

    if side == "bid" and dev > cap:
        tag = "inventory bailout" if mm else "inventory limit"
        return False, f"{tag}: +{dev:.0%} XRP drift → pause bids"

    if side == "ask" and dev < -cap:
        tag = "inventory bailout" if mm else "inventory limit"
        return False, f"{tag}: {dev:.0%} XRP drift → pause asks"

    return True, ""


def _append_circuit_breaker_notes(
    posture: Posture,
    *,
    inventory_max_deviation: float,
    inventory_mode: str,
    parts: list[str],
) -> None:
    """Surface inventory bailout text for operator logs when drift exceeds cap."""
    if posture.book.mode == BookMode.SOLO:
        return
    cap = max(0.05, float(inventory_max_deviation))
    dev = posture.inventory.deviation
    mm = (inventory_mode or "market_make").strip().lower() == "market_make"
    if dev > cap:
        tag = "inventory bailout" if mm else "inventory limit"
        parts.append(
            f"{tag}: {posture.inventory.xrp_ratio:.0%} XRP vs target "
            f"{posture.inventory.target_xrp_ratio:.0%} (+{dev:.0%}) → pause bids; unload via asks"
        )
    elif dev < -cap:
        tag = "inventory bailout" if mm else "inventory limit"
        parts.append(
            f"{tag}: {posture.inventory.xrp_ratio:.0%} XRP vs target "
            f"{posture.inventory.target_xrp_ratio:.0%} ({dev:.0%}) → pause asks; acquire XRP via bids"
        )


def _adverse_tape_block(
    posture: Posture,
    *,
    side: str,
    mm_mode: bool,
    momentum_pause_vulnerable: bool,
    acquiring_rlusd: bool = False,
) -> tuple[bool, str]:
    """Pause the side that is vulnerable to tape direction (MM mode only)."""
    if not mm_mode:
        return True, ""

    mom = posture.mid_momentum_pct
    if side == "bid":
        if momentum_pause_vulnerable and mom > 0:
            return False, f"momentum +{mom:.2f}% → pause bids"
        if mm_mode and mom >= 0.04:
            return False, f"momentum +{mom:.2f}% → pause bids (MM adverse-selection guard)"
    elif side == "ask":
        if momentum_pause_vulnerable and mom < 0:
            return False, f"momentum {mom:.2f}% → pause asks"

    if posture.market_condition == CONDITION_HOSTILE:
        inv = posture.inventory
        if side == "bid" and inv.band in (DriftBand.MILD_XRP, DriftBand.HEAVY_XRP):
            return False, "hostile + xrp drift → pause bids"
        if side == "ask" and inv.band in (DriftBand.MILD_RLUSD, DriftBand.HEAVY_RLUSD):
            return False, "hostile + rlusd drift → pause asks"

    return True, ""


def _base_permission(
    *,
    side: str,
    allowed: bool,
    edge: EdgeViability,
    posture: Posture,
    block_reason: str,
    pause_cause: str,
) -> SidePermission:
    if not allowed:
        return SidePermission(
            allowed=False,
            size_mult=0.0,
            implied_edge_pct=edge.implied_edge_pct,
            block_reason=block_reason,
            pause_cause=pause_cause,
        )
    mult = edge_size_mult(
        edge_pct=edge.implied_edge_pct,
        book_mode=posture.book.mode,
    )
    return SidePermission(
        allowed=True,
        size_mult=mult,
        implied_edge_pct=edge.implied_edge_pct,
        block_reason="",
        pause_cause="",
    )


def _pause_note(side: str, perm: SidePermission) -> str:
    if perm.allowed:
        return ""
    cause = perm.pause_cause or "blocked"
    label = "bids" if side == "bid" else "asks"
    return f"pause {label} ({cause}): {perm.block_reason}"


def build_layer_trace(
    posture: Posture,
    intent: QuoteIntent,
    bid_edge: EdgeViability,
    ask_edge: EdgeViability,
    bid: SidePermission,
    ask: SidePermission,
) -> LayerTrace:
    """Structured trace for solo diagnostics — no logging side effects."""
    return LayerTrace(
        book_mode=posture.book.mode,
        drift_band=posture.inventory.band,
        intent=intent,
        bid_edge_viable=bid_edge.viable,
        ask_edge_viable=ask_edge.viable,
        bid_capture_pct=bid_edge.implied_edge_pct,
        ask_capture_pct=ask_edge.implied_edge_pct,
        bid_pause_cause=bid.pause_cause if not bid.allowed else "",
        ask_pause_cause=ask.pause_cause if not ask.allowed else "",
    )


def build_layer_decision(
    posture: Posture,
    intent: IntentSelection,
    bid_edge: EdgeViability,
    ask_edge: EdgeViability,
    bleed: BleedAdjustment,
    *,
    inventory_max_deviation: float,
    inventory_mode: str,
    acquiring_rlusd: bool,
    mm_mode: bool,
    momentum_pause_vulnerable: bool,
    ops_path: str = "",
) -> LayerQuotingDecision:
    """Merge all layers into final side permissions."""
    if posture.book.mode == BookMode.SOLO:
        log_inventory_cb_skipped_solo(path=ops_path)

    bid_ok, bid_block = _intent_allows(intent, side="bid", edge=bid_edge)
    ask_ok, ask_block = _intent_allows(intent, side="ask", edge=ask_edge)

    bid_cb_ok, bid_cb = _inventory_circuit_breaker(
        posture,
        side="bid",
        inventory_max_deviation=inventory_max_deviation,
        inventory_mode=inventory_mode,
        acquiring_rlusd=acquiring_rlusd,
    )
    ask_cb_ok, ask_cb = _inventory_circuit_breaker(
        posture,
        side="ask",
        inventory_max_deviation=inventory_max_deviation,
        inventory_mode=inventory_mode,
        acquiring_rlusd=acquiring_rlusd,
    )

    bid_tape_ok, bid_tape = _adverse_tape_block(
        posture,
        side="bid",
        mm_mode=mm_mode,
        momentum_pause_vulnerable=momentum_pause_vulnerable,
        acquiring_rlusd=acquiring_rlusd,
    )
    ask_tape_ok, ask_tape = _adverse_tape_block(
        posture,
        side="ask",
        mm_mode=mm_mode,
        momentum_pause_vulnerable=momentum_pause_vulnerable,
        acquiring_rlusd=acquiring_rlusd,
    )

    bid_allowed = bid_ok and bid_cb_ok and bid_tape_ok
    ask_allowed = ask_ok and ask_cb_ok and ask_tape_ok

    bid_reason = bid_cb or bid_block or bid_tape or ""
    ask_reason = ask_cb or ask_block or ask_tape or ""

    bid_cause = ""
    if not bid_ok and not bid_edge.viable:
        bid_cause = "edge"
    elif not bid_ok:
        bid_cause = "intent"
    elif not bid_cb_ok:
        bid_cause = "inventory"
    elif not bid_tape_ok:
        bid_cause = "tape"

    ask_cause = ""
    if not ask_ok and not ask_edge.viable:
        ask_cause = "edge"
    elif not ask_ok:
        ask_cause = "intent"
    elif not ask_cb_ok:
        ask_cause = "inventory"
    elif not ask_tape_ok:
        ask_cause = "tape"

    bid = _base_permission(
        side="bid",
        allowed=bid_allowed,
        edge=bid_edge,
        posture=posture,
        block_reason=bid_reason,
        pause_cause=bid_cause,
    )
    ask = _base_permission(
        side="ask",
        allowed=ask_allowed,
        edge=ask_edge,
        posture=posture,
        block_reason=ask_reason,
        pause_cause=ask_cause,
    )

    bid = merge_bleed(bid, allowed_override=bleed.bid_allowed_override, bleed_note=bleed.bid_note)
    ask = merge_bleed(ask, allowed_override=bleed.ask_allowed_override, bleed_note=bleed.ask_note)

    sides: list[str] = []
    if bid.allowed:
        sides.append(f"bid@{bid.implied_edge_pct:.3f}%×{bid.size_mult:.2f}")
    if ask.allowed:
        sides.append(f"ask@{ask.implied_edge_pct:.3f}%×{ask.size_mult:.2f}")

    trace = build_layer_trace(
        posture, intent.intent, bid_edge, ask_edge, bid, ask
    )

    summary = (
        f"QD {intent.intent.value}: {', '.join(sides) or 'off'}"
        f" | book={posture.book.mode.value} drift={posture.inventory.band.value}"
    )
    if bid.block_reason and not bid.allowed:
        summary += f" | bid_block={bid.block_reason}"
    if ask.block_reason and not ask.allowed:
        summary += f" | ask_block={ask.block_reason}"

    solo_or_blocked = (
        posture.book.mode == BookMode.SOLO
        or not bid.allowed
        or not ask.allowed
    )
    if solo_or_blocked:
        summary += f" | {trace.compact()}"

    return LayerQuotingDecision(
        bid=bid,
        ask=ask,
        intent=intent.intent,
        posture=posture,
        summary=summary,
        bid_pause_note=_pause_note("bid", bid),
        ask_pause_note=_pause_note("ask", ask),
        trace=trace,
    )
