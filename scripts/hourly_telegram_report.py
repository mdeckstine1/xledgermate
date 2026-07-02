#!/usr/bin/env python3
"""Hourly operator summary to Telegram (fills, session, kill, WS pure A-S metrics)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOGS = ROOT / "logs"
WS_FILL_MARKER = "WS pure fill"
WS_ENGINE_START_MARKERS = ("Engine started", "WS-engine started", "ws-engine started")


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


def _is_ws_fill(row: dict[str, str]) -> bool:
    return WS_FILL_MARKER in (row.get("notes") or "")


def _session_start_index(rows: list[dict[str, str]]) -> int:
    majors = [
        i
        for i, r in enumerate(rows)
        if r.get("event_type") == "MAJOR"
        and any(m in (r.get("notes") or "") for m in WS_ENGINE_START_MARKERS)
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


def _is_ws_runtime(rs: dict[str, Any]) -> bool:
    if str(rs.get("as_mode") or "").lower() == "pure":
        return True
    if str(rs.get("active_profile") or "") == "ws_pure":
        return True
    return bool(rs.get("ws_as_version"))


def _fmt_on_off(value: Any) -> str:
    if value is True:
        return "ON"
    if value is False:
        return "OFF"
    return "?"


def _qd_lines_from_runtime(rs: dict[str, Any], *, logs: Path, since: datetime) -> list[str]:
    """Compact L1–L5 snapshot for Telegram (acquisition-centered MM)."""
    try:
        from experimental.ws_feed.qd_hud import build_qd_hud_fields

        hud = build_qd_hud_fields(rs)
    except Exception:
        hud = {}

    snap = hud.get("qd_snapshot") or {}
    summary = hud.get("qd_decision_summary") or {}
    bid = snap.get("bid") or {}
    ask = snap.get("ask") or {}

    book = str(snap.get("book_mode") or rs.get("qd_book_mode") or "?").upper()
    solo = snap.get("solo_mode", rs.get("solo_mode"))
    drift = snap.get("drift_label") or rs.get("qd_drift_band") or rs.get("inventory_label") or "?"
    peer = snap.get("peer_lane_token") or rs.get("qd_peer_lane_token") or "?"
    intent = snap.get("intent_short") or snap.get("intent") or rs.get("qd_intent") or "?"
    intent_reason = (snap.get("intent_reason") or rs.get("qd_intent_reason") or "")[:72]

    bid_allowed = rs.get("qd_bid_allowed", bid.get("allowed"))
    ask_allowed = rs.get("qd_ask_allowed", ask.get("allowed"))
    bid_cause = rs.get("qd_bid_pause_cause") or bid.get("block_cause") or ""
    ask_cause = rs.get("qd_ask_pause_cause") or ask.get("block_cause") or ""

    bid_bps = bid.get("implied_bps") or rs.get("qd_bid_implied_bps")
    ask_bps = ask.get("implied_bps") or rs.get("qd_ask_implied_bps")
    bid_edge = f"{float(bid_bps):.1f}bps" if bid_bps is not None else "?"
    ask_edge = f"{float(ask_bps):.1f}bps" if ask_bps is not None else "?"
    bid_ev = "✓" if bid.get("edge_viable", rs.get("qd_bid_edge_viable")) else "✗"
    ask_ev = "✓" if ask.get("edge_viable", rs.get("qd_ask_edge_viable")) else "✗"

    inv_cb = snap.get("inventory_cb_label") or rs.get("qd_inventory_cb_mode") or "?"
    bleed = "active" if summary.get("protection_active") else "clear"
    would = rs.get("qd_would_quote", snap.get("would_quote"))
    status = summary.get("status_hint") or rs.get("zero_quote_reason") or ""

    lines = [
        "QD (layered A-S):",
        f"  Posture: {book}{' · solo' if solo else ''} · drift {drift} · peer {peer}",
        f"  Intent: {intent}" + (f" — {intent_reason}" if intent_reason else ""),
        f"  L5: bid {_fmt_on_off(bid_allowed)}"
        + (f" ({bid_cause})" if bid_cause and not bid_allowed else "")
        + f" · ask {_fmt_on_off(ask_allowed)}"
        + (f" ({ask_cause})" if ask_cause and not ask_allowed else ""),
        f"  Edge: bid {bid_edge}{bid_ev} · ask {ask_edge}{ask_ev} · inv CB {inv_cb} · bleed {bleed}",
        f"  Quote: would_quote={_fmt_on_off(would).lower()}"
        + (f" · {status[:60]}" if status else ""),
    ]

    mix = _qd_intent_mix_in_window(logs / "xledgermate.log", since=since)
    if mix:
        lines.append(f"  Last hour intents: {mix}")
    return lines


def _qd_intent_mix_in_window(log_path: Path, *, since: datetime) -> str:
    """Count QD_FINAL intents in the lookback window (compact operator mix)."""
    if not log_path.exists():
        return ""
    try:
        from collections import Counter

        from scripts.qd_final_report import parse_qd_final_line, tail_qd_final_lines

        counts: Counter[str] = Counter()
        for line in tail_qd_final_lines(log_path, limit=120):
            rec = parse_qd_final_line(line)
            ts_raw = rec.get("_ts", "")
            if not ts_raw:
                continue
            ts = _parse_ts(ts_raw.replace(" ", "T") + "+00:00")
            if ts is None or ts < since:
                continue
            intent = rec.get("intent") or "?"
            if intent == "solo_accumulate_on_edge":
                counts["accum"] += 1
            elif intent == "inventory_unload":
                counts["trim"] += 1
            else:
                counts[intent] += 1
        if not counts:
            return ""
        parts = []
        for key in ("accum", "trim", "two_sided_skim", "patient_solo"):
            if counts.get(key):
                parts.append(f"{key}={counts[key]}")
        for key, val in sorted(counts.items()):
            if key not in ("accum", "trim", "two_sided_skim", "patient_solo"):
                parts.append(f"{key}={val}")
        return ", ".join(parts)
    except Exception:
        return ""


def _alpha_runtime_state(logs: Path) -> dict[str, Any]:
    return _load_json(logs / "alpha_runtime_state.json")


def _is_alpha_deploy(logs: Path) -> bool:
    return _alpha_runtime_state(logs).get("hud_kind") == "alpha"


def _alpha_cycles_since(logs: Path, *, since: datetime) -> int:
    path = logs / "alpha_activity.jsonl"
    if not path.exists():
        return 0
    count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("event") != "cycle":
                continue
            ts = _parse_ts(str(row.get("ts") or ""))
            if ts is not None and ts >= since:
                count += 1
    except (json.JSONDecodeError, OSError):
        return 0
    return count


def build_alpha_report(
    *,
    window_hours: float = 1.0,
    hud_url: str = "",
    logs_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> str:
    """Hourly digest for Trading Bot Alpha (reads alpha_runtime_state.json)."""
    logs = logs_dir or LOGS
    now = now or datetime.now(tz=timezone.utc)
    since = now - timedelta(hours=window_hours)
    state = _alpha_runtime_state(logs)
    kill = _load_json(logs / "kill_switch.json")

    mode = "DRY-RUN" if state.get("dry_run", True) else "LIVE"
    inv = state.get("inventory") or {}
    risk = state.get("risk") or {}
    decision = state.get("decision") or {}
    brackets = (state.get("brackets") or {}).get("summary") or {}
    cycles = _alpha_cycles_since(logs, since=since)

    kill_active = bool(kill.get("active")) or bool(risk.get("kill_switch_active"))
    kill_reason = str(kill.get("reason") or risk.get("kill_switch_reason") or "").strip()

    from alpha.reporting.bag_growth import build_bag_growth_snapshot, format_bag_growth_telegram_block

    bag = build_bag_growth_snapshot(
        xrp=float(state.get("xrp") or 0),
        rlusd=float(state.get("rlusd") or 0),
        mid_rlusd_per_xrp=state.get("mid"),
        logs_dir=logs,
        now=now,
        persist_week=False,
    )
    bag_block = format_bag_growth_telegram_block(bag)

    lines = [
        "XLedgerMate Alpha hourly",
        f"{now.strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        f"Mode: {mode} | Network: {state.get('network', '?')}",
        f"Posture: {state.get('posture', '?')} | Cycles ({window_hours:g}h): {cycles}",
        f"Decision: {decision.get('action', '?')} — {decision.get('reason', '')}",
        "",
        f"Portfolio: {float(state.get('portfolio_xrp_equiv') or 0):.4f} XRP equiv",
        f"XRP: {float(state.get('xrp') or 0):.4f} | RLUSD: {float(state.get('rlusd') or 0):.4f}",
        f"Mid: {float(state.get('mid') or 0):.6f} RLUSD/XRP",
        f"Inventory: {inv.get('label', '?')} dev={float(inv.get('deviation') or 0):+.3f}",
        f"Session P&L: {float(risk.get('session_pnl_xrp') or 0):+.4f} XRP | Drawdown: {float(risk.get('drawdown_pct') or 0):.2f}%",
        "",
        f"Brackets: pending={brackets.get('pending_buys', 0)} fixed={brackets.get('active_fixed', 0)} "
        f"sl_trail={brackets.get('active_sl_trailing', 0)} breakout={brackets.get('active_breakout_trailing', 0)}",
        f"Open offers: {int(state.get('open_offers_count') or 0)}",
        "",
        bag_block,
    ]
    if kill_active:
        lines.append(f"KILL: {kill_reason[:200] if kill_reason else 'active'}")
    hud = (hud_url or "").strip()
    if hud:
        lines.extend(["", f"HUD: {hud}"])
    return "\n".join(lines)


def build_report(
    *,
    window_hours: float = 1.0,
    hud_url: str = "",
    logs_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> str:
    logs = logs_dir or LOGS
    if _is_alpha_deploy(logs):
        return build_alpha_report(
            window_hours=window_hours,
            hud_url=hud_url,
            logs_dir=logs,
            now=now,
        )
    now = now or datetime.now(tz=timezone.utc)
    since_hour = now - timedelta(hours=window_hours)
    rows = _all_trade_rows() if logs_dir is None else _trade_rows_from_dir(logs)
    session_rows = rows[_session_start_index(rows) :]
    session_fills = [r for r in session_rows if _is_fill(r)]
    hour_fills = _fills_in_window(rows, since=since_hour)
    ws_fills_all = [r for r in rows if _is_ws_fill(r)]
    ws_session_fills = [r for r in session_fills if _is_ws_fill(r)]
    ws_hour_fills = [r for r in hour_fills if _is_ws_fill(r)]

    rs = _load_json(logs / "runtime_state.json")
    kill = _load_json(logs / "kill_switch.json")
    g6 = _load_json(logs / "g6_activation_report.json")

    hour = _summarize_fills(hour_fills)
    session = _summarize_fills(session_fills)
    ws_hour = _summarize_fills(ws_hour_fills)
    ws_session = _summarize_fills(ws_session_fills)

    kill_active = bool(kill.get("active")) or bool(rs.get("kill_switch_active"))
    kill_reason = str(kill.get("reason") or rs.get("kill_switch_reason") or "").strip()
    running = _engine_running()
    ws_path = _is_ws_runtime(rs)

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
    policy = str(rs.get("quoting_policy_label") or "")[:80]
    if not policy and ws_path:
        policy = str(rs.get("zero_quote_reason") or rs.get("edge_resolution_summary") or "")[:80]

    fills_session_rt = int(rs.get("fills_session") or 0)
    session_fill_count = fills_session_rt if fills_session_rt > 0 else session["count"]
    if ws_path and ws_session["count"]:
        session_fill_count = max(session_fill_count, ws_session["count"])

    status = "KILL" if kill_active else ("RUNNING" if running else "STOPPED")
    title = "XLedgerMate hourly (Ashigaru · WS pure A-S)" if ws_path else "XLedgerMate hourly report"
    lines = [
        title,
        f"{now.strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        f"Fills — last {window_hours:g}h: {hour['count']} | session: {session_fill_count}",
    ]
    if ws_path:
        lines.append(f"WS fills — last {window_hours:g}h: {ws_hour['count']} | session: {ws_session['count']} | total: {len(ws_fills_all)}")
    lines.extend(
        [
            "",
            f"Status: {status} | Profile: {profile}",
            f"Engine: {'up' if running else 'down'} | Cycles: {cycles}",
        ]
    )
    if ws_path:
        ws_ver = str(rs.get("ws_as_version") or g6.get("ws_as_version") or "?")
        presence = rs.get("as_presence_pct")
        g6_tier = str(
            g6.get("activation_tier")
            or (g6.get("performance_metrics") or {}).get("activation", {}).get("tier")
            or ""
        ).strip()
        g2 = str(rs.get("g2_grade") or "").strip()
        extra = f"v{ws_ver}"
        if presence is not None:
            extra += f" | Presence: {presence}%"
        if g6_tier:
            extra += f" | G6: {g6_tier}"
        if g2:
            extra += f" | G2: {g2}"
        lines.append(extra)
        from experimental.ws_feed.reservation_metrics import (
            enrich_runtime_reservation_metrics,
            format_reservation_bbo_delta,
        )

        rs = enrich_runtime_reservation_metrics(rs)
        delta = rs.get("reservation_to_bbo_delta_bps")
        if delta is not None:
            inside = rs.get("inside_l1")
            lines.append(
                f"Res→BBO: {format_reservation_bbo_delta(delta, inside_l1=inside)}"
            )
        lines.append("")
        lines.extend(_qd_lines_from_runtime(rs, logs=logs, since=since_hour))
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
            f"Session (since restart) — fills: {session_fill_count}",
            f"  Capture: {session['capture_xrp']:+.4f} XRP | ~{session['bps']:.1f} bps",
            f"  Neg capture: {session['neg_capture']}/{session['count']}",
            "",
            f"Toxic: {toxic:.0f}% | @30s: {toxic_30:.0f}% | Cancel/fill: {cancel_cf:.2f}",
        ]
    )
    if policy:
        label = "Quote status" if ws_path else "Policy"
        lines.append(f"{label}: {policy}")
    if not ws_path:
        kill_limit = 0.85
        kill_min_fills = 45
        if session_fill_count >= kill_min_fills and sess_bal_pnl <= -kill_limit:
            lines.append("")
            lines.append(f"⚠ Near session kill band (−{kill_limit} XRP @ {kill_min_fills}+ fills)")
    hud = (hud_url or "").strip()
    if hud:
        lines.append("")
        lines.append(f"HUD: {hud}")
    if kill_active:
        lines.append("")
        lines.append("Resume: python main.py --mode clear-kill && systemctl restart xledgermate")
    return "\n".join(lines)


def _trade_rows_from_dir(logs: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(logs.glob("trades_*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows.extend(csv.DictReader(handle))
        except OSError:
            continue
    return rows


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

    from config.settings import BotConfig

    config = BotConfig.load()
    if not getattr(config, "telegram_hourly_report_enabled", True):
        print("Hourly report disabled (telegram_hourly_report_enabled: false).", file=sys.stderr)
        return 0

    from monitoring.telegram_schedule import hourly_report_allowed_now, quiet_hours_label

    quiet_enabled = bool(getattr(config, "telegram_quiet_hours_enabled", False))
    quiet_start = int(getattr(config, "telegram_quiet_start_hour", 22))
    quiet_end = int(getattr(config, "telegram_quiet_end_hour", 7))
    if not hourly_report_allowed_now(
        quiet_hours_enabled=quiet_enabled,
        quiet_start_hour=quiet_start,
        quiet_end_hour=quiet_end,
    ):
        label = quiet_hours_label(quiet_start, quiet_end)
        print(f"Hourly report skipped — quiet hours ({label}).", file=sys.stderr)
        return 0

    text = build_report(
        window_hours=args.hours,
        hud_url=getattr(config, "telegram_hud_url", "") or "",
    )
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
