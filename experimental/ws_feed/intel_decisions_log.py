"""G3 — structured intel / performance JSONL (`logs/intel_decisions.jsonl`)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

INTEL_DECISIONS_PATH = Path("logs/intel_decisions.jsonl")


def append_intel_record(record: Dict[str, Any], path: Path = INTEL_DECISIONS_PATH) -> None:
    """Append one JSON line (cycle or peer_scrape)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(record)
    row.setdefault("ts_utc", datetime.now(tz=timezone.utc).isoformat())
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def tail_intel_records(*, limit: int = 500, path: Path = INTEL_DECISIONS_PATH) -> List[Dict[str, Any]]:
    if not path.exists() or limit <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _ratio_pct(xrp: float, rlusd: float, mid: float) -> Optional[float]:
    if mid <= 0:
        return None
    port = xrp + rlusd / mid
    if port <= 0:
        return None
    return round(100.0 * xrp / port, 2)


def build_cycle_intel_record(
    *,
    cycle: int,
    mid: Optional[float],
    balance_xrp: float,
    balance_rlusd: float,
    portfolio_xrp: float,
    engine_dec: Dict[str, Any],
    runtime_extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-cycle intel row from ws-engine (pure path + G2 + inventory)."""
    ed = engine_dec or {}
    extras = runtime_extras or {}
    target = float(extras.get("inventory_target_xrp_ratio") or 0.55)
    xrp_pct = _ratio_pct(balance_xrp, balance_rlusd, float(mid or 0))
    deviation_pct = None
    if xrp_pct is not None:
        deviation_pct = round(xrp_pct - target * 100.0, 2)

    bid_sz = float(ed.get("bid_size_xrp") or 0)
    ask_sz = float(ed.get("ask_size_xrp") or 0)
    our_lane = max(bid_sz, ask_sz) if (bid_sz or ask_sz) else None

    return {
        "kind": "cycle",
        "cycle": int(cycle),
        "mid_rlusd_per_xrp": mid,
        "portfolio_xrp_equiv": round(portfolio_xrp, 4) if portfolio_xrp else None,
        "balance_xrp": round(balance_xrp, 4),
        "balance_rlusd": round(balance_rlusd, 4),
        "xrp_ratio_pct": xrp_pct,
        "inventory_deviation_pct": deviation_pct,
        "inventory_label": str(ed.get("inventory_label") or ""),
        "pause_bids": bool(ed.get("pause_bids")),
        "pause_asks": bool(ed.get("pause_asks")),
        "would_quote": bool(ed.get("would_quote")),
        "our_lane_xrp": our_lane,
        "book_spread_pct": ed.get("book_spread_pct"),
        "g2_grade": str(ed.get("g2_grade") or ""),
        "g2_active": bool(ed.get("g2_active")),
        "g2_size_mult": float(ed.get("g2_size_mult") or 1.0),
        "g2_spread_mult": float(ed.get("g2_spread_mult") or 1.0),
        "toxic_fill_ratio": extras.get("toxic_fill_ratio"),
        "toxic_fill_ratio_30s": extras.get("toxic_fill_ratio_30s"),
        "mean_markout_30s_pct": extras.get("mean_markout_30s_pct"),
        "fills_session": extras.get("fills_session"),
        "session_pnl_balance_xrp": extras.get("session_pnl_balance_xrp"),
        "drawdown_pct": extras.get("drawdown_pct"),
        "ws_as_version": extras.get("ws_as_version"),
    }


def build_peer_scrape_intel_record(comp_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Peer-lane snapshot when HUD competitor scrape runs (~15s)."""
    cf = comp_fields or {}
    return {
        "kind": "peer_scrape",
        "our_lane_xrp": cf.get("our_lane_xrp"),
        "peer_lane_count": cf.get("peer_lane_count"),
        "peer_lane_low_xrp": cf.get("peer_lane_low_xrp"),
        "peer_lane_high_xrp": cf.get("peer_lane_high_xrp"),
        "peer_pressure_score": cf.get("peer_pressure_score"),
        "competitor_pressure": cf.get("competitor_pressure"),
        "competitor_observed_spread_pct": cf.get("competitor_observed_spread_pct"),
        "peer_lane_empty": cf.get("peer_lane_empty"),
        "peer_lane_widened": cf.get("peer_lane_widened"),
        "peer_fled_touch_count": cf.get("peer_fled_touch_count"),
        "num_active_mms": cf.get("num_active_mms"),
    }
