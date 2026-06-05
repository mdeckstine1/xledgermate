from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

try:
    from xrpl.models.currencies import IssuedCurrency, XRP
    from xrpl.models.requests.subscribe import SubscribeBook
except ImportError:  # pragma: no cover
    IssuedCurrency = None
    XRP = None
    SubscribeBook = None


@dataclass(frozen=True)
class RlusdXrpPair:
    rlusd_issuer: str
    rlusd_currency: str

    def issued_rlusd_code(self) -> str:
        code = (self.rlusd_currency or "RLUSD").strip()
        if len(code) <= 3:
            return code
        return code[:3]

    def subscribe_books(self, *, snapshot: bool = True) -> List["SubscribeBook"]:
        """Both sides of the RLUSD/XRP book for XRPL subscribe."""
        if SubscribeBook is None or XRP is None or IssuedCurrency is None:
            raise RuntimeError("xrpl-py is required for WebSocket book subscribe")

        rlusd = IssuedCurrency(currency=self.issued_rlusd_code(), issuer=self.rlusd_issuer)
        xrp = XRP()
        ask_book = SubscribeBook(
            taker_gets=xrp,
            taker_pays=rlusd,
            snapshot=snapshot,
            both=True,
        )
        bid_book = SubscribeBook(
            taker_gets=rlusd,
            taker_pays=xrp,
            snapshot=snapshot,
            both=True,
        )
        return [ask_book, bid_book]

    def book_side_labels(self) -> Tuple[str, str]:
        return ("ask", "bid")