"""Fill quality tracker reset."""

from strategy.fill_quality import FillQualityTracker


def test_fill_quality_reset_clears_window() -> None:
    tracker = FillQualityTracker()
    tracker.note_fill(
        side="BUY",
        xrp_amount=10.0,
        price=1.2,
        mid_at_fill=1.2,
    )
    tracker.note_mid(1.19)
    state = tracker.assess()
    assert state.recent_fills >= 1

    tracker.reset()
    state = tracker.assess()
    assert state.recent_fills == 0
    assert state.summary == "No recent fills"
