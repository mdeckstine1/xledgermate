"""Tests for M2/M6 OfferAgeTracker."""

from datetime import datetime, timedelta, timezone

from connectors.xrpl_connector import OpenOffer
from core.runtime_state import QuoteIntent
from engine.order_sync import find_offer_sequence_for_intent
from experimental.ws_feed.offer_age_tracker import OfferAgeTracker


def test_age_seconds_at_detected_fill() -> None:
    tracker = OfferAgeTracker()
    placed = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
    detected = placed + timedelta(seconds=4.5)
    tracker.record_place("bid", placed_utc=placed, sequence=1001)
    age = tracker.effective_quote_age_at_fill_seconds("bid", fill_detected_utc=detected)
    assert age == 4.5


def test_m6_sequence_survives_side_re_place() -> None:
    """Fill age uses sequence timestamp even after a newer side place."""
    tracker = OfferAgeTracker()
    t0 = datetime(2026, 6, 18, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=30)
    tracker.record_place("bid", placed_utc=t0, sequence=100)
    tracker.record_place("bid", placed_utc=t1, sequence=200)
    fill_time = t0 + timedelta(seconds=35)
    age = tracker.effective_quote_age_at_fill_seconds(
        "bid",
        fill_detected_utc=fill_time,
        sequence=100,
    )
    assert age == 35.0
    age_latest = tracker.effective_quote_age_at_fill_seconds("bid", fill_detected_utc=fill_time)
    assert age_latest == 5.0


def test_forget_sequence_on_cancel() -> None:
    tracker = OfferAgeTracker()
    placed = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    tracker.record_place("ask", placed_utc=placed, sequence=55)
    tracker.forget_sequence(55)
    assert tracker.effective_quote_age_at_fill_seconds("ask", sequence=55) is None
    assert tracker.snapshot()["ask_sequence"] is None


def test_unknown_side_returns_none() -> None:
    tracker = OfferAgeTracker()
    assert tracker.age_seconds_at("bid") is None


def test_clear_side() -> None:
    tracker = OfferAgeTracker()
    tracker.record_place("ask", sequence=9)
    assert tracker.last_placed_utc("ask") is not None
    tracker.clear_side("ask")
    assert tracker.last_placed_utc("ask") is None


def test_forget_sequence_after_fill_consumes_side() -> None:
    tracker = OfferAgeTracker()
    placed = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    tracker.record_place("ask", placed_utc=placed, sequence=77)
    tracker.forget_sequence(77)
    assert tracker.last_sequence_for_side("ask") is None
    assert tracker.effective_quote_age_at_fill_seconds("ask") is None


def test_find_offer_sequence_for_intent() -> None:
    intent = QuoteIntent(level=1, side="bid", price=2.18, size_xrp=10.0)
    offers = [
        OpenOffer(sequence=42, side="bid", price=2.18, size_xrp=10.0),
        OpenOffer(sequence=43, side="ask", price=2.19, size_xrp=8.0),
    ]
    assert find_offer_sequence_for_intent(
        intent, offers, price_tolerance_pct=0.1, size_tolerance_xrp=0.5
    ) == 42
