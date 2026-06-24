"""Tests for layered quote decision stack."""

from __future__ import annotations

from experimental.ws_feed.quote_decision.adapter import (
    compute_quoting_decision,
    shadow_compare_legacy,
)
from experimental.ws_feed.quote_decision.layer1_posture import build_posture_snapshot
from experimental.ws_feed.quote_decision.layer2_intent import select_quote_intent
from experimental.ws_feed.quote_decision.layer3_edge import evaluate_edge
from experimental.ws_feed.quote_decision.layer4_bleed import apply_bleed_protection
from experimental.ws_feed.quote_decision.pipeline import run_quote_decision_pipeline
from experimental.ws_feed.quote_decision.types import (
    BookMode,
    CycleQuoteInputs,
    DriftBand,
    QuoteIntent,
)


def _solo_inputs(
    *,
    l1_bid: float = 1.098,
    l1_ask: float = 1.102,
    mid: float = 1.10,
    xrp_ratio: float = 0.55,
    label: str = "balanced",
    buy_fills: tuple = (),
    sell_fills: tuple = (),
) -> CycleQuoteInputs:
    return CycleQuoteInputs(
        mid=mid,
        best_bid=1.099,
        best_ask=1.101,
        l1_bid_price=l1_bid,
        l1_ask_price=l1_ask,
        xrp_ratio=xrp_ratio,
        target_xrp_ratio=0.55,
        inventory_label=label,
        peer_lane_empty=True,
        peer_lane_count=0,
        toxic_ratio_30s=0.05,
        recent_buys=buy_fills,
        recent_sells=sell_fills,
        reservation_allows_bid=True,
        reservation_allows_ask=True,
    )


def test_solo_viable_buy_edge_accumulates_despite_xrp_heavy_drift() -> None:
    """Principle 3: solo + good buy edge → bid allowed even when drifted xrp-heavy."""
    qd = run_quote_decision_pipeline(
        _solo_inputs(xrp_ratio=0.71, label="xrp_heavy")
    )
    assert qd.intent == QuoteIntent.SOLO_ACCUMULATE_ON_EDGE
    assert qd.bid.allowed is True
    assert qd.ask.allowed is False
    assert qd.would_quote is True


def test_solo_no_edge_patient_off() -> None:
    qd = run_quote_decision_pipeline(
        _solo_inputs(l1_bid=1.0999, l1_ask=1.1001)
    )
    assert qd.intent == QuoteIntent.PATIENT_SOLO
    assert qd.would_quote is False


def test_solo_xrp_heavy_does_not_reopen_ask_when_bid_edge_fades() -> None:
    """Regression: solo acquire must not flip to ask trim when buy edge fades."""
    qd = run_quote_decision_pipeline(
        _solo_inputs(
            l1_bid=1.09985,
            l1_ask=1.1025,
            xrp_ratio=0.71,
            label="xrp_heavy",
        )
    )
    assert qd.intent == QuoteIntent.PATIENT_SOLO
    assert qd.bid.allowed is False
    assert qd.ask.allowed is False
    assert qd.trace.ask_edge.viable is True
    assert qd.would_quote is False


def test_bleed_pauses_buy_only_not_ask() -> None:
    """Principle 4: bleed on buy does not force ask-on."""
    fills = tuple(
        {"side": "BUY", "capture_xrp": -0.01, "xrp_amount": 5.0}
        for _ in range(3)
    )
    qd = run_quote_decision_pipeline(_solo_inputs(buy_fills=fills))
    assert qd.bid.allowed is False
    assert qd.ask.allowed is False  # solo accumulate intent — no ask by policy
    assert qd.trace.bid_bleed_note or "cap" in qd.bid.block_reason


def test_inventory_deadlock_avoided_xrp_heavy_solo() -> None:
    """Regression: old inv pause_bids + ask brake → both off; QD allows bid at edge."""
    qd = run_quote_decision_pipeline(
        _solo_inputs(xrp_ratio=0.71, label="xrp_heavy")
    )
    assert qd.bid.allowed is True
    assert not (not qd.bid.allowed and not qd.ask.allowed and qd.would_quote is False)


def test_crowded_two_sided_when_both_edges_viable() -> None:
    inp = CycleQuoteInputs(
        mid=1.10,
        best_bid=1.099,
        best_ask=1.101,
        l1_bid_price=1.098,
        l1_ask_price=1.102,
        xrp_ratio=0.55,
        target_xrp_ratio=0.55,
        inventory_label="balanced",
        peer_lane_empty=False,
        peer_lane_count=4,
        toxic_ratio_30s=0.05,
    )
    qd = run_quote_decision_pipeline(inp)
    assert qd.intent == QuoteIntent.TWO_SIDED_SKIM
    assert qd.bid.allowed is True
    assert qd.ask.allowed is True


def test_layer1_drift_bands_wide() -> None:
    posture = build_posture_snapshot(_solo_inputs(xrp_ratio=0.64))
    assert posture.inventory.band == DriftBand.MILD_XRP
    posture_heavy = build_posture_snapshot(_solo_inputs(xrp_ratio=0.72))
    assert posture_heavy.inventory.band == DriftBand.HEAVY_XRP


def test_layer3_solo_softer_than_crowded() -> None:
    solo = evaluate_edge(
        side="bid", l1_price=1.0995, mid=1.10, book_mode=BookMode.SOLO
    )
    crowded = evaluate_edge(
        side="bid", l1_price=1.0995, mid=1.10, book_mode=BookMode.CROWDED
    )
    assert solo.min_edge_bps < crowded.min_edge_bps


def test_shadow_compare_detects_legacy_conflict() -> None:
    qd = run_quote_decision_pipeline(_solo_inputs(xrp_ratio=0.71, label="xrp_heavy"))
    diff = shadow_compare_legacy(
        qd,
        legacy_pause_bids=True,
        legacy_pause_asks=True,
        legacy_would_quote=False,
    )
    assert diff["quote_decision_conflicts"]


def test_crowded_buy_bleed_does_not_boost_ask() -> None:
    """Crowded: buy bleed pauses bid; ask follows skim intent, not bleed reaction."""
    fills = tuple(
        {"side": "BUY", "capture_xrp": -0.01, "xrp_amount": 5.0}
        for _ in range(3)
    )
    inp = CycleQuoteInputs(
        mid=1.10,
        best_bid=1.099,
        best_ask=1.101,
        l1_bid_price=1.098,
        l1_ask_price=1.102,
        xrp_ratio=0.55,
        target_xrp_ratio=0.55,
        inventory_label="balanced",
        peer_lane_empty=False,
        peer_lane_count=4,
        toxic_ratio_30s=0.05,
        recent_buys=fills,
    )
    qd = run_quote_decision_pipeline(inp)
    assert qd.bid.allowed is False
    assert qd.ask.allowed is True  # two-sided skim — ask on edge, not bleed-boosted


def test_compute_quoting_decision_adapter() -> None:
    qd = compute_quoting_decision(
        mid=1.10,
        best_bid=1.099,
        best_ask=1.101,
        l1_bid_price=1.098,
        l1_ask_price=1.102,
        xrp_balance=200.0,
        rlusd_balance=200.0,
        target_xrp_ratio=0.55,
        inventory_label="balanced",
        peer_lane_empty=True,
    )
    assert qd.would_quote is True
    flags = qd.to_legacy_flags()
    assert "quote_intent" in flags
