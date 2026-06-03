"""Order prices must stay within spread-validation limits."""

from engine.order_manager import OrderManager, _clamp_quote_price
from config.settings import BotConfig
from strategy.quote_decision import QuoteAdjustments


def test_clamp_ask_to_book_touch() -> None:
    mid = 1.325
    best_ask = 1.328
    raw = 1.359
    clamped = _clamp_quote_price(
        side="ask",
        price=raw,
        mid_price=mid,
        best_bid=1.324,
        best_ask=best_ask,
        max_worse_than_touch_pct=0.50,
        max_improve_touch_pct=0.15,
        max_half_spread_from_mid_pct=1.0,
    )
    assert clamped <= best_ask * 1.005
    assert clamped >= best_ask * 0.998


def test_clamp_bid_stays_inside_validation_limit() -> None:
    best_bid = 1.326370
    clamped = _clamp_quote_price(
        side="bid",
        price=1.31,
        mid_price=1.327,
        best_bid=best_bid,
        best_ask=1.328,
        max_worse_than_touch_pct=0.50,
        max_improve_touch_pct=0.15,
        max_half_spread_from_mid_pct=1.0,
    )
    vs_touch_pct = ((clamped - best_bid) / best_bid) * 100.0
    assert vs_touch_pct >= -0.50 + 0.02


def test_xrp_only_build_quotes_near_book() -> None:
    config = BotConfig()
    config.fund_with_xrp_only = True
    config.order_sizes = [50.0, 0.0, 0.0]
    om = OrderManager(config)
    adj = QuoteAdjustments(
        spread_multiplier=1.05,
        ask_spread_add_pct=2.0,
        inventory_label="xrp_heavy",
    )
    plan = om.build_quotes(
        mid_price=1.325,
        spreads_pct={1: 0.08},
        xrp_balance=200.0,
        rlusd_balance=0.0,
        adjustments=adj,
        best_bid=1.324,
        best_ask=1.328,
    )
    assert len(plan.intents) == 1
    assert plan.intents[0].side == "ask"
    assert plan.intents[0].price <= 1.328 * 1.005


def test_join_touch_l1_matches_book() -> None:
    config = BotConfig()
    config.order_sizes = [50.0, 0.0, 0.0]
    om = OrderManager(config)
    adj = QuoteAdjustments(join_touch=True)
    plan = om.build_quotes(
        mid_price=1.336783,
        spreads_pct={1: 0.12},
        xrp_balance=120.0,
        rlusd_balance=170.0,
        adjustments=adj,
        best_bid=1.336489,
        best_ask=1.337077,
    )
    bids = [i for i in plan.intents if i.side == "bid"]
    asks = [i for i in plan.intents if i.side == "ask"]
    assert len(bids) == 1
    assert len(asks) == 1
    assert abs(bids[0].price - 1.336489) < 1e-9
    assert abs(asks[0].price - 1.337077) < 1e-9
