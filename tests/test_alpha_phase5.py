"""Tests for Trading Bot Alpha Phase 5 — risk, inventory, reporting integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.inventory.manager import InventoryManager
from alpha.reporting.service import format_rich_report
from alpha.risk.engine import RiskEngine
from alpha.risk.session import SessionPnlTracker
from alpha.types import (
    BalanceSnapshot,
    BracketStatusSummary,
    CycleReportContext,
    InventorySnapshot,
    OperatorSnapshot,
    RiskSnapshot,
    TrustLineSnapshot,
)
from config.settings import BotConfig


def _risk_ready(**overrides: Any) -> RiskSnapshot:
    base = dict(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        preflight_ready=True,
        preflight_summary="OK",
        trading_allowed=True,
    )
    base.update(overrides)
    return RiskSnapshot(**base)


def test_inventory_allocation_pct():
    cfg = BotConfig(inventory_target_xrp_ratio=0.55, alpha_max_inventory_imbalance_pct=0.10)
    mgr = InventoryManager(cfg)
    snap = mgr.snapshot(
        BalanceSnapshot(xrp=55.0, rlusd=90.0, mid_rlusd_per_xrp=2.0, portfolio_xrp_equiv=100.0)
    )
    assert abs(snap.xrp_allocation_pct - 55.0) < 0.5
    assert abs(snap.rlusd_allocation_pct - 45.0) < 0.5
    assert not snap.buy_blocked_imbalance


def test_inventory_buy_blocked_when_xrp_heavy():
    cfg = BotConfig(inventory_target_xrp_ratio=0.55, alpha_max_inventory_imbalance_pct=0.08)
    mgr = InventoryManager(cfg)
    snap = mgr.snapshot(
        BalanceSnapshot(xrp=70.0, rlusd=60.0, mid_rlusd_per_xrp=2.0, portfolio_xrp_equiv=100.0)
    )
    assert snap.buy_blocked_imbalance
    assert not mgr.allows_buy(snap)


def test_risk_validate_edge():
    cfg = BotConfig(alpha_min_edge_threshold_pct=0.10)
    risk_engine = RiskEngine(cfg, state_dir=Path("logs/test_alpha_phase5"))
    ok, _ = risk_engine.validate_edge(0.15)
    assert ok
    ok, msg = risk_engine.validate_edge(0.05)
    assert not ok
    assert "edge" in msg


def test_session_pnl_tracker(tmp_path: Path):
    path = tmp_path / "session.json"
    tracker = SessionPnlTracker(path=path)
    pnl = tracker.update(xrp=100.0, rlusd=200.0, mid_rlusd_per_xrp=2.0)
    assert pnl == 0.0
    pnl2 = tracker.update(xrp=110.0, rlusd=200.0, mid_rlusd_per_xrp=2.0)
    assert pnl2 == 10.0


def test_rich_report_includes_brackets_and_pnl():
    snap = OperatorSnapshot(
        generated_utc=datetime.now(tz=timezone.utc),
        alpha_version="1.0.0",
        network="mainnet",
        dry_run=True,
        trading_enabled=True,
        account_address="rTestAccount123456789012345678901234",
        balances=BalanceSnapshot(xrp=100.0, rlusd=200.0, mid_rlusd_per_xrp=2.0, portfolio_xrp_equiv=200.0),
        trust_line=TrustLineSnapshot(exists=True),
        inventory=InventorySnapshot(
            xrp_ratio=0.5,
            target_xrp_ratio=0.55,
            deviation=-0.05,
            label="balanced",
            pause_bids=False,
            pause_asks=False,
            summary="test",
            xrp_allocation_pct=50.0,
            rlusd_allocation_pct=50.0,
        ),
        risk=_risk_ready(session_pnl_xrp=1.5, alerts=["mainnet — real funds"]),
    )
    ctx = CycleReportContext(
        snapshot=snap,
        bracket_summary=BracketStatusSummary(pending_buys=1, active_fixed=2),
        decision_action="place_bid",
        decision_reason="weakness",
        execution_summary="dry_run would place_bid",
        open_offers_count=3,
    )
    text = format_rich_report(ctx)
    assert "Session P&L" in text
    assert "Pending buys: 1" in text
    assert "place_bid" in text
    assert "DRY-RUN" in text


def test_decision_uses_inventory_manager():
    cfg = BotConfig(
        alpha_weakness_deviation=0.05,
        alpha_buy_limit_offset_pct=0.15,
        alpha_min_edge_threshold_pct=0.08,
        alpha_risk_per_trade_pct=5.0,
        alpha_base_order_size_xrp=50.0,
        min_order_size_xrp=1.0,
        max_leg_size_pct_of_capital=1.0,
        trading_enabled=True,
    )
    inv_mgr = InventoryManager(cfg)
    engine = DecisionEngine(cfg, inventory=inv_mgr)
    from alpha.ledger.liquidity import compute_liquidity_depth
    from tests.test_alpha_phase2 import _book_snapshot

    book = _book_snapshot()
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    balances = BalanceSnapshot(xrp=40.0, rlusd=120.0, mid_rlusd_per_xrp=2.0, portfolio_xrp_equiv=100.0)
    inv = inv_mgr.snapshot(balances)
    result = engine.evaluate(
        inventory=inv,
        risk=_risk_ready(),
        book=book,
        liquidity=liquidity,
        balances=balances,
    )
    assert result.action == DecisionAction.PLACE_BID
