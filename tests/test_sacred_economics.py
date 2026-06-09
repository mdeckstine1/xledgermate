"""Tests for sacred corpus economics (grokster / replay)."""

from experimental.sacred_economics import (
    baseline_blocked,
    compute_baseline_economics,
    compute_marginal_economics,
    parse_decision_events,
)


def test_baseline_economics_capture_and_neg_pct() -> None:
    rows = [
        {
            "event_type": "BUY",
            "taxable": "Y",
            "side": "BUY",
            "xrp_amount": "10",
            "profit_xrp_equiv": "0.05",
            "price_rlusd_per_xrp": "1.1",
            "balance_xrp_after": "100",
            "balance_rlusd_after": "110",
            "cycle": "1",
        },
        {
            "event_type": "SELL",
            "taxable": "Y",
            "side": "SELL",
            "xrp_amount": "10",
            "profit_xrp_equiv": "-0.02",
            "price_rlusd_per_xrp": "1.1",
            "balance_xrp_after": "90",
            "balance_rlusd_after": "121",
            "cycle": "2",
        },
    ]
    eco = compute_baseline_economics(rows)
    assert eco.fill_count == 2
    assert abs(eco.capture_xrp - 0.03) < 1e-9
    assert eco.neg_fill_count == 1
    assert abs(eco.neg_fill_pct - 50.0) < 1e-9
    assert eco.first_portfolio_xrp == 200.0
    assert eco.last_portfolio_xrp == 200.0
    assert eco.balance_delta_xrp_proxy == 0.0


def test_marginal_economics_forward_window() -> None:
    trades = [
        {
            "event_type": "BUY",
            "taxable": "Y",
            "side": "BUY",
            "xrp_amount": "5",
            "profit_xrp_equiv": "0.04",
            "cycle": "11",
            "timestamp_utc": "t1",
        },
    ]
    decisions = [
        '{"cycle": 10, "events": [{"message": "Generated 0 quotes market_edge_met=false hard gate"}]}',
    ]

    def always_pure(_line: str) -> bool:
        return True

    m = compute_marginal_economics(decisions, trades, always_pure, lookahead_cycles=3, baseline_capture_xrp=1.0)
    assert m.marginal_cycles == 1
    assert m.marginal_with_fill_in_window == 1
    assert abs(m.marginal_capture_xrp - 0.04) < 1e-9
    assert abs(m.projected_capture_upper_bound - 1.04) < 1e-9


def test_baseline_blocked_detects_zero_quotes() -> None:
    assert baseline_blocked("Generated 0 quotes market_edge_met=false hard gate")
    assert not baseline_blocked("Generated 2 quotes from mid")


def test_parse_decision_events_cycle() -> None:
    line = '{"cycle": 42, "events": [{"message": "Book L1 spread 0.10%"}]}'
    cycle, msg = parse_decision_events(line)
    assert cycle == 42
    assert "Book L1 spread" in msg
