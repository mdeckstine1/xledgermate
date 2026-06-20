"""M-Purpose HUD fields — skim-funded inventory growth scoreboard (HUD-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

PURPOSE_HUD_VERSION = "1.0.0"


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate_purpose_gate(
    *,
    session_spread_capture_xrp: Optional[float],
    delta_xrp: Optional[float],
    buy_capture_xrp: float,
    sell_capture_xrp: float,
    at_edge: bool,
    fills_session: int,
) -> Dict[str, Any]:
    """North-star pass/fail — headline skim alone is insufficient."""
    skim = float(session_spread_capture_xrp or 0.0)
    buy_cap = float(buy_capture_xrp or 0.0)
    sell_cap = float(sell_capture_xrp or 0.0)

    checks = {
        "skim_positive": skim > 0,
        "buy_capture_positive": buy_cap > 0,
        "at_edge": bool(at_edge),
        "sell_capture_non_negative": sell_cap >= 0,
        "delta_xrp_positive": delta_xrp is not None and float(delta_xrp) > 0,
    }

    if fills_session <= 0:
        status = "warming"
        gate_pass = False
    elif all(checks.values()):
        status = "pass"
        gate_pass = True
    else:
        status = "fail"
        gate_pass = False

    failed = [k for k, ok in checks.items() if not ok]
    if status == "warming":
        summary = "warming — no session fills yet"
    elif gate_pass:
        summary = "purpose pass — skim-funded inventory growth at edge"
    else:
        summary = "purpose fail — " + ", ".join(failed[:3])

    return {
        "purpose_gate_status": status,
        "purpose_gate_pass": gate_pass,
        "purpose_gate_checks": checks,
        "purpose_gate_summary": summary,
    }


def build_purpose_hud_fields(
    runtime: Mapping[str, Any],
    *,
    logs_dir: Path | None = None,
) -> Dict[str, Any]:
    """
    Session purpose scoreboard for HUD /state (read-only; no engine change).

    Uses M6 fill stream + runtime baselines — same source as acquisition report.
    """
    from core.wealth_metrics import compute_wealth_metrics
    from experimental.ws_feed.acquisition_metrics import build_acquisition_metrics
    from experimental.ws_feed.fill_quote_age_log import tail_fill_quote_age_records

    logs = logs_dir or Path("logs")
    rt = dict(runtime)
    rt.update({k: v for k, v in compute_wealth_metrics(rt).items() if v is not None})

    boot_raw = str(rt.get("session_boot_utc") or "")
    boot_dt = _parse_ts(boot_raw) if boot_raw else None
    ws_ver = str(rt.get("ws_as_version") or "")

    fills = tail_fill_quote_age_records(
        limit=5000,
        path=logs / "fill_quote_age.jsonl",
        since=boot_dt,
        ws_as_version=ws_ver or None,
    )

    metrics = build_acquisition_metrics(runtime=rt, session_fills=fills)
    ig = metrics.get("inventory_growth_at_edge") or {}
    delta_xrp = ig.get("delta_xrp")
    buy_capture_xrp = float(ig.get("buy_capture_xrp") or 0.0)
    at_edge = bool(ig.get("at_edge"))

    sell_states = metrics.get("sell_capture_by_state") or {}
    sell_capture_xrp = sum(float(v.get("cap") or 0) for v in sell_states.values())

    skim_xrp = rt.get("session_spread_capture_xrp")
    try:
        skim_f = float(skim_xrp) if skim_xrp is not None else 0.0
    except (TypeError, ValueError):
        skim_f = 0.0

    fills_session = int(rt.get("fills_session") or len(fills) or 0)
    gate = evaluate_purpose_gate(
        session_spread_capture_xrp=skim_f,
        delta_xrp=float(delta_xrp) if delta_xrp is not None else None,
        buy_capture_xrp=buy_capture_xrp,
        sell_capture_xrp=sell_capture_xrp,
        at_edge=at_edge,
        fills_session=fills_session,
    )

    return {
        "purpose_hud_version": PURPOSE_HUD_VERSION,
        "purpose_at_edge": at_edge,
        "purpose_delta_xrp": delta_xrp,
        "purpose_buy_capture_xrp": round(buy_capture_xrp, 6),
        "purpose_sell_capture_xrp": round(sell_capture_xrp, 6),
        "purpose_session_skim_xrp": round(skim_f, 6),
        "purpose_fills_scoped": len(fills),
        **gate,
    }


__all__ = [
    "PURPOSE_HUD_VERSION",
    "build_purpose_hud_fields",
    "evaluate_purpose_gate",
]
