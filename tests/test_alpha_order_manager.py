"""Tests for Trading Bot Alpha Phase 3 — OrderManager bracket lifecycle."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

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

    async def place_limit_buy_xrp(
        self,
        *,
        size_xrp: float,
        price_rlusd_per_xrp: float,
    ) -> LedgerOfferResult:
        self._next_seq += 1
        seq = self._next_seq
        self._offers[seq] = {
            "sequence": seq,
            "side": "bid",
            "price": price_rlusd_per_xrp,
            "size_xrp": size_xrp,
        }
        return LedgerOfferResult(submitted=True, dry_run=False, action="buy", sequence=seq)

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
        self._cancelled_seqs.add(offer_sequence    )


@pytest.fixture
def bracket_state(tmp_path):
    return tmp_path


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


def test_bracket_places_tp_sl_after_buy_fill(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
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


def test_oco_cancels_opposing_leg_on_tp_fill(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
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


def test_min_fill_filter_skips_small_oco(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(min_fill_size_xrp_for_oco=5.0)
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
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


def test_proportional_partial_fill_places_bracket_early(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(partial_fill_mode="proportional")
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        mgr.register_pending_buy(buy_sequence=503, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(503, 6.0)  # 4 XRP filled

        await mgr.sync_brackets()
        record = mgr.store.get_by_buy_sequence(503)
        assert record is not None
        assert record.state == BracketLifecycleState.BRACKET_ACTIVE
        assert record.bracketed_xrp == 4.0

    asyncio.run(_run())


def test_cancelled_buy_skips_bracket_placement(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
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


def test_cancel_pending_buy_bracket(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        bid = mgr.register_pending_buy(buy_sequence=600, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(600, 10.0, price=2.0)
        ok = await mgr.cancel_bracket(bid)
        assert ok is True
        record = mgr.store.get(bid)
        assert record is not None
        assert record.state == BracketLifecycleState.CANCELLED
        assert 600 in ledger.cancelled

    asyncio.run(_run())


def test_adjust_pending_buy_entry_replaces_offer(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        bid = mgr.register_pending_buy(buy_sequence=601, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(601, 10.0, price=2.0)
        ok = await mgr.adjust_bracket_entry(bid, 1.95)
        assert ok is True
        record = mgr.store.get(bid)
        assert record is not None
        assert record.entry_price_rlusd_per_xrp == 1.95
        assert 601 in ledger.cancelled
        assert record.buy_sequence != 601

    asyncio.run(_run())


def test_cancel_all_dry_run_no_ledger_cancel(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        ledger.add_buy(600, 5.0)
        cfg = _bracket_config()
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=True, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        assert not await mgr.cancel_all()
        assert ledger.cancelled == []

    asyncio.run(_run())


def test_stale_pending_buy_cancelled_when_entry_drifts(bracket_state):
    from alpha.decision.structure import MarketStructureSnapshot

    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(
            alpha_buy_limit_offset_pct=0.15,
            alpha_stale_pending_buy_enabled=True,
            alpha_stale_pending_buy_max_drift_pct=0.5,
        )
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        mgr.set_structure(
            MarketStructureSnapshot(
                mid=2.0,
                sample_count=1,
                mean_mid=2.0,
                recent_high=2.0,
                recent_low=2.0,
                trend="neutral",
                breakout_up=False,
                breakout_down=False,
                summary="test",
                swing_high=2.0,
            )
        )
        bid = mgr.register_pending_buy(buy_sequence=700, size_xrp=10.0, entry_price_rlusd_per_xrp=1.90)
        ledger.add_buy(700, 10.0, price=1.90)

        await mgr.sync_brackets()

        record = mgr.store.get(bid)
        assert record is not None
        assert record.state == BracketLifecycleState.CANCELLED
        assert 700 in ledger.cancelled

    asyncio.run(_run())


def test_stale_pending_buy_kept_when_near_target(bracket_state):
    from alpha.decision.structure import MarketStructureSnapshot

    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(
            alpha_buy_limit_offset_pct=0.15,
            alpha_stale_pending_buy_enabled=True,
            alpha_stale_pending_buy_max_drift_pct=0.5,
        )
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        mgr.set_structure(
            MarketStructureSnapshot(
                mid=2.0,
                sample_count=1,
                mean_mid=2.0,
                recent_high=2.0,
                recent_low=2.0,
                trend="neutral",
                breakout_up=False,
                breakout_down=False,
                summary="test",
                swing_high=2.0,
            )
        )
        target = 2.0 * (1.0 - 0.15 / 100.0)
        bid = mgr.register_pending_buy(
            buy_sequence=701, size_xrp=10.0, entry_price_rlusd_per_xrp=target
        )
        ledger.add_buy(701, 10.0, price=target)

        await mgr.sync_brackets()

        record = mgr.store.get(bid)
        assert record is not None
        assert record.state == BracketLifecycleState.PENDING_BUY
        assert ledger.cancelled == []

    asyncio.run(_run())


def test_stale_pending_buy_disabled_skips_auto_cancel(bracket_state):
    from alpha.decision.structure import MarketStructureSnapshot

    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(
            alpha_stale_pending_buy_enabled=False,
            alpha_stale_pending_buy_max_drift_pct=0.5,
        )
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        mgr.set_structure(
            MarketStructureSnapshot(
                mid=2.0,
                sample_count=1,
                mean_mid=2.0,
                recent_high=2.0,
                recent_low=2.0,
                trend="neutral",
                breakout_up=False,
                breakout_down=False,
                summary="test",
                swing_high=2.0,
            )
        )
        bid = mgr.register_pending_buy(buy_sequence=702, size_xrp=10.0, entry_price_rlusd_per_xrp=1.90)
        ledger.add_buy(702, 10.0, price=1.90)

        await mgr.sync_brackets()

        record = mgr.store.get(bid)
        assert record is not None
        assert record.state == BracketLifecycleState.PENDING_BUY
        assert ledger.cancelled == []

    asyncio.run(_run())


def test_stale_pending_buy_cancelled_when_mid_passed_entry(bracket_state):
    from alpha.decision.structure import MarketStructureSnapshot

    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(
            alpha_buy_limit_offset_pct=0.15,
            alpha_stale_pending_buy_enabled=True,
            alpha_stale_pending_buy_max_drift_pct=0.15,
        )
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        mgr.set_structure(
            MarketStructureSnapshot(
                mid=1.103,
                sample_count=1,
                mean_mid=1.103,
                recent_high=1.103,
                recent_low=1.098,
                trend="neutral",
                breakout_up=False,
                breakout_down=False,
                summary="test",
                swing_high=1.103,
            )
        )
        bid = mgr.register_pending_buy(
            buy_sequence=703, size_xrp=10.0, entry_price_rlusd_per_xrp=1.098
        )
        ledger.add_buy(703, 10.0, price=1.098)

        await mgr.sync_brackets()

        record = mgr.store.get(bid)
        assert record is not None
        assert record.state == BracketLifecycleState.CANCELLED
        assert 703 in ledger.cancelled

    asyncio.run(_run())


def test_stale_pending_buy_cancelled_when_entry_above_mid(bracket_state):
    from alpha.decision.structure import MarketStructureSnapshot

    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(
            alpha_buy_limit_offset_pct=0.15,
            alpha_stale_pending_buy_enabled=True,
            alpha_stale_pending_buy_max_drift_pct=0.5,
        )
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        mgr.set_structure(
            MarketStructureSnapshot(
                mid=1.095,
                sample_count=1,
                mean_mid=1.095,
                recent_high=1.095,
                recent_low=1.095,
                trend="neutral",
                breakout_up=False,
                breakout_down=False,
                summary="test",
                swing_high=1.095,
            )
        )
        bid = mgr.register_pending_buy(
            buy_sequence=704, size_xrp=10.0, entry_price_rlusd_per_xrp=1.098
        )
        ledger.add_buy(704, 10.0, price=1.098)

        await mgr.sync_brackets()

        record = mgr.store.get(bid)
        assert record is not None
        assert record.state == BracketLifecycleState.CANCELLED
        assert 704 in ledger.cancelled

    asyncio.run(_run())


def test_excess_pending_buys_pruned_to_cap(bracket_state):
    from alpha.decision.structure import MarketStructureSnapshot

    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(
            alpha_buy_limit_offset_pct=0.15,
            alpha_max_pending_buys=2,
            alpha_stale_pending_buy_enabled=True,
            alpha_stale_pending_buy_max_drift_pct=0.5,
            alpha_rlusd_price_decimals=6,
        )
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        mgr.set_structure(
            MarketStructureSnapshot(
                mid=1.10,
                sample_count=1,
                mean_mid=1.10,
                recent_high=1.10,
                recent_low=1.10,
                trend="neutral",
                breakout_up=False,
                breakout_down=False,
                summary="test",
                swing_high=1.10,
            )
        )
        target = 1.10 * (1.0 - 0.15 / 100.0)
        bids = []
        for seq, entry in ((705, target), (706, target - 0.0005), (707, target - 0.0020)):
            bid = mgr.register_pending_buy(
                buy_sequence=seq, size_xrp=10.0, entry_price_rlusd_per_xrp=entry
            )
            ledger.add_buy(seq, 10.0, price=entry)
            bids.append((bid, seq, entry))

        await mgr.sync_brackets()

        open_pending = [
            mgr.store.get(bid_id)
            for bid_id, _, _ in bids
            if mgr.store.get(bid_id) and mgr.store.get(bid_id).state == BracketLifecycleState.PENDING_BUY
        ]
        assert len(open_pending) == 2
        assert 707 in ledger.cancelled

    asyncio.run(_run())


class _ImmediateFillSellLedger(_BracketFakeLedger):
    """Simulates XRPL immediate fill when a sell is marketable (at/through touch)."""

    def __init__(self) -> None:
        super().__init__()
        self.immediate_next = False

    async def place_limit_sell_xrp(
        self,
        *,
        size_xrp: float,
        price_rlusd_per_xrp: float,
    ) -> LedgerOfferResult:
        self.placed_sells.append((size_xrp, price_rlusd_per_xrp))
        if self.immediate_next:
            self.immediate_next = False
            return LedgerOfferResult(submitted=True, dry_run=False, action="sell", offer_resting=False)
        return await super().place_limit_sell_xrp(
            size_xrp=size_xrp,
            price_rlusd_per_xrp=price_rlusd_per_xrp,
        )


def test_sl_trail_immediate_fill_detected(bracket_state):
    from alpha.decision.structure import MarketStructureSnapshot

    async def _run() -> None:
        ledger = _ImmediateFillSellLedger()
        cfg = _bracket_config(
            bracket_trailing_enabled=True,
            trailing_step_pct=1.5,
            alpha_deferred_sl_enabled=True,
            alpha_stale_pending_buy_enabled=False,
        )
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )

        async def _dynamic_bid() -> float:
            return bid_state["value"]

        bid_state = {"value": 2.05}
        mgr._market_best_bid = _dynamic_bid  # type: ignore[method-assign]

        bid = mgr.register_pending_buy(buy_sequence=800, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(800, 10.0)
        ledger.remove_offer(800)
        await mgr.sync_brackets()
        record = mgr.store.get(bid)
        assert record and record.sl_leg and record.tp_leg
        assert record.sl_leg.sequence is None
        assert record.tp_leg.sequence is not None
        record.breakeven_passed = True
        record.sl_leg.price_rlusd_per_xrp = 1.96
        bid_state["value"] = 2.0
        ledger.immediate_next = True
        mgr.set_structure(
            MarketStructureSnapshot(
                mid=2.01,
                sample_count=1,
                mean_mid=2.01,
                recent_high=2.01,
                recent_low=2.0,
                trend="neutral",
                breakout_up=False,
                breakout_down=False,
                summary="test",
                swing_high=2.01,
            )
        )
        await mgr.sync_brackets()
        record = mgr.store.get(bid)
        assert record is not None
        assert record.state == BracketLifecycleState.SL_FILLED

    asyncio.run(_run())


def test_repair_attaches_missing_sl_sequence(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config()
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        bid = mgr.register_pending_buy(buy_sequence=801, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.remove_offer(801)
        await mgr.sync_brackets()
        record = mgr.store.get(bid)
        assert record and record.sl_leg
        sl_price = record.sl_leg.price_rlusd_per_xrp
        old_sl_seq = record.sl_leg.sequence
        assert old_sl_seq is not None
        # Simulate trail cancel+replace where sequence was lost but the offer is on book.
        record.sl_leg.sequence = None
        mgr.store.unregister_leg_sequence(old_sl_seq)
        ledger.remove_offer(old_sl_seq)
        ledger._offers[9001] = {
            "sequence": 9001,
            "side": "ask",
            "price": sl_price,
            "size_xrp": 10.0,
        }
        await mgr.sync_brackets()
        record = mgr.store.get(bid)
        assert record is not None
        assert record.sl_leg is not None
        assert record.sl_leg.sequence == 9001

    asyncio.run(_run())


def test_repair_replaces_missing_sl_at_same_price(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(alpha_deferred_sl_enabled=False)
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        bid = mgr.register_pending_buy(buy_sequence=802, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.remove_offer(802)
        await mgr.sync_brackets()
        record = mgr.store.get(bid)
        assert record and record.sl_leg
        sl_price = record.sl_leg.price_rlusd_per_xrp
        old_sl_seq = record.sl_leg.sequence
        assert old_sl_seq is not None
        record.sl_leg.sequence = None
        mgr.store.unregister_leg_sequence(old_sl_seq)
        ledger.remove_offer(old_sl_seq)
        placed_before = len(ledger.placed_sells)
        await mgr.sync_brackets()
        record = mgr.store.get(bid)
        assert record is not None
        assert record.sl_leg is not None
        assert record.sl_leg.sequence is not None
        assert len(ledger.placed_sells) == placed_before + 1

    asyncio.run(_run())


def test_deferred_sl_holds_off_ledger_when_bid_above_stop(bracket_state):
    async def _run() -> None:
        from alpha.decision.structure import MarketStructureSnapshot

        ledger = _BracketFakeLedger()
        cfg = _bracket_config(alpha_deferred_sl_enabled=True, alpha_stale_pending_buy_enabled=False)
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )
        mgr.set_structure(MarketStructureSnapshot(mid=2.05, sample_count=1, mean_mid=2.05, recent_high=2.05, recent_low=2.05, trend="neutral", breakout_up=False, breakout_down=False, summary="test"))

        async def _bid_above_stop() -> float:
            return 2.05

        mgr._market_best_bid = _bid_above_stop  # type: ignore[method-assign]

        mgr.register_pending_buy(buy_sequence=810, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(810, 10.0)
        ledger.remove_offer(810)
        await mgr.sync_brackets()

        record = mgr.store.get_by_buy_sequence(810)
        assert record is not None
        assert record.state == BracketLifecycleState.BRACKET_ACTIVE
        assert record.tp_leg is not None and record.tp_leg.sequence is not None
        assert record.sl_leg is not None
        assert record.sl_leg.sequence is None
        assert record.sl_leg.price_rlusd_per_xrp == pytest.approx(1.96)
        assert len(ledger.placed_sells) == 1

    asyncio.run(_run())


def test_deferred_sl_arms_when_mid_reaches_stop(bracket_state):
    async def _run() -> None:
        from alpha.decision.structure import MarketStructureSnapshot

        ledger = _BracketFakeLedger()
        cfg = _bracket_config(alpha_deferred_sl_enabled=True, alpha_stale_pending_buy_enabled=False)
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )

        bid_state = {"value": 2.05}

        async def _dynamic_bid() -> float:
            return bid_state["value"]

        mgr._market_best_bid = _dynamic_bid  # type: ignore[method-assign]
        mgr.set_structure(MarketStructureSnapshot(mid=2.05, sample_count=1, mean_mid=2.05, recent_high=2.05, recent_low=2.05, trend="neutral", breakout_up=False, breakout_down=False, summary="test"))

        mgr.register_pending_buy(buy_sequence=811, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(811, 10.0)
        ledger.remove_offer(811)
        await mgr.sync_brackets()

        record = mgr.store.get_by_buy_sequence(811)
        assert record and record.sl_leg and record.sl_leg.sequence is None

        bid_state["value"] = 1.95
        mgr.set_structure(MarketStructureSnapshot(mid=1.96, sample_count=1, mean_mid=1.96, recent_high=1.96, recent_low=1.96, trend="neutral", breakout_up=False, breakout_down=False, summary="test"))
        await mgr.sync_brackets()

        assert record.sl_leg.sequence is not None
        assert len(ledger.placed_sells) == 2

    asyncio.run(_run())


def test_immediate_sl_when_deferred_disabled(bracket_state):
    async def _run() -> None:
        ledger = _BracketFakeLedger()
        cfg = _bracket_config(alpha_deferred_sl_enabled=False)
        mgr = OrderManager(
            ledger,
            DryRunGuard(dry_run=False, network="mainnet"),
            cfg,
            state_dir=bracket_state,
        )

        async def _bid_above_stop() -> float:
            return 2.05

        mgr._market_best_bid = _bid_above_stop  # type: ignore[method-assign]

        mgr.register_pending_buy(buy_sequence=812, size_xrp=10.0, entry_price_rlusd_per_xrp=2.0)
        ledger.add_buy(812, 10.0)
        ledger.remove_offer(812)
        await mgr.sync_brackets()

        record = mgr.store.get_by_buy_sequence(812)
        assert record is not None
        assert record.sl_leg is not None and record.sl_leg.sequence is not None
        assert len(ledger.placed_sells) == 2

    asyncio.run(_run())
