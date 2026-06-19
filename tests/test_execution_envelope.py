"""Tests for G7 execution envelope."""

from experimental.ws_feed.execution_envelope import (
    ASK_DEFENSE_EXTRA_BPS,
    JOIN_BACKOFF_BPS,
    PASSIVE_BACKOFF_BPS,
    apply_solo_lane_posture,
    compute_execution_envelope,
    resolve_join_backoff_bps,
    sell_defense_active,
    touch_prices_from_backoff,
)


def test_balanced_default_8bps() -> None:
    env = compute_execution_envelope(inventory_label="balanced", g2_spread_mult=1.0)
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.inventory_posture == "balanced"


def test_xrp_heavy_ask_joins_bid_passive() -> None:
    env = compute_execution_envelope(inventory_label="xrp_heavy", g2_spread_mult=1.0)
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.ask_touch_backoff_bps == JOIN_BACKOFF_BPS
    assert env.bid_role == "passive"
    assert env.ask_role == "join"
    assert "join" in env.scaler_label


def test_rlusd_heavy_bid_joins() -> None:
    env = compute_execution_envelope(inventory_label="rlusd_heavy", g2_spread_mult=1.0)
    assert env.bid_touch_backoff_bps == JOIN_BACKOFF_BPS
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.bid_role == "join"
    assert env.ask_role == "passive"


def test_join_backoff_scales_with_half_spread() -> None:
    assert resolve_join_backoff_bps(book_half_spread_bps=10.0) == 5.0
    assert resolve_join_backoff_bps(book_half_spread_bps=20.0) == 7.0
    assert resolve_join_backoff_bps() == JOIN_BACKOFF_BPS


def test_rlusd_heavy_join_uses_book_half_spread() -> None:
    env = compute_execution_envelope(
        inventory_label="rlusd_heavy",
        g2_spread_mult=1.0,
        book_half_spread_bps=20.0,
    )
    assert env.bid_touch_backoff_bps == 7.0
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS


def test_g2_spread_mult_widens_both() -> None:
    env = compute_execution_envelope(inventory_label="balanced", g2_spread_mult=1.25)
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS * 1.25
    assert env.ask_touch_backoff_bps == (PASSIVE_BACKOFF_BPS + ASK_DEFENSE_EXTRA_BPS) * 1.25
    assert env.ask_sell_defense is True
    assert "G2 1.25" in env.summary


def test_touch_prices_never_cross() -> None:
    bid, ask = touch_prices_from_backoff(
        best_bid=1.10,
        best_ask=1.11,
        bid_backoff_bps=3.0,
        ask_backoff_bps=3.0,
    )
    assert bid <= 1.10
    assert ask >= 1.11
    assert bid < ask


def test_sell_defense_demotes_xrp_heavy_ask_join() -> None:
    env = compute_execution_envelope(
        inventory_label="xrp_heavy",
        g2_spread_mult=1.0,
        mean_markout_30s_pct=-0.02,
        recent_fills=20,
    )
    assert env.ask_sell_defense is True
    assert env.ask_role == "passive"
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS + ASK_DEFENSE_EXTRA_BPS
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert "ask defense" in env.summary


def test_sell_defense_widens_balanced_ask_only() -> None:
    env = compute_execution_envelope(
        inventory_label="balanced",
        g2_spread_mult=1.0,
        toxic_ratio_30s=0.20,
        recent_fills=10,
    )
    assert env.ask_sell_defense is True
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS + ASK_DEFENSE_EXTRA_BPS
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS


def test_sell_defense_inactive_when_markout_ok() -> None:
    active, _ = sell_defense_active(
        g2_spread_mult=1.0,
        toxic_ratio_30s=0.05,
        mean_markout_30s_pct=0.01,
        recent_fills=20,
    )
    assert active is False
    env = compute_execution_envelope(
        inventory_label="balanced",
        mean_markout_30s_pct=0.01,
        toxic_ratio_30s=0.05,
        recent_fills=20,
    )
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.ask_sell_defense is False


def test_solo_acquisition_balanced_bid_join() -> None:
    env = compute_execution_envelope(
        inventory_label="balanced",
        g2_spread_mult=1.0,
        peer_lane_empty=True,
        toxic_ratio_30s=0.05,
    )
    assert env.solo_acquisition is True
    assert env.bid_touch_backoff_bps == JOIN_BACKOFF_BPS
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.bid_role == "join"
    assert env.ask_role == "passive"
    assert "solo acquire" in env.summary


def test_solo_acquisition_xrp_heavy_passive_both() -> None:
    env = compute_execution_envelope(
        inventory_label="xrp_heavy",
        g2_spread_mult=1.0,
        peer_lane_empty=True,
        toxic_ratio_30s=0.05,
    )
    assert env.solo_acquisition is True
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.ask_touch_backoff_bps == PASSIVE_BACKOFF_BPS
    assert env.bid_role == "passive"
    assert env.ask_role == "passive"


def test_solo_acquisition_skipped_on_toxic() -> None:
    env = compute_execution_envelope(
        inventory_label="balanced",
        peer_lane_empty=True,
        toxic_ratio_30s=0.25,
    )
    assert env.solo_acquisition is False
    assert env.bid_touch_backoff_bps == PASSIVE_BACKOFF_BPS


def test_solo_acquisition_skipped_on_g2_brake() -> None:
    env = compute_execution_envelope(
        inventory_label="balanced",
        peer_lane_empty=True,
        g2_spread_mult=1.1,
        toxic_ratio_30s=0.05,
    )
    assert env.solo_acquisition is False


def test_apply_solo_lane_posture_no_intel_fields() -> None:
    bid, ask, br, ar, solo = apply_solo_lane_posture(
        posture="balanced",
        peer_lane_empty=False,
        join_bps=JOIN_BACKOFF_BPS,
        bid_base=PASSIVE_BACKOFF_BPS,
        ask_base=PASSIVE_BACKOFF_BPS,
        bid_role="wide",
        ask_role="wide",
    )
    assert solo is False
    assert bid == PASSIVE_BACKOFF_BPS
