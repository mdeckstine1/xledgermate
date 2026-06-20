"""Tests for A3 stale-quote guard."""

from datetime import datetime, timedelta, timezone

from connectors.xrpl_connector import OpenOffer
from experimental.ws_feed.offer_age_tracker import OfferAgeTracker
from experimental.ws_feed.stale_quote_guard import (
    WS_MAX_QUOTE_AGE_ASK_S,
    WS_MAX_QUOTE_AGE_BID_S,
    WS_MID_MOVE_REFRESH_BPS,
    WS_TOXIC_ASK_MAX_AGE_S,
    stale_quote_cancel_decisions,
    stale_quote_sequences_to_cancel,
)


def _placed(now: datetime, *, seconds_ago: float) -> datetime:
    return now - timedelta(seconds=seconds_ago)


def test_ask_at_127s_cancels() -> None:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    tracker = OfferAgeTracker()
    tracker.record_place("ask", placed_utc=_placed(now, seconds_ago=127.0), sequence=10)
    offers = [OpenOffer(sequence=10, side="ask", price=1.11, size_xrp=10.0)]
    seqs = stale_quote_sequences_to_cancel(
        offers,
        tracker,
        now=now,
        toxic_ratio_30s=0.0,
        mid=1.10,
        last_sync_mid=1.10,
    )
    assert seqs == [10]
    decisions = stale_quote_cancel_decisions(
        offers, tracker, now=now, toxic_ratio_30s=0.0, mid=1.10, last_sync_mid=1.10
    )
    assert decisions[0].reason.startswith("max_age")


def test_bid_at_50s_keeps() -> None:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    tracker = OfferAgeTracker()
    tracker.record_place("bid", placed_utc=_placed(now, seconds_ago=50.0), sequence=20)
    offers = [OpenOffer(sequence=20, side="bid", price=1.10, size_xrp=10.0)]
    seqs = stale_quote_sequences_to_cancel(
        offers,
        tracker,
        now=now,
        toxic_ratio_30s=0.0,
        mid=1.10,
        last_sync_mid=1.10,
    )
    assert seqs == []
    assert 50.0 < WS_MAX_QUOTE_AGE_BID_S


def test_ask_at_50s_with_elevated_toxic_cancels() -> None:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    tracker = OfferAgeTracker()
    tracker.record_place("ask", placed_utc=_placed(now, seconds_ago=50.0), sequence=30)
    offers = [OpenOffer(sequence=30, side="ask", price=1.11, size_xrp=10.0)]
    seqs = stale_quote_sequences_to_cancel(
        offers,
        tracker,
        now=now,
        toxic_ratio_30s=0.30,
        mid=1.10,
        last_sync_mid=1.10,
    )
    assert seqs == [30]
    assert 50.0 > WS_TOXIC_ASK_MAX_AGE_S
    assert 50.0 < WS_MAX_QUOTE_AGE_ASK_S


def test_mid_move_10bps_and_age_35s_cancels() -> None:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    tracker = OfferAgeTracker()
    tracker.record_place("bid", placed_utc=_placed(now, seconds_ago=35.0), sequence=40)
    offers = [OpenOffer(sequence=40, side="bid", price=1.10, size_xrp=10.0)]
    last_sync = 1.2750
    mid = last_sync * (1.0 + (WS_MID_MOVE_REFRESH_BPS + 2.0) / 10_000.0)
    seqs = stale_quote_sequences_to_cancel(
        offers,
        tracker,
        now=now,
        toxic_ratio_30s=0.0,
        mid=mid,
        last_sync_mid=last_sync,
    )
    assert seqs == [40]
    decisions = stale_quote_cancel_decisions(
        offers, tracker, now=now, toxic_ratio_30s=0.0, mid=mid, last_sync_mid=last_sync
    )
    assert "mid_move" in decisions[0].reason


def test_no_age_tracking_skips_offer() -> None:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    tracker = OfferAgeTracker()
    offers = [OpenOffer(sequence=99, side="ask", price=1.11, size_xrp=10.0)]
    assert stale_quote_sequences_to_cancel(
        offers, tracker, now=now, toxic_ratio_30s=0.5, mid=1.10, last_sync_mid=1.10
    ) == []


def test_dedupes_duplicate_sequences() -> None:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    tracker = OfferAgeTracker()
    tracker.record_place("ask", placed_utc=_placed(now, seconds_ago=200.0), sequence=5)
    offers = [
        OpenOffer(sequence=5, side="ask", price=1.11, size_xrp=10.0),
        OpenOffer(sequence=5, side="ask", price=1.11, size_xrp=10.0),
    ]
    assert stale_quote_sequences_to_cancel(
        offers, tracker, now=now, toxic_ratio_30s=0.0, mid=1.10, last_sync_mid=1.10
    ) == [5]


def test_solo_lane_ask_at_75s_keeps() -> None:
    from experimental.ws_feed.stale_quote_guard import WS_SOLO_MAX_QUOTE_AGE_ASK_S

    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    tracker = OfferAgeTracker()
    tracker.record_place("ask", placed_utc=_placed(now, seconds_ago=75.0), sequence=50)
    offers = [OpenOffer(sequence=50, side="ask", price=1.11, size_xrp=10.0)]
    assert stale_quote_sequences_to_cancel(
        offers,
        tracker,
        now=now,
        toxic_ratio_30s=0.0,
        mid=1.10,
        last_sync_mid=1.10,
        peer_lane_empty=True,
    ) == []
    assert 75.0 < WS_SOLO_MAX_QUOTE_AGE_ASK_S


def test_solo_lane_ask_at_75s_cancels_without_solo_flag() -> None:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    tracker = OfferAgeTracker()
    tracker.record_place("ask", placed_utc=_placed(now, seconds_ago=75.0), sequence=51)
    offers = [OpenOffer(sequence=51, side="ask", price=1.11, size_xrp=10.0)]
    assert stale_quote_sequences_to_cancel(
        offers,
        tracker,
        now=now,
        toxic_ratio_30s=0.0,
        mid=1.10,
        last_sync_mid=1.10,
        peer_lane_empty=False,
    ) == [51]
