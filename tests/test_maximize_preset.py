"""Tests for Maximize (harvest stack) preset and stranded-powder decision path."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.hud.maximize_preset import (
    MAXIMIZE_OPERATOR_OVERRIDES,
    compare_maximize_to_unassed,
    maximize_preset_payload,
)
from alpha.types import (
    BalanceSnapshot,
    InventorySnapshot,
    OrderBookSnapshot,
    RiskSnapshot,
)
from config.settings import BotConfig


def test_maximize_preset_harvest_loop_knobs() -> None:
    payload = maximize_preset_payload()
    ov = payload["operator_overrides"]
    assert ov["inventory_target_xrp_ratio"] == 0.85
    assert ov["alpha_strength_deviation"] == 0.05
    assert ov["alpha_reload_min_rlusd_deploy_xrp_equiv"] == 40.0
    assert ov["alpha_reload_block_accumulation_until_funded"] is False
    assert ov["alpha_brackets_enabled"] is False
    assert ov["alpha_risk_per_trade_pct"] == 3.5
    assert ov["alpha_accumulation_harvest_move_24h_watch_pct"] == 3.5
    assert "harvest" in payload["description"].lower() or "Maximize" in payload["label"]


def test_maximize_vs_unassed() -> None:
    cmp = compare_maximize_to_unassed()
    diff = cmp["different_operator_keys"]
    assert diff["alpha_reload_min_rlusd_deploy_xrp_equiv"]["maximize"] == 40.0
    assert MAXIMIZE_OPERATOR_OVERRIDES["alpha_brackets_enabled"] is False


def test_stranded_powder_forces_ask_not_balanced_hold() -> None:
    from datetime import datetime, timezone

    cfg = BotConfig(
        alpha_reload_min_rlusd_deploy_xrp_equiv=40.0,
        alpha_strength_deviation=0.05,
        alpha_max_pending_sells=2,
        inventory_target_xrp_ratio=0.85,
        min_order_size_xrp=1.0,
        alpha_base_order_size_xrp=10.0,
        alpha_risk_per_trade_pct=3.0,
    )
    engine = DecisionEngine(cfg)
    inv = InventorySnapshot(
        xrp_ratio=0.99,
        target_xrp_ratio=0.85,
        deviation=0.14,
        label="xrp_heavy",
        summary="test",
        pause_bids=False,
        pause_asks=False,
        buy_blocked_imbalance=True,
        sell_blocked_imbalance=False,
    )
    risk = RiskSnapshot(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        preflight_ready=True,
        preflight_summary="ok",
        trading_allowed=True,
    )
    book = OrderBookSnapshot(
        bids=(),
        asks=(),
        best_bid=1.05,
        best_ask=1.06,
        mid=1.055,
        spread=0.01,
        spread_pct=0.1,
        fetched_utc=datetime.now(tz=timezone.utc),
    )
    bal = BalanceSnapshot(xrp=1100.0, rlusd=12.0)
    inv_mgr = MagicMock()
    inv_mgr.allows_buy.return_value = False
    inv_mgr.allows_sell.return_value = False
    inv_mgr.cap_entry_size_xrp.side_effect = lambda **kw: kw.get("size_xrp", 0) or 10.0
    engine._inventory = inv_mgr

    result = engine.evaluate(
        inventory=inv,
        risk=risk,
        book=book,
        balances=bal,
        pending_buy_count=0,
        pending_sell_count=0,
    )
    assert result.action == DecisionAction.PLACE_ASK
    assert "stranded_powder" in (result.reason or "")


def test_reload_blocks_respects_config_off() -> None:
    from datetime import datetime, timezone

    cfg = BotConfig(alpha_reload_block_accumulation_until_funded=False)
    engine = DecisionEngine(cfg)
    book = OrderBookSnapshot(
        bids=(),
        asks=(),
        best_bid=1.0,
        best_ask=1.01,
        mid=1.005,
        spread=0.01,
        spread_pct=0.1,
        fetched_utc=datetime.now(tz=timezone.utc),
    )
    bal = BalanceSnapshot(xrp=100.0, rlusd=5.0)
    assert engine._reload_blocks_accumulation(bal, book, pending_sell_count=2) is False


def test_heavy_prefers_trim_before_chase_buy() -> None:
    """P0: overweight + strength gate → place_ask, not failed bull_run bid loop."""
    from datetime import datetime, timezone

    cfg = BotConfig(
        alpha_strength_deviation=0.05,
        alpha_weakness_deviation=0.03,
        alpha_max_pending_sells=2,
        alpha_max_pending_buys=3,
        inventory_target_xrp_ratio=0.85,
        min_order_size_xrp=1.0,
        alpha_base_order_size_xrp=20.0,
        alpha_risk_per_trade_pct=3.5,
        alpha_min_edge_threshold_pct=0.01,
        alpha_sell_limit_offset_pct=0.08,
        alpha_buy_limit_offset_pct=0.14,
        alpha_ta_weight=0.0,
    )
    engine = DecisionEngine(cfg)
    inv = InventorySnapshot(
        xrp_ratio=0.93,
        target_xrp_ratio=0.85,
        deviation=0.08,
        label="xrp_heavy",
        summary="test",
        pause_bids=False,
        pause_asks=False,
        portfolio_xrp_equiv=1100.0,
        xrp_allocation_pct=93.0,
    )
    risk = RiskSnapshot(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        preflight_ready=True,
        preflight_summary="ok",
        trading_allowed=True,
    )
    book = OrderBookSnapshot(
        bids=(),
        asks=(),
        best_bid=1.05,
        best_ask=1.06,
        mid=1.055,
        spread=0.01,
        spread_pct=0.1,
        fetched_utc=datetime.now(tz=timezone.utc),
    )
    bal = BalanceSnapshot(xrp=1000.0, rlusd=80.0, mid_rlusd_per_xrp=1.055, portfolio_xrp_equiv=1100.0)
    inv_mgr = MagicMock()
    inv_mgr.allows_buy.return_value = False
    inv_mgr.allows_sell.return_value = True
    inv_mgr.cap_entry_size_xrp.side_effect = lambda **kw: max(float(kw.get("size_xrp") or 0), 10.0)
    engine._inventory = inv_mgr

    result = engine.evaluate(
        inventory=inv,
        risk=risk,
        book=book,
        balances=bal,
        pending_buy_count=0,
        pending_sell_count=0,
    )
    assert result.action == DecisionAction.PLACE_ASK
    assert "heavy_prefer_trim" in (result.reason or "") or "strength" in (result.reason or "")


def test_accumulation_budget_heals_ghost_committed(tmp_path) -> None:
    from alpha.decision.accumulation_regime import AccumulationSessionTracker

    path = tmp_path / "accumulation_session.json"
    path.write_text(
        json.dumps(
            {
                "window_start_utc": "2026-07-31T13:00:00+00:00",
                "committed_rlusd": 951.0,
                "filled_rlusd": 96.0,
                "chase_cancels": 18,
                "bids_placed": 20,
                "fills_count": 2,
            }
        ),
        encoding="utf-8",
    )
    sess = AccumulationSessionTracker(path=path)
    cfg = BotConfig(alpha_accumulation_rlusd_budget_pct=40.0, alpha_accumulation_budget_hours=24.0)
    remaining = sess.remaining_rlusd(cfg, rlusd_balance=83.0)
    # budget = 0.4*83 ≈ 33.2; ghost 951 open healed to 0 → full budget available
    assert sess.open_committed_rlusd() == 0.0
    assert remaining == pytest.approx(83.0 * 0.40, rel=1e-3)
    sess.record_bid(size_xrp=10.0, price_rlusd_per_xrp=1.0)
    assert sess.open_committed_rlusd() == 10.0
    sess.release_bid(size_xrp=10.0, price_rlusd_per_xrp=1.0, reason="test")
    assert sess.open_committed_rlusd() == 0.0
