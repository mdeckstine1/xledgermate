"""Tests for Trading Bot Alpha Phase 2 — ledger depth, dry-run gates, decisions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, List, Optional

from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.dry_run import DryRunGuard
from alpha.ledger.liquidity import compute_liquidity_depth, depth_within_slippage
from alpha.ledger.xrpl_adapter import XrplLedgerAdapter
from alpha.types import (
    BalanceSnapshot,
    BookLevel,
    InventorySnapshot,
    LedgerOfferResult,
    LiquidityDepth,
    OrderBookSnapshot,
    RiskSnapshot,
    TrustLineSnapshot,
    utc_now,
)
from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig


def _book_snapshot() -> OrderBookSnapshot:
    bids = (
        BookLevel(price=2.00, size_xrp=100.0),
        BookLevel(price=1.99, size_xrp=200.0),
        BookLevel(price=1.95, size_xrp=500.0),
    )
    asks = (
        BookLevel(price=2.01, size_xrp=80.0),
        BookLevel(price=2.02, size_xrp=120.0),
        BookLevel(price=2.05, size_xrp=300.0),
    )
    return OrderBookSnapshot(
        bids=bids,
        asks=asks,
        best_bid=2.00,
        best_ask=2.01,
        mid=2.005,
        spread=0.01,
        spread_pct=0.4988,
        fetched_utc=utc_now(),
    )


def test_depth_within_slippage_ask_side():
    book = _book_snapshot()
    # 0.5% slippage from 2.01 -> ceiling 2.02005; includes first two ask levels
    depth = depth_within_slippage(book.asks, side="ask", max_slippage_pct=0.5)
    assert depth == 200.0


def test_depth_within_slippage_bid_side():
    book = _book_snapshot()
    depth = depth_within_slippage(book.bids, side="bid", max_slippage_pct=0.5)
    assert depth == 300.0


def test_compute_liquidity_depth_snapshot():
    book = _book_snapshot()
    depth = compute_liquidity_depth(book, max_slippage_pct=0.5)
    assert depth.ask_depth_xrp == 200.0
    assert depth.bid_depth_xrp == 300.0
    assert depth.mid == 2.005


class _RecordingConnector:
    account_address = "rTestAccount123456789012345678901234"

    def __init__(self) -> None:
        self.place_calls: List[tuple[str, float, float]] = []
        self.cancel_calls: List[int] = []

    async def place_quote(self, intent: Any) -> str:
        self.place_calls.append((intent.side, intent.size_xrp, intent.price))
        return "FAKE_HASH"

    async def cancel_offer(self, sequence: int) -> str:
        self.cancel_calls.append(sequence)
        return "FAKE_CANCEL_HASH"


def _adapter(dry_run: bool) -> XrplLedgerAdapter:
    cfg = BotConfig(
        bot_account_address="rTestAccount123456789012345678901234",
        dry_run=dry_run,
        testnet=False,
        rlusd_issuer_mainnet="rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De",
    )
    connector = XRPLConnector(
        account_address=cfg.bot_account_address,
        secret="sEdFakeSecretForTestsOnly123456789012345",
        rlusd_issuer=cfg.resolved_rlusd_issuer(),
        rlusd_currency=cfg.rlusd_currency,
        network=XRPLNetworkConfig(json_rpc_url="https://s1.ripple.com:51234"),
    )
    adapter = XrplLedgerAdapter(
        connector,
        config=cfg,
        dry_run_guard=DryRunGuard(dry_run=dry_run, network="mainnet"),
        ws_session=None,
    )
    adapter._connector = _RecordingConnector()  # type: ignore[assignment]
    return adapter


def test_dry_run_blocks_place_and_cancel():
    async def _run() -> None:
        adapter = _adapter(dry_run=True)
        buy = await adapter.place_limit_buy_xrp(size_xrp=10.0, price_rlusd_per_xrp=2.0)
        sell = await adapter.place_limit_sell_xrp(size_xrp=5.0, price_rlusd_per_xrp=2.1)
        cancel = await adapter.cancel_offer(42)
        assert buy.submitted is False and buy.dry_run is True
        assert sell.submitted is False and sell.dry_run is True
        assert cancel.submitted is False and cancel.dry_run is True
        rec = adapter._connector
        assert isinstance(rec, _RecordingConnector)
        assert rec.place_calls == []
        assert rec.cancel_calls == []

    asyncio.run(_run())


def test_live_place_and_cancel_submits():
    async def _run() -> None:
        adapter = _adapter(dry_run=False)
        buy = await adapter.place_limit_buy_xrp(size_xrp=10.0, price_rlusd_per_xrp=2.0)
        cancel = await adapter.cancel_offer(7)
        assert buy.submitted is True
        assert cancel.submitted is True
        rec = adapter._connector
        assert isinstance(rec, _RecordingConnector)
        assert rec.place_calls == [("bid", 10.0, 2.0)]
        assert rec.cancel_calls == [7]

    asyncio.run(_run())


def _risk_ready() -> RiskSnapshot:
    return RiskSnapshot(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        preflight_ready=True,
        preflight_summary="OK",
    )


def test_decision_bid_capped_by_ask_depth():
    cfg = BotConfig(
        alpha_base_order_size_xrp=500.0,
        alpha_weakness_deviation=0.05,
        min_order_size_xrp=1.0,
        max_leg_size_pct_of_capital=1.0,
        risk_capital_xrp=10_000.0,
    )
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    inv = InventorySnapshot(
        xrp_ratio=0.40,
        target_xrp_ratio=0.55,
        deviation=-0.15,
        label="heavy_rlusd",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )
    result = engine.evaluate(inventory=inv, risk=_risk_ready(), book=book, liquidity=liquidity)
    assert result.action == DecisionAction.PLACE_BID
    assert result.size_xrp == 200.0


def test_decision_hold_when_balanced():
    cfg = BotConfig(alpha_weakness_deviation=0.05, alpha_strength_deviation=0.05)
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    inv = InventorySnapshot(
        xrp_ratio=0.55,
        target_xrp_ratio=0.55,
        deviation=0.0,
        label="balanced",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )
    result = engine.evaluate(inventory=inv, risk=_risk_ready(), book=book)
    assert result.action == DecisionAction.HOLD


def _xrp_heavy_inventory() -> InventorySnapshot:
    return InventorySnapshot(
        xrp_ratio=0.70,
        target_xrp_ratio=0.55,
        deviation=0.15,
        label="xrp_heavy",
        pause_bids=False,
        pause_asks=False,
        summary="test",
    )


def test_decision_ask_capped_by_bid_depth():
    cfg = BotConfig(
        alpha_base_order_size_xrp=500.0,
        alpha_strength_deviation=0.05,
        alpha_sell_limit_offset_pct=0.15,
        alpha_min_edge_threshold_pct=0.08,
        min_order_size_xrp=1.0,
        max_leg_size_pct_of_capital=1.0,
        risk_capital_xrp=10_000.0,
    )
    engine = DecisionEngine(cfg)
    book = _book_snapshot()
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    result = engine.evaluate(
        inventory=_xrp_heavy_inventory(),
        risk=_risk_ready(),
        book=book,
        liquidity=liquidity,
    )
    assert result.action == DecisionAction.PLACE_ASK
    assert result.size_xrp == 300.0


def test_decision_insufficient_bid_depth_holds():
    cfg = BotConfig(
        alpha_strength_deviation=0.05,
        alpha_sell_limit_offset_pct=0.15,
        alpha_min_edge_threshold_pct=0.08,
        min_order_size_xrp=50.0,
    )
    engine = DecisionEngine(cfg)
    book = OrderBookSnapshot(
        bids=(BookLevel(price=2.00, size_xrp=10.0),),
        asks=(BookLevel(price=2.01, size_xrp=100.0),),
        best_bid=2.00,
        best_ask=2.01,
        mid=2.005,
        spread=0.01,
        spread_pct=0.5,
        fetched_utc=utc_now(),
    )
    liquidity = compute_liquidity_depth(book, max_slippage_pct=0.5)
    result = engine.evaluate(
        inventory=_xrp_heavy_inventory(),
        risk=_risk_ready(),
        book=book,
        liquidity=liquidity,
    )
    assert result.action == DecisionAction.HOLD
    assert "insufficient_bid_depth" in result.reason
