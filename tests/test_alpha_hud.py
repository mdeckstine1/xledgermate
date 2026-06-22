"""Tests for Alpha operator HUD state export."""

from __future__ import annotations

from datetime import datetime, timezone

from alpha.decision.engine import DecisionAction, DecisionResult
from alpha.hud.state_export import build_hud_state
from alpha.operator.controls import OperatorControls
from alpha.types import (
    BalanceSnapshot,
    BracketStatusSummary,
    InventorySnapshot,
    OperatorSnapshot,
    RiskSnapshot,
    TrustLineSnapshot,
)


def test_build_hud_state_minimal():
    snap = OperatorSnapshot(
        generated_utc=datetime.now(tz=timezone.utc),
        alpha_version="1.0.0",
        network="mainnet",
        dry_run=True,
        trading_enabled=True,
        account_address="rTest123",
        balances=BalanceSnapshot(xrp=100.0, rlusd=50.0, mid_rlusd_per_xrp=2.0, portfolio_xrp_equiv=125.0),
        trust_line=TrustLineSnapshot(exists=True, balance=50.0),
        inventory=InventorySnapshot(
            xrp_ratio=0.55,
            target_xrp_ratio=0.55,
            deviation=0.0,
            label="balanced",
            pause_bids=False,
            pause_asks=False,
            summary="ok",
        ),
        risk=RiskSnapshot(
            kill_switch_active=False,
            kill_switch_reason="",
            drawdown_pct=0.0,
            max_drawdown_pct=10.0,
            preflight_ready=True,
            preflight_summary="ok",
        ),
    )
    decision = DecisionResult(action=DecisionAction.HOLD, reason="balanced")
    state = build_hud_state(
        snapshot=snap,
        decision=decision,
        execution=None,
        recent_events=(),
        bracket_summary=BracketStatusSummary(),
        brackets=(),
        open_offers=[],
        activity=[],
        controls=OperatorControls(),
    )
    assert state["hud_kind"] == "alpha"
    assert state["decision"]["action"] == "hold"
    assert state["mid"] == 2.0
    assert "chart" in state
    assert "candles" in state["chart"]
    assert "indicators" in state["chart"]
