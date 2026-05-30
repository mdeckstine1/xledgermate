"""Drawdown monitor tests."""

from pytest import approx

from risk.drawdown import DrawdownMonitor, portfolio_value_xrp


def test_portfolio_value_xrp() -> None:
    assert portfolio_value_xrp(100.0, 66.0, 1.32) == approx(150.0)


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
