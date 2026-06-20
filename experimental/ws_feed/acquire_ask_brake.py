"""
A2.3 — acquire-mode ask brake for solo edge acquire.

Pause asks when accumulating XRP — do not sell into the acquire thesis.
Scope: same as A2.2 buy gate (solo + accumulate postures).
"""

from __future__ import annotations

from dataclasses import dataclass

from experimental.ws_feed.buy_edge_gate import should_apply_buy_edge_gate

ACQUIRE_ASK_BRAKE_VERSION = "1.0.0"


@dataclass(frozen=True)
class AcquireAskBrakeResult:
    active: bool
    blocked: bool
    reason: str


def resolve_acquire_ask_brake(
    *,
    g7_solo_acquisition: bool,
    inventory_posture: str,
) -> AcquireAskBrakeResult:
    if not should_apply_buy_edge_gate(
        g7_solo_acquisition=g7_solo_acquisition,
        inventory_posture=inventory_posture,
    ):
        return AcquireAskBrakeResult(active=False, blocked=False, reason="")

    return AcquireAskBrakeResult(
        active=True,
        blocked=True,
        reason="solo edge acquire — bid only",
    )


__all__ = [
    "ACQUIRE_ASK_BRAKE_VERSION",
    "AcquireAskBrakeResult",
    "resolve_acquire_ask_brake",
]
