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
