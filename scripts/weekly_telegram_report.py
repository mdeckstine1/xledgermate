#!/usr/bin/env python3
"""Weekly Alpha bag-growth + trading-edge Telegram digest."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOGS = ROOT / "logs"


def _load_runtime(logs: Path) -> dict:
    path = logs / "alpha_runtime_state.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def build_weekly_alpha_report(
    *,
    hud_url: str = "",
    logs_dir: Path | None = None,
    now: datetime | None = None,
) -> str:
    from alpha.reporting.bag_growth import build_bag_growth_snapshot, format_bag_growth_telegram_block

    logs = logs_dir or LOGS
    now = now or datetime.now(tz=timezone.utc)
    state = _load_runtime(logs)
    risk = state.get("risk") or {}
    inv = state.get("inventory") or {}
    decision = state.get("decision") or {}

    bag = build_bag_growth_snapshot(
        xrp=float(state.get("xrp") or 0),
        rlusd=float(state.get("rlusd") or 0),
        mid_rlusd_per_xrp=state.get("mid"),
        logs_dir=logs,
        now=now,
        persist_week=True,
    )

    mode = "DRY-RUN" if state.get("dry_run", True) else "LIVE"
    lines = [
        "XLedgerMate Alpha — weekly bag report",
        f"{now.strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        f"Mode: {mode} | Posture: {state.get('posture', '?')}",
        f"Decision: {decision.get('action', '?')} — {decision.get('reason', '')}",
        f"Inventory: {inv.get('label', '?')} dev={float(inv.get('deviation') or 0):+.3f}",
        f"Session P&L (MTM): {float(risk.get('session_pnl_xrp') or 0):+.4f} XRP",
        "",
        format_bag_growth_telegram_block(bag),
    ]
    hud = (hud_url or "").strip()
    if hud:
        lines.extend(["", f"HUD: {hud}"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send weekly Alpha bag-growth Telegram report")
    parser.add_argument("--dry-run", action="store_true", help="Print only; do not send")
    args = parser.parse_args()

    from config.settings import BotConfig

    config = BotConfig.load()
    if not getattr(config, "telegram_enabled", False):
        print("Telegram disabled (telegram_enabled: false).", file=sys.stderr)
        return 0
    if not getattr(config, "telegram_weekly_report_enabled", True):
        print("Weekly report disabled (telegram_weekly_report_enabled: false).", file=sys.stderr)
        return 0

    text = build_weekly_alpha_report(hud_url=getattr(config, "telegram_hud_url", "") or "")
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
    if not alerts.send_message(text):
        print("Failed to send weekly Telegram message.", file=sys.stderr)
        return 1
    print("Weekly report sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
