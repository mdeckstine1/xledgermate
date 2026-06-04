"""Book mid must not use crossed/stale ask as RLUSD/XRP."""

from connectors.xrpl_connector import (
    is_book_crossed,
    is_trustworthy_rlusd_mid,
)
from connectors.xrpl_connector import XRPLConnector


def test_crossed_book_returns_no_mid() -> None:
    book = {
        "bids": [{"price": 1.164, "size": 100.0}],
        "asks": [{"price": 0.283, "size": 50.0}],
    }
    conn = XRPLConnector.__new__(XRPLConnector)
    assert is_book_crossed(1.164, 0.283)
    assert conn.compute_mid_price(book) is None
    assert not is_trustworthy_rlusd_mid(0.283, best_bid=1.164, best_ask=0.283)


def test_normal_book_mid() -> None:
    book = {
        "bids": [{"price": 1.179, "size": 100.0}],
        "asks": [{"price": 1.181, "size": 50.0}],
    }
    conn = XRPLConnector.__new__(XRPLConnector)
    mid = conn.compute_mid_price(book)
    assert mid is not None
    assert is_trustworthy_rlusd_mid(mid, best_bid=1.179, best_ask=1.181)
