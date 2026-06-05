from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from connectors.xrpl_connector import XRPLConnector


@dataclass
class BookState:
    """In-memory bid/ask levels; keys are rounded price ticks for dedup."""

    connector: XRPLConnector
    bids: Dict[float, Dict[str, float]] = field(default_factory=dict)
    asks: Dict[float, Dict[str, float]] = field(default_factory=dict)
    last_update_monotonic: float = 0.0
    message_count: int = 0

    def apply_snapshot(self, side: str, levels: List[Dict[str, float]]) -> None:
        book = self.asks if side == "ask" else self.bids
        book.clear()
        for row in levels:
            price = float(row["price"])
            book[price] = {"price": price, "size": float(row["size"]), "side": side}
        self._touch()

    def apply_levels(self, side: str, levels: List[Dict[str, float]], *, deleted: bool) -> None:
        book = self.asks if side == "ask" else self.bids
        for row in levels:
            price = float(row["price"])
            if deleted or float(row.get("size", 0)) <= 0:
                book.pop(price, None)
            else:
                book[price] = {
                    "price": price,
                    "size": float(row["size"]),
                    "side": side,
                }
        self._touch()

    def _touch(self) -> None:
        self.last_update_monotonic = time.monotonic()
        self.message_count += 1

    def to_order_book(self) -> Dict[str, List[Dict[str, float]]]:
        return {
            "bids": sorted(self.bids.values(), key=lambda x: x["price"], reverse=True),
            "asks": sorted(self.asks.values(), key=lambda x: x["price"]),
        }

    def best_prices(self) -> tuple[Optional[float], Optional[float]]:
        book = self.to_order_book()
        return self.connector.compute_best_prices(book)

    def mid(self) -> Optional[float]:
        return self.connector.compute_mid_price(self.to_order_book())

    def age_seconds(self) -> float:
        if self.last_update_monotonic <= 0:
            return float("inf")
        return max(0.0, time.monotonic() - self.last_update_monotonic)