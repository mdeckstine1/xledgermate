from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from connectors.xrpl_connector import XRPLConnector
from experimental.ws_feed.book_feed import BookFeed
from experimental.ws_feed.book_messages import (
    extract_offers_from_message,
    normalize_snapshot_offers,
)
from experimental.ws_feed.book_state import BookState
from experimental.ws_feed.http_poll_feed import HttpPollBookFeed
from experimental.ws_feed.pair_books import RlusdXrpPair
from experimental.ws_feed.probe_verbose import WsProbeStats, log_verbose_frame

logger = logging.getLogger(__name__)

DEFAULT_MAX_BOOK_AGE_S = 12.0
DEFAULT_RECONNECT_BASE_S = 5.0
DEFAULT_RECONNECT_MAX_S = 60.0

try:
    from xrpl.asyncio.clients import AsyncWebsocketClient
    from xrpl.models.requests import BookOffers, Subscribe
except ImportError:  # pragma: no cover
    AsyncWebsocketClient = None
    BookOffers = None
    Subscribe = None


@dataclass
class WsBookFeed(BookFeed):
    """
    WebSocket book subscription with HTTP refresh fallback.

    Implements the common BookFeed interface (with HttpPollBookFeed)
    so it can eventually be selected via book_feed_mode in the engine.

    Uses current main run data (long Gate 2 runs with hard gate firing on
    thin books / edge thin) as the test cases: fresher WS data should reduce
    false "L1 too tight" / "Generated 0 quotes" periods and improve presence
    (the main gap observed in 150-fill and prior runs) while keeping the
    hard gate safety.
    """

    connector: XRPLConnector
    ws_url: str
    pair: RlusdXrpPair
    http_fallback: HttpPollBookFeed = field(init=False)
    state: BookState = field(init=False)
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _listener_task: Optional[asyncio.Task] = None
    verbose: bool = False
    stats: Optional[WsProbeStats] = None
    max_drift_bps: float = 5.0  # reconciliation target from PROBE_RESULTS
    max_book_age_s: float = DEFAULT_MAX_BOOK_AGE_S
    reconnect_count: int = 0
    last_reconnect_monotonic: float = 0.0

    def __post_init__(self) -> None:
        self.http_fallback = HttpPollBookFeed(self.connector)
        self.state = BookState(connector=self.connector)

    async def seed_from_http(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        book = await self.http_fallback.fetch_order_book(limit=limit)
        self.state.apply_snapshot("bid", book.get("bids", []))
        self.state.apply_snapshot("ask", book.get("asks", []))
        return book

    async def seed_from_ws_snapshot(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        """Seed full snapshot using WS one-shot BookOffers (native to the feed)."""
        try:
            book = await self.fetch_order_book_over_ws(limit=limit)
            self.state.apply_snapshot("bid", book.get("bids", []))
            self.state.apply_snapshot("ask", book.get("asks", []))
            logger.info("[WS] seeded full snapshot from WS one-shot")
            return book
        except Exception:
            logger.exception("WS snapshot seed failed, falling back to HTTP")
            return await self.seed_from_http(limit)

    async def seed_from_secondary(self, secondary_provider, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        """
        Seed or reconcile using secondary data (e.g. Anodos Finance).

        This is the concrete start for "services like Anodos providing secondary data".

        Use cases driven by current run:
        - When direct WS snapshot is weak or age high, get a secondary view of the book.
        - For reconciliation: if WS mid drifts > max_drift_bps from secondary, blend or reset state.
        - For edge: pass the secondary mid/liquidity into perception or edge calc to decide if a "thin" on-chain book is real or data artifact (common in the 150-fill run's hard-gate cycles on 0.15%+ spreads).

        secondary_provider should have fetch_secondary_book_snapshot() or similar returning
        the normalized book dict, or an ExternalMarketSnapshot with mid/liquidity.
        """
        try:
            if hasattr(secondary_provider, "fetch_secondary_book_snapshot"):
                book = await secondary_provider.fetch_secondary_book_snapshot(limit=limit)
                if book.get("bids") or book.get("asks"):
                    self.state.apply_snapshot("bid", book.get("bids", []))
                    self.state.apply_snapshot("ask", book.get("asks", []))
                    logger.info("[WS] seeded/reconciled from secondary (Anodos-style)")
                    return book
            # Fallback to snapshot object if provider gives mid/liquidity
            snap = await secondary_provider.fetch_snapshot()
            if snap.mid_price:
                # Simple: create minimal levels around the secondary mid for reconciliation
                # In real, parse full book from Anodos response.
                logger.info(f"[WS] secondary mid {snap.mid_price} (liquidity {snap.liquidity_score}) for recon")
            return {}
        except Exception:
            logger.exception("Secondary seed failed")
            return {}

    async def fetch_order_book_over_ws(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        """One-shot BookOffers over WS (sanity check without subscribe loop)."""
        if AsyncWebsocketClient is None or BookOffers is None:
            raise RuntimeError("xrpl-py WebSocket client unavailable")

        from xrpl.models.currencies import IssuedCurrency, XRP

        rlusd_code = self.connector._issued_rlusd_currency_code()
        taker_gets_xrp = XRP()
        taker_pays_rlusd = IssuedCurrency(currency=rlusd_code, issuer=self.pair.rlusd_issuer)

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
        applied = 0
        for side, raw_offers, deleted in extract_offers_from_message(
            message, rlusd_issuer=self.pair.rlusd_issuer
        ):
            levels = normalize_snapshot_offers(self.connector, side, raw_offers)
            if not levels and not deleted:
                continue
            applied += len(levels) or (1 if deleted else 0)
            if message.get("type") == "response" and message.get("result", {}).get("offers"):
                self.state.apply_snapshot(side, levels)
            else:
                self.state.apply_levels(side, levels, deleted=deleted)

        if self.stats is not None:
            label = self.stats.record_frame(message, offers_applied=applied)
            if self.verbose:
                log_verbose_frame(
                    self.stats,
                    label=label,
                    offers_applied=applied,
                    ws_mid=self.state.mid(),
                    ws_age_s=self.state.age_seconds(),
                )

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
        summary_interval_seconds: float = 60.0,
    ) -> BookState:
        if AsyncWebsocketClient is None or Subscribe is None:
            raise RuntimeError("xrpl-py WebSocket client unavailable")

        # Prefer native WS snapshot for initial seed (better for pure WS path).
        # Falls back to HTTP if WS one-shot fails. This helps close the
        # "rely on HTTP seed" gap.
        if seed_http:
            await self.seed_from_ws_snapshot()

        self._stop.clear()

        async with AsyncWebsocketClient(self.ws_url) as client:
            # Subscribe to bid and ask books *separately* so we get distinct
            # initial snapshot responses for each side. This addresses the top
            # "Subscribe snapshots" gap from PROBE_RESULTS.md: the subscribe
            # response(s) should now reliably contain the full current book
            # offers (result.offers + taker_gets/taker_pays) which
            # extract_offers_from_message will turn into a snapshot apply.
            for book in self.pair.subscribe_books(snapshot=True):
                await client.send(Subscribe(books=[book]))
            self._listener_task = asyncio.create_task(self._listen(client))

            deadline = time.monotonic() + seconds
            last_http = 0.0
            last_summary = time.monotonic()
            while time.monotonic() < deadline and not self._stop.is_set():
                now = time.monotonic()
                if not self.is_fresh():
                    try:
                        await self.seed_from_ws_snapshot()
                    except Exception:
                        logger.exception("Stale-book refresh failed in WS run loop")
                if now - last_http >= http_refresh_seconds:
                    try:
                        # Use WS snapshot for periodic reconciliation (addresses
                        # "Book reconciliation" gap). This keeps the incremental
                        # state aligned to a full native view and caps drift.
                        # If drift vs last known HTTP exceeds max_drift_bps we can
                        # force a full resync (future: compare to 3rd-party mid too).
                        await self.seed_from_ws_snapshot()
                        last_http = now
                        # Simple drift guard (using stats if available from probe mode)
                        if self.stats is not None:
                            # In full integration we'd compare self.state.mid() to
                            # last known good mid and decide.
                            pass
                    except Exception:
                        logger.exception("WS snapshot refresh failed during WS run (falling back)")
                        last_http = now
                if (
                    self.stats is not None
                    and summary_interval_seconds > 0
                    and now - last_summary >= summary_interval_seconds
                ):
                    bid, ask = self.state.best_prices()
                    _ = bid, ask
                    self.stats.log_summary(
                        ws_bid=bid,
                        ws_ask=ask,
                        ws_mid=self.state.mid(),
                        ws_age_s=self.state.age_seconds(),
                        ws_state_msgs=self.state.message_count,
                    )
                    last_summary = now
                await asyncio.sleep(0.25)

            self._stop.set()
            if self._listener_task:
                self._listener_task.cancel()
                try:
                    await self._listener_task
                except asyncio.CancelledError:
                    pass

        return self.state

    async def fetch_order_book(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        """Return current book (prefer live WS state; fall back to one-shot or HTTP)."""
        if self.state.age_seconds() < 10.0:  # fresh enough
            return self.state.to_order_book()
        try:
            book = await self.fetch_order_book_over_ws(limit=limit)
            self.state.apply_snapshot("bid", book.get("bids", []))
            self.state.apply_snapshot("ask", book.get("asks", []))
            return book
        except Exception:
            return await self.seed_from_http(limit)

    async def refresh_if_stale(self, max_age_s: float = 12.0, *, limit: int = 40) -> float:
        """Re-seed book when age exceeds max_age_s; returns age after refresh attempt."""
        if self.state.age_seconds() <= max_age_s:
            return self.state.age_seconds()
        try:
            await self.seed_from_ws_snapshot(limit=limit)
        except Exception:
            logger.exception("WS stale refresh failed, trying HTTP")
            try:
                await self.seed_from_http(limit=limit)
            except Exception:
                logger.exception("HTTP stale refresh failed")
        return self.state.age_seconds()

    def age_seconds(self) -> float:
        return self.state.age_seconds()

    def freshness_snapshot(self) -> Dict[str, Any]:
        return self.state.freshness_snapshot()

    def current_order_book(self) -> Dict[str, List[Dict[str, float]]]:
        return self.state.to_order_book()

    def is_fresh(self, max_age_s: Optional[float] = None) -> bool:
        """D1 guard: book state younger than max_age_s (default max_book_age_s)."""
        limit = self.max_book_age_s if max_age_s is None else max_age_s
        return self.age_seconds() < limit

    def data_freshness(self, max_age_s: float = 5.0) -> bool:
        """Data quality helper for A-S inputs: whether the book state is reasonably current."""
        return self.is_fresh(max_age_s)

    def reconnect_backoff_seconds(self) -> float:
        """Exponential backoff capped for run_forever reconnects."""
        exp = min(max(self.reconnect_count, 0), 4)
        return min(DEFAULT_RECONNECT_BASE_S * (2**exp), DEFAULT_RECONNECT_MAX_S)

    def feed_health_snapshot(self) -> Dict[str, Any]:
        return {
            "ws_reconnect_count": self.reconnect_count,
            "ws_book_is_fresh": self.is_fresh(),
            "ws_max_book_age_s": self.max_book_age_s,
        }

    def data_quality_score(self) -> float:
        """Simple 0-1 score for A-S input quality (based on age and update volume from WS)."""
        age = self.age_seconds()
        msgs = max(1, self.state.message_count)
        age_score = max(0.0, 1.0 - (age / 15.0))
        volume_score = min(1.0, msgs / 200.0)
        return round((age_score * 0.7 + volume_score * 0.3), 3)

    async def run_forever(self, *, http_refresh_seconds: float = 45.0):
        """
        Long-running loop (with reconnect backoff) for sustained WS + pure A-S operation.
        The A-S strategy itself provides the quoting protections; this is just to keep feeding it fresh book data.
        """
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                await self.run(
                    seconds=3600,
                    http_refresh_seconds=http_refresh_seconds,
                    seed_http=True,
                    summary_interval_seconds=60.0,
                )
                if time.monotonic() - started >= 120.0:
                    self.reconnect_count = 0
            except Exception:
                self.reconnect_count += 1
                self.last_reconnect_monotonic = time.monotonic()
                backoff = self.reconnect_backoff_seconds()
                logger.exception(
                    "[WS] run_forever error (reconnect #%s), backoff %.1fs...",
                    self.reconnect_count,
                    backoff,
                )
                await asyncio.sleep(backoff)
            if not self._stop.is_set():
                logger.info(
                    "[WS] Reconnecting for continued pure A-S feed (reconnect_count=%s)",
                    self.reconnect_count,
                )

    # best_and_mid and is_trustworthy inherited from BookFeed (uses connector + state)