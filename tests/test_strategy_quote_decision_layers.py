"""Tests for strategy/quote_decision_layers stack."""

import pytest

from core.market_conditions import assess_market_conditions
from core.perception import get_profile
from risk.inventory_limits import INVENTORY_MODE_MARKET_MAKE
from strategy.fill_quality import FillQualityState
from strategy.quote_decision import assess_inventory, build_quote_adjustments
from strategy.quote_decision_layers.edge import evaluate_side_edge, min_net_edge_pct
from strategy.quote_decision_layers.pipeline import run_layered_quote_decision
from strategy.quote_decision_layers.types import BookMode, QuoteIntent


def _favorable_assessment():
    return assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.9,
        book_spread_pct=0.07,
        active_profile="tight_spread",
    )


def _drifted_xrp_heavy_inv():
    return assess_inventory(
        xrp_balance=172.0,
        rlusd_balance=82.0,
        mid_price=1.346,
        target_xrp_ratio=0.55,
        skew_strength=0.75,
    )


def _solo_edge_kwargs(**overrides):
    """Params where bid capture clears solo soft floor (market_edge_met) but ask does not."""
    base = dict(
        book_spread_pct=0.07,
        bid_half_spread_pct=0.015,
        ask_half_spread_pct=0.03,
        min_edge_pct=0.0,
        market_edge_met=True,
    )
    base.update(overrides)
    return base


def _solo_layer(**overrides):
    inv = _drifted_xrp_heavy_inv()
    kwargs = dict(
        xrp_ratio=inv.xrp_ratio,
        inventory_label=inv.label,
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        inventory_max_deviation=0.12,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
        acquiring_rlusd=False,
        mm_mode=True,
        momentum_pause_vulnerable=False,
        peer_lane_empty=True,
    )
    kwargs.update(_solo_edge_kwargs())
    kwargs.update(overrides)
    return run_layered_quote_decision(**kwargs)


# --- Scenario A: solo + drifted + profitable edge → accumulate, no inv bailout ---


def test_scenario_a_solo_drifted_profitable_edge_accumulates() -> None:
    """peer_lane_empty + xrp-heavy drift + viable buy edge → bid on, no inventory pause."""
    layer = _solo_layer()
    assert layer.posture.book.mode == BookMode.SOLO
    assert layer.intent == QuoteIntent.SOLO_ACCUMULATE_ON_EDGE
    assert layer.bid.allowed
    assert not layer.ask.allowed
    assert layer.bid.pause_cause != "inventory"
    assert "inventory bailout" not in layer.bid.block_reason
    assert layer.trace is not None
    assert layer.trace.intent == QuoteIntent.SOLO_ACCUMULATE_ON_EDGE
    assert "solo_accumulate_on_edge" in layer.summary
    assert "book=solo" in layer.summary
    assert "trace book=solo" in layer.summary


def test_solo_drifted_xrp_heavy_allows_bid_at_edge() -> None:
    """Alias for scenario A via run_layered_quote_decision."""
    test_scenario_a_solo_drifted_profitable_edge_accumulates()


# --- Scenario B: solo + drifted + unprofitable capture → edge gate blocks bid ---


def test_scenario_b_solo_drifted_negative_capture_blocks_bid() -> None:
    """Solo drift ignored for intent selection but edge gate still blocks unprofitable bid."""
    layer = _solo_layer(
        bid_half_spread_pct=0.03,
        ask_half_spread_pct=0.03,
        market_edge_met=False,
    )
    assert layer.posture.book.mode == BookMode.SOLO
    assert not layer.bid.allowed
    assert "edge_gate" in layer.bid.block_reason
    assert layer.bid.pause_cause == "edge"
    assert layer.trace is not None
    assert not layer.trace.bid_edge_viable
    assert layer.trace.bid_pause_cause == "edge"


def test_solo_edge_rejects_negative_capture() -> None:
    min_edge = min_net_edge_pct(book_mode=BookMode.SOLO, profile_min_edge_pct=0.08)
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.04,
        our_half_spread_pct=0.03,
        profile_min_edge_pct=0.08,
        book_mode=BookMode.SOLO,
        market_edge_met=False,
    )
    assert not result.viable
    assert "edge_gate" in result.reason
    assert result.implied_edge_pct < 0
    assert result.min_edge_pct == min_edge


def test_solo_edge_rejects_near_zero_without_market_edge() -> None:
    min_edge = min_net_edge_pct(book_mode=BookMode.SOLO, profile_min_edge_pct=0.0)
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.07,
        our_half_spread_pct=0.03,
        profile_min_edge_pct=0.0,
        book_mode=BookMode.SOLO,
        market_edge_met=False,
    )
    assert result.implied_edge_pct == pytest.approx(0.005)
    assert min_edge == 0.025
    assert not result.viable
    assert "edge_gate" in result.reason


def test_solo_edge_allows_at_min_edge() -> None:
    min_edge = min_net_edge_pct(book_mode=BookMode.SOLO, profile_min_edge_pct=0.0)
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.07,
        our_half_spread_pct=0.01,
        profile_min_edge_pct=0.0,
        book_mode=BookMode.SOLO,
        market_edge_met=False,
    )
    assert result.implied_edge_pct == 0.025
    assert result.implied_edge_pct >= min_edge
    assert result.viable


def test_solo_edge_allows_marginal_capture_via_acquire_threshold() -> None:
    """Solo acquisition gate: 1.3% capture passes when full min_edge is 2.5%."""
    min_edge = min_net_edge_pct(book_mode=BookMode.SOLO, profile_min_edge_pct=0.0)
    assert min_edge == 0.025
    # capture = 0.035 - 0.022 = 0.013 (above 1.2% absolute floor, below full min_edge)
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.07,
        our_half_spread_pct=0.022,
        profile_min_edge_pct=0.0,
        book_mode=BookMode.SOLO,
        market_edge_met=False,
    )
    assert result.implied_edge_pct == pytest.approx(0.013)
    assert result.implied_edge_pct < min_edge
    assert result.viable


def test_solo_edge_allows_via_scaled_mult() -> None:
    min_edge = min_net_edge_pct(book_mode=BookMode.SOLO, profile_min_edge_pct=0.0)
    scaled = min_edge * 0.65
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.07,
        our_half_spread_pct=0.015,
        profile_min_edge_pct=0.0,
        book_mode=BookMode.SOLO,
        market_edge_met=False,
    )
    assert result.implied_edge_pct == pytest.approx(0.02)
    assert result.implied_edge_pct >= scaled
    assert result.implied_edge_pct < min_edge
    assert result.viable


def test_solo_edge_still_blocks_sub_floor_capture() -> None:
    """Clearly sub-floor capture (e.g. VPS 1.0% vs 1.2% floor) stays blocked."""
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.07,
        our_half_spread_pct=0.025,
        profile_min_edge_pct=0.0,
        book_mode=BookMode.SOLO,
        market_edge_met=True,
    )
    assert result.implied_edge_pct == pytest.approx(0.010)
    assert not result.viable
    assert "edge_gate" in result.reason
    assert "floor@0.012" in result.reason


def test_crowded_marginal_capture_still_viable() -> None:
    """Crowded/sparse: no hard gate — weak capture remains viable for size scaling."""
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.07,
        our_half_spread_pct=0.034,
        profile_min_edge_pct=0.0,
        book_mode=BookMode.CROWDED,
        market_edge_met=False,
    )
    assert result.implied_edge_pct == pytest.approx(0.001)
    assert result.viable


def test_solo_layer_marginal_edge_now_accumulates() -> None:
    """Pipeline: solo + marginal positive capture → SOLO_ACCUMULATE_ON_EDGE + bid on."""
    layer = _solo_layer(
        bid_half_spread_pct=0.022,
        ask_half_spread_pct=0.03,
        market_edge_met=False,
    )
    assert layer.intent == QuoteIntent.SOLO_ACCUMULATE_ON_EDGE
    assert layer.bid.allowed
    assert not layer.ask.allowed


def test_crowded_heavy_xrp_pauses_bids() -> None:
    inv = assess_inventory(
        xrp_balance=172.0,
        rlusd_balance=82.0,
        mid_price=1.346,
        target_xrp_ratio=0.55,
        skew_strength=0.75,
    )
    layer = run_layered_quote_decision(
        xrp_ratio=inv.xrp_ratio,
        inventory_label=inv.label,
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        book_spread_pct=0.07,
        bid_half_spread_pct=0.03,
        ask_half_spread_pct=0.03,
        min_edge_pct=0.08,
        market_edge_met=True,
        inventory_max_deviation=0.12,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
        acquiring_rlusd=False,
        mm_mode=True,
        momentum_pause_vulnerable=False,
        peer_lane_empty=False,
        peer_lane_count=3,
    )
    assert layer.posture.book.mode == BookMode.CROWDED
    assert layer.intent == QuoteIntent.TWO_SIDED_SKIM
    assert not layer.bid.allowed
    assert layer.ask.allowed
    assert "inventory bailout" in layer.bid.block_reason


def test_crowded_heavy_drift_selects_skim_not_inventory_unload() -> None:
    """Heavy drift on crowded book → TWO_SIDED_SKIM; L5 CB blocks vulnerable side."""
    from strategy.quote_decision_layers.intent import select_intent
    from strategy.quote_decision_layers.posture import build_posture

    posture = build_posture(
        xrp_ratio=0.72,
        inventory_label="xrp_heavy",
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        peer_lane_empty=False,
        peer_lane_count=3,
    )
    intent = select_intent(
        posture,
        buy_edge_viable=True,
        sell_edge_viable=True,
    )
    assert posture.book.mode == BookMode.CROWDED
    assert intent.intent == QuoteIntent.TWO_SIDED_SKIM
    assert intent.allow_two_sided


def test_solo_heavy_drift_no_edge_inventory_unload_trim() -> None:
    """Solo + heavy drift + no edge → trim-only INVENTORY_UNLOAD safety net."""
    layer = _solo_layer(
        bid_half_spread_pct=0.03,
        ask_half_spread_pct=0.03,
        market_edge_met=False,
    )
    assert layer.posture.book.mode == BookMode.SOLO
    assert layer.intent == QuoteIntent.INVENTORY_UNLOAD
    assert not layer.bid.allowed
    assert not layer.ask.allowed
    assert "edge_gate" in layer.bid.block_reason
    assert "edge_gate" in layer.ask.block_reason


def test_scenario_c_solo_bleed_pauses_bid_only_ask_if_edge() -> None:
    """Buy-side bleed pauses bid only; ask allowed when sell edge viable — no opposite boost."""
    fq = FillQualityState(
        buy_fill_count=4,
        buy_toxic_ratio_30s=0.5,
        buy_mean_markout_30s_pct=-0.06,
    )
    inv = assess_inventory(
        xrp_balance=100.0,
        rlusd_balance=100.0,
        mid_price=1.34,
        target_xrp_ratio=0.55,
        skew_strength=0.75,
    )
    layer = run_layered_quote_decision(
        xrp_ratio=inv.xrp_ratio,
        inventory_label=inv.label,
        fill_quality=fq,
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        book_spread_pct=0.07,
        bid_half_spread_pct=0.015,
        ask_half_spread_pct=0.015,
        min_edge_pct=0.0,
        market_edge_met=True,
        inventory_max_deviation=0.12,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
        acquiring_rlusd=False,
        mm_mode=True,
        momentum_pause_vulnerable=False,
        peer_lane_empty=True,
    )
    assert not layer.bid.allowed
    assert layer.ask.allowed
    assert layer.bid.pause_cause == "bleed"
    assert layer.trace is not None
    assert layer.trace.ask_edge_viable
    assert layer.trace.bid_pause_cause == "bleed"
    assert "pause_bid=bleed" in layer.trace.compact()


def test_bleed_pauses_buy_side_only() -> None:
    test_scenario_c_solo_bleed_pauses_bid_only_ask_if_edge()


def test_low_book_pressure_sparse_allows_solo_accumulate() -> None:
    """peer_lane_count=1 + balanced book → solo accumulate on buy edge when drifted."""
    inv = assess_inventory(
        xrp_balance=172.0,
        rlusd_balance=82.0,
        mid_price=1.346,
        target_xrp_ratio=0.55,
        skew_strength=0.75,
    )
    layer = run_layered_quote_decision(
        xrp_ratio=inv.xrp_ratio,
        inventory_label=inv.label,
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        **_solo_edge_kwargs(),
        inventory_max_deviation=0.12,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
        acquiring_rlusd=False,
        mm_mode=True,
        momentum_pause_vulnerable=False,
        peer_lane_empty=False,
        peer_lane_count=1,
        low_book_pressure=True,
    )
    assert layer.posture.book.mode == BookMode.SOLO
    assert layer.bid.allowed
    assert "inventory bailout" not in layer.bid.block_reason


def test_pause_cause_attributed_in_summary() -> None:
    assessment = _favorable_assessment()
    inv = assess_inventory(
        xrp_balance=162.0,
        rlusd_balance=95.0,
        mid_price=1.346,
        target_xrp_ratio=0.55,
        skew_strength=0.75,
    )
    adj = build_quote_adjustments(
        profile=get_profile("tight_spread"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.08,
        book_spread_pct=0.07,
        depth_imbalance=0.0,
        min_edge_pct=0.08,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
    )
    assert "pause bids (inventory)" in adj.decision_summary


def test_scenario_d_build_quote_adjustments_solo_integration() -> None:
    """build_quote_adjustments + peer_lane_empty on drifted inventory → solo trace in summary."""
    assessment = _favorable_assessment()
    inv = _drifted_xrp_heavy_inv()
    adj = build_quote_adjustments(
        profile=get_profile("tight_spread"),
        assessment=assessment,
        inventory=inv,
        mid_momentum_pct=0.0,
        effective_spread_l1_pct=0.03,
        book_spread_pct=0.07,
        depth_imbalance=0.0,
        min_edge_pct=0.0,
        inventory_mode=INVENTORY_MODE_MARKET_MAKE,
        peer_lane_empty=True,
        peer_lane_count=0,
    )
    assert not adj.pause_bids
    assert "inventory bailout" not in adj.decision_summary
    assert "solo_accumulate_on_edge" in adj.decision_summary
    assert "book=solo" in adj.decision_summary
    assert "solo lane active (peer_lane_empty=True)" in adj.decision_summary
    assert "trace book=solo" in adj.decision_summary
    assert "pause_bid=—" in adj.decision_summary


def test_build_quote_adjustments_solo_lane_drifts_xrp_heavy_allows_bid() -> None:
    test_scenario_d_build_quote_adjustments_solo_integration()


# --- Posture hardening (input validation, no quoting behavior change) ---


def test_posture_contradictory_empty_flag_normalizes_count() -> None:
    from strategy.quote_decision_layers.posture import build_posture

    p = build_posture(
        xrp_ratio=0.55,
        inventory_label="balanced",
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        peer_lane_empty=True,
        peer_lane_count=5,
    )
    assert p.book.solo is True
    assert p.book.peer_lane_count == 0
    assert p.book.mode == BookMode.SOLO


def test_posture_unknown_peer_count_defaults_crowded_mode() -> None:
    from strategy.quote_decision_layers.posture import (
        PEER_LANE_COUNT_CROWDED_ASSUMED,
        build_posture,
    )

    p = build_posture(
        xrp_ratio=0.55,
        inventory_label="balanced",
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        peer_lane_empty=False,
        peer_lane_count=0,
    )
    assert p.book.solo is False
    assert p.book.peer_lane_count == 0
    assert p.book.mode == BookMode.CROWDED
    assert PEER_LANE_COUNT_CROWDED_ASSUMED == 3


def test_posture_clamps_invalid_ratios_and_market_condition() -> None:
    from strategy.quote_decision_layers.posture import build_posture
    from core.market_conditions import CONDITION_NEUTRAL

    p = build_posture(
        xrp_ratio=float("nan"),
        inventory_label="",
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="not_a_real_condition",
        mid_momentum_pct=float("inf"),
        peer_lane_empty=True,
    )
    assert p.inventory.xrp_ratio == 0.5  # default clamp for NaN
    assert p.inventory.label == "balanced"
    assert p.market_condition == CONDITION_NEUTRAL
    assert p.mid_momentum_pct == 0.0

