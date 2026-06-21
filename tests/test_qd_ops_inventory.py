"""QD_OPS logging for crowded/sparse inventory paths."""

from __future__ import annotations

import logging

from strategy.fill_quality import FillQualityState
from strategy.quote_decision_layers.ops_log import (
    log_heavy_drift_l5_deferred,
    log_inventory_cb_block,
    log_inventory_unload_intent,
)
from strategy.quote_decision_layers.pipeline import run_layered_quote_decision
from strategy.quote_decision_layers.posture import build_posture
from strategy.quote_decision_layers.types import BookMode, DriftBand, QuoteIntent


def test_log_inventory_cb_block_format(caplog) -> None:
    posture = build_posture(
        xrp_ratio=0.73,
        inventory_label="xrp_heavy",
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        peer_lane_empty=False,
        peer_lane_count=3,
    )
    with caplog.at_level(logging.INFO):
        log_inventory_cb_block(
            posture=posture,
            side="bid",
            inventory_max_deviation=0.12,
            inventory_mode="market_make",
            path="ws",
        )
    line = caplog.text
    assert "QD_OPS inventory_cb_block=true" in line
    assert "book_mode=crowded" in line
    assert "side=bid" in line
    assert "layer=L5" in line
    assert "path=ws" in line


def test_log_inventory_unload_intent_format_solo_trim(caplog) -> None:
    posture = build_posture(
        xrp_ratio=0.72,
        inventory_label="xrp_heavy",
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        peer_lane_empty=True,
        peer_lane_count=0,
    )
    assert posture.inventory.band == DriftBand.HEAVY_XRP
    assert posture.book.mode == BookMode.SOLO
    with caplog.at_level(logging.INFO):
        log_inventory_unload_intent(
            posture=posture,
            intent_reason="solo + xrp drift + no edge — trim only (ask)",
            favor_bid=False,
            favor_ask=True,
            buy_edge_viable=False,
            sell_edge_viable=False,
            path="engine",
        )
    line = caplog.text
    assert "QD_OPS intent=INVENTORY_UNLOAD" in line
    assert "favor=ask" in line
    assert "layer=L2" in line
    assert "book_mode=solo" in line


def test_log_heavy_drift_l5_deferred_format(caplog) -> None:
    posture = build_posture(
        xrp_ratio=0.72,
        inventory_label="xrp_heavy",
        fill_quality=FillQualityState(),
        target_xrp_ratio=0.55,
        market_condition="favorable",
        mid_momentum_pct=0.0,
        peer_lane_empty=False,
        peer_lane_count=4,
    )
    with caplog.at_level(logging.INFO):
        log_heavy_drift_l5_deferred(
            posture=posture,
            selected_intent=QuoteIntent.TWO_SIDED_SKIM,
            buy_edge_viable=True,
            sell_edge_viable=True,
            path="ws",
        )
    line = caplog.text
    assert "QD_OPS heavy_drift_l5_deferred=true" in line
    assert "book_mode=crowded" in line
    assert "intent=two_sided_skim" in line
    assert "l5_inventory_cb_owns_permission" in line


def test_pipeline_emits_inventory_cb_ops_on_crowded_drift(caplog) -> None:
    with caplog.at_level(logging.INFO):
        run_layered_quote_decision(
            xrp_ratio=0.72,
            inventory_label="xrp_heavy",
            fill_quality=FillQualityState(),
            target_xrp_ratio=0.55,
            market_condition="favorable",
            mid_momentum_pct=0.0,
            book_spread_pct=0.07,
            bid_half_spread_pct=0.03,
            ask_half_spread_pct=0.03,
            min_edge_pct=0.0,
            market_edge_met=True,
            inventory_max_deviation=0.12,
            inventory_mode="market_make",
            acquiring_rlusd=False,
            mm_mode=True,
            momentum_pause_vulnerable=False,
            peer_lane_empty=False,
            peer_lane_count=3,
            ops_path="test",
        )
    assert "inventory_cb_block=true" in caplog.text
    assert "side=bid" in caplog.text


def test_pipeline_crowded_heavy_drift_skims_not_unload(caplog) -> None:
    with caplog.at_level(logging.INFO):
        layer = run_layered_quote_decision(
            xrp_ratio=0.72,
            inventory_label="xrp_heavy",
            fill_quality=FillQualityState(),
            target_xrp_ratio=0.55,
            market_condition="favorable",
            mid_momentum_pct=0.0,
            book_spread_pct=0.07,
            bid_half_spread_pct=0.015,
            ask_half_spread_pct=0.015,
            min_edge_pct=0.0,
            market_edge_met=True,
            inventory_max_deviation=0.12,
            inventory_mode="market_make",
            acquiring_rlusd=False,
            mm_mode=True,
            momentum_pause_vulnerable=False,
            peer_lane_empty=False,
            peer_lane_count=4,
            ops_path="test",
        )
    assert layer.intent == QuoteIntent.TWO_SIDED_SKIM
    assert layer.posture.book.mode == BookMode.CROWDED
    assert "intent=INVENTORY_UNLOAD" not in caplog.text
    assert "heavy_drift_l5_deferred=true" in caplog.text
    assert "inventory_cb_block=true" in caplog.text
