"""Ledger read/write boundary for Trading Bot Alpha."""

from __future__ import annotations

from typing import Any, List, Protocol, runtime_checkable

from alpha.types import (
    AccountSnapshot,
    BalanceSnapshot,
    LedgerOfferResult,
    LiquidityDepth,
    OrderBookSnapshot,
    TrustLineSnapshot,
)


@runtime_checkable
class LedgerInterface(Protocol):
    """Abstract ledger access — XRPL adapter in production; mock in tests."""

    @property
    def account_address(self) -> str:
        ...

    async def connect(self) -> None:
        ...

    async def get_balances(self) -> BalanceSnapshot:
        ...

    async def get_trust_line(self) -> TrustLineSnapshot:
        ...

    async def get_order_book(self, *, limit: int = 40) -> OrderBookSnapshot:
        ...

    async def get_liquidity_depth(self, max_slippage_pct: float) -> LiquidityDepth:
        ...

    async def get_account_snapshot(self) -> AccountSnapshot:
        ...

    async def get_open_offers(self) -> List[dict[str, Any]]:
        ...

    async def place_limit_buy_xrp(
        self,
        *,
        size_xrp: float,
        price_rlusd_per_xrp: float,
    ) -> LedgerOfferResult:
        ...

    async def place_limit_sell_xrp(
        self,
        *,
        size_xrp: float,
        price_rlusd_per_xrp: float,
    ) -> LedgerOfferResult:
        ...

    async def cancel_offer(self, sequence: int) -> LedgerOfferResult:
        ...

    async def close(self) -> None:
        ...
