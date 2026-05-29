"""Live-book spread validation."""

from core.runtime_state import QuoteIntent
from utils.quote_validation import validate_quotes_against_book


def test_good_ask_near_touch_passes() -> None:
    mid = 1.32
    best_bid = 1.319
    best_ask = 1.320
    intents = [QuoteIntent(level=1, side="ask", price=1.3205, size_xrp=50.0)]
    result = validate_quotes_against_book(
        intents,
        mid_price=mid,
        best_bid=best_bid,
        best_ask=best_ask,
    )
    assert result.ok
    assert not result.errors


def test_absurd_ask_fails() -> None:
    mid = 1.32
    best_bid = 1.319
    best_ask = 1.320
    intents = [QuoteIntent(level=1, side="ask", price=1.42, size_xrp=50.0)]
    result = validate_quotes_against_book(
        intents,
        mid_price=mid,
        best_bid=best_bid,
        best_ask=best_ask,
        max_worse_than_touch_pct=0.50,
    )
    assert not result.ok
    assert any("above best ask" in e for e in result.errors)
