"""
A2.3b — sell-side skim gate for solo whale book.

Do not post asks when implied fill would not capture spread above mid.
Scope: peer_lane_empty (solo whale book) — covers skew ask-only and two-sided.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

SELL_EDGE_GATE_VERSION = "1.0.0"
MIN_SELL_EDGE_BPS = 1.0
SESSION_SELL_CAPTURE_BRAKE_XRP = 0.0


@dataclass(frozen=True)
class SellEdgeGateResult:
    active: bool
    blocked: bool
    reason: str
    implied_edge_bps: Optional[float]


def ask_implied_edge_bps(*, l1_ask_price: float, mid: float) -> Optional[float]:
    """Positive when ask is above mid (sell skim if filled at posted price)."""
    if mid <= 0 or l1_ask_price <= 0:
        return None
    return (l1_ask_price - mid) / mid * 10_000.0


def should_apply_sell_edge_gate(*, peer_lane_empty: bool) -> bool:
    return bool(peer_lane_empty)


def resolve_sell_edge_gate(
    *,
    l1_ask_price: float,
    mid: float,
    peer_lane_empty: bool,
    session_sell_capture_xrp: Optional[float] = None,
    min_sell_edge_bps: float = MIN_SELL_EDGE_BPS,
    session_sell_capture_brake_xrp: float = SESSION_SELL_CAPTURE_BRAKE_XRP,
) -> SellEdgeGateResult:
    if not should_apply_sell_edge_gate(peer_lane_empty=peer_lane_empty):
        return SellEdgeGateResult(
            active=False,
            blocked=False,
            reason="",
            implied_edge_bps=None,
        )

    implied = ask_implied_edge_bps(l1_ask_price=l1_ask_price, mid=mid)

    if (
        session_sell_capture_xrp is not None
        and session_sell_capture_xrp < session_sell_capture_brake_xrp
    ):
        return SellEdgeGateResult(
            active=True,
            blocked=True,
            reason=(
                f"session_sell_cap={session_sell_capture_xrp:.4f}"
                f"<{session_sell_capture_brake_xrp:.4f}"
            ),
            implied_edge_bps=implied,
        )

    if implied is None:
        return SellEdgeGateResult(
            active=True,
            blocked=False,
            reason="",
            implied_edge_bps=None,
        )

    if implied < min_sell_edge_bps:
        return SellEdgeGateResult(
            active=True,
            blocked=True,
            reason=f"ask_edge@{implied:.1f}bps<{min_sell_edge_bps:.1f}",
            implied_edge_bps=implied,
        )

    return SellEdgeGateResult(
        active=True,
        blocked=False,
        reason="",
        implied_edge_bps=implied,
    )


__all__ = [
    "SELL_EDGE_GATE_VERSION",
    "MIN_SELL_EDGE_BPS",
    "SESSION_SELL_CAPTURE_BRAKE_XRP",
    "SellEdgeGateResult",
    "ask_implied_edge_bps",
    "resolve_sell_edge_gate",
    "should_apply_sell_edge_gate",
]
