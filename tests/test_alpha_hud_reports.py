"""Tests for Alpha HUD reports catalog."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from alpha.hud.reports_support import (
    generate_report_text,
    get_report_spec,
    list_reports,
    wrap_report_html,
)


def test_list_reports_has_alpha_entries() -> None:
    reports = list_reports()
    assert len(reports) >= 9
    ids = {r["id"] for r in reports}
    assert "alpha_cycle" in ids
    assert "alpha_hourly" in ids
    assert "alpha_realized_pnl" in ids
    assert "alpha_ohlc_ta" in ids
    assert "alpha_trades_csv" in ids
    assert "alpha_transfers" in ids
    assert all(r["soak_safe"] for r in reports)


def test_trades_csv_report(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    month = datetime.now(tz=timezone.utc).strftime("%Y-%m")
    (logs / f"trades_{month}.csv").write_text(
        "timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,"
        "price_rlusd_per_xrp,profit_xrp_equiv,tx_hash,cycle,notes,balance_xrp_after,balance_rlusd_after\n"
        "2026-06-25T12:00:00+00:00,BUY,Y,mainnet,BUY,10,10.5,1.05,0,abc,1,test bracket,,",
        encoding="utf-8",
    )
    text = generate_report_text("alpha_trades_csv", logs_dir=logs)
    assert "BUY" in text
    assert "buys=1" in text


def test_transfers_report(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "transfers.csv").write_text(
        "timestamp_utc,network,asset,amount,destination,tx_hash\n"
        "2026-06-25T12:00:00+00:00,mainnet,XRP,5,rDest,TX1\n",
        encoding="utf-8",
    )
    text = generate_report_text("alpha_transfers", logs_dir=logs)
    assert "rDest" in text
    assert "rows=1" in text


def test_alpha_cycle_from_runtime(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "alpha_runtime_state.json").write_text(
        json.dumps({"report_text": "xLedgerMate Alpha v1.0.0\nMode: LIVE"}),
        encoding="utf-8",
    )
    text = generate_report_text("alpha_cycle", logs_dir=logs)
    assert "LIVE" in text


def test_unknown_report_raises() -> None:
    try:
        generate_report_text("not_a_real_report")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_wrap_report_html_includes_id() -> None:
    spec = get_report_spec("alpha_hourly")
    assert spec is not None
    page = wrap_report_html(
        report_id="alpha_hourly",
        title=spec.title,
        subtitle=spec.subtitle,
        body_text="line one",
        spec=spec,
    )
    assert "alpha_hourly" in page
    assert "line one" in page
