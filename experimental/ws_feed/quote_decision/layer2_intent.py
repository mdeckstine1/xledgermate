"""
Layer 2 — Intent / policy selection.

Chooses what the bot is *trying* to do. Does not set final permissions —
that is Layer 5. Inventory drift informs intent but does not hard-block solo
accumulation when edges are available (principle 3).
"""

from __future__ import annotations

from dataclasses import dataclass

from experimental.ws_feed.execution_envelope import SOLO_ACQUIRE_TOXIC_30S_MAX
from experimental.ws_feed.quote_decision.types import (
    BookMode,
    DriftBand,
    PostureSnapshot,
    QuoteIntent,
)

# Prefer bid accumulation on solo when buy edge is viable (set in pipeline).
SOLO_TOXIC_MAX = SOLO_ACQUIRE_TOXIC_30S_MAX


@dataclass(frozen=True)
class IntentSelection:
    intent: QuoteIntent
    reason: str
    favor_bid: bool
    favor_ask: bool
    allow_two_sided: bool


def select_quote_intent(
    posture: PostureSnapshot,
    *,
    buy_edge_viable: bool,
    sell_edge_viable: bool,
) -> IntentSelection:
    """
    Pick operational intent from posture + edge viability hints.

    Edge viability comes from Layer 3 preview (implied prices only).
    """
    book = posture.book
    inv = posture.inventory

    if posture.buy_quality.bleeding and posture.sell_quality.bleeding:
        return IntentSelection(
            intent=QuoteIntent.HOLD_OFF,
            reason="both sides bleeding",
            favor_bid=False,
            favor_ask=False,
            allow_two_sided=False,
        )

    # Single-side bleed: Layer 4 pauses that side only — do not flip intent or
    # enable the opposite side here (principle 4).

    if book.mode == BookMode.SOLO:
        if posture.toxic_ratio_30s >= SOLO_TOXIC_MAX:
            return IntentSelection(
                intent=QuoteIntent.PATIENT_SOLO,
                reason=f"toxic@{posture.toxic_ratio_30s:.0%}>={SOLO_TOXIC_MAX:.0%}",
                favor_bid=False,
                favor_ask=False,
                allow_two_sided=False,
            )

        # Solo default: accumulate on good buy edge even when drifted (principle 3).
        if buy_edge_viable:
            return IntentSelection(
                intent=QuoteIntent.SOLO_ACCUMULATE_ON_EDGE,
                reason="solo book + viable buy edge",
                favor_bid=True,
                favor_ask=False,
                allow_two_sided=False,
            )

        if sell_edge_viable and inv.band in (DriftBand.HEAVY_XRP, DriftBand.MILD_XRP):
            # Trim only when sell edge is good — not forced unload.
            return IntentSelection(
                intent=QuoteIntent.PATIENT_SOLO,
                reason="solo + xrp drift + sell edge — optional trim",
                favor_bid=False,
                favor_ask=True,
                allow_two_sided=False,
            )

        return IntentSelection(
            intent=QuoteIntent.PATIENT_SOLO,
            reason="solo — waiting for edge",
            favor_bid=False,
            favor_ask=False,
            allow_two_sided=False,
        )

    # Crowded / sparse — two-sided skim when edges allow.
    if buy_edge_viable or sell_edge_viable:
        return IntentSelection(
            intent=QuoteIntent.TWO_SIDED_SKIM,
            reason=f"{book.mode.value} book + edge available",
            favor_bid=buy_edge_viable,
            favor_ask=sell_edge_viable,
            allow_two_sided=buy_edge_viable and sell_edge_viable,
        )

    return IntentSelection(
        intent=QuoteIntent.PATIENT_SOLO,
        reason=f"{book.mode.value} — no viable edge",
        favor_bid=False,
        favor_ask=False,
        allow_two_sided=False,
    )


__all__ = ["IntentSelection", "select_quote_intent"]
