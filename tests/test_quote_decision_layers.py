"""Tests for layered quote decision stack (WS API → strategy layers)."""

from __future__ import annotations

from strategy.fill_quality import FillQualityState
from strategy.quote_decision_layers.edge import evaluate_side_edge, min_net_edge_pct
from strategy.quote_decision_layers.posture import build_posture
from strategy.quote_decision_layers.types import BookMode as StrategyBookMode

from experimental.ws_feed.quote_decision.adapter import (
    compute_quoting_decision,
    shadow_compare_legacy,
)
from experimental.ws_feed.quote_decision.pipeline import run_quote_decision_pipeline
from experimental.ws_feed.quote_decision.types import (
    CycleQuoteInputs,
    DriftBand,
    QuoteIntent,
)


def _solo_inputs(
    *,
    l1_bid: float = 1.0993,
    l1_ask: float = 1.102,
    mid: float = 1.10,
    xrp_ratio: float = 0.55,
    label: str = "balanced",
    fill_quality: FillQualityState | None = None,
    bid_half_spread_pct: float = 0.015,
    ask_half_spread_pct: float = 0.03,
    market_edge_met: bool = True,
) -> CycleQuoteInputs:
    """Solo fixture with spread-capture edge that clears strategy solo gate."""
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
        reservation_allows_bid=True,
        reservation_allows_ask=True,
        fill_quality=fill_quality,
        bid_half_spread_pct=bid_half_spread_pct,
        ask_half_spread_pct=ask_half_spread_pct,
        market_edge_met=market_edge_met,
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
        _solo_inputs(
            bid_half_spread_pct=0.08,
            ask_half_spread_pct=0.08,
        )
    )
    assert qd.intent == QuoteIntent.PATIENT_SOLO
    assert qd.would_quote is False


def test_bleed_pauses_buy_only_not_ask() -> None:
    """Principle 4: bleed on buy pauses bid; ask allowed when sell edge viable."""
    fq = FillQualityState(
        buy_fill_count=4,
        buy_toxic_ratio_30s=0.5,
        buy_mean_markout_30s_pct=-0.06,
    )
    qd = run_quote_decision_pipeline(
        _solo_inputs(fill_quality=fq, ask_half_spread_pct=0.015)
    )
    assert qd.bid.allowed is False
    assert qd.ask.allowed is True
    assert qd.trace.bid_bleed_note or "toxic" in qd.bid.block_reason
    assert "trace book=solo" in qd.summary
    assert "pause_bid=bleed" in qd.summary


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
        bid_half_spread_pct=0.015,
        ask_half_spread_pct=0.015,
    )
    qd = run_quote_decision_pipeline(inp)
    assert qd.intent == QuoteIntent.TWO_SIDED_SKIM
    assert qd.bid.allowed is True
    assert qd.ask.allowed is True


def test_layer1_drift_bands_wide() -> None:
    posture = build_posture(
        xrp_ratio=0.64,
        inventory_label="balanced",
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        peer_lane_empty=True,
    )
    assert posture.inventory.band.value == DriftBand.MILD_XRP.value
    posture_heavy = build_posture(
        xrp_ratio=0.72,
        inventory_label="xrp_heavy",
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        peer_lane_empty=True,
    )
    assert posture_heavy.inventory.band.value == DriftBand.HEAVY_XRP.value


def test_layer3_solo_softer_than_crowded() -> None:
    solo = min_net_edge_pct(
        book_mode=StrategyBookMode.SOLO, profile_min_edge_pct=0.0
    )
    crowded = min_net_edge_pct(
        book_mode=StrategyBookMode.CROWDED, profile_min_edge_pct=0.0
    )
    assert solo < crowded


def test_solo_edge_gate_uses_spread_capture() -> None:
    """WS bridge maps L1 prices → spread capture pct (not mid-distance bps)."""
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.181818,
        our_half_spread_pct=0.063636,
        profile_min_edge_pct=0.0,
        book_mode=StrategyBookMode.SOLO,
        market_edge_met=True,
    )
    assert result.viable


def test_ws_scenario_b_solo_negative_capture_edge_gate() -> None:
    """Solo + unprofitable capture → edge_gate blocks bid."""
    qd = run_quote_decision_pipeline(
        _solo_inputs(
            bid_half_spread_pct=0.08,
            ask_half_spread_pct=0.08,
            market_edge_met=False,
        )
    )
    assert qd.bid.allowed is False
    assert "edge_gate" in qd.bid.block_reason
    assert qd.would_quote is False


def test_ws_scenario_d_pipeline_summary_has_solo_trace() -> None:
    qd = run_quote_decision_pipeline(
        _solo_inputs(xrp_ratio=0.71, label="xrp_heavy")
    )
    assert qd.intent == QuoteIntent.SOLO_ACCUMULATE_ON_EDGE
    assert "solo_accumulate_on_edge" in qd.summary
    assert "trace book=solo" in qd.summary


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
    fq = FillQualityState(
        buy_fill_count=4,
        buy_toxic_ratio_30s=0.5,
        buy_mean_markout_30s_pct=-0.06,
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
        fill_quality=fq,
    )
    qd = run_quote_decision_pipeline(inp)
    assert qd.bid.allowed is False
    assert qd.ask.allowed is True  # two-sided skim — ask on edge, not bleed-boosted


def test_compute_quoting_decision_adapter() -> None:
    qd = compute_quoting_decision(
        mid=1.10,
        best_bid=1.099,
        best_ask=1.101,
        l1_bid_price=1.0993,
        l1_ask_price=1.102,
        xrp_balance=200.0,
        rlusd_balance=200.0,
        target_xrp_ratio=0.55,
        inventory_label="balanced",
        peer_lane_empty=True,
        bid_half_spread_pct=0.015,
        ask_half_spread_pct=0.03,
    )
    assert qd.would_quote is True
    flags = qd.to_legacy_flags()
    assert "quote_intent" in flags
