"""Cap quote legs so one fill cannot overshoot inventory target."""

from config.settings import BotConfig
from engine.order_manager import OrderManager
from risk.inventory_limits import (
    INVENTORY_MODE_REBALANCE,
    cap_leg_size_for_inventory,
    max_bid_xrp_without_overshoot,
    max_ask_xrp_without_overshoot,
)
from strategy.quote_decision import QuoteAdjustments


def test_max_bid_to_target_rlusd_heavy() -> None:
    # ~39% XRP, target 55%, total ~232 XRP equiv
    cap = max_bid_xrp_without_overshoot(
        xrp_balance=91.0,
        rlusd_balance=190.0,
        mid_price=1.347,
        target_xrp_ratio=0.55,
        overshoot_slack=0.0,
    )
    assert 34.0 < cap < 38.0


def test_rebalance_bid_capped_not_70_xrp() -> None:
    config = BotConfig()
    config.order_sizes = [70.0, 0.0, 0.0]
    config.inventory_mode = INVENTORY_MODE_REBALANCE
    config.inventory_target_xrp_ratio = 0.55
    config.max_leg_size_pct_of_capital = 0.50  # loosen pct cap — overshoot cap should still bind
    config.risk_capital_xrp = 250.0
    om = OrderManager(config)
    adj = QuoteAdjustments(
        pause_asks=True,
        pause_bids=False,
        join_touch=True,
        inventory_label="rlusd_heavy",
    )
    plan = om.build_quotes(
        mid_price=1.347,
        spreads_pct={1: 0.08},
        xrp_balance=91.0,
        rlusd_balance=190.0,
        adjustments=adj,
        best_bid=1.346,
        best_ask=1.348,
    )
    bids = [i for i in plan.intents if i.side == "bid"]
    assert len(bids) == 1
    assert bids[0].size_xrp < 45.0
    assert bids[0].size_xrp > 30.0


def test_market_make_balanced_no_overshoot_cap() -> None:
    size = cap_leg_size_for_inventory(
        side="bid",
        size_xrp=28.0,
        xrp_balance=128.0,
        rlusd_balance=140.0,
        mid_price=1.346,
        target_xrp_ratio=0.55,
        xrp_reserve=12.0,
        inventory_mode="market_make",
        overshoot_slack=0.03,
        pause_bids=False,
        pause_asks=False,
        min_size=1.0,
    )
    assert size == 28.0


def test_xrp_heavy_ask_capped() -> None:
    cap = max_ask_xrp_without_overshoot(
        xrp_balance=162.0,
        rlusd_balance=95.0,
        mid_price=1.346,
        target_xrp_ratio=0.55,
        xrp_reserve=12.0,
        overshoot_slack=0.0,
    )
    assert 20.0 < cap < 35.0
