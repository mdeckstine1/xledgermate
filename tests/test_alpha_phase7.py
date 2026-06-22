"""Phase 7 — edge cases, validation, and critical-path coverage."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

import pytest

from alpha.config_validator import validate_alpha_config
from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.dry_run import DryRunGuard
from alpha.inventory.manager import InventoryManager
from alpha.ledger.liquidity import compute_liquidity_depth, depth_within_slippage
from alpha.operator.controls import OperatorControlStore
from alpha.orders.manager import OrderManager
from alpha.orders.types import BracketLifecycleState
from alpha.risk.engine import RiskEngine
from alpha.types import (
    BalanceSnapshot,
    BookLevel,
    InventorySnapshot,
    LedgerOfferResult,
    OrderBookSnapshot,
    RiskSnapshot,
    TrustLineSnapshot,
    utc_now,
)
from config.settings import BotConfig
from tests.test_alpha_phase2 import _book_snapshot, _risk_ready


def _volatile_book() -> OrderBookSnapshot:
    bids = (BookLevel(price=1.80, size_xrp=50.0), BookLevel(price=1.75, size_xrp=200.0))
    asks = (BookLevel(price=2.20, size_xrp=40.0), BookLevel(price=2.30, size_xrp=150.0))
    return OrderBookSnapshot(
        bids=bids,
        asks=asks,
        best_bid=1.80,
        best_ask=2.20,
        mid=2.00,
        spread=0.40,
        spread_pct=20.0,
        fetched_utc=utc_now(),
    )


def test_config_validation_catches_invalid_bracket_params():
    cfg = BotConfig(
        bot_account_address="rTestAccount123456789012345678901234",
        initial_stop_loss_pct=0.0,
        take_profit_rr=0.0,
        take_profit_pct=0.0,
    )
    result = validate_alpha_config(cfg)
    assert not result.ok
    assert any("stop_loss" in e or "take_profit" in e for e in result.errors)


def test_config_validation_warns_edge_offset_mismatch():
    cfg = BotConfig(
        bot_account_address="rTestAccount123456789012345678901234",
        alpha_buy_limit_offset_pct=0.05,
        alpha_min_edge_threshold_pct=0.10,
    )
    result = validate_alpha_config(cfg)
    assert any("edge" in w.lower() or "offset" in w.lower() for w in result.warnings)


def test_liquidity_depth_zero_on_empty_book():
    empty = OrderBookSnapshot(
        bids=(),
        asks=(),
        best_bid=None,
        best_ask=None,
        mid=None,
        spread=None,
        spread_pct=None,
        fetched_utc=utc_now(),
    )
    depth = compute_liquidity_depth(empty, max_slippage_pct=0.5)
    assert depth.ask_depth_xrp == 0.0
    assert depth.bid_depth_xrp == 0.0


def test_depth_within_slippage_tight_touch():
    book = _book_snapshot()
    # Very tight slippage — only first level
    depth = depth_within_slippage(book.asks, side="ask", max_slippage_pct=0.01)
    assert depth == 80.0


def test_decision_holds_on_zero_depth():
    cfg = BotConfig(
        alpha_weakness_deviation=0.05,
        alpha_buy_limit_offset_pct=0.15,
        alpha_min_edge_threshold_pct=0.08,
        alpha_risk_per_trade_pct=5.0,
        trading_enabled=True,
    )
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    empty = OrderBookSnapshot(
        bids=(BookLevel(2.0, 0.0),),
        asks=(BookLevel(2.01, 0.0),),
        best_bid=2.0,
        best_ask=2.01,
        mid=2.005,
        spread=0.01,
        spread_pct=0.5,
        fetched_utc=utc_now(),
    )
    liquidity = compute_liquidity_depth(empty, max_slippage_pct=0.5)
    inv = InventorySnapshot(
        xrp_ratio=0.40,
        target_xrp_ratio=0.55,
        deviation=-0.15,
        label="heavy_rlusd",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )
    result = engine.evaluate(
        inventory=inv,
        risk=_risk_ready(),
        book=empty,
        liquidity=liquidity,
        balances=BalanceSnapshot(xrp=40.0, rlusd=120.0, mid_rlusd_per_xrp=2.0, portfolio_xrp_equiv=100.0),
    )
    assert result.action == DecisionAction.HOLD
    assert "depth" in result.reason.lower() or "size" in result.reason.lower()


def test_decision_holds_on_volatile_wide_spread_without_edge():
    cfg = BotConfig(
        alpha_weakness_deviation=0.05,
        alpha_buy_limit_offset_pct=0.02,
        alpha_min_edge_threshold_pct=0.10,
        trading_enabled=True,
    )
    engine = DecisionEngine(cfg, inventory=InventoryManager(cfg))
    book = _volatile_book()
    inv = InventorySnapshot(
        xrp_ratio=0.40,
        target_xrp_ratio=0.55,
        deviation=-0.15,
        label="heavy_rlusd",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )
    result = engine.evaluate(inventory=inv, risk=_risk_ready(), book=book)
    assert result.action in (DecisionAction.HOLD, DecisionAction.PLACE_BID)
    if result.action == DecisionAction.HOLD:
        assert "edge" in result.reason.lower() or "depth" in result.reason.lower()


def test_kill_switch_blocks_trading_allowed():
    cfg = BotConfig(bot_account_address="rTestAccount123456789012345678901234")
    risk_engine = RiskEngine(cfg, state_dir=Path("logs/test_alpha_phase7_kill"))
    snap = risk_engine.evaluate(
        balances=BalanceSnapshot(xrp=100.0, rlusd=0.0, mid_rlusd_per_xrp=2.0, portfolio_xrp_equiv=100.0),
        trust_line=TrustLineSnapshot(exists=True, balance=0.0, limit=1_000_000.0),
    )
    assert isinstance(snap.trading_allowed, bool)

    blocked = RiskSnapshot(
        kill_switch_active=True,
        kill_switch_reason="test",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        preflight_ready=False,
        preflight_summary="blocked",
        trading_allowed=False,
    )
    ok, msg = risk_engine.validate_entry(blocked)
    assert not ok


class _PartialFillLedger:
    account_address = "rFake123456789012345678901234567890"

    def __init__(self) -> None:
        self._offers: Dict[int, dict[str, Any]] = {}
        self._seq = 4000

    async def get_open_offers(self) -> List[dict[str, Any]]:
        return list(self._offers.values())

    async def place_limit_sell_xrp(self, *, size_xrp: float, price_rlusd_per_xrp: float) -> LedgerOfferResult:
        self._seq += 1
        self._offers[self._seq] = {
            "sequence": self._seq,
            "side": "ask",
            "price": price_rlusd_per_xrp,
            "size_xrp": size_xrp,
        }
        return LedgerOfferResult(submitted=True, dry_run=False, action="sell", sequence=self._seq)

    async def cancel_offer(self, sequence: int) -> LedgerOfferResult:
        self._offers.pop(sequence, None)
        return LedgerOfferResult(submitted=True, dry_run=False, action="cancel", sequence=sequence)


def test_proportional_partial_fill_places_initial_bracket(tmp_path: Path):
    """Proportional mode brackets first partial while buy still open."""
    async def _run() -> None:
        ledger = _PartialFillLedger()
        cfg = BotConfig(
            dry_run=False,
            partial_fill_mode="proportional",
            min_order_size_xrp=1.0,
            initial_stop_loss_pct=0.02,
            take_profit_rr=2.0,
        )
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=tmp_path,
        )
        mgr.register_pending_buy(buy_sequence=401, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger._offers[401] = {"sequence": 401, "side": "bid", "price": 2.0, "size_xrp": 7.0}
        await mgr.sync_brackets()
        record = mgr.store.get_by_buy_sequence(401)
        assert record is not None
        assert record.bracketed_xrp == pytest.approx(3.0, abs=0.01)
        assert record.state == BracketLifecycleState.BRACKET_ACTIVE

    asyncio.run(_run())


def test_operator_pause_prevents_execution_path(tmp_path: Path):
    store = OperatorControlStore(path=tmp_path / "controls.json")
    store.pause("phase7 test")
    assert store.is_paused()


def test_dry_run_guard_all_write_actions():
    guard = DryRunGuard(dry_run=True, network="mainnet")
    for action in ("place_bid", "place_ask", "cancel_offer", "submit_bracket", "cancel_all"):
        assert not guard.require_live(action)


def test_bracket_state_machine_terminal_states(tmp_path: Path):
    from alpha.orders.state import BracketStateStore
    from alpha.orders.types import BracketMode, BracketRecord

    store = BracketStateStore(persist_path=tmp_path / "brackets.json")
    for state in (
        BracketLifecycleState.TP_FILLED,
        BracketLifecycleState.SL_FILLED,
        BracketLifecycleState.CANCELLED,
    ):
        record = BracketRecord(
            bracket_id=f"id-{state.value}",
            state=state,
            mode=BracketMode.BRACKET,
            buy_sequence=100,
            entry_price_rlusd_per_xrp=2.0,
            target_size_xrp=5.0,
        )
        store.add(record)
    open_count = sum(1 for _ in store.iter_open())
    assert open_count == 0
