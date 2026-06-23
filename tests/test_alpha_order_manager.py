"""Tests for Trading Bot Alpha Phase 3 — OrderManager bracket lifecycle."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from alpha.dry_run import DryRunGuard
from alpha.orders.bracket import compute_bracket_prices, normalize_partial_fill_mode
from alpha.orders.manager import OrderManager
from alpha.orders.types import BracketLifecycleState
from alpha.types import LedgerOfferResult
from dataclasses import replace
from config.settings import BotConfig


def _bracket_config(**overrides: Any) -> BotConfig:
    base = BotConfig(
        bot_account_address="rTestAccount123456789012345678901234",
        dry_run=True,
        testnet=False,
        min_order_size_xrp=1.0,
        initial_stop_loss_pct=0.02,
        take_profit_rr=2.0,
        partial_fill_mode="wait_full",
        min_fill_size_xrp_for_oco=0.5,
        bracket_trailing_enabled=False,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return replace(
        base,
        alpha_technical_analysis=replace(base.alpha_technical_analysis, enabled=False),
    )


class _BracketFakeLedger:
    """Simulates open offers for bracket sync tests."""

    account_address = "rFake123456789012345678901234567890"

    def __init__(self) -> None:
        self._offers: Dict[int, dict[str, Any]] = {}
        self._next_seq = 1000
        self.cancelled: List[int] = []
        self.placed_sells: List[tuple[float, float]] = []
        self._cancelled_seqs: set[int] = set()

    async def connect(self) -> None:
        return None

    async def get_open_offers(self) -> List[dict[str, Any]]:
        return list(self._offers.values())

    async def place_limit_sell_xrp(
        self,
        *,
        size_xrp: float,
        price_rlusd_per_xrp: float,
    ) -> LedgerOfferResult:
        self._next_seq += 1
        seq = self._next_seq
        self._offers[seq] = {
            "sequence": seq,
            "side": "ask",
            "price": price_rlusd_per_xrp,
            "size_xrp": size_xrp,
        }
        self.placed_sells.append((size_xrp, price_rlusd_per_xrp))
        return LedgerOfferResult(submitted=True, dry_run=False, action="sell", sequence=seq)

    async def place_limit_buy_xrp(self, **kwargs: Any) -> LedgerOfferResult:
        return LedgerOfferResult(submitted=False, dry_run=True, action="buy")

    async def cancel_offer(self, sequence: int) -> LedgerOfferResult:
        self.cancelled.append(sequence)
        self._offers.pop(sequence, None)
        return LedgerOfferResult(submitted=True, dry_run=False, action="cancel", sequence=sequence)

    def add_buy(self, sequence: int, size_xrp: float, price: float = 2.0) -> None:
        self._offers[sequence] = {
            "sequence": sequence,
            "side": "bid",
            "price": price,
            "size_xrp": size_xrp,
        }

    def remove_offer(self, sequence: int) -> None:
        self._offers.pop(sequence, None)

    def shrink_offer(self, sequence: int, remaining_xrp: float) -> None:
        if sequence in self._offers:
            self._offers[sequence]["size_xrp"] = remaining_xrp

    async def close(self) -> None:
        return None

    def offer_cancel_seen(self, offer_sequence: int) -> bool:
        return offer_sequence in self._cancelled_seqs

    def mark_cancelled(self, offer_sequence: int) -> None:
        self._cancelled_seqs.add(offer_sequence)


def test_compute_bracket_prices_rr_mode():
    cfg = _bracket_config(initial_stop_loss_pct=0.02, take_profit_rr=2.0)
    prices = compute_bracket_prices(2.0, cfg)
    assert prices.pricing_mode == "rr"
    assert prices.stop_loss_price == 1.96
    assert prices.take_profit_price == 2.08  # 4% above entry (2x SL)


def test_compute_bracket_prices_fixed_pct_mode():
    cfg = _bracket_config(take_profit_rr=0.0, take_profit_pct=0.03)
    prices = compute_bracket_prices(2.0, cfg)
    assert prices.pricing_mode == "fixed_pct"
    assert prices.take_profit_price == 2.06


def test_normalize_partial_fill_mode():
    assert normalize_partial_fill_mode("wait_full") == "wait_full"
    assert normalize_partial_fill_mode("proportional") == "proportional"


def test_bracket_places_tp_sl_after_buy_fill():
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(ledger, DryRunGuard(dry_run=False, network="mainnet"), cfg)
        mgr.register_pending_buy(buy_sequence=500, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(500, 10.0)
        ledger.remove_offer(500)

        state = await mgr.sync_brackets()
        record = mgr.store.get_by_buy_sequence(500)
        assert record is not None
        assert record.state == BracketLifecycleState.BRACKET_ACTIVE
        assert record.tp_leg is not None and record.sl_leg is not None
        assert len(ledger.placed_sells) == 2
        assert state.active_brackets == 1

    asyncio.run(_run())


def test_oco_cancels_opposing_leg_on_tp_fill():
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(ledger, DryRunGuard(dry_run=False, network="mainnet"), cfg)
        mgr.register_pending_buy(buy_sequence=501, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.remove_offer(501)
        await mgr.sync_brackets()

        record = mgr.store.get_by_buy_sequence(501)
        assert record and record.tp_leg and record.sl_leg
        tp_seq = record.tp_leg.sequence
        sl_seq = record.sl_leg.sequence
        assert tp_seq and sl_seq

        ledger.remove_offer(tp_seq)
        await mgr.sync_brackets()

        assert record.state == BracketLifecycleState.TP_FILLED
        assert sl_seq in ledger.cancelled

    asyncio.run(_run())


def test_min_fill_filter_skips_small_oco():
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(min_fill_size_xrp_for_oco=5.0)
        mgr = OrderManager(ledger, DryRunGuard(dry_run=False, network="mainnet"), cfg)
        mgr.register_pending_buy(buy_sequence=502, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.remove_offer(502)
        await mgr.sync_brackets()

        record = mgr.store.get_by_buy_sequence(502)
        assert record and record.tp_leg
        tp_seq = record.tp_leg.sequence
        assert tp_seq
        ledger.shrink_offer(tp_seq, 8.0)  # 2 XRP partial — below min OCO threshold

        await mgr.sync_brackets()
        assert record.state == BracketLifecycleState.BRACKET_ACTIVE
        assert record.sl_leg and record.sl_leg.sequence not in ledger.cancelled

    asyncio.run(_run())


def test_proportional_partial_fill_places_bracket_early():
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(partial_fill_mode="proportional")
        mgr = OrderManager(ledger, DryRunGuard(dry_run=False, network="mainnet"), cfg)
        mgr.register_pending_buy(buy_sequence=503, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(503, 6.0)  # 4 XRP filled

        await mgr.sync_brackets()
        record = mgr.store.get_by_buy_sequence(503)
        assert record is not None
        assert record.state == BracketLifecycleState.BRACKET_ACTIVE
        assert record.bracketed_xrp == 4.0

    asyncio.run(_run())


def test_cancelled_buy_skips_bracket_placement():
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(ledger, DryRunGuard(dry_run=False, network="mainnet"), cfg)
        mgr.register_pending_buy(buy_sequence=504, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(504, 10.0)
        ledger.mark_cancelled(504)
        ledger.remove_offer(504)

        await mgr.sync_brackets()
        record = mgr.store.get_by_buy_sequence(504)
        assert record is not None
        assert record.state == BracketLifecycleState.CANCELLED
        assert ledger.placed_sells == []

    asyncio.run(_run())

    async def _run() -> None:
        ledger = _BracketFakeLedger()
        ledger.add_buy(600, 5.0)
        cfg = _bracket_config()
        mgr = OrderManager(ledger, DryRunGuard(dry_run=True, network="mainnet"), cfg)
        assert not await mgr.cancel_all()
        assert ledger.cancelled == []

    asyncio.run(_run())
