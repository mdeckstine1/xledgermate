"""Tests for orphan bid reconciliation and offer sequence extraction."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

import pytest

from alpha.dry_run import DryRunGuard
from alpha.orders.manager import OrderManager
from alpha.orders.types import BracketLifecycleState
from alpha.types import LedgerOfferResult
from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector


def test_extract_created_offer_sequence_from_meta():
    response = type("R", (), {})()
    response.result = {
        "hash": "ABC",
        "meta": {
            "TransactionResult": "tesSUCCESS",
            "AffectedNodes": [
                {
                    "CreatedNode": {
                        "LedgerEntryType": "Offer",
                        "NewFields": {
                            "Sequence": 104583075,
                            "TakerGets": "1000000",
                            "TakerPays": {"value": "1.1", "currency": "524C555344", "issuer": "rISSUER"},
                        },
                    }
                }
            ],
        },
    }
    assert XRPLConnector.extract_created_offer_sequence(response) == 104583075


def test_classify_offer_create_resting():
    response = type("R", (), {})()
    response.result = {
        "meta": {
            "TransactionResult": "tesSUCCESS",
            "AffectedNodes": [
                {
                    "CreatedNode": {
                        "LedgerEntryType": "Offer",
                        "NewFields": {"Sequence": 42},
                    }
                }
            ],
        },
    }
    seq, resting = XRPLConnector.classify_offer_create(response)
    assert seq == 42
    assert resting is True


def test_classify_offer_create_consumed():
    response = type("R", (), {})()
    response.result = {
        "meta": {
            "TransactionResult": "tesSUCCESS",
            "AffectedNodes": [{"ModifiedNode": {"LedgerEntryType": "AccountRoot"}}],
        },
    }
    seq, resting = XRPLConnector.classify_offer_create(response)
    assert seq is None
    assert resting is False


class _OrphanLedger:
    account_address = "rTestAccount123456789012345678901234567890"

    def __init__(self, offers: List[dict[str, Any]]) -> None:
        self._offers = {int(o["sequence"]): o for o in offers}

    async def connect(self) -> None:
        return None

    async def get_open_offers(self) -> List[dict[str, Any]]:
        return list(self._offers.values())

    async def place_limit_sell_xrp(self, **kwargs: Any) -> LedgerOfferResult:
        return LedgerOfferResult(submitted=True, dry_run=False, action="sell")

    async def place_limit_buy_xrp(self, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def cancel_offer(self, sequence: int) -> Any:
        self._offers.pop(int(sequence), None)
        return None

    async def get_order_book(self, *, limit: int = 40) -> Any:
        from datetime import datetime, timezone

        from alpha.types import OrderBookSnapshot

        return OrderBookSnapshot(
            bids=(),
            asks=(),
            best_bid=1.10,
            best_ask=1.11,
            mid=1.105,
            spread=0.01,
            spread_pct=0.1,
            fetched_utc=datetime.now(tz=timezone.utc),
        )

    def offer_cancel_seen(self, offer_sequence: int) -> bool:
        return False


def test_resolve_leg_sequence_unknown_resting_not_immediate_fill(tmp_path: Path):
    cfg = BotConfig(dry_run=False, min_order_size_xrp=1.0)
    ledger = _OrphanLedger([])
    mgr = OrderManager(
        ledger,
        DryRunGuard(dry_run=False, network="mainnet"),
        cfg,
        state_dir=tmp_path,
    )

    async def _run() -> None:
        seq, immediate = await mgr._resolve_leg_sequence(
            set(),
            side="ask",
            price=1.12,
            size_xrp=10.0,
            place_result=LedgerOfferResult(
                submitted=True,
                dry_run=False,
                action="sell",
                offer_resting=True,
            ),
        )
        assert seq is None
        assert immediate is False

    asyncio.run(_run())


def test_reconcile_orphan_bid_registers_pending(tmp_path: Path):
    cfg = BotConfig(dry_run=False, min_order_size_xrp=1.0)
    ledger = _OrphanLedger(
        [
            {
                "sequence": 9001,
                "side": "bid",
                "price": 1.10,
                "size_xrp": 20.0,
            }
        ]
    )
    mgr = OrderManager(
        ledger,
        DryRunGuard(dry_run=False, network="mainnet"),
        cfg,
        state_dir=tmp_path,
    )

    async def _run() -> None:
        state = await mgr.sync_brackets()
        assert state.reconciled_bids == 1
        assert state.pending_buys == 1
        assert state.orphan_bids == 0
        record = mgr.store.get_by_buy_sequence(9001)
        assert record is not None
        assert record.state == BracketLifecycleState.PENDING_BUY

    asyncio.run(_run())


def test_revive_cancelled_bid_still_on_ledger(tmp_path: Path):
    cfg = BotConfig(dry_run=False, min_order_size_xrp=1.0)
    ledger = _OrphanLedger(
        [
            {
                "sequence": 8999,
                "side": "bid",
                "price": 1.10,
                "size_xrp": 15.0,
            }
        ]
    )
    mgr = OrderManager(
        ledger,
        DryRunGuard(dry_run=False, network="mainnet"),
        cfg,
        state_dir=tmp_path,
    )
    bid = mgr.register_pending_buy(
        buy_sequence=8999,
        size_xrp=15.0,
        entry_price_rlusd_per_xrp=1.10,
    )
    record = mgr.store.get(bid)
    assert record is not None
    record.state = BracketLifecycleState.CANCELLED
    mgr.store.touch_persist()

    async def _run() -> None:
        state = await mgr.sync_brackets()
        assert state.reconciled_bids >= 1
        revived = mgr.store.get_by_buy_sequence(8999)
        assert revived is not None
        assert revived.state == BracketLifecycleState.PENDING_BUY

    asyncio.run(_run())
