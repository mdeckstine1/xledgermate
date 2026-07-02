"""Tests for tax ledger month/year rollups."""

from __future__ import annotations

from pathlib import Path

import pytest

from alpha.hud.reports_support import generate_report_text
from alpha.reporting.tax_ledger import (
    annual_csv_path,
    estimate_avg_cost_basis_rlusd,
    estimate_open_lot_cost_basis,
    list_trade_months,
    list_trade_years,
    load_year_rows,
    tax_periods_payload,
    write_annual_csv,
)


def _write_month(logs: Path, month: str, rows: str) -> None:
    header = (
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after\n"
    )
    (logs / f"trades_{month}.csv").write_text(header + rows, encoding="utf-8")


def test_list_months_and_years(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_month(logs, "2026-05", "2026-05-01T00:00:00+00:00,BUY,Y,mainnet,BUY,10,11,1.1,0,,1,buy,,")
    _write_month(logs, "2026-06", "2026-06-01T00:00:00+00:00,SELL,Y,mainnet,SELL,10,12,1.2,1,,1,tp entry=1.1,,")
    assert list_trade_months(logs) == ["2026-06", "2026-05"]
    assert 2026 in list_trade_years(logs)


def test_write_annual_csv_merges_months(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_month(logs, "2026-05", "2026-05-01T00:00:00+00:00,BUY,Y,mainnet,BUY,10,11,1.1,0,,1,buy,,\n")
    _write_month(logs, "2026-06", "2026-06-01T00:00:00+00:00,SELL,Y,mainnet,SELL,10,12,1.2,1,,1,tp,,\n")
    out = write_annual_csv(logs, 2026)
    assert out == annual_csv_path(logs, 2026)
    assert out.is_file()
    rows = load_year_rows(logs, 2026)
    assert len(rows) == 2


def test_tax_periods_payload(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_month(logs, "2026-06", "2026-06-01T00:00:00+00:00,BUY,Y,mainnet,BUY,5,5.5,1.1,0,,1,buy,,\n")
    payload = tax_periods_payload(logs)
    assert "2026-06" in payload["months"]
    assert payload["month_summaries"][0]["buys"] == 1


def test_month_and_year_reports(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_month(logs, "2026-06", "2026-06-01T00:00:00+00:00,SELL,Y,mainnet,SELL,10,12,1.2,0.5,,1,alpha bracket take-profit x entry=1.1,,\n")
    month_text = generate_report_text("alpha_trades_month", logs_dir=logs, month="2026-06")
    assert "2026-06" in month_text
    assert "SELL" in month_text
    year_text = generate_report_text("alpha_tax_year", logs_dir=logs, year=2026)
    assert "tax_year: 2026" in year_text
    assert "trades_2026_annual.csv" in year_text


def test_estimate_avg_cost_basis_rlusd(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_month(
        logs,
        "2026-06",
        "2026-06-01T00:00:00+00:00,BUY,Y,mainnet,BUY,10,20,2,0,,1,buy,,,\n"
        "2026-06-02T00:00:00+00:00,SELL,Y,mainnet,SELL,4,8.8,2.2,0.2,,1,tp,,,\n",
    )
    assert estimate_avg_cost_basis_rlusd(logs) == pytest.approx(2.0)
    avg, remaining = estimate_open_lot_cost_basis(logs)
    assert avg == pytest.approx(2.0)
    assert remaining == pytest.approx(6.0)
