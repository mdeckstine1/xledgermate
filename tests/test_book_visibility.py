"""Book visibility helpers for queue position."""

from utils.book_visibility import (
    invisible_offer_sequences,
    offer_vs_touch_bps,
    quote_visibility,
)


def test_bid_below_touch_is_invisible() -> None:
    bps = offer_vs_touch_bps(
        side="bid", price=1.3456, best_bid=1.3472, best_ask=1.3480
    )
    assert bps is not None
    assert bps < -10.0
    offers = [
        {
            "side": "bid",
            "price": 1.3456,
            "vs_touch_bps": bps,
        }
    ]
    visible, worst, summary = quote_visibility(offers)
    assert not visible
    assert worst > 8.0
    assert "storefront" in summary.lower() or "behind" in summary.lower()


def test_bid_at_touch_is_visible() -> None:
    offers = [{"side": "bid", "price": 1.3472, "vs_touch_bps": 0.0}]
    visible, worst, _ = quote_visibility(offers)
    assert visible
    assert worst == 0.0


def test_invisible_offer_sequences_stale_ask() -> None:
    class Offer:
        sequence = 99
        side = "ask"
        price = 1.22

    stale = invisible_offer_sequences(
        [Offer()],
        best_bid=1.20,
        best_ask=1.203,
        max_visible_bps=8.0,
    )
    assert stale == [99]
