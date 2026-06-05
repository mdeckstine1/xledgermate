from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from connectors.xrpl_connector import XRPLConnector
from experimental.ws_feed.book_messages import (
    extract_offers_from_message,
    normalize_snapshot_offers,
)
from experimental.ws_feed.book_state import BookState
from experimental.ws_feed.http_poll_feed import HttpPollBookFeed
from experimental.ws_feed.pair_books import RlusdXrpPair

logger = logging.getLogger(__name__)

try:
    from xrpl.asyncio.clients import AsyncWebsocketClient
    from xrpl.models.requests import BookOffers, Subscribe
except ImportError:  # pragma: no cover
    AsyncWebsocketClient = None
    BookOffers = None
    Subscribe = None


@dataclass
class WsBookFeed:
    """
    WebSocket book subscription with HTTP refresh fallback.

    Not used by TradingEngine. Call `run()` from probes or future integration.
    """

    connector: XRPLConnector
    ws_url: str
    pair: RlusdXrpPair
    http_fallback: HttpPollBookFeed = field(init=False)
    state: BookState = field(init=False)
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _listener_task: Optional[asyncio.Task] = None

    def __post_init__(self) -> None:
        self.http_fallback = HttpPollBookFeed(self.connector)
        self.state = BookState(connector=self.connector)

    async def seed_from_http(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        book = await self.http_fallback.fetch_order_book(limit=limit)
        self.state.apply_snapshot("bid", book.get("bids", []))
        self.state.apply_snapshot("ask", book.get("asks", []))
        return book

    async def fetch_order_book_over_ws(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        """One-shot BookOffers over WS (sanity check without subscribe loop)."""
        if AsyncWebsocketClient is None or BookOffers is None:
            raise RuntimeError("xrpl-py WebSocket client unavailable")

        rlusd = self.pair.issued_rlusd_code()
        from xrpl.models.currencies import IssuedCurrency, XRP

        taker_gets_xrp = XRP()
        taker_pays_rlusd = IssuedCurrency(currency=rlusd, issuer=self.pair.rlusd_issuer)

        async with AsyncWebsocketClient(self.ws_url) as client:
            asks_raw = (
                await client.request(
                    BookOffers(
                        taker_gets=taker_gets_xrp,
                        taker_pays=taker_pays_rlusd,
                        limit=limit,
                    )
                )
            ).result.get("offers", [])
            bids_raw = (
                await client.request(
                    BookOffers(
                        taker_gets=taker_pays_rlusd,
                        taker_pays=taker_gets_xrp,
                        limit=limit,
                    )
                )
            ).result.get("offers", [])

        return {
            "asks": self.connector._normalize_offers(asks_raw, side="ask"),
            "bids": self.connector._normalize_offers(bids_raw, side="bid"),
        }

    async def _handle_message(self, message: Any) -> None:
        if not isinstance(message, dict):
            return
        for side, raw_offers, deleted in extract_offers_from_message(
            message, rlusd_issuer=self.pair.rlusd_issuer
        ):
            levels = normalize_snapshot_offers(self.connector, side, raw_offers)
            if message.get("type") == "response" and message.get("result", {}).get("offers"):
                self.state.apply_snapshot(side, levels)
            else:
                self.state.apply_levels(side, levels, deleted=deleted)

    async def _listen(self, client: AsyncWebsocketClient) -> None:
        async for message in client:
            if self._stop.is_set():
                break
            await self._handle_message(message)

    async def run(
        self,
        *,
        seconds: float = 60.0,
        http_refresh_seconds: float = 45.0,
        seed_http: bool = True,
    ) -> BookState:
        if AsyncWebsocketClient is None or Subscribe is None:
            raise RuntimeError("xrpl-py WebSocket client unavailable")

        if seed_http:
            await self.seed_from_http()

        self._stop.clear()

        async with AsyncWebsocketClient(self.ws_url) as client:
            await client.send(
                Subscribe(books=self.pair.subscribe_books(snapshot=True))
            )
            self._listener_task = asyncio.create_task(self._listen(client))

            deadline = time.monotonic() + seconds
            last_http = 0.0
            while time.monotonic() < deadline and not self._stop.is_set():
                now = time.monotonic()
                if now - last_http >= http_refresh_seconds:
                    try:
                        await self.seed_from_http()
                        last_http = now
                    except Exception:
                        logger.exception("HTTP book refresh failed during WS run")
                        last_http = now
                await asyncio.sleep(0.25)

            self._stop.set()
            if self._listener_task:
                self._listener_task.cancel()
                try:
                    await self._listener_task
                except asyncio.CancelledError:
                    pass

        return self.state

    def current_order_book(self) -> Dict[str, List[Dict[str, float]]]:
        return self.state.to_order_book()