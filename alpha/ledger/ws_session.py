"""Lightweight XRPL WebSocket session for account transaction stream."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from xrpl.asyncio.clients import AsyncWebsocketClient
    from xrpl.models.requests import Subscribe
except ImportError:  # pragma: no cover
    AsyncWebsocketClient = None
    Subscribe = None


@dataclass
class AccountWsSession:
    """Maintains account tx subscription over rippled WebSocket."""

    account_address: str
    ws_url: str
    max_buffer: int = 100
    _client: Optional[Any] = field(default=None, init=False, repr=False)
    _listener_task: Optional[asyncio.Task[None]] = field(default=None, init=False, repr=False)
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _connected: bool = field(default=False, init=False, repr=False)
    _recent_txs: Deque[Dict[str, Any]] = field(default_factory=deque, init=False, repr=False)

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def recent_transactions(self) -> List[Dict[str, Any]]:
        return list(self._recent_txs)

    def offer_cancel_seen(self, offer_sequence: int) -> bool:
        from alpha.ledger.offer_events import offer_cancel_seen

        return offer_cancel_seen(self.recent_transactions, offer_sequence)

    async def connect(self) -> None:
        if self._connected:
            return
        if AsyncWebsocketClient is None or Subscribe is None:
            raise RuntimeError("xrpl-py WebSocket client unavailable")
        self._stop.clear()
        self._client = AsyncWebsocketClient(self.ws_url)
        await self._client.__aenter__()
        await self._client.send(Subscribe(accounts=[self.account_address]))
        self._listener_task = asyncio.create_task(self._listen())
        self._connected = True
        logger.info("ws_account_connected | account=%s", self.account_address)

    async def close(self) -> None:
        self._stop.set()
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                logger.exception("ws_account_close_error")
            self._client = None
        self._connected = False
        logger.info("ws_account_closed | account=%s", self.account_address)

    async def _listen(self) -> None:
        if self._client is None:
            return
        try:
            async for message in self._client:
                if self._stop.is_set():
                    break
                self._handle_message(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ws_account_listener_error")
            self._connected = False

    def _handle_message(self, message: Any) -> None:
        if not isinstance(message, dict):
            return
        msg_type = message.get("type")
        if msg_type not in ("transaction", "ledgerClosed"):
            return
        if msg_type == "transaction":
            tx = message.get("transaction")
            if not isinstance(tx, dict):
                return
            account = tx.get("Account") or tx.get("account")
            if account and account != self.account_address:
                return
            self._recent_txs.append(message)
            while len(self._recent_txs) > self.max_buffer:
                self._recent_txs.popleft()
            logger.debug(
                "ws_account_tx | type=%s hash=%s",
                tx.get("TransactionType"),
                tx.get("hash"),
            )
