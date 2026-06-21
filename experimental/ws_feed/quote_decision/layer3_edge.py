"""
Layer 3 — Profitable edge filter.

A side is viable only if implied edge clears fees + adverse selection buffer.
Solo books use a softer threshold; crowded books are stricter. Better edge →
higher size multiplier (principle: growth from good edges, not volume).
"""

from __future__ import annotations

from experimental.ws_feed.quote_decision.types import BookMode, EdgeViability

# Net edge after ~1bp fees + adverse selection cushion.
MIN_EDGE_SOLO_BPS = 1.0
MIN_EDGE_CROWDED_BPS = 2.5
FEE_BUFFER_BPS = 0.5
ADVERSE_BUFFER_SOLO_BPS = 0.5
ADVERSE_BUFFER_CROWDED_BPS = 1.0

# Size scaling from edge strength (applied in Layer 5).
EDGE_SIZE_FLOOR_MULT = 0.65
EDGE_SIZE_CEILING_MULT = 1.15
EDGE_SIZE_REF_BPS = 8.0


def bid_implied_edge_bps(*, l1_bid_price: float, mid: float) -> float | None:
    if mid <= 0 or l1_bid_price <= 0:
        return None
    return (mid - l1_bid_price) / mid * 10_000.0


def ask_implied_edge_bps(*, l1_ask_price: float, mid: float) -> float | None:
    if mid <= 0 or l1_ask_price <= 0:
        return None
    return (l1_ask_price - mid) / mid * 10_000.0


def min_net_edge_bps(*, book_mode: BookMode) -> float:
    base = MIN_EDGE_SOLO_BPS if book_mode == BookMode.SOLO else MIN_EDGE_CROWDED_BPS
    adverse = (
        ADVERSE_BUFFER_SOLO_BPS
        if book_mode == BookMode.SOLO
        else ADVERSE_BUFFER_CROWDED_BPS
    )
    return base + FEE_BUFFER_BPS + adverse


def evaluate_edge(
    *,
    side: str,
    l1_price: float,
    mid: float,
    book_mode: BookMode,
) -> EdgeViability:
    """Net profitability check for one side."""
    implied = (
        bid_implied_edge_bps(l1_bid_price=l1_price, mid=mid)
        if side == "bid"
        else ask_implied_edge_bps(l1_ask_price=l1_price, mid=mid)
    )
    min_edge = min_net_edge_bps(book_mode=book_mode)

    if implied is None:
        return EdgeViability(
            implied_edge_bps=None,
            min_edge_bps=min_edge,
            viable=False,
            reason="no_price",
        )

    if implied < min_edge:
        return EdgeViability(
            implied_edge_bps=implied,
            min_edge_bps=min_edge,
            viable=False,
            reason=f"edge@{implied:.1f}bps<{min_edge:.1f}",
        )

    return EdgeViability(
        implied_edge_bps=implied,
        min_edge_bps=min_edge,
        viable=True,
        reason="",
    )


def edge_size_mult(*, edge_bps: float | None, book_mode: BookMode) -> float:
    """Better edge → larger size (bounded)."""
    if edge_bps is None or edge_bps <= 0:
        return EDGE_SIZE_FLOOR_MULT
    ref = EDGE_SIZE_REF_BPS
    if book_mode != BookMode.SOLO:
        ref = EDGE_SIZE_REF_BPS * 1.25
    mult = EDGE_SIZE_FLOOR_MULT + (edge_bps / ref) * (
        EDGE_SIZE_CEILING_MULT - EDGE_SIZE_FLOOR_MULT
    )
    return round(min(EDGE_SIZE_CEILING_MULT, max(EDGE_SIZE_FLOOR_MULT, mult)), 3)


__all__ = [
    "evaluate_edge",
    "edge_size_mult",
    "bid_implied_edge_bps",
    "ask_implied_edge_bps",
    "min_net_edge_bps",
]
