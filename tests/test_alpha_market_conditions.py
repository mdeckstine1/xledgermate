"""Tests for market conditions HUD payload."""

from __future__ import annotations

from datetime import datetime, timezone

from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
from alpha.ledger.market_conditions import (
    build_market_conditions,
    compute_bag_dca,
    compute_bracket_dca,
    compute_order_counts,
    count_filled_trades,
    refresh_dca_vs_mid,
)
from alpha.orders.types import (
    BracketLeg,
    BracketLegRole,
    BracketLifecycleState,
    BracketMode,
    BracketRecord,
)
from alpha.types import BookLevel, LiquidityDepth, OrderBookSnapshot
from config.settings import BotConfig


def _book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        bids=(BookLevel(price=1.10, size_xrp=5000.0), BookLevel(price=1.09, size_xrp=3000.0)),
        asks=(BookLevel(price=1.11, size_xrp=4000.0), BookLevel(price=1.12, size_xrp=2000.0)),
        best_bid=1.10,
        best_ask=1.11,
        mid=1.105,
        spread=0.01,
        spread_pct=0.90,
        fetched_utc=datetime.now(tz=timezone.utc),
    )


def test_market_conditions_depth_and_sizes() -> None:
    cfg = BotConfig(
        alpha_cycle_interval_seconds=15,
        alpha_base_order_size_xrp=50.0,
        min_order_size_xrp=1.0,
        alpha_risk_per_trade_pct=0.5,
    )
    book = _book()
    liquidity = LiquidityDepth(
        max_slippage_pct=0.5,
        bid_depth_xrp=5000.0,
        ask_depth_xrp=4000.0,
        best_bid=1.10,
        best_ask=1.11,
        mid=1.105,
        spread_pct=0.90,
    )
    ta = TechnicalAnalysisSnapshot(
        mid=1.105,
        enabled=True,
        buy_score=2.0,
        sell_score=1.0,
        breakout_score=0.0,
        bias="bullish",
        entry_buy_allowed=True,
        entry_sell_allowed=False,
        breakout_confirmed=False,
        summary="test",
    )
    mc = build_market_conditions(
        book=book,
        liquidity=liquidity,
        config=cfg,
        portfolio_xrp_equiv=400.0,
        ta=ta,
    )
    assert mc["mid"] == 1.105
    assert mc["ask_depth_xrp"] > 0
    assert mc["bid_depth_xrp"] > 0
    assert mc["recommended_max_buy_xrp"] > 0
    assert mc["recommended_max_sell_xrp"] > 0
    assert mc["cycle_interval_seconds"] == 15
    assert mc["ta"]["buy_score"] == 2.0
    assert mc["liquidity_health"] in ("green", "yellow", "red")


def test_bracket_dca_weighted_average() -> None:
    records = [
        BracketRecord(
            bracket_id="a",
            state=BracketLifecycleState.BRACKET_ACTIVE,
            mode=BracketMode.BRACKET,
            buy_sequence=1,
            entry_price_rlusd_per_xrp=1.00,
            target_size_xrp=10.0,
            filled_xrp=10.0,
            bracketed_xrp=10.0,
        ),
        BracketRecord(
            bracket_id="b",
            state=BracketLifecycleState.BRACKET_ACTIVE,
            mode=BracketMode.BRACKET,
            buy_sequence=2,
            entry_price_rlusd_per_xrp=1.10,
            target_size_xrp=10.0,
            filled_xrp=10.0,
            bracketed_xrp=10.0,
        ),
        BracketRecord(
            bracket_id="c",
            state=BracketLifecycleState.PENDING_BUY,
            mode=BracketMode.BRACKET,
            buy_sequence=3,
            entry_price_rlusd_per_xrp=1.20,
            target_size_xrp=5.0,
        ),
    ]
    dca = compute_bracket_dca(records, mid=1.08)
    assert dca["avg_entry_rlusd_per_xrp"] == 1.05
    assert dca["total_xrp"] == 20.0
    assert dca["position_count"] == 2
    assert dca["vs_mid_pct"] is not None
    assert dca["grade"] == "green"


def test_market_conditions_includes_dca() -> None:
    cfg = BotConfig(min_order_size_xrp=1.0, alpha_base_order_size_xrp=50.0)
    record = BracketRecord(
        bracket_id="x",
        state=BracketLifecycleState.BRACKET_ACTIVE,
        mode=BracketMode.BRACKET,
        buy_sequence=9,
        entry_price_rlusd_per_xrp=1.05,
        target_size_xrp=8.0,
        filled_xrp=8.0,
        bracketed_xrp=8.0,
    )
    mc = build_market_conditions(
        book=_book(),
        liquidity=None,
        config=cfg,
        portfolio_xrp_equiv=100.0,
        ta=None,
        brackets=[record],
    )
    assert mc["dca"]["avg_entry_rlusd_per_xrp"] == 1.05
    assert mc["dca"]["total_xrp"] == 8.0


def test_refresh_dca_vs_mid_on_book_patch() -> None:
    mc = {"dca": {"avg_entry_rlusd_per_xrp": 1.0, "total_xrp": 5.0, "position_count": 1}}
    refresh_dca_vs_mid(mc, 1.02)
    assert mc["dca"]["vs_mid_pct"] == 2.0
    assert mc["dca"]["grade"] == "green"


def test_market_conditions_dca_falls_back_to_bag_basis(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    header = (
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after\n"
    )
    (logs / "trades_2026-06.csv").write_text(
        header
        + "t,BUY,Y,mainnet,BUY,10,10.5,1.05,0,,0,,,\n"
        + "t,SELL,Y,mainnet,SELL,2,2.2,1.10,0.1,,0,tp,,,\n",
        encoding="utf-8",
    )
    cfg = BotConfig(min_order_size_xrp=1.0, alpha_base_order_size_xrp=50.0)
    mc = build_market_conditions(
        book=_book(),
        liquidity=None,
        config=cfg,
        portfolio_xrp_equiv=100.0,
        ta=None,
        brackets=[],
        log_dir=logs,
    )
    assert mc["dca"]["source"] == "bag"
    assert mc["dca"]["avg_entry_rlusd_per_xrp"] == 1.05
    assert mc["dca"]["total_xrp"] == 8.0
    assert mc["dca"]["vs_mid_pct"] is not None


def test_market_conditions_dca_falls_back_to_lifetime_buys(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    header = (
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after\n"
    )
    (logs / "trades_2026-06.csv").write_text(
        header
        + "t,BUY,Y,mainnet,BUY,10,10.5,1.05,0,,0,,,\n"
        + "t,SELL,Y,mainnet,SELL,12,13.2,1.10,0.1,,0,tp,,,\n",
        encoding="utf-8",
    )
    cfg = BotConfig(min_order_size_xrp=1.0, alpha_base_order_size_xrp=50.0)
    mc = build_market_conditions(
        book=_book(),
        liquidity=None,
        config=cfg,
        portfolio_xrp_equiv=100.0,
        ta=None,
        brackets=[],
        log_dir=logs,
        balance_xrp=50.0,
    )
    assert mc["dca"]["source"] == "lifetime_buys"
    assert mc["dca"]["avg_entry_rlusd_per_xrp"] == 1.05
    assert mc["dca"]["total_xrp"] == 50.0


def test_count_filled_trades_from_csv(tmp_path: Path) -> None:
    header = (
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after\n"
    )
    (tmp_path / "trades_2026-06.csv").write_text(
        header
        + "t,BUY,Y,mainnet,BUY,1,1,1,0,,0,,,\n"
        + "t,BUY,Y,mainnet,BUY,1,1,1,0,,0,,,\n"
        + "t,SELL,Y,mainnet,SELL,1,1,1,0,,0,,,\n"
        + "t,MAJOR,N,mainnet,,0,0,0,0,,0,,,\n",
        encoding="utf-8",
    )
    counts = count_filled_trades(tmp_path)
    assert counts["purchase_fills"] == 2
    assert counts["sell_fills"] == 1


def test_order_counts_open_and_filled(tmp_path: Path) -> None:
    header = (
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after\n"
    )
    (tmp_path / "trades_2026-06.csv").write_text(
        header + "t,BUY,Y,mainnet,BUY,1,1,1,0,,0,,,\n", encoding="utf-8"
    )
    tp = BracketLeg(
        role=BracketLegRole.TAKE_PROFIT,
        sequence=100,
        price_rlusd_per_xrp=1.2,
        size_xrp=5.0,
        remaining_xrp=5.0,
    )
    sl = BracketLeg(
        role=BracketLegRole.STOP_LOSS,
        sequence=101,
        price_rlusd_per_xrp=0.9,
        size_xrp=5.0,
        remaining_xrp=5.0,
    )
    records = [
        BracketRecord(
            bracket_id="open-buy",
            state=BracketLifecycleState.PENDING_BUY,
            mode=BracketMode.BRACKET,
            buy_sequence=1,
            entry_price_rlusd_per_xrp=1.0,
            target_size_xrp=5.0,
        ),
        BracketRecord(
            bracket_id="active",
            state=BracketLifecycleState.BRACKET_ACTIVE,
            mode=BracketMode.BRACKET,
            buy_sequence=2,
            entry_price_rlusd_per_xrp=1.0,
            target_size_xrp=5.0,
            filled_xrp=5.0,
            bracketed_xrp=5.0,
            tp_leg=tp,
            sl_leg=sl,
        ),
    ]
    oc = compute_order_counts(records, log_dir=tmp_path)
    assert oc["purchase_fills"] == 1
    assert oc["sell_fills"] == 0
    assert oc["open_purchases"] == 1
    assert oc["open_sells"] == 2
