"""
Layer 2 — Intent / policy selection.

Chooses what the bot is trying to do. Does not set ``SidePermission.allowed``
(Layer 5 via ``build_layer_decision`` only).

Solo books use **Balanced Aggressive** intent:
  - Accumulate strongly on the right-way side when edge is viable.
  - Allow wrong-way one-sided accumulation only when edge clears the *full*
    net threshold (strong edge), not merely the relaxed solo L3 gate.
  - When both sides have edge and skew is neutral, prefer ``TWO_SIDED_SKIM``.
  - Reserve ``INVENTORY_UNLOAD`` for *heavy* drift with no viable edge (trim-only).
  - Mild drift + no edge → ``PATIENT_SOLO`` (not one-sided unload).

Layer 4 bleed protection is unchanged and side-local; this module never reads
bleed overrides — only ``posture.*_quality.bleeding`` flags from L1.
"""

from __future__ import annotations

from strategy.quote_decision_layers.types import (
    BookMode,
    DriftBand,
    IntentSelection,
    Posture,
    QuoteIntent,
)


def _edge_is_strong(capture_pct: float, min_edge_pct: float) -> bool:
    """
    Strong edge for Balanced Aggressive wrong-way accumulation.

    Uses the full net ``min_edge_pct`` from L3 — stricter than the relaxed solo
    gate (65% of min or absolute floor). Wrong-way one-sided intent requires this.
    """
    return capture_pct >= min_edge_pct


def _bid_deepens_xrp_skew(band: DriftBand) -> bool:
    """Buying XRP when already XRP-heavy deepens inventory skew."""
    return band in (DriftBand.MILD_XRP, DriftBand.HEAVY_XRP)


def _ask_deepens_rlusd_skew(band: DriftBand) -> bool:
    """Selling XRP when RLUSD-heavy deepens inventory skew."""
    return band in (DriftBand.MILD_RLUSD, DriftBand.HEAVY_RLUSD)


def _solo_accumulate(
    *,
    favor_bid: bool,
    favor_ask: bool,
    reason: str,
) -> IntentSelection:
    return IntentSelection(
        intent=QuoteIntent.SOLO_ACCUMULATE_ON_EDGE,
        reason=reason,
        favor_bid=favor_bid,
        favor_ask=favor_ask,
        allow_two_sided=False,
    )


def _solo_skim(*, reason: str, favor_bid: bool, favor_ask: bool) -> IntentSelection:
    return IntentSelection(
        intent=QuoteIntent.TWO_SIDED_SKIM,
        reason=reason,
        favor_bid=favor_bid,
        favor_ask=favor_ask,
        allow_two_sided=favor_bid and favor_ask,
    )


def _select_solo_balanced_aggressive(
    posture: Posture,
    *,
    buy_edge_viable: bool,
    sell_edge_viable: bool,
    buy_capture_pct: float,
    sell_capture_pct: float,
    buy_min_edge_pct: float,
    sell_min_edge_pct: float,
) -> IntentSelection:
    """Balanced Aggressive solo intent — skew-aware, strong-edge gated."""
    band = posture.inventory.band
    buy_strong = buy_edge_viable and _edge_is_strong(buy_capture_pct, buy_min_edge_pct)
    sell_strong = sell_edge_viable and _edge_is_strong(sell_capture_pct, sell_min_edge_pct)

    # Both sides pass L3 solo gate — prefer skim on neutral books; on skewed books
    # favor the rebalancing side unless wrong-way edge is clearly strong.
    if buy_edge_viable and sell_edge_viable:
        if band == DriftBand.NEUTRAL:
            return _solo_skim(
                reason="solo neutral — both edges viable; two-sided skim",
                favor_bid=True,
                favor_ask=True,
            )
        if band in (DriftBand.MILD_XRP, DriftBand.HEAVY_XRP):
            if buy_strong and sell_strong:
                return _solo_skim(
                    reason="solo xrp skew — both edges strong; skim over one-sided",
                    favor_bid=True,
                    favor_ask=True,
                )
            if buy_strong:
                return _solo_accumulate(
                    favor_bid=True,
                    favor_ask=False,
                    reason="solo xrp skew — strong buy edge overrides skew",
                )
            return _solo_accumulate(
                favor_bid=False,
                favor_ask=True,
                reason="solo xrp skew — sell edge rebalances (right-way)",
            )
        if band in (DriftBand.MILD_RLUSD, DriftBand.HEAVY_RLUSD):
            if buy_strong and sell_strong:
                return _solo_skim(
                    reason="solo rlusd skew — both edges strong; skim over one-sided",
                    favor_bid=True,
                    favor_ask=True,
                )
            if sell_strong:
                return _solo_accumulate(
                    favor_bid=False,
                    favor_ask=True,
                    reason="solo rlusd skew — strong sell edge overrides skew",
                )
            return _solo_accumulate(
                favor_bid=True,
                favor_ask=False,
                reason="solo rlusd skew — buy edge rebalances (right-way)",
            )

    if buy_edge_viable:
        if _bid_deepens_xrp_skew(band) and not buy_strong:
            return IntentSelection(
                intent=QuoteIntent.PATIENT_SOLO,
                reason="solo — buy edge marginal vs xrp skew; waiting",
                favor_bid=False,
                favor_ask=False,
                allow_two_sided=False,
            )
        return _solo_accumulate(
            favor_bid=True,
            favor_ask=False,
            reason="solo book + viable buy edge (balanced aggressive)",
        )

    if sell_edge_viable:
        if _ask_deepens_rlusd_skew(band) and not sell_strong:
            return IntentSelection(
                intent=QuoteIntent.PATIENT_SOLO,
                reason="solo — sell edge marginal vs rlusd skew; waiting",
                favor_bid=False,
                favor_ask=False,
                allow_two_sided=False,
            )
        return _solo_accumulate(
            favor_bid=False,
            favor_ask=True,
            reason="solo book + viable sell edge (balanced aggressive)",
        )

    # No viable edge — heavy drift only: trim-only safety net (L5 CB skipped solo).
    if band == DriftBand.HEAVY_XRP:
        return IntentSelection(
            intent=QuoteIntent.INVENTORY_UNLOAD,
            reason="solo + heavy xrp drift + no edge — trim only (ask)",
            favor_bid=False,
            favor_ask=True,
            allow_two_sided=False,
        )
    if band == DriftBand.HEAVY_RLUSD:
        return IntentSelection(
            intent=QuoteIntent.INVENTORY_UNLOAD,
            reason="solo + heavy rlusd drift + no edge — trim only (bid)",
            favor_bid=True,
            favor_ask=False,
            allow_two_sided=False,
        )

    return IntentSelection(
        intent=QuoteIntent.PATIENT_SOLO,
        reason="solo — waiting for edge",
        favor_bid=False,
        favor_ask=False,
        allow_two_sided=False,
    )


def select_intent(
    posture: Posture,
    *,
    buy_edge_viable: bool,
    sell_edge_viable: bool,
    buy_capture_pct: float = 0.0,
    sell_capture_pct: float = 0.0,
    buy_min_edge_pct: float = 0.0,
    sell_min_edge_pct: float = 0.0,
) -> IntentSelection:
    """Pick operational intent from posture + L3 edge viability and capture."""
    book = posture.book

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

        return _select_solo_balanced_aggressive(
            posture,
            buy_edge_viable=buy_edge_viable,
            sell_edge_viable=sell_edge_viable,
            buy_capture_pct=buy_capture_pct,
            sell_capture_pct=sell_capture_pct,
            buy_min_edge_pct=buy_min_edge_pct,
            sell_min_edge_pct=sell_min_edge_pct,
        )

    # Crowded / sparse — unchanged; L5 inventory CB owns hard blocks there.
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
