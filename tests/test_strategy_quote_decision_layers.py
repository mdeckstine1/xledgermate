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


def test_solo_edge_allows_soft_floor_with_market_edge_met() -> None:
    min_edge = min_net_edge_pct(book_mode=BookMode.SOLO, profile_min_edge_pct=0.0)
    soft_floor = min_edge * 0.75
    result = evaluate_side_edge(
        side="bid",
        book_spread_pct=0.07,
        our_half_spread_pct=0.015,
        profile_min_edge_pct=0.0,
        book_mode=BookMode.SOLO,
        market_edge_met=True,
    )
    assert result.implied_edge_pct == pytest.approx(0.02)
    assert soft_floor == pytest.approx(0.01875)
    assert result.implied_edge_pct >= soft_floor
    assert result.implied_edge_pct < min_edge
    assert result.viable


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
    assert not layer.bid.allowed
    assert layer.ask.allowed
    assert "inventory bailout" in layer.bid.block_reason


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
