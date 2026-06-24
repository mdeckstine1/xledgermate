"""Realized bracket P&L from tax CSV — for SKYNET / operator dashboards."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


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


def _classify_exit(notes: str) -> str:
    n = (notes or "").lower()
    if "take-profit" in n or "take_profit" in n:
        return "tp"
    if "stop-loss" in n or "stop_loss" in n:
        return "sl"
    return "sell_other"


def _load_tax_rows(logs_dir: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not logs_dir.is_dir():
        return rows
    paths = sorted(logs_dir.glob("trades_*.csv"), key=lambda p: p.stat().st_mtime)
    for path in paths:
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows.extend(list(csv.DictReader(handle)))
        except (OSError, csv.Error):
            continue
    return rows


def build_realized_pnl_snapshot(
    *,
    logs_dir: str | Path = "logs",
    hours: float = 24.0,
    now: Optional[datetime] = None,
    session_pnl_xrp: Optional[float] = None,
    max_recent_exits: int = 8,
) -> Dict[str, Any]:
    """
    Summarize taxable bracket exits from ``logs/trades_*.csv`` over a rolling window.

    ``realized_profit_xrp_equiv`` sums ``profit_xrp_equiv`` on SELL rows only (TP/SL vs entry).
    ``session_pnl_xrp`` (MTM) is optional — pass from HUD risk block for contrast.
    """
    window_h = max(0.25, float(hours))
    end = now or datetime.now(tz=timezone.utc)
    since = end - timedelta(hours=window_h)

    out: Dict[str, Any] = {
        "window_hours": round(window_h, 2),
        "window_start_utc": since.isoformat(),
        "window_end_utc": end.isoformat(),
        "available": False,
        "taxable_buys": 0,
        "taxable_sells": 0,
        "tp_exits": 0,
        "sl_exits": 0,
        "sell_other": 0,
        "realized_profit_xrp_equiv": 0.0,
        "buy_xrp_acquired": 0.0,
        "sell_xrp_disposed": 0.0,
        "negative_exit_count": 0,
        "session_pnl_xrp_mtm": session_pnl_xrp,
        "mtm_vs_realized_delta": None,
        "recent_exits": [],
        "note": (
            "realized_profit_xrp_equiv = sum profit on SELL rows (bracket TP/SL vs entry). "
            "session_pnl_xrp_mtm = portfolio mark-to-market — can diverge from trading edge."
        ),
    }

    rows = _load_tax_rows(Path(logs_dir))
    if not rows:
        out["note"] = "No trades_*.csv found in logs — realized P&L unavailable."
        return out

    recent_exits: List[Dict[str, Any]] = []

    for row in rows:
        if str(row.get("taxable") or "").upper() != "Y":
            continue
        ts = _parse_ts(row.get("timestamp_utc") or "")
        if ts is None or ts < since:
            continue

        side = (row.get("side") or row.get("event_type") or "").strip().upper()
        try:
            xrp = float(row.get("xrp_amount") or 0)
            profit = float(row.get("profit_xrp_equiv") or 0)
            price = float(row.get("price_rlusd_per_xrp") or 0)
        except (TypeError, ValueError):
            continue

        out["available"] = True

        if side == "BUY":
            out["taxable_buys"] += 1
            out["buy_xrp_acquired"] += xrp
            continue

        if side != "SELL":
            continue

        out["taxable_sells"] += 1
        out["sell_xrp_disposed"] += xrp
        out["realized_profit_xrp_equiv"] += profit
        if profit < 0:
            out["negative_exit_count"] += 1

        notes = str(row.get("notes") or "")
        exit_kind = _classify_exit(notes)
        if exit_kind == "tp":
            out["tp_exits"] += 1
        elif exit_kind == "sl":
            out["sl_exits"] += 1
        else:
            out["sell_other"] += 1

        recent_exits.append(
            {
                "ts": ts.isoformat(),
                "kind": exit_kind,
                "xrp": round(xrp, 6),
                "price": round(price, 6),
                "profit_xrp_equiv": round(profit, 6),
                "notes": notes[:80],
            }
        )

    out["realized_profit_xrp_equiv"] = round(float(out["realized_profit_xrp_equiv"]), 6)
    out["buy_xrp_acquired"] = round(float(out["buy_xrp_acquired"]), 6)
    out["sell_xrp_disposed"] = round(float(out["sell_xrp_disposed"]), 6)

    if session_pnl_xrp is not None:
        try:
            mtm = float(session_pnl_xrp)
            out["mtm_vs_realized_delta"] = round(mtm - out["realized_profit_xrp_equiv"], 6)
        except (TypeError, ValueError):
            pass

    recent_exits.sort(key=lambda r: r["ts"])
    out["recent_exits"] = recent_exits[-max(0, int(max_recent_exits)) :]

    if out["available"] and out["taxable_sells"] == 0 and out["taxable_buys"] > 0:
        out["interpretation"] = "Buys only in window — no closed TP/SL yet; session MTM is not trading P&L."
    elif out["sl_exits"] > out["tp_exits"] and out["realized_profit_xrp_equiv"] < 0:
        out["interpretation"] = (
            "SL-heavy window with negative realized P&L — trust phase should avoid offset↓ / weakness↓."
        )
    elif out["tp_exits"] > 0 and out["realized_profit_xrp_equiv"] >= 0:
        out["interpretation"] = "Positive realized exits — scale phase may be appropriate if ratio is climbing."
    else:
        out["interpretation"] = "Use realized_profit_xrp_equiv and tp_exits/sl_exits for bleed, not session MTM alone."

    return out


def format_realized_pnl_context_block(snapshot: Dict[str, Any]) -> str:
    """Human-readable block for Grok context."""
    lines = [
        "=== Realized bracket P&L (tax CSV, rolling window) ===",
        f"window_hours={snapshot.get('window_hours')} "
        f"start={snapshot.get('window_start_utc', '')[:19]}",
    ]
    if not snapshot.get("available"):
        lines.append(snapshot.get("note", "unavailable"))
        return "\n".join(lines)

    lines.extend(
        [
            f"taxable_buys={snapshot.get('taxable_buys')} "
            f"buy_xrp_acquired={snapshot.get('buy_xrp_acquired')}",
            f"taxable_sells={snapshot.get('taxable_sells')} "
            f"sell_xrp_disposed={snapshot.get('sell_xrp_disposed')}",
            f"tp_exits={snapshot.get('tp_exits')} sl_exits={snapshot.get('sl_exits')} "
            f"sell_other={snapshot.get('sell_other')}",
            f"realized_profit_xrp_equiv={snapshot.get('realized_profit_xrp_equiv')} "
            f"(sum profit on SELL rows vs bracket entry)",
            f"negative_exit_count={snapshot.get('negative_exit_count')}",
        ]
    )
    mtm = snapshot.get("session_pnl_xrp_mtm")
    if mtm is not None:
        lines.append(f"session_pnl_xrp_mtm={mtm} (portfolio MTM — NOT same as realized_profit_xrp_equiv)")
        delta = snapshot.get("mtm_vs_realized_delta")
        if delta is not None:
            lines.append(f"mtm_minus_realized={delta}")
    if snapshot.get("interpretation"):
        lines.append(f"interpretation: {snapshot['interpretation']}")
    recent: Sequence[Dict[str, Any]] = snapshot.get("recent_exits") or []
    if recent:
        lines.append("recent_exits:")
        for ex in recent:
            lines.append(
                f"  {ex.get('ts', '')[:19]} {ex.get('kind')} "
                f"xrp={ex.get('xrp')} profit={ex.get('profit_xrp_equiv'):+} "
                f"{ex.get('notes', '')[:50]}"
            )
    lines.append(snapshot.get("note", ""))
    return "\n".join(lines)
