"""Tests for Trading Bot Alpha Phase 4 — entry logic and integration."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, Dict, List

from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.dry_run import DryRunGuard
from alpha.orders.manager import OrderManager
from alpha.runtime.executor import EntryExecutor
from alpha.types import (
    BalanceSnapshot,
    InventorySnapshot,
    LedgerOfferResult,
    OperatorSnapshot,
    RiskSnapshot,
    TrustLineSnapshot,
    utc_now,
)
from config.settings import BotConfig
from alpha.ledger.liquidity import compute_liquidity_depth
from tests.test_alpha_phase2 import _book_snapshot, _risk_ready


def _entry_config(**overrides: Any) -> BotConfig:
    ta_enabled = overrides.pop("ta_enabled", False)
    base = BotConfig(
        trading_enabled=True,
        alpha_weakness_deviation=0.05,
        alpha_buy_limit_offset_pct=0.15,
        alpha_min_edge_threshold_pct=0.08,
        alpha_max_inventory_imbalance_pct=0.10,
        alpha_max_pending_buys=1,
        alpha_risk_per_trade_pct=0.5,
        min_order_size_xrp=1.0,
        max_leg_size_pct_of_capital=1.0,
        risk_capital_xrp=10_000.0,
        alpha_base_order_size_xrp=50.0,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return replace(
        base,
        alpha_technical_analysis=replace(base.alpha_technical_analysis, enabled=ta_enabled),
    )


def _weak_inventory() -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=0.40,
        target_xrp_ratio=0.55,
        deviation=-0.15,
        label="heavy_rlusd",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )


def _operator(portfolio: float = 10_000.0) -> OperatorSnapshot:
    return OperatorSnapshot(
        generated_utc=utc_now(),
        alpha_version="1.0.0",
        network="mainnet",
        dry_run=True,
        trading_enabled=True,
        account_address="rTestAccount123456789012345678901234",
        balances=BalanceSnapshot(
            xrp=4000.0,
            rlusd=12_000.0,
            mid_rlusd_per_xrp=2.0,
            portfolio_xrp_equiv=portfolio,
        ),
        trust_line=TrustLineSnapshot(exists=True),
        inventory=_weak_inventory(),
        risk=_risk_ready(),
    )


def test_buy_signal_requires_edge_threshold():
    cfg = _entry_config(alpha_buy_limit_offset_pct=0.05, alpha_min_edge_threshold_pct=0.10)
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    result = engine.evaluate(
        inventory=_weak_inventory(),
        risk=_risk_ready(),
        book=book,
        liquidity=liquidity,
        operator=_operator(),
    )
    assert result.action == DecisionAction.HOLD
    assert "edge_below_threshold" in result.reason


def test_buy_blocked_when_inventory_too_xrp_heavy():
    cfg = _entry_config()
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    inv = InventorySnapshot(
        xrp_ratio=0.70,
        target_xrp_ratio=0.55,
        deviation=0.15,
        label="xrp_heavy",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )
    result = engine.evaluate(inventory=inv, risk=_risk_ready(), book=book, operator=_operator())
    assert result.action != DecisionAction.PLACE_BID
    assert result.action == DecisionAction.PLACE_ASK


def test_buy_signal_with_edge_and_weakness():
    cfg = _entry_config()
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    result = engine.evaluate(
        inventory=_weak_inventory(),
        risk=_risk_ready(),
        book=book,
        liquidity=liquidity,
        operator=_operator(portfolio=10_000.0),
    )
    assert result.action == DecisionAction.PLACE_BID
    assert result.size_xrp is not None and result.size_xrp > 0
    assert result.edge_pct is not None and result.edge_pct >= cfg.alpha_min_edge_threshold_pct
    mid = book.mid
    assert mid is not None
    expected_price = round(mid * (1.0 - cfg.alpha_buy_limit_offset_pct / 100.0), 6)
    assert result.price_rlusd_per_xrp == expected_price


def test_risk_per_trade_caps_size():
    cfg = _entry_config(alpha_risk_per_trade_pct=0.5, alpha_base_order_size_xrp=500.0)
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    result = engine.evaluate(
        inventory=_weak_inventory(),
        risk=_risk_ready(),
        book=book,
        liquidity=liquidity,
        operator=_operator(portfolio=10_000.0),
    )
    assert result.action == DecisionAction.PLACE_BID
    assert result.size_xrp == 50.0  # 0.5% of 10k portfolio


class _IntegrationLedger:
    account_address = "rFake123456789012345678901234567890"

    def __init__(self) -> None:
        self._offers: Dict[int, dict[str, Any]] = {}
        self._next_seq = 2000

    async def connect(self) -> None:
        return None

    async def get_open_offers(self) -> List[dict[str, Any]]:
        return list(self._offers.values())

    async def place_limit_buy_xrp(self, *, size_xrp: float, price_rlusd_per_xrp: float) -> LedgerOfferResult:
        self._next_seq += 1
        seq = self._next_seq
        self._offers[seq] = {
            "sequence": seq,
            "side": "bid",
            "price": price_rlusd_per_xrp,
            "size_xrp": size_xrp,
        }
        return LedgerOfferResult(submitted=True, dry_run=False, action="buy", sequence=seq)

    async def place_limit_sell_xrp(self, **kwargs: Any) -> LedgerOfferResult:
        self._next_seq += 1
        seq = self._next_seq
        self._offers[seq] = {"sequence": seq, "side": "ask", **kwargs}
        return LedgerOfferResult(submitted=True, dry_run=False, action="sell", sequence=seq)

    async def cancel_offer(self, sequence: int) -> LedgerOfferResult:
        self._offers.pop(sequence, None)
        return LedgerOfferResult(submitted=True, dry_run=False, action="cancel", sequence=sequence)

    async def close(self) -> None:
        return None


def test_executor_dry_run_logs_without_register():
    async def _run() -> None:
        ledger = _IntegrationLedger()
        cfg = _entry_config(dry_run=True)
        guard = DryRunGuard(dry_run=True, network="mainnet")
        orders = OrderManager(ledger, guard, cfg)
        executor = EntryExecutor(ledger, orders, guard, cfg)
        from alpha.decision.engine import DecisionResult

        decision = DecisionResult(
            action=DecisionAction.PLACE_BID,
            reason="test",
            size_xrp=10.0,
            price_rlusd_per_xrp=1.98,
        )
        result = await executor.execute(decision)
        assert not result.executed
        assert result.dry_run
        assert orders.pending_buy_count() == 0
        assert len(await ledger.get_open_offers()) == 0

    asyncio.run(_run())


def test_executor_registers_buy_and_bracket_on_fill():
    async def _run() -> None:
        ledger = _IntegrationLedger()
        cfg = _entry_config(dry_run=False)
        guard = DryRunGuard(dry_run=False, network="mainnet")
        orders = OrderManager(ledger, guard, cfg)
        executor = EntryExecutor(ledger, orders, guard, cfg)
        from alpha.decision.engine import DecisionResult

        decision = DecisionResult(
            action=DecisionAction.PLACE_BID,
            reason="test",
            size_xrp=10.0,
            price_rlusd_per_xrp=2.0,
        )
        entry = await executor.execute(decision)
        assert entry.executed
        assert entry.buy_sequence is not None
        assert orders.pending_buy_count() == 1

        ledger._offers.pop(entry.buy_sequence)
        await orders.sync_brackets()
        record = orders.store.get(entry.bracket_id or "")
        assert record is not None
        assert record.tp_leg is not None and record.sl_leg is not None

    asyncio.run(_run())


def _strong_inventory() -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=0.70,
        target_xrp_ratio=0.55,
        deviation=0.15,
        label="xrp_heavy",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )


def test_sell_signal_requires_edge_threshold():
    cfg = _entry_config(alpha_sell_limit_offset_pct=0.05, alpha_min_edge_threshold_pct=0.10)
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    result = engine.evaluate(
        inventory=_strong_inventory(),
        risk=_risk_ready(),
        book=book,
        liquidity=liquidity,
        operator=_operator(),
    )
    assert result.action == DecisionAction.HOLD
    assert "edge" in result.reason.lower()


def test_sell_signal_with_edge_and_strength():
    cfg = _entry_config(alpha_sell_limit_offset_pct=0.15)
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    result = engine.evaluate(
        inventory=_strong_inventory(),
        risk=_risk_ready(),
        book=book,
        liquidity=liquidity,
        operator=_operator(portfolio=10_000.0),
    )
    assert result.action == DecisionAction.PLACE_ASK
    assert result.size_xrp is not None and result.size_xrp > 0
    assert result.edge_pct is not None and result.edge_pct >= cfg.alpha_min_edge_threshold_pct
    mid = book.mid
    assert mid is not None
    expected_price = round(mid * (1.0 + cfg.alpha_sell_limit_offset_pct / 100.0), 6)
    assert result.price_rlusd_per_xrp == expected_price


def test_max_pending_buys_does_not_block_sell():
    cfg = _entry_config(alpha_max_pending_buys=1)
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    result = engine.evaluate(
        inventory=_strong_inventory(),
        risk=_risk_ready(),
        book=book,
        liquidity=liquidity,
        pending_buy_count=1,
        operator=_operator(),
    )
    assert result.action == DecisionAction.PLACE_ASK


def test_executor_sell_dry_run_logs_without_ledger_write():
    async def _run() -> None:
        ledger = _IntegrationLedger()
        cfg = _entry_config(dry_run=True)
        guard = DryRunGuard(dry_run=True, network="mainnet")
        orders = OrderManager(ledger, guard, cfg)
        executor = EntryExecutor(ledger, orders, guard, cfg)
        from alpha.decision.engine import DecisionResult

        decision = DecisionResult(
            action=DecisionAction.PLACE_ASK,
            reason="test",
            size_xrp=10.0,
            price_rlusd_per_xrp=2.05,
            edge_pct=0.15,
        )
        result = await executor.execute(decision)
        assert not result.executed
        assert result.dry_run
        assert result.action == "place_ask"
        assert len(await ledger.get_open_offers()) == 0

    asyncio.run(_run())


def test_executor_places_strength_sell_live(tmp_path):
    async def _run() -> None:
        ledger = _IntegrationLedger()
        cfg = _entry_config(dry_run=False)
        guard = DryRunGuard(dry_run=False, network="mainnet")
        orders = OrderManager(ledger, guard, cfg, state_dir=tmp_path)
        executor = EntryExecutor(ledger, orders, guard, cfg)
        from alpha.decision.engine import DecisionResult

        decision = DecisionResult(
            action=DecisionAction.PLACE_ASK,
            reason="test",
            size_xrp=10.0,
            price_rlusd_per_xrp=2.05,
            edge_pct=0.15,
        )
        result = await executor.execute(decision)
        assert result.executed
        offers = await ledger.get_open_offers()
        assert len(offers) == 1
        assert offers[0]["side"] == "ask"
        assert orders.count_strength_sells(offers) == 1

    asyncio.run(_run())
