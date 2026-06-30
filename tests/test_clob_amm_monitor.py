"""Tests for H1 CLOB vs AMM monitor."""

from pathlib import Path

from experimental.arb.clob_amm_monitor import (
    augment_clob_amm_row,
    append_clob_amm_record,
    clob_half_spread_bps,
    estimate_arb_costs_bps,
    format_clob_amm_report,
    latest_hud_fields,
    net_edge_bps,
    spread_bps,
    summarize_clob_amm_rows,
    tail_clob_amm_records,
)
from experimental.liquidity.amm_provider import (
    implied_mid_rlusd_per_xrp_from_amm_info,
    trading_fee_bps_from_amm,
)


def test_spread_bps() -> None:
    bps = spread_bps(1.28, 1.281)
    assert bps is not None
    assert 5.0 < bps < 15.0


def test_implied_mid_from_amm_info() -> None:
    mid = implied_mid_rlusd_per_xrp_from_amm_info(
        {"amount": "1000000", "amount2": {"currency": "RLUSD", "value": "1.28"}}
    )
    assert mid is not None
    assert abs(mid - 1.28) < 0.001


def test_trading_fee_bps() -> None:
    assert trading_fee_bps_from_amm({"TradingFee": 500}) == 5.0


def test_net_edge_after_costs() -> None:
    costs = estimate_arb_costs_bps(clob_spread_pct=0.1, amm_fee_bps=5.0, slippage_buffer_bps=2.0)
    assert costs["clob_half_spread_bps"] == clob_half_spread_bps(0.1)
    assert costs["total_cost_bps"] == costs["clob_half_spread_bps"] + 5.0 + 2.0
    net = net_edge_bps(11.0, costs["total_cost_bps"])
    assert net is not None
    assert net < 11.0


def test_augment_row_adds_net_fields() -> None:
    row = augment_clob_amm_row(
        {"spread_bps": 12.0, "clob_spread_pct": 0.1, "amm_fee_bps": 5.0},
        slippage_buffer_bps=2.0,
    )
    assert row["net_edge_bps"] is not None
    assert row["total_cost_bps"] is not None
    assert row["net_positive"] is bool(row["net_edge_bps"] > 0)


def test_clob_amm_jsonl_tail(tmp_path: Path) -> None:
    path = tmp_path / "clob_amm_spread.jsonl"
    append_clob_amm_record(
        {
            "kind": "clob_amm",
            "spread_bps": 9.5,
            "dislocation": True,
            "status": "ok",
            "clob_spread_pct": 0.1,
            "amm_fee_bps": 5.0,
            "slippage_buffer_bps": 2.0,
            "clob_half_spread_bps": 5.0,
            "total_cost_bps": 12.0,
            "net_edge_bps": -2.5,
            "net_positive": False,
        },
        path=path,
    )
    rows = tail_clob_amm_records(limit=5, path=path)
    assert len(rows) == 1
    hud = latest_hud_fields(path=path)
    assert hud["clob_amm_dislocation"] is True
    assert hud["clob_amm_net_edge_bps"] == -2.5
    report = format_clob_amm_report(logs_dir=tmp_path)
    assert "net positive" in report
    summary = summarize_clob_amm_rows(rows)
    assert summary["samples"] == 1
