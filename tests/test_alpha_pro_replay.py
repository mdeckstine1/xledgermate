"""Tests for Alpha PRO replay analytics."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone

from alpha.pro.replay import build_replay_report, format_replay_report_text


def _write_tax_csv(path, rows):
    fields = [
        "timestamp_utc",
        "taxable",
        "side",
        "xrp_amount",
        "profit_xrp_equiv",
        "price_rlusd_per_xrp",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def test_replay_sl_heavy_verdict(tmp_path):
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    ts = (now - timedelta(hours=2)).isoformat()
    _write_tax_csv(
        tmp_path / "trades_2026-06.csv",
        [
            {
                "timestamp_utc": ts,
                "taxable": "Y",
                "side": "SELL",
                "xrp_amount": "10",
                "profit_xrp_equiv": "-0.05",
                "price_rlusd_per_xrp": "1.02",
                "notes": "stop-loss",
            }
            for _ in range(6)
        ]
        + [
            {
                "timestamp_utc": ts,
                "taxable": "Y",
                "side": "SELL",
                "xrp_amount": "10",
                "profit_xrp_equiv": "0.08",
                "price_rlusd_per_xrp": "1.03",
                "notes": "take-profit",
            }
        ],
    )
    report = build_replay_report(logs_dir=tmp_path, hours=24, now=now)
    assert report["tp_exits"] == 1
    assert report["sl_exits"] == 6
    assert report["verdict"] == "sl_heavy"
    text = format_replay_report_text(report)
    assert "sl_heavy" in text
    assert "Realized P&L" in text


def test_replay_empty_logs(tmp_path):
    report = build_replay_report(logs_dir=tmp_path, hours=24)
    assert report["tp_exits"] == 0
    assert report["verdict"] == "healthy"
