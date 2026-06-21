"""
Layer 2 — Intent / policy selection.

Chooses what the bot is trying to do. Does not set ``SidePermission.allowed``
(Layer 5 via ``build_layer_decision`` only).
On solo books, profitable edge on the favorable side wins over drifted inventory.
"""

from __future__ import annotations

from strategy.quote_decision_layers.types import (
    BookMode,
    DriftBand,
    IntentSelection,
    Posture,
    QuoteIntent,
)


def select_intent(
    posture: Posture,
    *,
    buy_edge_viable: bool,
    sell_edge_viable: bool,
) -> IntentSelection:
    """Pick operational intent from posture + edge viability hints."""
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

    # Single-side bleed: Layer 4 pauses that side only — no opposite-side boost here.

    if book.mode == BookMode.SOLO:
        if posture.buy_quality.bleeding and not posture.sell_quality.bleeding:
            if sell_edge_viable:
                return IntentSelection(
                    intent=QuoteIntent.PATIENT_SOLO,
                    reason="solo — buy side bleeding, ask only if edge",
                    favor_bid=False,
                    favor_ask=True,
                    allow_two_sided=False,
                )
            return IntentSelection(
                intent=QuoteIntent.HOLD_OFF,
                reason="solo — buy side bleeding",
                favor_bid=False,
                favor_ask=False,
                allow_two_sided=False,
            )

        if posture.sell_quality.bleeding and not posture.buy_quality.bleeding:
            if buy_edge_viable:
                return IntentSelection(
                    intent=QuoteIntent.PATIENT_SOLO,
                    reason="solo — sell side bleeding, bid only if edge",
                    favor_bid=True,
                    favor_ask=False,
                    allow_two_sided=False,
                )
            return IntentSelection(
                intent=QuoteIntent.HOLD_OFF,
                reason="solo — sell side bleeding",
                favor_bid=False,
                favor_ask=False,
                allow_two_sided=False,
            )

        # Solo: quote the side with viable edge even when drifted (grow from edge).
        if buy_edge_viable:
            return IntentSelection(
                intent=QuoteIntent.SOLO_ACCUMULATE_ON_EDGE,
                reason="solo book + viable buy edge (drift ignored)",
                favor_bid=True,
                favor_ask=False,
                allow_two_sided=False,
            )

        if sell_edge_viable:
            return IntentSelection(
                intent=QuoteIntent.SOLO_ACCUMULATE_ON_EDGE,
                reason="solo book + viable sell edge (drift ignored)",
                favor_bid=False,
                favor_ask=True,
                allow_two_sided=False,
            )

        if inv.band in (DriftBand.HEAVY_XRP, DriftBand.MILD_XRP):
            return IntentSelection(
                intent=QuoteIntent.INVENTORY_UNLOAD,
                reason="solo + xrp drift + sell edge — trim only",
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

    # Crowded / sparse — inventory unload when far from target on the bleeding side.
    if inv.band in (DriftBand.HEAVY_XRP, DriftBand.HEAVY_RLUSD):
        if inv.band == DriftBand.HEAVY_XRP and sell_edge_viable:
            return IntentSelection(
                intent=QuoteIntent.INVENTORY_UNLOAD,
                reason=f"{book.mode.value} + heavy xrp drift + sell edge",
                favor_bid=False,
                favor_ask=True,
                allow_two_sided=False,
            )
        if inv.band == DriftBand.HEAVY_RLUSD and buy_edge_viable:
            return IntentSelection(
                intent=QuoteIntent.INVENTORY_UNLOAD,
                reason=f"{book.mode.value} + heavy rlusd drift + buy edge",
                favor_bid=True,
                favor_ask=False,
                allow_two_sided=False,
            )

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
