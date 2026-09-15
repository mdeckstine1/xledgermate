"""FX session clock — Tokyo 00:00 / London 07:00 / NY 13:00 UTC."""

from datetime import datetime, timezone

from alpha.decision.fx_session import current_fx_session, move_window_hours
from config.settings import BotConfig


def test_tokyo_session_at_0100():
    now = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
    sess = current_fx_session(now)
    assert sess.name == "tokyo"
    assert sess.open_hour == 0
    assert 0.9 < sess.hours_elapsed < 1.1


def test_london_session_at_0800():
    now = datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)
    sess = current_fx_session(now)
    assert sess.name == "london"
    assert sess.open_hour == 7
    assert 0.9 < sess.hours_elapsed < 1.1
    assert sess.next_open_utc.hour == 13


def test_ny_session_at_1500():
    now = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)
    sess = current_fx_session(now)
    assert sess.name == "new_york"
    assert sess.open_hour == 13
    assert 1.9 < sess.hours_elapsed < 2.1


def test_move_window_uses_session_not_24h():
    cfg = BotConfig(alpha_fx_session_clock_enabled=True)
    now = datetime(2026, 9, 15, 8, 30, tzinfo=timezone.utc)
    hours, name = move_window_hours(cfg, now=now)
    assert name == "london"
    assert 1.4 < hours < 1.6


def test_move_window_fallback_24h():
    cfg = BotConfig(
        alpha_fx_session_clock_enabled=False,
        alpha_accumulation_harvest_move_hours=24.0,
    )
    hours, name = move_window_hours(cfg)
    assert name == "24h"
    assert hours == 24.0
