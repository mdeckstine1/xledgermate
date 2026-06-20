"""Tests for A2.3 acquire-mode ask brake."""

from experimental.ws_feed.acquire_ask_brake import resolve_acquire_ask_brake


def test_brake_active_on_solo_accumulate() -> None:
    result = resolve_acquire_ask_brake(
        g7_solo_acquisition=True,
        inventory_posture="balanced",
    )
    assert result.active is True
    assert result.blocked is True
    assert "bid only" in result.reason


def test_brake_active_rlusd_heavy() -> None:
    result = resolve_acquire_ask_brake(
        g7_solo_acquisition=True,
        inventory_posture="rlusd_heavy",
    )
    assert result.blocked is True


def test_brake_inactive_xrp_heavy() -> None:
    result = resolve_acquire_ask_brake(
        g7_solo_acquisition=False,
        inventory_posture="xrp_heavy",
    )
    assert result.active is False
    assert result.blocked is False


def test_brake_inactive_without_solo() -> None:
    result = resolve_acquire_ask_brake(
        g7_solo_acquisition=False,
        inventory_posture="balanced",
    )
    assert result.blocked is False
