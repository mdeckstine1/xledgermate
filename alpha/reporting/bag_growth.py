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
    """Persist Monday-UTC week baseline; roll forward on new calendar week."""
    ws = _load_week_state(path)
    current_week = _week_start_utc(now).isoformat()
    stored_week = str(ws.get("week_start_utc") or "")

    if stored_week != current_week:
        ws = {
            "week_start_utc": current_week,
            "week_start_portfolio_xrp": portfolio_xrp,
            "week_start_xrp": xrp,
            "week_start_rlusd": rlusd,
            "last_portfolio_xrp": portfolio_xrp,
            "last_xrp": xrp,
            "last_rlusd": rlusd,
            "updated_utc": now.isoformat(),
        }
    else:
        ws["last_portfolio_xrp"] = portfolio_xrp
        ws["last_xrp"] = xrp
        ws["last_rlusd"] = rlusd
        ws["updated_utc"] = now.isoformat()

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
        "portfolio_xrp_equiv": round(portfolio, 4) if portfolio > 0 else None,
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
        "trading_edge_7d": {
            "available": realized_7d.get("available"),
            "realized_profit_xrp_equiv": realized_7d.get("realized_profit_xrp_equiv", 0.0),
            "tp_exits": realized_7d.get("tp_exits", 0),
            "sl_exits": realized_7d.get("sl_exits", 0),
            "window_hours": realized_7d.get("window_hours"),
        },
        "explain": (
            "Value Δ = XRP-equiv (coins + RLUSD at mid — moves with price). "
            "XRP stack Δ = coin count only. Bot-adjusted subtracts operator deposits. "
            "Trading edge = realized bracket P&L from tax CSV (TP/SL only)."
        ),
    }


def format_bag_growth_telegram_block(snap: Dict[str, Any]) -> str:
    """Compact multi-line block for Telegram weekly / hourly digests."""
    if not snap.get("available"):
        return "Bag growth: baseline not set yet (wait for valid mid quote)."

    lines = [
        "Bag growth (portfolio vs baseline)",
        f"Now: {snap.get('portfolio_xrp_equiv', 0):.2f} XRP equiv "
        f"({snap.get('xrp', 0):.1f} XRP + {snap.get('rlusd', 0):.1f} RLUSD)",
    ]
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
        label = "Bot bag growth" if deposits > 0 else "Since baseline"
        lines.append(f"{label} ({base_date}): {display_since:+.2f} XRP{pct_s}")
        if deposits > 0 and since is not None:
            lines.append(
                f"  (raw {since:+.2f} XRP-equiv incl. {deposits:.2f} XRP-equiv deposits)"
            )

    stack_bot = snap.get("xrp_stack_delta_bot")
    stack_raw = snap.get("xrp_stack_delta_raw")
    stack_val = stack_bot if stack_bot is not None else stack_raw
    if stack_val is not None:
        src = snap.get("stack_baseline_source") or "session"
        lines.append(f"XRP stack Δ ({src}): {float(stack_val):+.2f} XRP coins")
        lines.append(f"  (now {snap.get('xrp', 0):.1f} XRP · baseline {snap.get('baseline_xrp', 0):.1f})")

    week = snap.get("week_delta_xrp")
    if week is not None:
        wpct = snap.get("week_delta_pct")
        wpct_s = f" ({wpct:+.1f}%)" if wpct is not None else ""
        lines.append(f"This week (Mon UTC): {week:+.2f} XRP{wpct_s}")

    edge = snap.get("trading_edge_7d") or {}
    if edge.get("available"):
        lines.append(
            f"Trading edge 7d: {float(edge.get('realized_profit_xrp_equiv') or 0):+.2f} XRP "
            f"(TP {edge.get('tp_exits', 0)} / SL {edge.get('sl_exits', 0)})"
        )
    else:
        lines.append("Trading edge 7d: no closed brackets in window")

    lines.append("(Value moves with price; XRP stack Δ is coin count only.)")
    return "\n".join(lines)


def format_bag_growth_context_block(snap: Dict[str, Any]) -> str:
    """SKYNET context — bag size vs trading edge (authoritative for 'building the bag')."""
    if not snap or not snap.get("available"):
        return "=== Bag growth ===\n(baseline not set — wait for valid mid)"
    lines = [
        "=== Bag growth (are we building the bag? — prefer over session_pnl MTM) ===",
        f"portfolio_xrp_equiv={snap.get('portfolio_xrp_equiv')} mid={snap.get('mid_rlusd_per_xrp')}",
        f"since_baseline_bot_xrp={snap.get('since_baseline_bot_xrp')} "
        f"since_baseline_bot_pct={snap.get('since_baseline_bot_pct')}",
        f"xrp_stack_delta_bot={snap.get('xrp_stack_delta_bot')} "
        f"(raw coins Δ; baseline source={snap.get('stack_baseline_source')})",
        f"operator_deposits_xrp_equiv={snap.get('operator_deposits_xrp_equiv')}",
        f"week_delta_xrp={snap.get('week_delta_xrp')} week_delta_pct={snap.get('week_delta_pct')}",
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
