#!/usr/bin/env python3
"""Hourly operator summary to Telegram (fills, session, kill, Gate 2 hints)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOGS = ROOT / "logs"


def _parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _all_trade_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(LOGS.glob("trades_*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows.extend(csv.DictReader(handle))
        except OSError:
            continue
    return rows


def _is_fill(row: dict[str, str]) -> bool:
    side = (row.get("side") or row.get("event_type") or "").upper()
    return side in ("BUY", "SELL")


def _session_start_index(rows: list[dict[str, str]]) -> int:
    majors = [
        i
        for i, r in enumerate(rows)
        if r.get("event_type") == "MAJOR" and "Engine started" in (r.get("notes") or "")
    ]
    return majors[-1] if majors else 0


def _fills_in_window(rows: list[dict[str, str]], *, since: datetime) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        if not _is_fill(row):
            continue
        ts = _parse_ts(row.get("timestamp_utc", ""))
        if ts is None or ts < since:
            continue
        out.append(row)
    return out


def _summarize_fills(fills: list[dict[str, str]]) -> dict[str, Any]:
    n = len(fills)
    if n == 0:
        return {
            "count": 0,
            "buys": 0,
            "sells": 0,
            "capture_xrp": 0.0,
            "neg_capture": 0,
            "volume_xrp": 0.0,
            "bps": 0.0,
            "last_side": "",
            "last_ts": "",
        }
    capture = sum(float(r.get("profit_xrp_equiv") or 0) for r in fills)
    neg = sum(1 for r in fills if float(r.get("profit_xrp_equiv") or 0) < 0)
    volume = sum(float(r.get("xrp_amount") or 0) for r in fills)
    bps = (capture / volume * 10000.0) if volume > 0 else 0.0
    buys = sum(1 for r in fills if (r.get("side") or "").upper() == "BUY")
    sells = sum(1 for r in fills if (r.get("side") or "").upper() == "SELL")
    last = fills[-1]
    return {
        "count": n,
        "buys": buys,
        "sells": sells,
        "capture_xrp": capture,
        "neg_capture": neg,
        "volume_xrp": volume,
        "bps": bps,
        "last_side": (last.get("side") or "").upper(),
        "last_ts": (last.get("timestamp_utc") or "")[:19],
    }


def _engine_running() -> bool:
    try:
        from gui.engine_control import is_engine_running

        return bool(is_engine_running())
    except Exception:
        pid_path = LOGS / "engine.pid"
        if not pid_path.exists():
            return False
        try:
            import os

            pid = int(pid_path.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False


def build_report(*, window_hours: float = 1.0) -> str:
    now = datetime.now(tz=timezone.utc)
    since_hour = now - timedelta(hours=window_hours)
    rows = _all_trade_rows()
    session_rows = rows[_session_start_index(rows) :]
    session_fills = [r for r in session_rows if _is_fill(r)]
    hour_fills = _fills_in_window(rows, since=since_hour)

    rs = _load_json(LOGS / "runtime_state.json")
    kill = _load_json(LOGS / "kill_switch.json")

    hour = _summarize_fills(hour_fills)
    session = _summarize_fills(session_fills)

    kill_active = bool(kill.get("active")) or bool(rs.get("kill_switch_active"))
    kill_reason = str(kill.get("reason") or rs.get("kill_switch_reason") or "").strip()
    running = _engine_running()

    portfolio = float(rs.get("portfolio_value_xrp") or 0)
    drawdown = float(rs.get("drawdown_pct") or 0)
    mid = float(rs.get("mid_price") or 0)
    profile = rs.get("active_profile") or "?"
    cycles = int(rs.get("cycle_count") or 0)
    open_offers = int(rs.get("open_offers_count") or len(rs.get("open_offers") or []))
    sess_bal_pnl = float(
        rs.get("session_pnl_balance_xrp")
        or rs.get("session_pnl_xrp_estimate")
        or 0
    )
    toxic = float(rs.get("toxic_fill_ratio") or 0) * 100
    toxic_30 = float(rs.get("toxic_fill_ratio_30s") or 0) * 100
    cancel_cf = float(rs.get("cancel_per_fill") or 0)
    policy = str(rs.get("quoting_policy_label") or rs.get("edge_resolution_summary") or "")[:80]

    status = "KILL" if kill_active else ("RUNNING" if running else "STOPPED")
    lines = [
        f"XLedgerMate hourly report",
        f"{now.strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        f"Status: {status} | Profile: {profile}",
        f"Engine: {'up' if running else 'down'} | Cycles: {cycles}",
    ]
    if kill_active and kill_reason:
        lines.append(f"Kill: {kill_reason[:200]}")
    lines.extend(
        [
            "",
            f"Portfolio: {portfolio:.4f} XRP | Drawdown: {drawdown:.2f}%",
            f"Mid: {mid:.6f} RLUSD/XRP | Open offers: {open_offers}",
            f"Session balance PnL: {sess_bal_pnl:+.4f} XRP",
            "",
            f"Last {window_hours:g}h — fills: {hour['count']} "
            f"(B{hour['buys']}/S{hour['sells']})",
            f"  Capture: {hour['capture_xrp']:+.4f} XRP | ~{hour['bps']:.1f} bps",
            f"  Neg capture: {hour['neg_capture']}/{hour['count']}",
        ]
    )
    if hour["count"] and hour["last_ts"]:
        lines.append(f"  Last fill: {hour['last_side']} @ {hour['last_ts']} UTC")
    lines.extend(
        [
            "",
            f"Session (since restart) — fills: {session['count']}",
            f"  Capture: {session['capture_xrp']:+.4f} XRP | ~{session['bps']:.1f} bps",
            f"  Neg capture: {session['neg_capture']}/{session['count']}",
            "",
            f"Toxic: {toxic:.0f}% | @30s: {toxic_30:.0f}% | Cancel/fill: {cancel_cf:.2f}",
        ]
    )
    if policy:
        lines.append(f"Policy: {policy}")
    if session["count"] >= 45 and sess_bal_pnl <= -0.85:
        lines.append("")
        lines.append("⚠ Near session kill band (−0.85 XRP @ 45+ fills)")
    lines.append("")
    lines.append("Clear kill: clear-kill + systemctl restart xledgermate")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send hourly XLedgerMate summary to Telegram")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print message only; do not send",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=1.0,
        help="Lookback window for fill stats (default 1)",
    )
    args = parser.parse_args()

    text = build_report(window_hours=args.hours)
    if args.dry_run:
        print(text)
        return 0

    from config.settings import BotConfig
    from monitoring.telegram_alerts import TelegramAlerts

    config = BotConfig.load()
    alerts = TelegramAlerts(
        token=config.telegram_token,
        chat_id=config.telegram_chat_id,
        enabled=config.telegram_enabled,
    )
    if not alerts.is_configured():
        print("Telegram not configured (telegram_enabled + token + chat_id).", file=sys.stderr)
        return 1
    ok = alerts.send_message(text)
    if not ok:
        print("Failed to send Telegram message.", file=sys.stderr)
        return 1
    print("Hourly report sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())