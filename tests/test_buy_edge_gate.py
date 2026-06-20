"""Tests for A2.2 buy-side skim gate."""

from experimental.ws_feed.buy_edge_gate import (
    MIN_BUY_EDGE_BPS,
    bid_implied_edge_bps,
    resolve_buy_edge_gate,
    should_apply_buy_edge_gate,
)


def test_bid_implied_edge_bps_below_mid() -> None:
    edge = bid_implied_edge_bps(l1_bid_price=1.099, mid=1.10)
    assert edge is not None
    assert edge > 0


def test_bid_implied_edge_bps_at_mid_is_zero() -> None:
    assert bid_implied_edge_bps(l1_bid_price=1.10, mid=1.10) == 0.0


def test_should_apply_solo_accumulate_only() -> None:
    assert should_apply_buy_edge_gate(
        g7_solo_acquisition=True,
        inventory_posture="balanced",
    )
    assert should_apply_buy_edge_gate(
        g7_solo_acquisition=True,
        inventory_posture="rlusd_heavy",
    )
    assert not should_apply_buy_edge_gate(
        g7_solo_acquisition=False,
        inventory_posture="balanced",
    )
    assert not should_apply_buy_edge_gate(
        g7_solo_acquisition=True,
        inventory_posture="xrp_heavy",
    )


def test_gate_blocks_bid_too_close_to_mid() -> None:
    result = resolve_buy_edge_gate(
        l1_bid_price=1.09995,
        mid=1.10,
        g7_solo_acquisition=True,
        inventory_posture="balanced",
        min_buy_edge_bps=MIN_BUY_EDGE_BPS,
    )
    assert result.active is True
    assert result.blocked is True
    assert "bid_edge" in result.reason


def test_gate_allows_bid_with_edge() -> None:
    result = resolve_buy_edge_gate(
        l1_bid_price=1.098,
        mid=1.10,
        g7_solo_acquisition=True,
        inventory_posture="balanced",
    )
    assert result.active is True
    assert result.blocked is False
    assert result.implied_edge_bps is not None
    assert result.implied_edge_bps >= MIN_BUY_EDGE_BPS


def test_session_buy_capture_brake() -> None:
    result = resolve_buy_edge_gate(
        l1_bid_price=1.098,
        mid=1.10,
        g7_solo_acquisition=True,
        inventory_posture="balanced",
        session_buy_capture_xrp=-0.01,
    )
    assert result.blocked is True
    assert "session_buy_cap" in result.reason


def test_gate_inactive_outside_solo_acquire() -> None:
    result = resolve_buy_edge_gate(
        l1_bid_price=1.09995,
        mid=1.10,
        g7_solo_acquisition=False,
        inventory_posture="balanced",
    )
    assert result.active is False
    assert result.blocked is False
