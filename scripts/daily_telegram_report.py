#!/usr/bin/env python3
"""Daily Alpha bag story — primary narrative Telegram digest."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOGS = ROOT / "logs"


def build_daily_alpha_report(
    *,
    hud_url: str = "",
    logs_dir: Path | None = None,
    now: datetime | None = None,
) -> str:
    from alpha.reporting.telegram_narrative import (
        build_alpha_narrative_report,
        load_agent_for_recs,
        load_alpha_state,
    )

    logs = logs_dir or LOGS
    now = now or datetime.now(tz=timezone.utc)
    state = load_alpha_state(logs)
    return build_alpha_narrative_report(
        state=state,
        logs_dir=logs,
        period="daily",
        now=now,
        hud_url=hud_url,
        agent=load_agent_for_recs(logs),
        persist_week=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Send daily Alpha narrative Telegram report")
    parser.add_argument("--dry-run", action="store_true", help="Print only; do not send")
    args = parser.parse_args()

    from config.settings import BotConfig
    from monitoring.telegram_schedule import hourly_report_allowed_now

    config = BotConfig.load()
    if not getattr(config, "telegram_enabled", False):
        print("Telegram disabled (telegram_enabled: false).", file=sys.stderr)
        return 0
    if not getattr(config, "telegram_daily_report_enabled", True):
        print("Daily report disabled (telegram_daily_report_enabled: false).", file=sys.stderr)
        return 0

    # Optional quiet hours: same window as hourly if enabled
    if getattr(config, "telegram_quiet_hours_enabled", False):
        if not hourly_report_allowed_now(
            quiet_hours_enabled=True,
            quiet_start_hour=int(getattr(config, "telegram_quiet_start_hour", 22)),
            quiet_end_hour=int(getattr(config, "telegram_quiet_end_hour", 7)),
        ):
            print("Quiet hours — skip daily report.", file=sys.stderr)
            return 0

    text = build_daily_alpha_report(hud_url=getattr(config, "telegram_hud_url", "") or "")
    if args.dry_run:
        print(text)
        return 0

    from monitoring.telegram_alerts import TelegramAlerts

    alerts = TelegramAlerts(
        token=config.telegram_token,
        chat_id=config.telegram_chat_id,
        enabled=config.telegram_enabled,
    )
    if not alerts.is_configured():
        print("Telegram not configured.", file=sys.stderr)
        return 1
    if alerts.send_message(text):
        print("Daily narrative sent.")
        return 0
    print("Failed to send daily report.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
