"""Tests for A2.3b sell-side skim gate."""

from experimental.ws_feed.sell_edge_gate import (
    MIN_SELL_EDGE_BPS,
    ask_implied_edge_bps,
    resolve_sell_edge_gate,
    should_apply_sell_edge_gate,
)


def test_ask_implied_edge_bps_above_mid() -> None:
    edge = ask_implied_edge_bps(l1_ask_price=1.101, mid=1.10)
    assert edge is not None
    assert edge > 0


def test_ask_implied_edge_bps_at_mid_is_zero() -> None:
    assert ask_implied_edge_bps(l1_ask_price=1.10, mid=1.10) == 0.0


def test_should_apply_solo_empty_lane_only() -> None:
    assert should_apply_sell_edge_gate(peer_lane_empty=True)
    assert not should_apply_sell_edge_gate(peer_lane_empty=False)


def test_gate_blocks_ask_too_close_to_mid() -> None:
    result = resolve_sell_edge_gate(
        l1_ask_price=1.10005,
        mid=1.10,
        peer_lane_empty=True,
    )
    assert result.active is True
    assert result.blocked is True
    assert "ask_edge" in result.reason


def test_gate_allows_ask_with_edge() -> None:
    result = resolve_sell_edge_gate(
        l1_ask_price=1.102,
        mid=1.10,
        peer_lane_empty=True,
    )
    assert result.active is True
    assert result.blocked is False
    assert result.implied_edge_bps is not None
    assert result.implied_edge_bps >= MIN_SELL_EDGE_BPS


def test_session_sell_capture_brake() -> None:
    result = resolve_sell_edge_gate(
        l1_ask_price=1.102,
        mid=1.10,
        peer_lane_empty=True,
        session_sell_capture_xrp=-0.01,
    )
    assert result.blocked is True
    assert "session_sell_cap" in result.reason


def test_gate_inactive_with_peers() -> None:
    result = resolve_sell_edge_gate(
        l1_ask_price=1.10005,
        mid=1.10,
        peer_lane_empty=False,
    )
    assert result.active is False
    assert result.blocked is False
