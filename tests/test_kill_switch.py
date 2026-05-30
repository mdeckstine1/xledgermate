"""Kill switch persistence tests."""

from pathlib import Path

from risk.kill_switch import KillSwitch


def test_kill_switch_activate_and_clear(tmp_path: Path) -> None:
    path = tmp_path / "kill_switch.json"
    ks = KillSwitch(path=path)
    assert not ks.is_active()

    ks.activate("test drawdown")
    assert ks.is_active()
    assert "drawdown" in ks.reason.lower()

    ks2 = KillSwitch(path=path)
    assert ks2.is_active()

    ks2.clear("operator reset")
    assert not ks2.is_active()


def test_kill_switch_reload_picks_up_disk_change(tmp_path: Path) -> None:
    path = tmp_path / "kill_switch.json"
    ks = KillSwitch(path=path)
    ks.activate("remote")
    ks.clear("cleared")
    assert not KillSwitch(path=path).is_active()
