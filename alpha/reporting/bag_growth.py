"""Bag growth vs trading edge — portfolio baseline, week-to-date, realized P&L."""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from alpha.reporting.operator_deposits import (
    total_deposited_rlusd,
    total_deposited_xrp,
    total_deposits_xrp_equiv,
)
from alpha.reporting.realized_pnl import build_realized_pnl_snapshot
from risk.drawdown import portfolio_value_xrp

_WEEK_PATH = Path("logs/alpha_bag_week.json")


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except ValueError:
        return None


def _stack_baseline_from_tax_csv(
    logs: Path,
    baseline_utc: str,
) -> tuple[Optional[float], Optional[float]]:
    """Best-effort XRP/RLUSD balances at session baseline from tax CSV snapshots."""
    target = _parse_ts(baseline_utc)
    if target is None:
        return None, None
    best: Optional[datetime] = None
    best_xrp: Optional[float] = None
    best_rlusd: Optional[float] = None
    if not logs.is_dir():
        return None, None
    for path in sorted(logs.glob("trades_*.csv")):
        try:
            import csv

            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    ts = _parse_ts(str(row.get("timestamp_utc") or ""))
                    if ts is None or ts > target:
                        continue
                    try:
                        bx = float(row.get("balance_xrp_after") or 0)
                        br = float(row.get("balance_rlusd_after") or 0)
                    except (TypeError, ValueError):
                        continue
                    if bx <= 0:
                        continue
                    if best is None or ts > best:
                        best = ts
                        best_xrp = bx
                        best_rlusd = br
        except (OSError, csv.Error):
            continue
    return best_xrp, best_rlusd


def _persist_stack_baseline(
    logs: Path,
    *,
    baseline_xrp: float,
    baseline_rlusd: float,
) -> None:
    """Write backfilled stack baseline into alpha_session.json (one-time anchor)."""
    session_path = logs / "alpha_session.json"
    if not session_path.is_file():
        return
    try:
        data = json.loads(session_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict):
        return
    if float(data.get("baseline_xrp") or 0) > 0:
        return
    data["baseline_xrp"] = round(baseline_xrp, 6)
    data["baseline_rlusd"] = round(baseline_rlusd, 6)
    tmp = session_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(session_path)


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _week_start_utc(dt: datetime) -> datetime:
    d = dt.astimezone(timezone.utc).date()
    monday = d - timedelta(days=d.weekday())
    return datetime.combine(monday, time.min, tzinfo=timezone.utc)


def _day_start_utc(dt: datetime) -> datetime:
    d = dt.astimezone(timezone.utc).date()
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _load_week_state(path: Path = _WEEK_PATH) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_week_state(payload: Dict[str, Any], path: Path = _WEEK_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _update_week_anchor(
    *,
    portfolio_xrp: float,
    xrp: float,
    rlusd: float,
    now: datetime,
    path: Path = _WEEK_PATH,
) -> Dict[str, Any]:
    """Persist week/day baselines + lifetime high-water for the bag scoreboard."""
    ws = _load_week_state(path)
    current_week = _week_start_utc(now).isoformat()
    current_day = _day_start_utc(now).isoformat()
    stored_week = str(ws.get("week_start_utc") or "")
    stored_day = str(ws.get("day_start_utc") or "")

    # Preserve high-water across week rolls (lifetime ATH of total bag).
    prev_high = float(ws.get("high_water_portfolio_xrp") or 0.0)
    prev_high_utc = str(ws.get("high_water_utc") or "")

    if stored_week != current_week:
        ws["week_start_utc"] = current_week
        ws["week_start_portfolio_xrp"] = portfolio_xrp
        ws["week_start_xrp"] = xrp
        ws["week_start_rlusd"] = rlusd
    if stored_day != current_day or float(ws.get("day_start_portfolio_xrp") or 0.0) <= 0:
        # New UTC day (or first seed). If today is also week-open day and we already
        # have a week open, reuse it so Monday "today" matches "this week" open.
        week_open = float(ws.get("week_start_portfolio_xrp") or 0.0)
        if (
            current_day == current_week
            and week_open > 0
            and str(ws.get("week_start_utc") or "") == current_week
        ):
            ws["day_start_utc"] = current_day
            ws["day_start_portfolio_xrp"] = week_open
            ws["day_start_xrp"] = float(ws.get("week_start_xrp") or xrp)
            ws["day_start_rlusd"] = float(ws.get("week_start_rlusd") or rlusd)
        else:
            ws["day_start_utc"] = current_day
            ws["day_start_portfolio_xrp"] = portfolio_xrp
            ws["day_start_xrp"] = xrp
            ws["day_start_rlusd"] = rlusd

    ws["last_portfolio_xrp"] = portfolio_xrp
    ws["last_xrp"] = xrp
    ws["last_rlusd"] = rlusd
    ws["updated_utc"] = now.isoformat()

    if portfolio_xrp > prev_high + 1e-9:
        ws["high_water_portfolio_xrp"] = portfolio_xrp
        ws["high_water_utc"] = now.isoformat()
    else:
        ws["high_water_portfolio_xrp"] = prev_high if prev_high > 0 else portfolio_xrp
        ws["high_water_utc"] = prev_high_utc or now.isoformat()

    _save_week_state(ws, path)
    return ws


def build_bag_growth_snapshot(
    *,
    xrp: float,
    rlusd: float,
    mid_rlusd_per_xrp: Optional[float],
    logs_dir: str | Path = "logs",
    now: Optional[datetime] = None,
    persist_week: bool = True,
    persist_stack_baseline: bool = True,
) -> Dict[str, Any]:
    """
    Bag growth separates **portfolio size** (holdings + price) from **trading edge**
    (realized bracket P&L from tax CSV).

    - ``since_baseline_*`` — from ``logs/alpha_session.json`` (operator session anchor).
    - ``week_*`` — Monday 00:00 UTC rolling week portfolio change.
    - ``trading_edge_7d`` — realized TP/SL sum over 7 days (tax CSV).
    """
    end = now or _utc_now()
    logs = Path(logs_dir)

    portfolio = 0.0
    if mid_rlusd_per_xrp is not None and mid_rlusd_per_xrp > 0:
        portfolio = portfolio_value_xrp(xrp, rlusd, float(mid_rlusd_per_xrp))

    week_path = logs / "alpha_bag_week.json"
    week_state = _load_week_state(week_path)
    if persist_week and portfolio > 0:
        week_state = _update_week_anchor(
            portfolio_xrp=portfolio,
            xrp=xrp,
            rlusd=rlusd,
            now=end,
            path=week_path,
        )

    sess_data = _load_week_state(logs / "alpha_session.json")
    baseline_portfolio = float(sess_data.get("baseline_portfolio_xrp") or 0.0)
    baseline_utc = str(sess_data.get("baseline_utc") or "")
    since_baseline_xrp = portfolio - baseline_portfolio if baseline_portfolio > 0 else None
    since_baseline_pct = None
    if since_baseline_xrp is not None and baseline_portfolio > 0:
        since_baseline_pct = (since_baseline_xrp / baseline_portfolio) * 100.0

    operator_deposits_xrp_equiv = total_deposits_xrp_equiv(logs)
    operator_deposits_xrp = total_deposited_xrp(logs)
    operator_deposits_rlusd = total_deposited_rlusd(logs)
    since_baseline_bot_xrp = None
    since_baseline_bot_pct = None
    if since_baseline_xrp is not None:
        since_baseline_bot_xrp = since_baseline_xrp - operator_deposits_xrp_equiv
        if baseline_portfolio > 0:
            since_baseline_bot_pct = (since_baseline_bot_xrp / baseline_portfolio) * 100.0

    baseline_xrp = float(sess_data.get("baseline_xrp") or 0.0)
    baseline_rlusd = float(sess_data.get("baseline_rlusd") or 0.0)
    stack_baseline_source = "session" if baseline_xrp > 0 or baseline_rlusd > 0 else None
    if stack_baseline_source is None and baseline_utc:
        tax_xrp, tax_rlusd = _stack_baseline_from_tax_csv(logs, baseline_utc)
        if tax_xrp is not None and tax_xrp > 0:
            baseline_xrp = tax_xrp
            baseline_rlusd = float(tax_rlusd or 0.0)
            stack_baseline_source = "tax_csv"
            if persist_stack_baseline:
                _persist_stack_baseline(
                    logs,
                    baseline_xrp=baseline_xrp,
                    baseline_rlusd=baseline_rlusd,
                )

    xrp_stack_delta_raw = None
    xrp_stack_delta_bot = None
    rlusd_stack_delta_raw = None
    if stack_baseline_source is not None:
        xrp_stack_delta_raw = xrp - baseline_xrp
        xrp_stack_delta_bot = xrp_stack_delta_raw - operator_deposits_xrp
        rlusd_stack_delta_raw = rlusd - baseline_rlusd

    week_start_xrp = float(week_state.get("week_start_xrp") or 0.0)
    week_xrp_delta = None
    if week_start_xrp > 0:
        week_xrp_delta = xrp - week_start_xrp

    week_start_portfolio = float(week_state.get("week_start_portfolio_xrp") or 0.0)
    week_delta_xrp = None
    week_delta_pct = None
    if week_start_portfolio > 0 and portfolio > 0:
        week_delta_xrp = portfolio - week_start_portfolio
        week_delta_pct = (week_delta_xrp / week_start_portfolio) * 100.0

    day_start_portfolio = float(week_state.get("day_start_portfolio_xrp") or 0.0)
    day_delta_xrp = None
    day_delta_pct = None
    if day_start_portfolio > 0 and portfolio > 0:
        day_delta_xrp = portfolio - day_start_portfolio
        day_delta_pct = (day_delta_xrp / day_start_portfolio) * 100.0

    high_water = float(week_state.get("high_water_portfolio_xrp") or 0.0)
    if portfolio > 0 and high_water <= 0:
        high_water = portfolio
    off_high_xrp = None
    at_high_water = None
    if high_water > 0 and portfolio > 0:
        off_high_xrp = portfolio - high_water
        at_high_water = abs(off_high_xrp) < 0.05  # within 0.05 XRP-eq counts as at high

    portfolio_rlusd_equiv = None
    if portfolio > 0 and mid_rlusd_per_xrp is not None and mid_rlusd_per_xrp > 0:
        portfolio_rlusd_equiv = portfolio * float(mid_rlusd_per_xrp)

    realized_7d = build_realized_pnl_snapshot(
        logs_dir=logs,
        hours=24.0 * 7,
        now=end,
        mid_rlusd_per_xrp=mid_rlusd_per_xrp,
        max_recent_exits=0,
    )

    return {
        "available": portfolio > 0 and baseline_portfolio > 0,
        "as_of_utc": end.isoformat(),
        # Primary scoreboard number — total bag size in XRP-equiv (XRP + RLUSD/mid).
        "portfolio_xrp_equiv": round(portfolio, 4) if portfolio > 0 else None,
        "portfolio_rlusd_equiv": (
            round(portfolio_rlusd_equiv, 4) if portfolio_rlusd_equiv is not None else None
        ),
        "xrp": round(xrp, 4),
        "rlusd": round(rlusd, 4),
        "mid_rlusd_per_xrp": mid_rlusd_per_xrp,
        "baseline_portfolio_xrp": round(baseline_portfolio, 4) if baseline_portfolio > 0 else None,
        "baseline_utc": baseline_utc or None,
        "since_baseline_xrp": round(since_baseline_xrp, 4) if since_baseline_xrp is not None else None,
        "since_baseline_pct": round(since_baseline_pct, 2) if since_baseline_pct is not None else None,
        "operator_deposits_xrp_equiv": round(operator_deposits_xrp_equiv, 4),
        "operator_deposits_xrp": round(operator_deposits_xrp, 4),
        "operator_deposits_rlusd": round(operator_deposits_rlusd, 4),
        "since_baseline_bot_xrp": (
            round(since_baseline_bot_xrp, 4) if since_baseline_bot_xrp is not None else None
        ),
        "since_baseline_bot_pct": (
            round(since_baseline_bot_pct, 2) if since_baseline_bot_pct is not None else None
        ),
        "baseline_xrp": round(baseline_xrp, 4) if baseline_xrp > 0 else None,
        "baseline_rlusd": round(baseline_rlusd, 4) if baseline_rlusd > 0 else None,
        "stack_baseline_source": stack_baseline_source,
        "xrp_stack_delta_raw": (
            round(xrp_stack_delta_raw, 4) if xrp_stack_delta_raw is not None else None
        ),
        "xrp_stack_delta_bot": (
            round(xrp_stack_delta_bot, 4) if xrp_stack_delta_bot is not None else None
        ),
        "rlusd_stack_delta_raw": (
            round(rlusd_stack_delta_raw, 4) if rlusd_stack_delta_raw is not None else None
        ),
        "week_xrp_delta": round(week_xrp_delta, 4) if week_xrp_delta is not None else None,
        "week_start_utc": week_state.get("week_start_utc"),
        "week_start_portfolio_xrp": round(week_start_portfolio, 4) if week_start_portfolio > 0 else None,
        "week_delta_xrp": round(week_delta_xrp, 4) if week_delta_xrp is not None else None,
        "week_delta_pct": round(week_delta_pct, 2) if week_delta_pct is not None else None,
        "day_start_utc": week_state.get("day_start_utc"),
        "day_start_portfolio_xrp": round(day_start_portfolio, 4) if day_start_portfolio > 0 else None,
        "day_delta_xrp": round(day_delta_xrp, 4) if day_delta_xrp is not None else None,
        "day_delta_pct": round(day_delta_pct, 2) if day_delta_pct is not None else None,
        "high_water_portfolio_xrp": round(high_water, 4) if high_water > 0 else None,
        "high_water_utc": week_state.get("high_water_utc"),
        "off_high_xrp": round(off_high_xrp, 4) if off_high_xrp is not None else None,
        "at_high_water": at_high_water,
        "trading_edge_7d": {
            "available": realized_7d.get("available"),
            "realized_profit_xrp_equiv": realized_7d.get("realized_profit_xrp_equiv", 0.0),
            "tp_exits": realized_7d.get("tp_exits", 0),
            "sl_exits": realized_7d.get("sl_exits", 0),
            "window_hours": realized_7d.get("window_hours"),
        },
        "explain": (
            "TOTAL BAG = portfolio_xrp_equiv (XRP coins + RLUSD converted at mid). "
            "This is the primary scoreboard number — bot goal is to grow it. "
            "Day/week/ATH deltas show whether the bag is climbing. "
            "Bot growth strips operator deposits. Trading edge = realized TP/SL only."
        ),
    }


def format_bag_growth_telegram_block(snap: Dict[str, Any]) -> str:
    """Compact multi-line block for Telegram weekly / hourly digests."""
    if not snap.get("available"):
        return "Bag growth: baseline not set yet (wait for valid mid quote)."

    total = float(snap.get("portfolio_xrp_equiv") or 0.0)
    lines = [
        f"TOTAL BAG: {total:.4f} XRP-eq "
        f"({snap.get('xrp', 0):.1f} XRP + {snap.get('rlusd', 0):.1f} RLUSD)",
    ]
    day = snap.get("day_delta_xrp")
    if day is not None:
        dp = snap.get("day_delta_pct")
        dp_s = f" ({dp:+.2f}%)" if dp is not None else ""
        lines.append(f"Today: {float(day):+.4f} XRP-eq{dp_s}")
    week = snap.get("week_delta_xrp")
    if week is not None:
        wpct = snap.get("week_delta_pct")
        wpct_s = f" ({wpct:+.2f}%)" if wpct is not None else ""
        lines.append(f"This week: {float(week):+.4f} XRP-eq{wpct_s}")
    off = snap.get("off_high_xrp")
    if off is not None:
        if snap.get("at_high_water"):
            lines.append(f"ATH: {float(snap.get('high_water_portfolio_xrp') or total):.4f} (at high)")
        else:
            lines.append(
                f"ATH: {float(snap.get('high_water_portfolio_xrp') or 0):.4f} "
                f"({float(off):+.4f} off high)"
            )

    deposits = float(snap.get("operator_deposits_xrp_equiv") or 0.0)
    bot_since = snap.get("since_baseline_bot_xrp")
    since = snap.get("since_baseline_xrp")
    display_since = bot_since if bot_since is not None else since
    if display_since is not None:
        pct = snap.get("since_baseline_bot_pct")
        if pct is None:
            pct = snap.get("since_baseline_pct")
        pct_s = f" ({pct:+.1f}%)" if pct is not None else ""
        base_date = (snap.get("baseline_utc") or "")[:10] or "?"
        label = "Bot growth (ex deposits)" if deposits > 0 else "Since baseline"
        lines.append(f"{label} ({base_date}): {display_since:+.2f} XRP-eq{pct_s}")
        if deposits > 0 and since is not None:
            lines.append(
                f"  (raw {since:+.2f} incl. {deposits:.2f} deposits)"
            )

    stack_bot = snap.get("xrp_stack_delta_bot")
    stack_raw = snap.get("xrp_stack_delta_raw")
    stack_val = stack_bot if stack_bot is not None else stack_raw
    if stack_val is not None:
        lines.append(f"XRP coin stack Δ: {float(stack_val):+.2f} coins")

    edge = snap.get("trading_edge_7d") or {}
    if edge.get("available"):
        lines.append(
            f"Trading edge 7d: {float(edge.get('realized_profit_xrp_equiv') or 0):+.2f} XRP "
            f"(TP {edge.get('tp_exits', 0)} / SL {edge.get('sl_exits', 0)})"
        )

    lines.append("(Primary goal: grow TOTAL BAG. Moves with price + trading.)")
    return "\n".join(lines)


def format_bag_growth_context_block(snap: Dict[str, Any]) -> str:
    """SKYNET context — bag size vs trading edge (authoritative for 'building the bag')."""
    if not snap or not snap.get("available"):
        return "=== Bag growth ===\n(baseline not set — wait for valid mid)"
    lines = [
        "=== Bag scoreboard (PRIMARY metric = TOTAL BAG / portfolio_xrp_equiv) ===",
        f"TOTAL_BAG portfolio_xrp_equiv={snap.get('portfolio_xrp_equiv')} "
        f"portfolio_rlusd_equiv={snap.get('portfolio_rlusd_equiv')} "
        f"mid={snap.get('mid_rlusd_per_xrp')}",
        f"day_delta_xrp={snap.get('day_delta_xrp')} week_delta_xrp={snap.get('week_delta_xrp')} "
        f"off_high_xrp={snap.get('off_high_xrp')} at_high_water={snap.get('at_high_water')}",
        f"since_baseline_bot_xrp={snap.get('since_baseline_bot_xrp')} "
        f"since_baseline_bot_pct={snap.get('since_baseline_bot_pct')}",
        f"xrp_stack_delta_bot={snap.get('xrp_stack_delta_bot')} "
        f"(raw coins Δ; baseline source={snap.get('stack_baseline_source')})",
        f"operator_deposits_xrp_equiv={snap.get('operator_deposits_xrp_equiv')}",
    ]
    edge = snap.get("trading_edge_7d") or {}
    if edge.get("available"):
        lines.append(
            f"trading_edge_7d={edge.get('realized_profit_xrp_equiv')} XRP "
            f"(TP {edge.get('tp_exits')} / SL {edge.get('sl_exits')})"
        )
    explain = snap.get("explain")
    if explain:
        lines.append(f"explain={explain}")
    return "\n".join(lines)
