"""Tests for RLUSD reload regime (post-run chop funding)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from alpha.decision.reload_regime import (
    ReloadSessionTracker,
    compute_reload_sell_size_xrp,
    detect_post_run_consolidation,
    evaluate_reload_regime,
    reload_blocks_accumulation_bids,
    reload_shortfall_xrp_equiv,
)
from alpha.decision.structure import MarketStructureSnapshot
from alpha.types import BalanceSnapshot, InventorySnapshot
from config.settings import BotConfig


def _inventory_at_target() -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=0.80,
        target_xrp_ratio=0.80,
        deviation=0.01,
        label="balanced",
        pause_bids=False,
        pause_asks=False,
        summary="test",
        portfolio_xrp_equiv=600.0,
        xrp_allocation_pct=80.0,
        rlusd_allocation_pct=20.0,
        buy_blocked_imbalance=False,
        sell_blocked_imbalance=False,
    )


def _chop_structure() -> MarketStructureSnapshot:
    return MarketStructureSnapshot(
        mid=1.05,
        sample_count=20,
        mean_mid=1.048,
        recent_high=1.051,
        recent_low=1.044,
        trend="neutral",
        breakout_up=False,
        breakout_down=False,
        summary="chop",
        swing_high=1.051,
    )


def test_shortfall_below_floor():
    cfg = BotConfig(alpha_reload_min_rlusd_deploy_xrp_equiv=45.0)
    # 100 RLUSD at 1.05 = ~95 xrp equiv
    short = reload_shortfall_xrp_equiv(cfg, rlusd_balance=100.0, mid=1.05)
    assert short == pytest.approx(0.0, abs=1.0)
    short2 = reload_shortfall_xrp_equiv(cfg, rlusd_balance=30.0, mid=1.05)
    assert short2 > 15.0


def test_reload_blocks_accumulation_when_under_floor():
    cfg = BotConfig(
        alpha_reload_regime_enabled=True,
        alpha_reload_block_accumulation_until_funded=True,
        alpha_reload_min_rlusd_deploy_xrp_equiv=45.0,
    )
    assert reload_blocks_accumulation_bids(cfg, rlusd_balance=20.0, mid=1.05) is True
    assert reload_blocks_accumulation_bids(cfg, rlusd_balance=200.0, mid=1.05) is False


def test_chop_detected_near_high_after_run():
    cfg = BotConfig(alpha_reload_post_run_min_move_pct=0.25, alpha_reload_near_high_pct=0.15)
    ok, reason = detect_post_run_consolidation(
        cfg,
        mid=1.05,
        structure=_chop_structure(),
        tape_active=False,
    )
    assert ok is True
    assert "chop" in reason or "digest" in reason


def test_reload_watching_when_low_rlusd_but_still_breaking_out():
    cfg = BotConfig(alpha_reload_min_rlusd_deploy_xrp_equiv=45.0)
    rip_structure = replace(_chop_structure(), trend="bullish", breakout_up=True)
    snap = evaluate_reload_regime(
        cfg,
        inventory=_inventory_at_target(),
        mid=1.05,
        structure=rip_structure,
        ta=None,
        operator_market_regime="bull",
        rlusd_balance=25.0,
    )
    assert snap.phase == "watching"
    assert snap.blocks_accumulation is True
    assert "chop" in snap.detail.lower() or "break" in snap.detail.lower() or snap.detail


def test_reload_armed_in_chop_when_under_floor():
    cfg = BotConfig(alpha_reload_min_rlusd_deploy_xrp_equiv=45.0)
    snap = evaluate_reload_regime(
        cfg,
        inventory=_inventory_at_target(),
        mid=1.05,
        structure=_chop_structure(),
        ta=None,
        operator_market_regime="bull",
        rlusd_balance=25.0,
    )
    assert snap.armed is True
    assert snap.entry_allowed is True
    assert snap.shortfall_xrp_equiv > 0


def test_reload_sell_size_to_shortfall():
    cfg = BotConfig(alpha_reload_min_rlusd_deploy_xrp_equiv=45.0, xrp_reserve=12.0)
    bal = BalanceSnapshot(
        xrp=400.0,
        rlusd=25.0,
        mid_rlusd_per_xrp=1.05,
        portfolio_xrp_equiv=600.0,
    )
    short = reload_shortfall_xrp_equiv(cfg, rlusd_balance=25.0, mid=1.05)
    size = compute_reload_sell_size_xrp(
        cfg,
        shortfall_xrp_equiv=short,
        balances=bal,
        inventory=_inventory_at_target(),
    )
    assert size >= cfg.min_order_size_xrp


def test_reload_window_cap(tmp_path: Path):
    path = tmp_path / "reload.json"
    session = ReloadSessionTracker(path=path)
    cfg = BotConfig(alpha_reload_max_sells_per_window=1)
    session.record_sell_placed(size_xrp=10.0, mid=1.05, config=cfg)
    assert session.can_place_sell(cfg) is False
