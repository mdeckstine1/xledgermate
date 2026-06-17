"""Tests for Telegram quiet-hours scheduling."""

from __future__ import annotations

from datetime import datetime, timezone

from monitoring.telegram_schedule import (
    hourly_report_allowed_now,
    is_quiet_hour,
    quiet_hours_label,
)


def test_is_quiet_hour_overnight_window() -> None:
    assert is_quiet_hour(23, start_hour=22, end_hour=7)
    assert is_quiet_hour(3, start_hour=22, end_hour=7)
    assert not is_quiet_hour(12, start_hour=22, end_hour=7)
    assert not is_quiet_hour(7, start_hour=22, end_hour=7)
    assert is_quiet_hour(22, start_hour=22, end_hour=7)


def test_is_quiet_hour_same_day_window() -> None:
    assert is_quiet_hour(10, start_hour=9, end_hour=17)
    assert not is_quiet_hour(8, start_hour=9, end_hour=17)
    assert not is_quiet_hour(17, start_hour=9, end_hour=17)


def test_hourly_report_allowed_respects_quiet() -> None:
    noon = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
    night = datetime(2026, 6, 17, 3, 0, tzinfo=timezone.utc)
    assert hourly_report_allowed_now(
        quiet_hours_enabled=True,
        quiet_start_hour=22,
        quiet_end_hour=7,
        now=noon,
    )
    assert not hourly_report_allowed_now(
        quiet_hours_enabled=True,
        quiet_start_hour=22,
        quiet_end_hour=7,
        now=night,
    )
    assert hourly_report_allowed_now(
        quiet_hours_enabled=False,
        quiet_start_hour=22,
        quiet_end_hour=7,
        now=night,
    )


def test_quiet_hours_label() -> None:
    assert quiet_hours_label(22, 7) == "22:00–07:00 UTC"
