"""Execute decision engine signals via ledger and OrderManager."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from alpha.decision.engine import DecisionAction, DecisionResult
from alpha.dry_run import DryRunGuard
from alpha.ledger.interface import LedgerInterface
from alpha.orders.manager import OrderManager
from alpha.types import RiskSnapshot
from config.settings import BotConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntryExecutionResult:
    executed: bool
    dry_run: bool
    action: str
    bracket_id: Optional[str] = None
    buy_sequence: Optional[int] = None
    message: str = ""


class EntryExecutor:
    """Places limit entries and registers buys for bracket lifecycle."""

    def __init__(
        self,
        ledger: LedgerInterface,
        orders: OrderManager,
        guard: DryRunGuard,
        config: BotConfig,
        *,
        risk: object | None = None,
    ) -> None:
        self._ledger = ledger
        self._orders = orders
        self._guard = guard
        self._config = config
        self._risk = risk

    async def execute(
        self,
        decision: DecisionResult,
        *,
        risk: Optional[RiskSnapshot] = None,
    ) -> EntryExecutionResult:
        if decision.action == DecisionAction.HOLD:
            return EntryExecutionResult(
                executed=False,
                dry_run=self._guard.dry_run,
                action="hold",
                message=decision.reason,
            )

        if risk is not None and self._risk is not None:
            from alpha.risk.engine import RiskEngine

            if isinstance(self._risk, RiskEngine):
                ok, msg = self._risk.validate_entry(risk, edge_pct=decision.edge_pct)
                if not ok:
                    logger.info("entry_blocked_by_risk | %s", msg)
                    return EntryExecutionResult(
                        executed=False,
                        dry_run=self._guard.dry_run,
                        action=decision.action.value,
                        message=msg,
                    )

        if decision.action == DecisionAction.PLACE_BID:
            return await self._execute_buy(decision)
        if decision.action == DecisionAction.PLACE_ASK:
            return await self._execute_sell(decision)
        return EntryExecutionResult(
            executed=False,
            dry_run=self._guard.dry_run,
            action=decision.action.value,
            message=f"unsupported_action:{decision.action.value}",
        )

    async def _execute_buy(self, decision: DecisionResult) -> EntryExecutionResult:
        size = decision.size_xrp
        price = decision.price_rlusd_per_xrp
        if size is None or price is None or size <= 0 or price <= 0:
            return EntryExecutionResult(
                executed=False,
                dry_run=self._guard.dry_run,
                action="place_bid",
                message="invalid_bid_params",
            )

        if self._guard.dry_run:
            logger.info(
                "entry_execute_dry_run | action=PLACE_BID | size=%.4f | price=%.6f | reason=%s",
                size,
                price,
                decision.reason,
            )
            return EntryExecutionResult(
                executed=False,
                dry_run=True,
                action="place_bid",
                message=f"dry_run:{decision.reason}",
            )

        before = await self._orders.open_sequences()
        buy_result = await self._ledger.place_limit_buy_xrp(size_xrp=size, price_rlusd_per_xrp=price)
        if not buy_result.submitted:
            logger.warning("entry_buy_not_submitted | reason=%s", decision.reason)
            return EntryExecutionResult(
                executed=False,
                dry_run=False,
                action="place_bid",
                message="ledger_did_not_submit",
            )

        seq = buy_result.sequence
        if seq is None:
            seq = await self._orders.resolve_new_sequence(
                before,
                side="bid",
                price=price,
                size_xrp=size,
            )
        if seq is None:
            logger.warning(
                "entry_buy_sequence_deferred | size=%.4f price=%.6f — will reconcile on next sync",
                size,
                price,
            )
            return EntryExecutionResult(
                executed=True,
                dry_run=False,
                action="place_bid",
                message=f"{decision.reason}|sequence_deferred_reconcile",
            )

        bracket_id = self._orders.register_pending_buy(
            buy_sequence=seq,
            size_xrp=size,
            entry_price_rlusd_per_xrp=price,
        )
        logger.info(
            "entry_buy_placed | bracket_id=%s | seq=%s | size=%.4f | price=%.6f",
            bracket_id,
            seq,
            size,
            price,
        )
        return EntryExecutionResult(
            executed=True,
            dry_run=False,
            action="place_bid",
            bracket_id=bracket_id,
            buy_sequence=seq,
            message=decision.reason,
        )

    async def _execute_sell(self, decision: DecisionResult) -> EntryExecutionResult:
        size = decision.size_xrp
        price = decision.price_rlusd_per_xrp
        if size is None or price is None or size <= 0 or price <= 0:
            return EntryExecutionResult(
                executed=False,
                dry_run=self._guard.dry_run,
                action="place_ask",
                message="invalid_ask_params",
            )

        if self._guard.dry_run:
            logger.info(
                "entry_execute_dry_run | action=PLACE_ASK | size=%.4f | price=%.6f | reason=%s",
                size,
                price,
                decision.reason,
            )
            return EntryExecutionResult(
                executed=False,
                dry_run=True,
                action="place_ask",
                message=f"dry_run:{decision.reason}",
            )

        before = await self._orders.open_sequences()
        sell_result = await self._ledger.place_limit_sell_xrp(size_xrp=size, price_rlusd_per_xrp=price)
        if not sell_result.submitted:
            return EntryExecutionResult(
                executed=False,
                dry_run=False,
                action="place_ask",
                message="ledger_did_not_submit",
            )

        seq = sell_result.sequence
        if seq is None:
            seq = await self._orders.resolve_new_sequence(
                before,
                side="ask",
                price=price,
                size_xrp=size,
            )

        reason = decision.reason or ""
        if "reload_funding" in reason:
            purpose = "reload_funding"
        elif "drawdown_reload" in reason:
            purpose = "drawdown_reload"
        elif "harvest_trim" in reason:
            purpose = "harvest_trim"
        else:
            purpose = "strength"
        if seq is not None:
            self._orders.register_strength_sell(
                sequence=seq,
                size_xrp=size,
                price_rlusd_per_xrp=price,
                purpose=purpose,
            )
        elif sell_result.offer_resting is False:
            from alpha.reporting.tax_events import log_strength_sell_tax_event

            if purpose == "reload_funding":
                self._orders.record_reload_funding_fill(
                    size_xrp=size,
                    price_rlusd_per_xrp=price,
                    mid=price,
                )
            elif purpose == "drawdown_reload":
                self._orders.record_drawdown_reload_fill(
                    size_xrp=size,
                    price_rlusd_per_xrp=price,
                    mid=price,
                )
            dedupe_seq = hash((size, price, sell_result.tx_hash or "")) & 0x7FFFFFFF
            log_strength_sell_tax_event(
                sequence=dedupe_seq or 1,
                size_xrp=size,
                price_rlusd_per_xrp=price,
                network="testnet" if self._config.testnet else "mainnet",
                dry_run=False,
            )

        logger.info(
            "entry_sell_placed | size=%.4f | price=%.6f | seq=%s | reason=%s",
            size,
            price,
            seq,
            decision.reason,
        )
        return EntryExecutionResult(
            executed=True,
            dry_run=False,
            action="place_ask",
            message=decision.reason,
        )
