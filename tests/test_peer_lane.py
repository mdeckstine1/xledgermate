"""Tests for G1 posted-touch peer lane helpers."""

from experimental.market_analysis.peer_lane import (
    aggregate_peer_pressure,
    compute_touch_by_account,
    detect_fled_touch,
    our_lane_from_runtime,
    select_peer_lane,
)


def test_our_lane_from_intents_max_l1() -> None:
    lane = our_lane_from_runtime(
        quote_intents=[
            {"level": 1, "active": True, "size_xrp": 80.0},
            {"level": 1, "active": True, "size_xrp": 120.0},
            {"level": 2, "active": True, "size_xrp": 200.0},
        ],
    )
    assert lane == 120.0


def test_our_lane_from_runtime_sizes() -> None:
    lane = our_lane_from_runtime(l1_xrp=50.0, bid_size_xrp=90.0, ask_size_xrp=70.0)
    assert lane == 90.0


def test_select_peer_lane_band() -> None:
    touch = {"peer_a": 100.0, "peer_b": 50.0, "whale": 500.0, "tiny": 10.0}
    result = select_peer_lane(touch, our_lane_xrp=100.0)
    assert result.peer_lane_count == 2
    assert "peer_a" in result.peer_accounts
    assert "peer_b" in result.peer_accounts
    assert "whale" not in result.peer_accounts
    assert result.peer_low_xrp == 40.0
    assert result.peer_high_xrp == 250.0


def test_select_peer_lane_widen_when_sparse() -> None:
    touch = {"only_peer": 35.0, "far": 500.0}
    result = select_peer_lane(touch, our_lane_xrp=100.0)
    assert result.widened is True
    assert result.peer_lane_count == 1
    assert result.peer_accounts == ["only_peer"]


def test_select_peer_lane_empty_when_no_our_lane() -> None:
    result = select_peer_lane({"a": 100.0}, our_lane_xrp=0.0)
    assert result.empty is True
    assert result.peer_lane_count == 0


def test_detect_fled_touch() -> None:
    prev = {"rPeer1": 100.0, "rPeer2": 80.0}
    curr = {"rPeer2": 85.0}
    events = detect_fled_touch(
        prev,
        curr,
        our_lane_xrp=100.0,
        age_s=4.0,
    )
    assert len(events) == 1
    assert events[0].account == "rPeer1"
    assert events[0].in_peer_lane is True


def test_detect_fled_touch_ignores_stale_gap() -> None:
    events = detect_fled_touch(
        {"rPeer1": 100.0},
        {},
        our_lane_xrp=100.0,
        age_s=0.0,
    )
    assert events == []


def test_compute_touch_by_account() -> None:
    bids = [
        {"account": "rA", "price": 2.0, "size": 50.0},
        {"account": "rB", "price": 1.99, "size": 200.0},
        {"account": "rA", "price": 2.0, "size": 30.0},
    ]
    asks = [
        {"account": "rC", "price": 2.01, "size": 40.0},
    ]
    touch = compute_touch_by_account(bids, asks, best_bid=2.0, best_ask=2.01)
    assert touch["rA"] == 80.0
    assert touch["rC"] == 40.0
    assert "rB" not in touch


def test_aggregate_peer_pressure_fled_lowers_pressure() -> None:
    base = aggregate_peer_pressure(
        peer_spreads=[0.08],
        global_spread=0.12,
        peer_count=2,
        fled_in_lane_count=0,
    )
    fled = aggregate_peer_pressure(
        peer_spreads=[0.08],
        global_spread=0.12,
        peer_count=2,
        fled_in_lane_count=2,
    )
    assert fled < base


def test_aggregate_peer_pressure_neutral_when_no_peers() -> None:
    assert aggregate_peer_pressure(
        peer_spreads=[],
        global_spread=0.1,
        peer_count=0,
        fled_in_lane_count=0,
    ) == 0.5
