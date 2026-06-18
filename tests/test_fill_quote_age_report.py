"""Tests for offline fill quote-age report."""

import csv
from datetime import datetime, timezone
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
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_fill_age_matches_prior_refresh(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_csv(
        logs / "trades_2026-06.csv",
        [
            {
                "timestamp_utc": "2026-06-17T10:00:00+00:00",
                "event_type": "OFFER_REFRESH",
                "taxable": "False",
                "network": "mainnet",
                "side": "",
                "xrp_amount": "",
                "rlusd_amount": "",
                "price_rlusd_per_xrp": "",
                "profit_xrp_equiv": "",
                "tx_hash": "",
                "cycle": "100",
                "notes": "live: cancelled 1, placed 2 offer(s)",
                "balance_xrp_after": "",
                "balance_rlusd_after": "",
            },
            {
                "timestamp_utc": "2026-06-17T10:00:25+00:00",
                "event_type": "BUY",
                "taxable": "True",
                "network": "mainnet",
                "side": "BUY",
                "xrp_amount": "1.5",
                "rlusd_amount": "1.9",
                "price_rlusd_per_xrp": "1.28",
                "profit_xrp_equiv": "0.01",
                "tx_hash": "",
                "cycle": "105",
                "notes": "WS pure fill (balance delta); capture ~+0.0100 XRP @ mid 1.28",
                "balance_xrp_after": "50",
                "balance_rlusd_after": "200",
            },
        ],
    )
    report = build_fill_age_report(logs_dir=logs, cycle_seconds=5.0)
    assert report.fill_count == 1
    assert report.with_refresh_match == 1
    assert report.m2_proxy_count == 1
    assert report.rows[0].age_seconds_since_refresh == 25.0
    assert report.age_seconds_mean == 25.0
