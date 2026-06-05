from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from connectors.xrpl_connector import XRPLConnector


@dataclass
class HttpPollBookFeed:
    """Baseline: same HTTP BookOffers path the production engine uses."""

    connector: XRPLConnector
    last_fetch_monotonic: float = 0.0
    last_latency_ms: float = 0.0

    async def fetch_order_book(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        started = time.monotonic()
        book = await self.connector.fetch_xrp_rlusd_order_book(limit=limit)
        self.last_fetch_monotonic = time.monotonic()
        self.last_latency_ms = (self.last_fetch_monotonic - started) * 1000.0
        return book

    def best_and_mid(
        self, book: Dict[str, List[Dict[str, float]]]
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        bid, ask = self.connector.compute_best_prices(book)
        mid = self.connector.compute_mid_price(book)
        return bid, ask, mid