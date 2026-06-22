"""Tests for Trading Bot Alpha foundation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, List

from alpha.config_validator import validate_alpha_config
from alpha.decision.engine import DecisionAction, DecisionEngine
from alpha.dry_run import DryRunGuard
from alpha.inventory.manager import InventoryManager
from alpha.orders.manager import OrderManager
from alpha.reporting.service import format_operator_report
from alpha.types import (
    BalanceSnapshot,
    InventorySnapshot,
    OperatorSnapshot,
    RiskSnapshot,
    TrustLineSnapshot,
)
from config.settings import BotConfig


def _minimal_config(**overrides: Any) -> BotConfig:
    base = BotConfig(
        bot_account_address="rTestAccount123456789012345678901234",
        dry_run=True,
        testnet=False,
        rlusd_issuer_mainnet="rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De",
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_validate_alpha_config_requires_address():
    cfg = _minimal_config(bot_account_address="")
    result = validate_alpha_config(cfg)
    assert not result.ok
    assert any("bot_account_address" in e for e in result.errors)


def test_validate_alpha_config_live_requires_secret():
    cfg = _minimal_config(dry_run=False, bot_secret_key="")
    result = validate_alpha_config(cfg)
    assert not result.ok
    assert any("bot_secret_key" in e for e in result.errors)


def test_dry_run_guard_blocks_live_actions():
    guard = DryRunGuard(dry_run=True, network="mainnet")
    assert not guard.require_live("submit_bracket")
    assert not guard.live_trading_allowed


class _FakeLedger:
    account_address = "rFake123456789012345678901234567890"

    async def connect(self) -> None:
        return None

    async def get_balances(self) -> BalanceSnapshot:
        return BalanceSnapshot(xrp=100.0, rlusd=50.0, mid_rlusd_per_xrp=2.0, portfolio_xrp_equiv=125.0)

    async def get_trust_line(self) -> TrustLineSnapshot:
        return TrustLineSnapshot(exists=True, balance=50.0, limit=1_000_000.0)

    async def get_order_book(self, *, limit: int = 40):
        from alpha.types import BookLevel, OrderBookSnapshot, utc_now

        return OrderBookSnapshot(
            bids=(BookLevel(2.0, 100.0),),
            asks=(BookLevel(2.01, 100.0),),
            best_bid=2.0,
            best_ask=2.01,
            mid=2.005,
            spread=0.01,
            spread_pct=0.5,
            fetched_utc=utc_now(),
        )

    async def get_liquidity_depth(self, max_slippage_pct: float):
        from alpha.ledger.liquidity import compute_liquidity_depth

        book = await self.get_order_book()
        return compute_liquidity_depth(book, max_slippage_pct=max_slippage_pct)

    async def get_account_snapshot(self):
        from alpha.types import AccountSnapshot

        balances = await self.get_balances()
        trust = await self.get_trust_line()
        book = await self.get_order_book()
        return AccountSnapshot(
            xrp=balances.xrp,
            rlusd=balances.rlusd,
            mid_rlusd_per_xrp=balances.mid_rlusd_per_xrp,
            portfolio_xrp_equiv=balances.portfolio_xrp_equiv,
            trust_line=trust,
            book=book,
        )

    async def get_open_offers(self) -> List[dict[str, Any]]:
        return []

    async def place_limit_buy_xrp(self, *, size_xrp: float, price_rlusd_per_xrp: float):
        from alpha.types import LedgerOfferResult

        return LedgerOfferResult(submitted=False, dry_run=True, action="test")

    async def place_limit_sell_xrp(self, *, size_xrp: float, price_rlusd_per_xrp: float):
        from alpha.types import LedgerOfferResult

        return LedgerOfferResult(submitted=False, dry_run=True, action="test")

    async def cancel_offer(self, sequence: int):
        from alpha.types import LedgerOfferResult

        return LedgerOfferResult(submitted=False, dry_run=True, action="test", sequence=sequence)

    async def close(self) -> None:
        return None


def test_order_manager_sync_respects_dry_run():
    async def _run() -> None:
        cfg = _minimal_config()
        guard = DryRunGuard(dry_run=True, network="mainnet")
        mgr = OrderManager(_FakeLedger(), guard, cfg)
        state = await mgr.sync_state()
        assert state.open_offers == []
        assert not await mgr.cancel_all()

    asyncio.run(_run())


def test_inventory_manager_balanced_label():
    cfg = _minimal_config(inventory_target_xrp_ratio=0.55)
    mgr = InventoryManager(cfg)
    snap = mgr.snapshot(
        BalanceSnapshot(xrp=55.0, rlusd=90.0, mid_rlusd_per_xrp=2.0, portfolio_xrp_equiv=100.0)
    )
    assert snap.label == "balanced"
    assert abs(snap.xrp_ratio - 0.55) < 0.01


def test_decision_engine_holds_when_balanced():
    engine = DecisionEngine(_minimal_config())
    inv = InventorySnapshot(
        xrp_ratio=0.55,
        target_xrp_ratio=0.55,
        deviation=0.0,
        label="balanced",
        pause_bids=False,
        pause_asks=False,
        summary="ok",
    )
    risk = RiskSnapshot(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        preflight_ready=True,
        preflight_summary="OK",
    )

    async def _book():
        return await _FakeLedger().get_order_book()

    book = asyncio.run(_book())
    result = engine.evaluate(inventory=inv, risk=risk, book=book)
    assert result.action == DecisionAction.HOLD


def test_format_operator_report_includes_mode():
    snap = OperatorSnapshot(
        generated_utc=datetime.now(tz=timezone.utc),
        alpha_version="1.0.0",
        network="mainnet",
        dry_run=True,
        trading_enabled=True,
        account_address="rTestAccount123456789012345678901234",
        balances=BalanceSnapshot(xrp=1.0, rlusd=2.0, mid_rlusd_per_xrp=0.5, portfolio_xrp_equiv=5.0),
        trust_line=TrustLineSnapshot(exists=True),
        inventory=InventorySnapshot(
            xrp_ratio=0.5,
            target_xrp_ratio=0.55,
            deviation=-0.05,
            label="balanced",
            pause_bids=False,
            pause_asks=False,
            summary="test",
        ),
        risk=RiskSnapshot(
            kill_switch_active=False,
            kill_switch_reason="",
            drawdown_pct=0.0,
            max_drawdown_pct=10.0,
            preflight_ready=True,
            preflight_summary="Preflight OK",
        ),
    )
    text = format_operator_report(snap)
    assert "DRY-RUN" in text
    assert "xLedgerMate Alpha" in text
