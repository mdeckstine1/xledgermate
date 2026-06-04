"""Session insights builder."""

from utils.session_insights import build_session_insights


def test_build_session_insights_empty_runtime(tmp_path) -> None:
    empty_logs = tmp_path / "empty_logs"
    empty_logs.mkdir()
    insights = build_session_insights({}, logs_dir=empty_logs)
    assert insights.fill_count == 0
    assert insights.status == "ok"
    assert "No fills" in insights.headline


def test_build_session_insights_from_csv(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    csv_path = logs / "trades_2026-06.csv"
    csv_path.write_text(
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after\n"
        "2026-06-03T10:00:00+00:00,MAJOR,N,mainnet,,0,0,0,0,,0,Engine started | dry_run=False,0,0\n"
        "2026-06-03T10:05:00+00:00,BUY,Y,mainnet,BUY,10,12,1.2,0.01,,1,fill,100,50\n"
        "2026-06-03T10:10:00+00:00,SELL,Y,mainnet,SELL,5,6,1.21,0.02,,2,fill,95,56\n",
        encoding="utf-8",
    )
    runtime = {
        "mid_price": 1.2,
        "balance_xrp": 66.0,
        "balance_rlusd": 79.2,
        "toxic_fill_ratio": 0.0,
        "toxic_fill_ratio_30s": 0.0,
        "cancel_per_fill": 0.5,
        "fills_session": 2,
        "dynamic_min_edge_enabled": True,
        "market_edge_met": True,
        "book_spread_pct": 0.08,
    }
    insights = build_session_insights(runtime, logs_dir=logs)
    assert insights.fill_count == 2
    assert insights.buy_count == 1
    assert insights.sell_count == 1
    assert insights.capture_xrp == 0.03
    assert insights.status == "ok"
