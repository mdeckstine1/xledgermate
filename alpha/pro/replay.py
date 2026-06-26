"""Alpha bracket replay — realized edge and churn from tax CSV + bracket store."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from alpha.orders.types import BracketLifecycleState
from alpha.reporting.realized_pnl import build_realized_pnl_snapshot


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


def _load_bracket_records(logs_dir: Path) -> List[Dict[str, Any]]:
    path = logs_dir / "alpha_brackets.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    records = data if isinstance(data, list) else data.get("records", [])
    return [r for r in records if isinstance(r, dict)]


def build_replay_report(
    *,
    logs_dir: str | Path = "logs",
    hours: float = 168.0,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Summarize bracket outcomes and realized P&L over a rolling window."""
    window_h = max(1.0, float(hours))
    end = now or datetime.now(tz=timezone.utc)
    since = end - timedelta(hours=window_h)
    logs = Path(logs_dir)

    realized = build_realized_pnl_snapshot(logs_dir=logs, hours=window_h, now=end)

    tp_brackets = sl_brackets = pending = active = 0
    scratch_sl = 0
    for rec in _load_bracket_records(logs):
        st = str(rec.get("state") or "")
        updated = _parse_ts(str(rec.get("updated_at") or rec.get("created_at") or ""))
        if updated is None or updated < since:
            continue
        if st == BracketLifecycleState.TP_FILLED.value:
            tp_brackets += 1
        elif st == BracketLifecycleState.SL_FILLED.value:
            sl_brackets += 1
        elif st == BracketLifecycleState.PENDING_BUY.value:
            pending += 1
        elif st == BracketLifecycleState.BRACKET_ACTIVE.value:
            active += 1

    for exit_row in realized.get("recent_exits") or []:
        if exit_row.get("exit_type") == "sl" and abs(float(exit_row.get("profit_xrp_equiv") or 0)) < 0.01:
            scratch_sl += 1

    tp_exits = int(realized.get("tp_exits") or 0)
    sl_exits = int(realized.get("sl_exits") or 0)
    total_exits = tp_exits + sl_exits
    tp_sl_ratio = round(tp_exits / total_exits, 3) if total_exits > 0 else None
    realized_pnl = float(realized.get("realized_profit_xrp_equiv") or 0.0)

    churn_score = round(sl_exits / max(1, total_exits), 3) if total_exits else 0.0
    verdict = "healthy"
    if total_exits >= 4 and (tp_sl_ratio is None or tp_sl_ratio < 0.25):
        verdict = "sl_heavy"
    elif realized_pnl < -2.0 and total_exits >= 3:
        verdict = "bleeding"
    elif total_exits >= 4 and scratch_sl >= sl_exits * 0.5:
        verdict = "churn"

    return {
        "window_hours": window_h,
        "window_start_utc": since.isoformat(),
        "window_end_utc": end.isoformat(),
        "available": bool(realized.get("available")),
        "tp_exits": tp_exits,
        "sl_exits": sl_exits,
        "tp_sl_ratio": tp_sl_ratio,
        "scratch_sl_exits": scratch_sl,
        "realized_profit_xrp_equiv": round(realized_pnl, 4),
        "session_pnl_xrp_mtm": realized.get("session_pnl_xrp_mtm"),
        "buy_xrp_acquired": round(float(realized.get("buy_xrp_acquired") or 0), 4),
        "sell_xrp_disposed": round(float(realized.get("sell_xrp_disposed") or 0), 4),
        "brackets_tp_filled": tp_brackets,
        "brackets_sl_filled": sl_brackets,
        "brackets_pending": pending,
        "brackets_active": active,
        "churn_score": churn_score,
        "verdict": verdict,
        "recent_exits": realized.get("recent_exits") or [],
        "note": (
            "Replay uses tax CSV SELL rows (realized) + bracket store state counts in window. "
            "Use verdict sl_heavy/bleeding/churn to justify defensive circuit."
        ),
    }


def format_replay_report_text(report: Dict[str, Any]) -> str:
    lines = [
        f"Alpha replay ({report.get('window_hours')}h)",
        f"  Verdict: {report.get('verdict')}",
        f"  TP exits: {report.get('tp_exits')} | SL exits: {report.get('sl_exits')} | "
        f"TP:SL ratio: {report.get('tp_sl_ratio')}",
        f"  Scratch SL (≈0 profit): {report.get('scratch_sl_exits')}",
        f"  Realized P&L (XRP-equiv): {report.get('realized_profit_xrp_equiv'):+}",
        f"  Buys +{report.get('buy_xrp_acquired')} XRP | Sells -{report.get('sell_xrp_disposed')} XRP",
        f"  Brackets touched: tp={report.get('brackets_tp_filled')} sl={report.get('brackets_sl_filled')} "
        f"active={report.get('brackets_active')} pending={report.get('brackets_pending')}",
    ]
    mtm = report.get("session_pnl_xrp_mtm")
    if mtm is not None:
        lines.append(f"  Session MTM (contrast only): {float(mtm):+} XRP")
    lines.append("")
    lines.append(str(report.get("note") or ""))
    return "\n".join(lines)
