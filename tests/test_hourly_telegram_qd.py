"""QD section in hourly Telegram report."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.hourly_telegram_report import build_report


def test_hourly_report_qd_intent_mix_from_log(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    now_dt = datetime(2026, 6, 21, 17, 0, tzinfo=timezone.utc)
    ts1 = (now_dt - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
    ts2 = (now_dt - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    (logs / "xledgermate.log").write_text(
        f"2026-06-21 {ts1[11:]} | INFO | ops | QD_FINAL | intent=solo_accumulate_on_edge | bid_allowed=true\n"
        f"2026-06-21 {ts2[11:]} | INFO | ops | QD_FINAL | intent=inventory_unload | bid_allowed=false\n",
        encoding="utf-8",
    )
    (logs / "runtime_state.json").write_text(
        '{"as_mode":"pure","ws_as_version":"2.3.1","cycle_count":1,'
        '"qd_intent":"solo_accumulate_on_edge","qd_book_mode":"solo","solo_mode":true,'
        '"qd_bid_allowed":true,"qd_ask_allowed":false,"qd_would_quote":true}',
        encoding="utf-8",
    )
    text = build_report(window_hours=1.0, logs_dir=logs, now=now_dt)
    assert "Last hour intents:" in text
    assert "accum=" in text
    assert "trim=" in text
