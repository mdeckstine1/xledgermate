"""Bag growth vs trading edge — portfolio baseline, week-to-date, realized P&L."""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from alpha.reporting.operator_deposits import total_deposits_xrp_equiv
from alpha.reporting.realized_pnl import build_realized_pnl_snapshot
from risk.drawdown import portfolio_value_xrp

_WEEK_PATH = Path("logs/alpha_bag_week.json")


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
    since_baseline_bot_xrp = None
    since_baseline_bot_pct = None
    if since_baseline_xrp is not None:
        since_baseline_bot_xrp = since_baseline_xrp - operator_deposits_xrp_equiv
        if baseline_portfolio > 0:
            since_baseline_bot_pct = (since_baseline_bot_xrp / baseline_portfolio) * 100.0

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
        "since_baseline_bot_xrp": (
            round(since_baseline_bot_xrp, 4) if since_baseline_bot_xrp is not None else None
        ),
        "since_baseline_bot_pct": (
            round(since_baseline_bot_pct, 2) if since_baseline_bot_pct is not None else None
        ),
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
            "Bag growth = portfolio size vs session baseline (price + holdings). "
            "Bot-adjusted growth subtracts operator deposits. "
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
                f"  (raw {since:+.2f} XRP incl. {deposits:.2f} XRP operator deposits)"
            )

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

    lines.append("(Bag ≠ edge: price moves and RLUSD deploy can grow the book while TP/SL bleeds.)")
    return "\n".join(lines)
