"""
Layer 4 — Narrow bleed protection.

When one side is bleeding, reduce or pause *that side only*. Never enable or
boost the opposite side (principle 4 — fixes effective_quote_sides bailout bug).
"""

from __future__ import annotations

from dataclasses import dataclass

from experimental.ws_feed.quote_decision.types import PostureSnapshot, SidePermission

BLEED_SIZE_MULT = 0.0  # hard pause when bleeding
SESSION_BLEED_XRP = 0.0


@dataclass(frozen=True)
class BleedAdjustment:
    bid_size_mult: float
    ask_size_mult: float
    bid_allowed_override: bool | None  # None = no override
    ask_allowed_override: bool | None
    bid_note: str
    ask_note: str


def apply_bleed_protection(posture: PostureSnapshot) -> BleedAdjustment:
    """
    Side-local bleed rules — no cross-side coupling.

    Session capture below zero on a side with fills reinforces recent bleed.
    """
    bid_note = ""
    ask_note = ""
    bid_mult = 1.0
    ask_mult = 1.0
    bid_override: bool | None = None
    ask_override: bool | None = None

    buy = posture.buy_quality
    sell = posture.sell_quality

    if buy.bleeding:
        bid_mult = BLEED_SIZE_MULT
        bid_override = False
        bid_note = buy.bleed_reason or "buy_bleed"
    elif buy.session_capture_xrp < SESSION_BLEED_XRP:
        bid_mult = BLEED_SIZE_MULT
        bid_override = False
        bid_note = f"session_buy_cap={buy.session_capture_xrp:.4f}"

    if sell.bleeding:
        ask_mult = BLEED_SIZE_MULT
        ask_override = False
        ask_note = sell.bleed_reason or "sell_bleed"
    elif sell.session_capture_xrp < SESSION_BLEED_XRP:
        ask_mult = BLEED_SIZE_MULT
        ask_override = False
        ask_note = f"session_sell_cap={sell.session_capture_xrp:.4f}"

    return BleedAdjustment(
        bid_size_mult=bid_mult,
        ask_size_mult=ask_mult,
        bid_allowed_override=bid_override,
        ask_allowed_override=ask_override,
        bid_note=bid_note,
        ask_note=ask_note,
    )


def merge_bleed_into_permission(
    perm: SidePermission,
    *,
    bleed_mult: float,
    allowed_override: bool | None,
    bleed_note: str,
) -> SidePermission:
    if not perm.allowed:
        return perm
    if allowed_override is False:
        return SidePermission(
            allowed=False,
            size_mult=0.0,
            implied_edge_bps=perm.implied_edge_bps,
            block_reason=bleed_note or "bleed_protection",
        )
    if bleed_mult <= 0:
        return SidePermission(
            allowed=False,
            size_mult=0.0,
            implied_edge_bps=perm.implied_edge_bps,
            block_reason=bleed_note or "bleed_protection",
        )
    return SidePermission(
        allowed=True,
        size_mult=round(perm.size_mult * bleed_mult, 3),
        implied_edge_bps=perm.implied_edge_bps,
        block_reason="",
    )


__all__ = ["BleedAdjustment", "apply_bleed_protection", "merge_bleed_into_permission"]
