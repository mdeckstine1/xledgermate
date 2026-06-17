"""Tests for M2 lab OfferAgeTracker."""

from datetime import datetime, timedelta, timezone

from experimental.ws_feed.offer_age_tracker import OfferAgeTracker


def test_age_seconds_at_detected_fill() -> None:
    tracker = OfferAgeTracker()
    placed = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
    detected = placed + timedelta(seconds=4.5)
    tracker.record_place("bid", placed_utc=placed, sequence=1001)
    age = tracker.effective_quote_age_at_fill_seconds("bid", fill_detected_utc=detected)
    assert age == 4.5


def test_unknown_side_returns_none() -> None:
    tracker = OfferAgeTracker()
    assert tracker.age_seconds_at("bid") is None


def test_clear_side() -> None:
    tracker = OfferAgeTracker()
    tracker.record_place("ask")
    assert tracker.last_placed_utc("ask") is not None
    tracker.clear_side("ask")
    assert tracker.last_placed_utc("ask") is None
