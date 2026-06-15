"""Tests for B2 pure A-S dynamic sizing."""

from experimental.ws_feed.dynamic_sizing import build_pure_quote_ladder, compute_pure_l1_sizes


def test_l1_capped_by_balance_fraction() -> None:
    sizes = compute_pure_l1_sizes(
        xrp_balance=1000.0,
        configured_l1_xrp=150.0,
        inventory_skew=0.0,
        pressure_size_mult=1.0,
    )
    assert sizes.l1_xrp == 70.0  # min(150, 0.07*1000)


def test_l1_uses_config_when_balance_small() -> None:
    sizes = compute_pure_l1_sizes(
        xrp_balance=100.0,
        configured_l1_xrp=150.0,
        inventory_skew=0.0,
        pressure_size_mult=1.0,
    )
    assert sizes.l1_xrp == 7.0  # min(150, 7)


def test_rlusd_heavy_skew_boosts_bid_under_low_pressure() -> None:
    base = compute_pure_l1_sizes(
        xrp_balance=200.0,
        configured_l1_xrp=50.0,
        inventory_skew=-0.30,
        inventory_label="rlusd_heavy",
        pressure_size_mult=1.0,
        effective_pressure=0.25,
    )
    no_boost = compute_pure_l1_sizes(
        xrp_balance=200.0,
        configured_l1_xrp=50.0,
        inventory_skew=-0.30,
        inventory_label="rlusd_heavy",
        pressure_size_mult=1.0,
        effective_pressure=0.55,
    )
    assert base.bid_size_xrp > no_boost.bid_size_xrp
    assert base.ask_size_xrp < no_boost.ask_size_xrp
    assert "bid-boost" in base.rationale


def test_ask_boost_xrp_heavy_low_pressure() -> None:
    base = compute_pure_l1_sizes(
        xrp_balance=2000.0,
        configured_l1_xrp=500.0,
        inventory_skew=0.30,
        inventory_label="xrp_heavy",
        pressure_size_mult=1.0,
        effective_pressure=0.25,
    )
    no_boost = compute_pure_l1_sizes(
        xrp_balance=2000.0,
        configured_l1_xrp=500.0,
        inventory_skew=0.30,
        inventory_label="xrp_heavy",
        pressure_size_mult=1.0,
        effective_pressure=0.55,
    )
    assert base.ask_size_xrp > no_boost.ask_size_xrp
    assert base.bid_size_xrp < no_boost.bid_size_xrp
    assert "ask-boost" in base.rationale


def test_signed_skew_boosts_bid_when_rlusd_heavy() -> None:
    heavy_rlusd = compute_pure_l1_sizes(
        xrp_balance=1000.0,
        configured_l1_xrp=150.0,
        inventory_skew=-0.30,
        inventory_label="rlusd_heavy",
        pressure_size_mult=1.0,
    )
    balanced = compute_pure_l1_sizes(
        xrp_balance=1000.0,
        configured_l1_xrp=150.0,
        inventory_skew=0.0,
        pressure_size_mult=1.0,
    )
    assert heavy_rlusd.bid_size_xrp > balanced.bid_size_xrp
    assert heavy_rlusd.ask_size_xrp < balanced.ask_size_xrp


def test_pressure_size_mult_scales_both_sides() -> None:
    low = compute_pure_l1_sizes(
        xrp_balance=1000.0,
        configured_l1_xrp=150.0,
        inventory_skew=0.0,
        pressure_size_mult=1.0,
    )
    high = compute_pure_l1_sizes(
        xrp_balance=1000.0,
        configured_l1_xrp=150.0,
        inventory_skew=0.0,
        pressure_size_mult=1.4,
    )
    assert high.bid_size_xrp > low.bid_size_xrp
    assert high.ask_size_xrp > low.ask_size_xrp


def test_ladder_three_levels_six_intents() -> None:
    ladder = build_pure_quote_ladder(
        mid=1.10,
        l1_bid_price=1.0995,
        l1_ask_price=1.1005,
        l1_bid_size=10.0,
        l1_ask_size=12.0,
        optimal_spread_pct=0.12,
        level_spread_increment=0.0003,
        order_levels=3,
        active=True,
    )
    assert len(ladder) == 6
    l1_bid = next(i for i in ladder if i["level"] == 1 and i["side"] == "bid")
    l2_ask = next(i for i in ladder if i["level"] == 2 and i["side"] == "ask")
    assert l1_bid["price"] == 1.0995
    assert l1_bid["size_xrp"] == 10.0
    l2_ask = next(i for i in ladder if i["level"] == 2 and i["side"] == "ask")
    assert l2_ask["size_xrp"] == 7.2  # 12 * 0.6
    assert l2_ask["planned"] is True


def test_ladder_l1_ignores_configured_cap_for_level1() -> None:
    ladder = build_pure_quote_ladder(
        mid=1.10,
        l1_bid_price=1.0995,
        l1_ask_price=1.1005,
        l1_bid_size=11.2,
        l1_ask_size=11.2,
        optimal_spread_pct=0.12,
        configured_level_sizes=(15.0, 0.0, 0.0),
    )
    l1_bid = next(i for i in ladder if i["level"] == 1 and i["side"] == "bid")
    assert l1_bid["size_xrp"] == 11.2


def test_ladder_inactive_marks_l1_not_active() -> None:
    ladder = build_pure_quote_ladder(
        mid=1.10,
        l1_bid_price=1.0995,
        l1_ask_price=1.1005,
        l1_bid_size=10.0,
        l1_ask_size=10.0,
        optimal_spread_pct=0.12,
        active=False,
    )
    l1_bid = next(i for i in ladder if i["level"] == 1 and i["side"] == "bid")
    assert l1_bid["active"] is False
    assert l1_bid["planned"] is True
