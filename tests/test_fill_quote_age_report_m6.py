"""Tests for M6-primary fill quote age report."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.fill_quote_age_report import build_fill_age_report


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    header = [
        "timestamp_utc",
        "event_type",
        "taxable",
        "network",
        "side",
        "xrp_amount",
        "rlusd_amount",
        "price_rlusd_per_xrp",
        "profit_xrp_equiv",
        "tx_hash",
        "cycle",
        "notes",
        "balance_xrp_after",
        "balance_rlusd_after",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        import csv

        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_report_prefers_m6_jsonl_over_m2_proxy(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_csv(
        logs / "trades_2026-06.csv",
        [
            {
                "timestamp_utc": "2026-06-18T20:00:25+00:00",
                "event_type": "BUY",
                "taxable": "True",
                "network": "mainnet",
                "side": "BUY",
                "xrp_amount": "10",
                "rlusd_amount": "11",
                "price_rlusd_per_xrp": "1.1",
                "profit_xrp_equiv": "0.01",
                "tx_hash": "",
                "cycle": "50",
                "notes": "WS pure fill (balance delta); capture ~+0.0100 XRP @ mid 1.1",
                "balance_xrp_after": "50",
                "balance_rlusd_after": "200",
            },
        ],
    )
    m6_row = {
        "kind": "fill",
        "ts_utc": "2026-06-18T20:00:25+00:00",
        "cycle": 50,
        "side": "BUY",
        "offer_side": "bid",
        "quote_age_seconds": 42.5,
        "tracking": "m6_sequence",
        "offer_sequence": 123,
    }
    (logs / "fill_quote_age.jsonl").write_text(
        json.dumps(m6_row, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    report = build_fill_age_report(logs_dir=logs)
    assert report.m6_live_count == 1
    assert report.m2_proxy_count == 0
    assert report.rows[0].age_seconds_since_refresh == 42.5
    assert report.rows[0].method == "m6_sequence"
