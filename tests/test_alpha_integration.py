"""Integration tests — full buy → bracket → OCO flow (mocked ledger)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from alpha.decision.engine import DecisionAction, DecisionEngine, DecisionResult
from alpha.dry_run import DryRunGuard
from alpha.inventory.manager import InventoryManager
from alpha.orders.manager import OrderManager
from alpha.risk.engine import RiskEngine
from alpha.runtime.executor import EntryExecutor
from alpha.types import LedgerOfferResult, RiskSnapshot
from config.settings import BotConfig


class _FlowLedger:
    account_address = "rFake123456789012345678901234567890"

    def __init__(self) -> None:
        self._offers: Dict[int, dict[str, Any]] = {}
        self._seq = 3000
        self.cancelled: List[int] = []

    async def connect(self) -> None:
        return None

    async def get_open_offers(self) -> List[dict[str, Any]]:
        return list(self._offers.values())

    async def place_limit_buy_xrp(self, *, size_xrp: float, price_rlusd_per_xrp: float) -> LedgerOfferResult:
        self._seq += 1
        self._offers[self._seq] = {
            "sequence": self._seq,
            "side": "bid",
            "price": price_rlusd_per_xrp,
            "size_xrp": size_xrp,
        }
        return LedgerOfferResult(submitted=True, dry_run=False, action="buy", sequence=self._seq)

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
        self.cancelled.append(sequence)
        self._offers.pop(sequence, None)
        return LedgerOfferResult(submitted=True, dry_run=False, action="cancel", sequence=sequence)

    async def close(self) -> None:
        return None


def _risk_ready() -> RiskSnapshot:
    return RiskSnapshot(
        kill_switch_active=False,
        kill_switch_reason="",
        drawdown_pct=0.0,
        max_drawdown_pct=10.0,
        preflight_ready=True,
        preflight_summary="OK",
        trading_allowed=True,
    )


def test_full_buy_bracket_oco_flow(tmp_path: Path):
    async def _run() -> None:
        ledger = _FlowLedger()
        cfg = BotConfig(
            dry_run=False,
            min_order_size_xrp=1.0,
            initial_stop_loss_pct=0.02,
            take_profit_rr=2.0,
            min_fill_size_xrp_for_oco=0.5,
        )
        guard = DryRunGuard(dry_run=False, network="mainnet")
        risk_engine = RiskEngine(cfg, state_dir=tmp_path)
        orders = OrderManager(ledger, guard, cfg, risk_engine=risk_engine, state_dir=tmp_path)
        executor = EntryExecutor(ledger, orders, guard, cfg, risk=risk_engine)

        decision = DecisionResult(
            action=DecisionAction.PLACE_BID,
            reason="integration_test",
            size_xrp=10.0,
            price_rlusd_per_xrp=2.0,
            edge_pct=0.15,
        )
        entry = await executor.execute(decision, risk=_risk_ready())
        assert entry.executed
        buy_seq = entry.buy_sequence
        assert buy_seq is not None

        ledger._offers.pop(buy_seq)
        risk = _risk_ready()
        await orders.sync_brackets(risk=risk)
        record = orders.store.get(entry.bracket_id or "")
        assert record is not None
        assert record.tp_leg and record.sl_leg
        tp_seq = record.tp_leg.sequence
        assert tp_seq

        ledger._offers.pop(tp_seq)
        await orders.sync_brackets(risk=risk)
        assert record.sl_leg.sequence in ledger.cancelled

        persist_file = tmp_path / "alpha_brackets.json"
        assert persist_file.exists()

    asyncio.run(_run())


def test_dry_run_full_path_no_ledger_writes():
    async def _run() -> None:
        ledger = _FlowLedger()
        cfg = BotConfig(dry_run=True)
        guard = DryRunGuard(dry_run=True, network="mainnet")
        orders = OrderManager(ledger, guard, cfg)
        executor = EntryExecutor(ledger, orders, guard, cfg)
        decision = DecisionResult(
            action=DecisionAction.PLACE_BID,
            reason="dry",
            size_xrp=5.0,
            price_rlusd_per_xrp=2.0,
        )
        result = await executor.execute(decision, risk=_risk_ready())
        assert result.dry_run
        assert not result.executed
        assert len(await ledger.get_open_offers()) == 0

    asyncio.run(_run())
