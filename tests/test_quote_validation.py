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


def test_bid_at_touch_limit_passes_with_tolerance() -> None:
    """Bid clamped to -0.50% vs touch must not fail on float rounding."""
    best_bid = 1.326370
    price = best_bid * 0.995  # exact -0.50% boundary
    intents = [QuoteIntent(level=1, side="bid", price=price, size_xrp=2.0)]
    result = validate_quotes_against_book(
        intents,
        mid_price=1.327,
        best_bid=best_bid,
        best_ask=1.328,
        max_worse_than_touch_pct=0.50,
    )
    assert result.ok, result.errors


def test_bid_too_far_below_touch_fails() -> None:
    best_bid = 1.326370
    price = best_bid * 0.994  # -0.60%
    intents = [QuoteIntent(level=1, side="bid", price=price, size_xrp=2.0)]
    result = validate_quotes_against_book(
        intents,
        mid_price=1.327,
        best_bid=best_bid,
        best_ask=1.328,
        max_worse_than_touch_pct=0.50,
    )
    assert not result.ok
    assert any("below best bid" in e for e in result.errors)


def test_no_mid_is_book_unreliable() -> None:
    result = validate_quotes_against_book(
        [],
        mid_price=None,
        best_bid=1.17,
        best_ask=1.18,
    )
    assert not result.ok
    assert result.book_unreliable


def test_inverted_book_is_book_unreliable() -> None:
    result = validate_quotes_against_book(
        [],
        mid_price=0.28,
        best_bid=1.164,
        best_ask=0.283,
    )
    assert not result.ok
    assert result.book_unreliable
    assert any("Inverted" in e for e in result.errors)


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
    assert not result.book_unreliable
    assert any("above best ask" in e for e in result.errors)
