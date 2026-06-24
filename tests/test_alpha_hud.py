"""Tests for Alpha operator HUD state export."""

from __future__ import annotations

from datetime import datetime, timezone

from alpha.decision.engine import DecisionAction, DecisionResult
from alpha.hud.state_export import _bracket_row, build_hud_state, patch_runtime_book_quote, write_alpha_runtime_state
from alpha.operator.controls import OperatorControls
from alpha.orders.types import BracketLifecycleState, BracketMode, BracketRecord
from alpha.types import (
    BalanceSnapshot,
    BracketStatusSummary,
    InventorySnapshot,
    OperatorSnapshot,
    OrderBookSnapshot,
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
    assert "mids" in state["chart"]
    assert "chart_interval_options" in state["chart"]
    assert state["chart"]["max_candles"] == 96
    assert "indicators" in state["chart"]
    assert "realized_pnl_24h" in state
    assert state["realized_pnl_24h"]["window_hours"] == 24.0


def test_bracket_row_includes_size_and_rlusd():
    record = BracketRecord(
        bracket_id="abc12345-uuid-full",
        state=BracketLifecycleState.PENDING_BUY,
        mode=BracketMode.BRACKET,
        buy_sequence=1,
        entry_price_rlusd_per_xrp=1.10,
        target_size_xrp=50.0,
    )
    row = _bracket_row(record)
    assert row["size_xrp"] == 50.0
    assert row["committed_rlusd"] == 55.0
    assert row["size_label"] == "order"
    assert row["can_cancel"] is True
    assert row["can_edit_entry"] is True


def test_patch_runtime_book_quote_updates_mid(tmp_path):
    path = tmp_path / "alpha_runtime_state.json"
    write_alpha_runtime_state(
        path,
        {
            "mid": 1.09,
            "updated_utc": "2026-01-01T00:00:00+00:00",
            "market_conditions": {"mid": 1.09, "spread_pct": 0.1},
        },
    )
    book = OrderBookSnapshot(
        bids=(),
        asks=(),
        best_bid=1.095,
        best_ask=1.097,
        mid=1.096,
        spread=0.002,
        spread_pct=0.18,
        fetched_utc=datetime.now(tz=timezone.utc),
    )
    assert patch_runtime_book_quote(path, book) is True
    data = __import__("json").loads(path.read_text(encoding="utf-8"))
    assert data["mid"] == 1.096
    assert data["book"]["mid"] == 1.096
    assert data["market_conditions"]["mid"] == 1.096
    assert data["book_updated_utc"]
    assert data["updated_utc"] == "2026-01-01T00:00:00+00:00"
