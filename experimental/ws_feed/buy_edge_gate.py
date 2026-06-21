"""
A2.2 — buy-side skim gate for solo edge acquire.

Do not post bids when implied fill would not capture spread below mid.
Scope: solo empty lane + accumulate postures only (G7 v1.6 edge acquire).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from experimental.ws_feed.execution_envelope import ACCUMULATE_POSTURES

BUY_EDGE_GATE_VERSION = "1.0.0"
MIN_BUY_EDGE_BPS = 1.0
SESSION_BUY_CAPTURE_BRAKE_XRP = 0.0


@dataclass(frozen=True)
class BuyEdgeGateResult:
    active: bool
    blocked: bool
    reason: str
    implied_edge_bps: Optional[float]


def bid_implied_edge_bps(*, l1_bid_price: float, mid: float) -> Optional[float]:
    """Positive when bid is below mid (buy skim if filled at posted price)."""
    if mid <= 0 or l1_bid_price <= 0:
        return None
    return (mid - l1_bid_price) / mid * 10_000.0


def should_apply_buy_edge_gate(
    *,
    peer_lane_empty: bool,
    g7_solo_acquisition: bool = False,
    inventory_posture: str = "",
) -> bool:
    """Solo whale book: all bids need min edge (v2.1.40 — was solo-acquire accumulate only)."""
    if peer_lane_empty:
        return True
    return bool(g7_solo_acquisition) and inventory_posture in ACCUMULATE_POSTURES


def resolve_buy_edge_gate(
    *,
    l1_bid_price: float,
    mid: float,
    peer_lane_empty: bool,
    g7_solo_acquisition: bool,
    inventory_posture: str,
    session_buy_capture_xrp: Optional[float] = None,
    min_buy_edge_bps: float = MIN_BUY_EDGE_BPS,
    session_buy_capture_brake_xrp: float = SESSION_BUY_CAPTURE_BRAKE_XRP,
) -> BuyEdgeGateResult:
    if not should_apply_buy_edge_gate(
        peer_lane_empty=peer_lane_empty,
        g7_solo_acquisition=g7_solo_acquisition,
        inventory_posture=inventory_posture,
    ):
        return BuyEdgeGateResult(
            active=False,
            blocked=False,
            reason="",
            implied_edge_bps=None,
        )

    implied = bid_implied_edge_bps(l1_bid_price=l1_bid_price, mid=mid)

    if (
        session_buy_capture_xrp is not None
        and session_buy_capture_xrp < session_buy_capture_brake_xrp
    ):
        return BuyEdgeGateResult(
            active=True,
            blocked=True,
            reason=(
                f"session_buy_cap={session_buy_capture_xrp:.4f}"
                f"<{session_buy_capture_brake_xrp:.4f}"
            ),
            implied_edge_bps=implied,
        )

    if implied is None:
        return BuyEdgeGateResult(
            active=True,
            blocked=False,
            reason="",
            implied_edge_bps=None,
        )

    if implied < min_buy_edge_bps:
        return BuyEdgeGateResult(
            active=True,
            blocked=True,
            reason=f"bid_edge@{implied:.1f}bps<{min_buy_edge_bps:.1f}",
            implied_edge_bps=implied,
        )

    return BuyEdgeGateResult(
        active=True,
        blocked=False,
        reason="",
        implied_edge_bps=implied,
    )


__all__ = [
    "BUY_EDGE_GATE_VERSION",
    "MIN_BUY_EDGE_BPS",
    "SESSION_BUY_CAPTURE_BRAKE_XRP",
    "BuyEdgeGateResult",
    "bid_implied_edge_bps",
    "resolve_buy_edge_gate",
    "should_apply_buy_edge_gate",
]
