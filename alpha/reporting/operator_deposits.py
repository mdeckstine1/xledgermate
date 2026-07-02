"""Operator inbound deposits — separate manual funding from bot bag growth."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from risk.drawdown import portfolio_value_xrp

_DEFAULT_PATH = Path("logs/operator_deposits.json")


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _load(path: Path = _DEFAULT_PATH) -> Dict[str, Any]:
    if not path.is_file():
        return {"deposits": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"deposits": []}
        deposits = data.get("deposits")
        if not isinstance(deposits, list):
            data["deposits"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"deposits": []}


def _save(payload: Dict[str, Any], path: Path = _DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def list_deposits(logs_dir: str | Path = "logs") -> List[Dict[str, Any]]:
    data = _load(Path(logs_dir) / "operator_deposits.json")
    rows = [r for r in data.get("deposits", []) if isinstance(r, dict)]
    return sorted(rows, key=lambda r: str(r.get("recorded_utc") or ""), reverse=True)


def total_deposits_xrp_equiv(logs_dir: str | Path = "logs") -> float:
    return sum(float(d.get("xrp_equiv") or 0.0) for d in list_deposits(logs_dir))


def total_deposited_xrp(logs_dir: str | Path = "logs") -> float:
    return sum(float(d.get("xrp") or 0.0) for d in list_deposits(logs_dir))


def total_deposited_rlusd(logs_dir: str | Path = "logs") -> float:
    return sum(float(d.get("rlusd") or 0.0) for d in list_deposits(logs_dir))


def deposits_snapshot(logs_dir: str | Path = "logs") -> Dict[str, Any]:
    rows = list_deposits(logs_dir)
    total_xrp = sum(float(d.get("xrp") or 0.0) for d in rows)
    total_rlusd = sum(float(d.get("rlusd") or 0.0) for d in rows)
    total_equiv = sum(float(d.get("xrp_equiv") or 0.0) for d in rows)
    return {
        "count": len(rows),
        "total_xrp": round(total_xrp, 4),
        "total_rlusd": round(total_rlusd, 4),
        "total_xrp_equiv": round(total_equiv, 4),
        "deposits": rows,
    }


def record_deposit(
    *,
    xrp: float = 0.0,
    rlusd: float = 0.0,
    mid_rlusd_per_xrp: Optional[float] = None,
    note: str = "",
    logs_dir: str | Path = "logs",
    reset_session_baseline: bool = False,
    current_xrp: Optional[float] = None,
    current_rlusd: Optional[float] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Log an operator inbound transfer. ``xrp_equiv`` is frozen at record time using ``mid``.
    Optionally reset ``alpha_session.json`` baseline so Session P&L starts fresh.
    """
    errors: List[str] = []
    xrp_amt = max(0.0, float(xrp))
    rlusd_amt = max(0.0, float(rlusd))
    if xrp_amt <= 0 and rlusd_amt <= 0:
        return {}, ["At least one of xrp or rlusd must be > 0"]

    mid = float(mid_rlusd_per_xrp or 0.0)
    if mid <= 0:
        return {}, ["Valid mid_rlusd_per_xrp required to value RLUSD portion"]

    xrp_equiv = portfolio_value_xrp(xrp_amt, rlusd_amt, mid)
    if xrp_equiv <= 0:
        return {}, ["Deposit xrp_equiv must be > 0"]

    path = Path(logs_dir) / "operator_deposits.json"
    data = _load(path)
    entry = {
        "id": uuid.uuid4().hex[:12],
        "recorded_utc": _utc_now(),
        "xrp": round(xrp_amt, 6),
        "rlusd": round(rlusd_amt, 6),
        "xrp_equiv": round(xrp_equiv, 4),
        "mid_rlusd_per_xrp": round(mid, 6),
        "note": (note or "").strip()[:500],
    }
    data.setdefault("deposits", []).append(entry)
    _save(data, path)

    baseline_reset = False
    if reset_session_baseline:
        from alpha.risk.session import SessionPnlTracker

        session_path = Path(logs_dir) / "alpha_session.json"
        tracker = SessionPnlTracker(session_path)
        last_portfolio = 0.0
        if session_path.is_file():
            try:
                sess = json.loads(session_path.read_text(encoding="utf-8"))
                last_portfolio = float(sess.get("last_portfolio_xrp") or 0.0)
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                last_portfolio = 0.0
        if last_portfolio > 0:
            tracker.reset_baseline(
                last_portfolio,
                xrp=current_xrp if current_xrp is not None else None,
                rlusd=current_rlusd if current_rlusd is not None else None,
            )
            baseline_reset = True
        else:
            errors.append(
                "Session baseline not reset — engine has not written last_portfolio_xrp yet"
            )

    entry["session_baseline_reset"] = baseline_reset
    return entry, errors


def delete_deposit(deposit_id: str, *, logs_dir: str | Path = "logs") -> bool:
    path = Path(logs_dir) / "operator_deposits.json"
    data = _load(path)
    before = len(data.get("deposits", []))
    data["deposits"] = [
        d for d in data.get("deposits", []) if isinstance(d, dict) and d.get("id") != deposit_id
    ]
    if len(data["deposits"]) == before:
        return False
    _save(data, path)
    return True
