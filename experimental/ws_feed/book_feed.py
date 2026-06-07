from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from connectors.xrpl_connector import XRPLConnector


class BookFeed(ABC):
    """
    Abstract interface for book data sources (poll, WS, future 3rd party, etc.).

    Both HttpPollBookFeed and WsBookFeed implement this so the engine
    (or replay/simulation) can swap sources behind a book_feed_mode flag
    without changing quoting logic.

    This is the foundation for "add what we need for ws book" + future
    expansion to competitive MM (multi-venue aggregation, external signals,
    full L2, etc.).

    Current main run data (150+ fills long run with hard gate) is used to
    validate: e.g., does a fresher WS source reduce false "edge thin" /
    "0 quotes" periods seen in the poll-based run?
    """

    connector: XRPLConnector

    @abstractmethod
    async def fetch_order_book(self, limit: int = 40) -> Dict[str, List[Dict[str, float]]]:
        """Return normalized book dict with 'bids' and 'asks'."""
        ...

    def best_and_mid(
        self, book: Dict[str, List[Dict[str, float]]]
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Convenience: best bid, best ask, mid from a book snapshot."""
        bid, ask = self.connector.compute_best_prices(book)
        mid = self.connector.compute_mid_price(book)
        return bid, ask, mid

    @abstractmethod
    def age_seconds(self) -> float:
        """How stale is the current book state? (inf if never updated)"""
        ...

    def is_trustworthy(self, book: Optional[Dict[str, List[Dict[str, float]]]] = None) -> bool:
        """
        Reuse the main codebase's trustworthiness check.
        WS feed should expose fresher books, so this can flip true more often
        on marginal books where poll was stale.
        """
        if book is None:
            book = self.current_order_book()
        # Delegate to connector's existing logic (is_trustworthy_rlusd_mid etc.)
        mid = self.connector.compute_mid_price(book)
        bid, ask = self.connector.compute_best_prices(book)
        # Import here to avoid circular; main code has is_trustworthy_rlusd_mid
        try:
            from connectors.xrpl_connector import is_trustworthy_rlusd_mid
            return is_trustworthy_rlusd_mid(mid, best_bid=bid, best_ask=ask)
        except Exception:
            return mid is not None and bid is not None and ask is not None

    @abstractmethod
    def current_order_book(self) -> Dict[str, List[Dict[str, float]]]:
        """Return the latest book state (may be from WS state or last poll)."""
        ...

    def record_metrics(self) -> Dict[str, float]:
        """Optional hook for logging age, drift, apply rate etc. (used by probes/replay)."""
        return {
            "age_s": self.age_seconds(),
        }
