from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from connectors.xrpl_connector import XRPLConnector
from experimental.ws_feed.book_feed import BookFeed


@dataclass
class HttpPollBookFeed(BookFeed):
    """Baseline: same HTTP BookOffers path the production engine uses.

    Implements the common BookFeed interface so engine/replay can treat
    poll and WS (and future 3rd-party or aggregated feeds) uniformly.
    """

    connector: XRPLConnector
    last_fetch_monotonic: float = 0.0
    last_latency_ms: float = 0.0

    async def fetch_order_book(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        started = time.monotonic()
        book = await self.connector.fetch_xrp_rlusd_order_book(limit=limit)
        self.last_fetch_monotonic = time.monotonic()
        self.last_latency_ms = (self.last_fetch_monotonic - started) * 1000.0
        return book

    def age_seconds(self) -> float:
        if self.last_fetch_monotonic <= 0:
            return float("inf")
        return max(0.0, time.monotonic() - self.last_fetch_monotonic)

    def current_order_book(self) -> Dict[str, List[Dict[str, float]]]:
        # For pure poll, we don't keep state; caller should use the book
        # returned from the last fetch_order_book call. For interface
        # compatibility we raise – real usage always passes the book.
        raise NotImplementedError("HttpPollBookFeed does not cache state; pass the book from fetch_order_book()")

    # best_and_mid is inherited from BookFeed (delegates to connector)