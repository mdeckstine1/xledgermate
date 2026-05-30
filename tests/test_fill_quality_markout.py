"""Tests for multi-horizon fill quality markout."""

from datetime import datetime, timedelta, timezone

from strategy.fill_quality import FillQualityTracker


def test_markout_30s_classifies_toxic_sell() -> None:
    tracker = FillQualityTracker(max_records=5)
    tracker.set_toxic_threshold_pct(0.04)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tracker.note_fill(
        side="SELL",
        xrp_amount=50.0,
        price=1.33,
        mid_at_fill=1.33,
        filled_at=t0,
    )
    tracker.note_mid(1.33, now=t0 + timedelta(seconds=5))
    tracker.note_mid(1.34, now=t0 + timedelta(seconds=31))
    state = tracker.assess()
    assert state.recent_fills == 1
    assert state.toxic_fills == 1
    assert state.toxic_ratio_30s == 1.0


def test_markout_visible_at_30s_before_5m_archive() -> None:
    tracker = FillQualityTracker(max_records=5)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    tracker.note_fill(
        side="BUY",
        xrp_amount=10.0,
        price=1.30,
        mid_at_fill=1.30,
        filled_at=t0,
    )
    tracker.note_mid(1.30, now=t0 + timedelta(seconds=31))
    assert tracker.assess().recent_fills == 1
    assert len(tracker._records) == 0
    tracker.note_mid(1.30, now=t0 + timedelta(minutes=5, seconds=1))
    assert len(tracker._records) == 1
