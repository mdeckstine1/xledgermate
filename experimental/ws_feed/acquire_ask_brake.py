"""
A2.3 — acquire-mode ask brake for solo edge acquire.

Pause asks when accumulating XRP — do not sell into the acquire thesis.
v2.1.40: also pause asks on solo whale book when XRP-heavy (hold bag, no dump).
"""

from __future__ import annotations

from dataclasses import dataclass

from experimental.ws_feed.execution_envelope import ACCUMULATE_POSTURES, HOLD_XRP_POSTURES

ACQUIRE_ASK_BRAKE_VERSION = "1.1.0"


@dataclass(frozen=True)
class AcquireAskBrakeResult:
    active: bool
    blocked: bool
    reason: str


def should_pause_asks_solo(
    *,
    peer_lane_empty: bool,
    g7_solo_acquisition: bool,
    inventory_posture: str,
) -> bool:
    if not peer_lane_empty:
        return False
    posture = (inventory_posture or "").strip().lower()
    if posture in HOLD_XRP_POSTURES:
        return True
    return bool(g7_solo_acquisition) and posture in ACCUMULATE_POSTURES


def resolve_acquire_ask_brake(
    *,
    peer_lane_empty: bool,
    g7_solo_acquisition: bool,
    inventory_posture: str,
) -> AcquireAskBrakeResult:
    if not should_pause_asks_solo(
        peer_lane_empty=peer_lane_empty,
        g7_solo_acquisition=g7_solo_acquisition,
        inventory_posture=inventory_posture,
    ):
        return AcquireAskBrakeResult(active=False, blocked=False, reason="")

    posture = (inventory_posture or "").strip().lower()
    if posture in HOLD_XRP_POSTURES:
        return AcquireAskBrakeResult(
            active=True,
            blocked=True,
            reason="solo whale book — xrp-heavy hold, no asks",
        )

    return AcquireAskBrakeResult(
        active=True,
        blocked=True,
        reason="solo edge acquire — bid only",
    )


__all__ = [
    "ACQUIRE_ASK_BRAKE_VERSION",
    "AcquireAskBrakeResult",
    "resolve_acquire_ask_brake",
    "should_pause_asks_solo",
]
