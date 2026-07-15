"""Drawdown monitor tests."""

from datetime import datetime

from pytest import approx

from risk.drawdown import (
    DrawdownMonitor,
    is_valid_portfolio_mid,
    portfolio_value_xrp,
)


def test_portfolio_value_xrp() -> None:
    assert portfolio_value_xrp(100.0, 66.0, 1.32) == approx(150.0)


def test_is_valid_portfolio_mid() -> None:
    assert is_valid_portfolio_mid(1.18)
    assert not is_valid_portfolio_mid(None)
    assert not is_valid_portfolio_mid(0.0)
    assert not is_valid_portfolio_mid(200.0)


def test_drawdown_triggers_at_threshold() -> None:
    mon = DrawdownMonitor(max_drawdown_percent=10.0)
    mon.update_portfolio(100.0, 0.0, 1.0)
    mon.update_portfolio(85.0, 0.0, 1.0)
    assert mon.get_drawdown_percent() == approx(15.0)
    assert mon.is_kill_switch_triggered()


def test_drawdown_reset_baseline() -> None:
    mon = DrawdownMonitor(max_drawdown_percent=10.0)
    mon.update_portfolio(100.0, 0.0, 1.0)
    mon.update_portfolio(88.0, 0.0, 1.0)
    mon.reset_baseline(88.0)
    mon.update_portfolio(88.0, 0.0, 1.0)
    assert mon.get_drawdown_percent() == approx(0.0)
    assert not mon.is_kill_switch_triggered()


def test_invalid_mid_does_not_trigger_false_drawdown_kill() -> None:
    """Stale book (mid None/0) must not mark RLUSD at zero and trip kill."""
    mon = DrawdownMonitor(max_drawdown_percent=10.0)
    _, ok = mon.update_portfolio(146.0, 117.0, 1.20)
    assert ok
    assert mon.get_drawdown_percent() == approx(0.0)

    value, ok = mon.update_portfolio(146.0, 117.0, None)
    assert not ok
    assert value == approx(243.5)
    assert mon.get_drawdown_percent() == approx(0.0)
    assert not mon.is_kill_switch_triggered()

    _, ok = mon.update_portfolio(146.0, 117.0, 0.0)
    assert not ok
    assert not mon.is_kill_switch_triggered()


def test_invalid_mid_before_first_mark_does_not_set_baseline() -> None:
    mon = DrawdownMonitor(max_drawdown_percent=10.0)
    _, ok = mon.update_portfolio(146.0, 117.0, None)
    assert not ok
    assert mon.daily_start_value is None
    assert not mon.is_kill_switch_triggered()


def test_restore_daily_baseline_preserves_restart_drawdown() -> None:
    mon = DrawdownMonitor(max_drawdown_percent=10.0)
    restored = mon.restore_daily_baseline(
        daily_start_value=100.0,
        daily_start_time_utc=datetime.utcnow().isoformat(),
        current_value=95.0,
    )
    assert restored
    assert mon.get_drawdown_percent() == approx(5.0)

    mon.update_portfolio(89.0, 0.0, 1.0)
    assert mon.get_drawdown_percent() == approx(11.0)
    assert mon.is_kill_switch_triggered()
