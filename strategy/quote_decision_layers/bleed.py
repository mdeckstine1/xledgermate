"""
Layer 4 — Narrow bleed protection.

When one side is bleeding, pause *that side only*. Never enable or boost the
opposite side (principle: protect against major bleed, not cross-side bailout).
"""

from __future__ import annotations

from dataclasses import dataclass

from strategy.quote_decision_layers.types import Posture, SidePermission


@dataclass(frozen=True)
class BleedAdjustment:
    bid_allowed_override: bool | None
    ask_allowed_override: bool | None
    bid_note: str
    ask_note: str


def apply_bleed_protection(posture: Posture) -> BleedAdjustment:
    """
    Side-local bleed rules — no cross-side coupling.

    Returns override hints only; Layer 5 ``merge_bleed`` applies them and is
    the sole place that sets ``SidePermission.allowed`` for production.
    """
    bid_note = ""
    ask_note = ""
    bid_override: bool | None = None
    ask_override: bool | None = None

    if posture.buy_quality.bleeding:
        bid_override = False
        bid_note = posture.buy_quality.bleed_reason or "buy_bleed"

    if posture.sell_quality.bleeding:
        ask_override = False
        ask_note = posture.sell_quality.bleed_reason or "sell_bleed"

    return BleedAdjustment(
        bid_allowed_override=bid_override,
        ask_allowed_override=ask_override,
        bid_note=bid_note,
        ask_note=ask_note,
    )


def merge_bleed(
    perm: SidePermission,
    *,
    allowed_override: bool | None,
    bleed_note: str,
) -> SidePermission:
    """
    Apply Layer 4 bleed within Layer 5 — may block only, never allow.

    Called exclusively from ``build_layer_decision`` after base permissions
    are computed; must not be used to grant quoting outside L5.
    """
    if allowed_override is False:
        reason = bleed_note or perm.block_reason or "bleed_protection"
        return SidePermission(
            allowed=False,
            size_mult=0.0,
            implied_edge_pct=perm.implied_edge_pct,
            block_reason=reason,
            pause_cause="bleed",
        )
    return perm
