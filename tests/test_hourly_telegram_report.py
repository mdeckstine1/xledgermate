"""Tests for hourly Telegram report builder."""

from __future__ import annotations

import csv
from pathlib import Path

from datetime import datetime, timedelta, timezone

from scripts.hourly_telegram_report import WS_FILL_MARKER, build_report


def _write_trades(path: Path, rows: list[dict[str, str]]) -> None:
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
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_hourly_report_ws_fill_counts_and_hud_link(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    now_dt = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    now = now_dt.isoformat()
    hour_ago = (now_dt - timedelta(hours=0, minutes=30)).isoformat()
    old = (now_dt - timedelta(days=1)).isoformat()
    _write_trades(
        logs / "trades_2026-06.csv",
        [
            {
                "timestamp_utc": old,
                "event_type": "MAJOR",
                "taxable": "N",
                "network": "mainnet",
                "side": "",
                "xrp_amount": "0",
                "rlusd_amount": "0",
                "price_rlusd_per_xrp": "0",
                "profit_xrp_equiv": "0",
                "tx_hash": "",
                "cycle": "0",
                "notes": "WS-engine started | dry_run=False",
                "balance_xrp_after": "0",
                "balance_rlusd_after": "0",
            },
            {
                "timestamp_utc": hour_ago,
                "event_type": "SELL",
                "taxable": "Y",
                "network": "mainnet",
                "side": "SELL",
                "xrp_amount": "10",
                "rlusd_amount": "21.8",
                "price_rlusd_per_xrp": "2.18",
                "profit_xrp_equiv": "0.05",
                "tx_hash": "",
                "cycle": "1",
                "notes": f"{WS_FILL_MARKER} (balance delta); capture ~+0.0500 XRP",
                "balance_xrp_after": "100",
                "balance_rlusd_after": "50",
            },
            {
                "timestamp_utc": now,
                "event_type": "BUY",
                "taxable": "Y",
                "network": "mainnet",
                "side": "BUY",
                "xrp_amount": "8",
                "rlusd_amount": "17.44",
                "price_rlusd_per_xrp": "2.18",
                "profit_xrp_equiv": "0.02",
                "tx_hash": "",
                "cycle": "2",
                "notes": f"{WS_FILL_MARKER} (balance delta); capture ~+0.0200 XRP",
                "balance_xrp_after": "108",
                "balance_rlusd_after": "32.56",
            },
        ],
    )
    (logs / "runtime_state.json").write_text(
        '{"as_mode":"pure","active_profile":"ws_pure","ws_as_version":"2.1.10",'
        '"fills_session":2,"portfolio_value_xrp":234.1,"as_presence_pct":79.0,'
        '"g2_grade":"watch","cycle_count":100,"mid_price":2.18,"open_offers_count":2,'
        '"toxic_fill_ratio":0.18,"toxic_fill_ratio_30s":0.40,"cancel_per_fill":1.4,'
        '"session_pnl_balance_xrp":0.1}',
        encoding="utf-8",
    )
    (logs / "g6_activation_report.json").write_text(
        '{"activation_tier":"pilot_watch","ws_as_version":"2.1.10"}',
        encoding="utf-8",
    )

    text = build_report(
        window_hours=1.0,
        hud_url="http://188.245.50.229:8765",
        logs_dir=logs,
        now=now_dt,
    )

    assert "WS pure A-S" in text
    assert "Fills — last 1h: 2 | session: 2" in text
    assert "WS fills — last 1h: 2 | session: 2 | total: 2" in text
    assert "G6: pilot_watch" in text
    assert "Presence: 79.0%" in text
    assert "HUD: http://188.245.50.229:8765" in text
    assert "Clear kill" not in text
    assert "Resume:" not in text


def test_hourly_report_shows_resume_only_when_kill_active(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "runtime_state.json").write_text(
        '{"as_mode":"pure","ws_as_version":"2.1.11","cycle_count":1}',
        encoding="utf-8",
    )
    (logs / "kill_switch.json").write_text(
        '{"active": true, "reason": "Daily portfolio drawdown 12.00%"}',
        encoding="utf-8",
    )
    text = build_report(hud_url="", logs_dir=logs)
    assert "Status: KILL" in text
    assert "Resume:" in text


def test_hourly_report_omits_hud_when_url_empty(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "runtime_state.json").write_text(
        '{"active_profile":"safe","cycle_count":1}',
        encoding="utf-8",
    )
    text = build_report(hud_url="", logs_dir=logs)
    assert "HUD:" not in text
    assert "XLedgerMate hourly report" in text


def test_hourly_main_skips_during_quiet_hours(tmp_path: Path, monkeypatch) -> None:
    from config.settings import BotConfig
    from scripts import hourly_telegram_report as mod

    class _Cfg:
        telegram_hourly_report_enabled = True
        telegram_enabled = True
        telegram_token = "t"
        telegram_chat_id = "1"
        telegram_hud_url = ""
        telegram_quiet_hours_enabled = True
        telegram_quiet_start_hour = 22
        telegram_quiet_end_hour = 7

    monkeypatch.setattr(BotConfig, "load", lambda: _Cfg())
    monkeypatch.setattr(
        "monitoring.telegram_schedule.hourly_report_allowed_now",
        lambda **_: False,
    )
    monkeypatch.setattr(mod.sys, "argv", ["hourly_telegram_report.py"])
    assert mod.main() == 0

