"""Tests for H1 CLOB vs AMM monitor."""

from pathlib import Path

from experimental.arb.clob_amm_monitor import (
    append_clob_amm_record,
    format_clob_amm_report,
    latest_hud_fields,
    spread_bps,
    tail_clob_amm_records,
)
from experimental.liquidity.amm_provider import implied_mid_rlusd_per_xrp_from_amm_info


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


def test_clob_amm_jsonl_tail(tmp_path: Path) -> None:
    path = tmp_path / "clob_amm_spread.jsonl"
    append_clob_amm_record(
        {"kind": "clob_amm", "spread_bps": 9.5, "dislocation": True, "status": "ok"},
        path=path,
    )
    rows = tail_clob_amm_records(limit=5, path=path)
    assert len(rows) == 1
    hud = latest_hud_fields(path=path)
    assert hud["clob_amm_dislocation"] is True
    report = format_clob_amm_report(logs_dir=tmp_path)
    assert "dislocations" in report
