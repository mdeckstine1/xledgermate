"""Tests for Maximize (harvest stack) preset and stranded-powder decision path."""

from __future__ import annotations

from unittest.mock import MagicMock

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
