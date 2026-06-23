"""XRPL ledger adapter — HTTP book + optional WS account stream."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, List, Optional

from alpha.dry_run import DryRunGuard
from alpha.ledger.interface import LedgerInterface
from alpha.ledger.liquidity import build_order_book_snapshot, compute_liquidity_depth
from alpha.ledger.ws_session import AccountWsSession
from alpha.types import (
    AccountSnapshot,
    BalanceSnapshot,
    LedgerOfferResult,
    LiquidityDepth,
    OrderBookSnapshot,
    TrustLineSnapshot,
)
from alpha.precision import format_rlusd_amount, format_rlusd_price, price_decimals
from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from core.runtime_state import QuoteIntent
from experimental.ws_feed.network_urls import rpc_url_to_websocket_url
from risk.inventory_limits import portfolio_xrp_equiv

logger = logging.getLogger(__name__)


class XrplLedgerAdapter(LedgerInterface):
    """Ledger reads via XRPLConnector; writes gated by DryRunGuard."""

    def __init__(
        self,
        connector: XRPLConnector,
        *,
        config: BotConfig,
        dry_run_guard: DryRunGuard,
        ws_session: Optional[AccountWsSession] = None,
    ) -> None:
        self._connector = connector
        self._config = config
        self._guard = dry_run_guard
        self._ws = ws_session
        self._book_cache: Optional[OrderBookSnapshot] = None

    @property
    def account_address(self) -> str:
        return self._connector.account_address

    @classmethod
    def from_config(
        cls,
        config: BotConfig,
        *,
        dry_run_guard: DryRunGuard,
    ) -> XrplLedgerAdapter:
        rpc_url = config.resolved_rpc_url()
        network = XRPLNetworkConfig(json_rpc_url=rpc_url)
        connector = XRPLConnector(
            account_address=config.bot_account_address,
            secret=config.bot_secret_key or None,
            rlusd_issuer=config.resolved_rlusd_issuer(),
            rlusd_currency=config.rlusd_currency,
            network=network,
        )
        ws_session: Optional[AccountWsSession] = None
        if config.alpha_ws_enabled:
            ws_url = rpc_url_to_websocket_url(rpc_url)
            ws_session = AccountWsSession(
                account_address=config.bot_account_address,
                ws_url=ws_url,
            )
        return cls(connector, config=config, dry_run_guard=dry_run_guard, ws_session=ws_session)

    async def connect(self) -> None:
        if self._ws is not None and not self._ws.connected:
            try:
                await self._ws.connect()
            except Exception:
                logger.exception("ws_connect_failed | continuing with HTTP book reads")

    async def get_order_book(self, *, limit: int = 40) -> OrderBookSnapshot:
        raw = await self._connector.fetch_xrp_rlusd_order_book(limit=limit)
        best_bid, best_ask = self._connector.compute_best_prices(raw)
        mid = self._connector.compute_mid_price(raw)
        snap = build_order_book_snapshot(raw, best_bid=best_bid, best_ask=best_ask, mid=mid)
        self._book_cache = snap
        logger.info(
            "ledger_book | bid=%s ask=%s mid=%s spread_pct=%s",
            f"{best_bid:.6f}" if best_bid else "n/a",
            f"{best_ask:.6f}" if best_ask else "n/a",
            f"{mid:.6f}" if mid else "n/a",
            f"{snap.spread_pct:.4f}" if snap.spread_pct is not None else "n/a",
        )
        return snap

    async def get_liquidity_depth(self, max_slippage_pct: float) -> LiquidityDepth:
        book = self._book_cache or await self.get_order_book()
        depth = compute_liquidity_depth(book, max_slippage_pct=max_slippage_pct)
        logger.info(
            "ledger_liquidity | slippage=%.2f%% bid_depth=%.2f ask_depth=%.2f",
            max_slippage_pct,
            depth.bid_depth_xrp,
            depth.ask_depth_xrp,
        )
        return depth

    async def get_balances(self) -> BalanceSnapshot:
        xrp = await self._connector.get_xrp_balance()
        rlusd = await self._connector.get_rlusd_balance()
        mid = await self._connector.get_mid_price()
        equiv = portfolio_xrp_equiv(xrp, rlusd, mid) if mid is not None else max(0.0, xrp)
        logger.info(
            "ledger_balances | xrp=%.4f | rlusd=%.4f | mid=%s | xrp_equiv=%.4f",
            xrp,
            rlusd,
            f"{mid:.6f}" if mid is not None else "n/a",
            equiv,
        )
        return BalanceSnapshot(
            xrp=xrp,
            rlusd=rlusd,
            mid_rlusd_per_xrp=mid,
            portfolio_xrp_equiv=equiv,
        )

    async def get_account_snapshot(self) -> AccountSnapshot:
        book = await self.get_order_book()
        xrp = await self._connector.get_xrp_balance()
        rlusd = await self._connector.get_rlusd_balance()
        trust_info = await self._connector.get_rlusd_trust_line()
        mid = book.mid
        equiv = portfolio_xrp_equiv(xrp, rlusd, mid) if mid is not None else max(0.0, xrp)
        trust = TrustLineSnapshot(
            exists=trust_info.exists,
            balance=trust_info.balance,
            limit=trust_info.limit,
            no_ripple=trust_info.no_ripple,
            issuer=self._config.resolved_rlusd_issuer(),
        )
        return AccountSnapshot(
            xrp=xrp,
            rlusd=rlusd,
            mid_rlusd_per_xrp=mid,
            portfolio_xrp_equiv=equiv,
            trust_line=trust,
            book=book,
        )

    async def get_trust_line(self) -> TrustLineSnapshot:
        info = await self._connector.get_rlusd_trust_line()
        snap = TrustLineSnapshot(
            exists=info.exists,
            balance=info.balance,
            limit=info.limit,
            no_ripple=info.no_ripple,
            issuer=self._config.resolved_rlusd_issuer(),
        )
        logger.info(
            "ledger_trustline | exists=%s | balance=%.4f | limit=%.2f",
            snap.exists,
            snap.balance,
            snap.limit,
        )
        return snap

    async def get_open_offers(self) -> List[dict[str, Any]]:
        raw = await self._connector.get_open_offers()
        offers = [asdict(o) for o in raw]
        logger.info("ledger_open_offers | count=%d", len(offers))
        return offers

    def offer_cancel_seen(self, offer_sequence: int) -> bool:
        if self._ws is not None:
            return self._ws.offer_cancel_seen(offer_sequence)
        return False

    async def place_limit_buy_xrp(
        self,
        *,
        size_xrp: float,
        price_rlusd_per_xrp: float,
    ) -> LedgerOfferResult:
        dec = price_decimals(self._config)
        action = (
            f"place_limit_buy_xrp size={size_xrp:.4f} "
            f"price={format_rlusd_price(price_rlusd_per_xrp, dec)}"
        )
        if not self._guard.require_live(action):
            return LedgerOfferResult(submitted=False, dry_run=True, action=action)
        intent = QuoteIntent(
            side="bid",
            size_xrp=size_xrp,
            price=price_rlusd_per_xrp,
            level=1,
            price_decimals=dec,
        )
        tx_hash, offer_seq = await self._connector.place_quote(intent)
        logger.info("ledger_place_buy | %s | hash=%s | seq=%s", action, tx_hash, offer_seq)
        return LedgerOfferResult(
            submitted=True,
            dry_run=False,
            action=action,
            tx_hash=tx_hash,
            sequence=offer_seq,
        )

    async def place_limit_sell_xrp(
        self,
        *,
        size_xrp: float,
        price_rlusd_per_xrp: float,
    ) -> LedgerOfferResult:
        dec = price_decimals(self._config)
        action = (
            f"place_limit_sell_xrp size={size_xrp:.4f} "
            f"price={format_rlusd_price(price_rlusd_per_xrp, dec)}"
        )
        if not self._guard.require_live(action):
            return LedgerOfferResult(submitted=False, dry_run=True, action=action)
        intent = QuoteIntent(
            side="ask",
            size_xrp=size_xrp,
            price=price_rlusd_per_xrp,
            level=1,
            price_decimals=dec,
        )
        tx_hash, offer_seq = await self._connector.place_quote(intent)
        logger.info("ledger_place_sell | %s | hash=%s | seq=%s", action, tx_hash, offer_seq)
        return LedgerOfferResult(
            submitted=True,
            dry_run=False,
            action=action,
            tx_hash=tx_hash,
            sequence=offer_seq,
        )

    async def cancel_offer(self, sequence: int) -> LedgerOfferResult:
        action = f"cancel_offer seq={sequence}"
        if not self._guard.require_live(action):
            return LedgerOfferResult(
                submitted=False,
                dry_run=True,
                action=action,
                sequence=sequence,
            )
        tx_hash = await self._connector.cancel_offer(sequence)
        logger.info("ledger_cancel | seq=%s | hash=%s", sequence, tx_hash)
        return LedgerOfferResult(
            submitted=True,
            dry_run=False,
            action=action,
            tx_hash=tx_hash,
            sequence=sequence,
        )

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()

