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
        "g4_size_mult": float(ed.get("g4_size_mult") or 1.0),
        "g4_grade": str(ed.get("g4_grade") or ""),
        "g4_active": bool(ed.get("g4_active")),
        "g4_peer_lane_count": ed.get("g4_peer_lane_count"),
        "g4_peer_pressure": ed.get("g4_peer_pressure"),
        "peer_lane_count": ed.get("g4_peer_lane_count"),
        "peer_pressure_score": ed.get("g4_peer_pressure"),
        "toxic_fill_ratio": extras.get("toxic_fill_ratio"),
        "toxic_fill_ratio_30s": extras.get("toxic_fill_ratio_30s"),
        "mean_markout_30s_pct": extras.get("mean_markout_30s_pct"),
        "fills_session": extras.get("fills_session"),
        "session_pnl_balance_xrp": extras.get("session_pnl_balance_xrp"),
        "drawdown_pct": extras.get("drawdown_pct"),
        "ws_as_version": extras.get("ws_as_version"),
        "g7_solo_acquisition": bool(ed.get("g7_solo_acquisition")),
        "g7_bid_role": str(ed.get("g7_bid_role") or ""),
        "g7_ask_role": str(ed.get("g7_ask_role") or ""),
        "g7_ask_sell_defense": bool(ed.get("g7_ask_sell_defense")),
        "buy_edge_gate_active": bool(ed.get("buy_edge_gate_active")),
        "buy_edge_gate_blocked": bool(ed.get("buy_edge_gate_blocked")),
        "buy_edge_implied_bps": ed.get("buy_edge_implied_bps"),
        "buy_edge_gate_reason": str(ed.get("buy_edge_gate_reason") or ""),
        "acquire_ask_brake_active": bool(ed.get("acquire_ask_brake_active")),
        "acquire_ask_brake_blocked": bool(ed.get("acquire_ask_brake_blocked")),
        "acquire_ask_brake_reason": str(ed.get("acquire_ask_brake_reason") or ""),
        "bid_size_xrp": round(bid_sz, 4) if bid_sz else None,
        "ask_size_xrp": round(ask_sz, 4) if ask_sz else None,
        "peer_lane_empty": extras.get("peer_lane_empty"),
        "worst_vs_touch_bps": extras.get("worst_vs_touch_bps"),
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
        "book_bid_offers": cf.get("book_bid_offers"),
        "book_ask_offers": cf.get("book_ask_offers"),
        "book_side_skew": cf.get("book_side_skew"),
        "book_side_skew_label": cf.get("book_side_skew_label"),
    }


def build_grok_suggestion_intel_record(
    *,
    address: str,
    model: str,
    briefing: Dict[str, Any],
    result_text: str,
    context_snapshot: Optional[Dict[str, Any]] = None,
    outcome_status: str = "pending",
) -> Dict[str, Any]:
    """F4 — log Grok analyze_competitor call for later outcome correlation."""
    ctx = context_snapshot or {}
    structured = briefing.get("structured_briefing") if isinstance(briefing.get("structured_briefing"), dict) else {}
    excerpt = (result_text or "").strip()[:500]
    return {
        "kind": "grok_suggestion",
        "address": address,
        "model": model,
        "in_peer_lane": bool(briefing.get("in_peer_lane")),
        "scrape_source": briefing.get("source"),
        "touch_xrp": briefing.get("touch_xrp"),
        "structured_briefing": structured or None,
        "result_chars": len(result_text or ""),
        "result_excerpt": excerpt,
        "outcome_status": outcome_status,
        "competitor_pressure": ctx.get("competitor_pressure"),
        "book_regime_pressure": ctx.get("book_regime_pressure"),
        "book_side_skew_label": ctx.get("book_side_skew_label"),
        "inventory_label": ctx.get("inventory_label"),
        "our_lane_xrp": ctx.get("our_lane_xrp") or briefing.get("our_lane_xrp"),
        "peer_lane_count": ctx.get("peer_lane_count"),
    }


def build_advisory_signal_intel_record(fields: Dict[str, Any]) -> Dict[str, Any]:
    """F2 HUD advisory stub — rate-limited JSONL row."""
    return {
        "kind": "advisory_signal",
        "source": fields.get("ai_advisory_source"),
        "vol_mult": fields.get("ai_advisory_vol_mult"),
        "size_mult": fields.get("ai_advisory_size_mult"),
        "skim_harder": fields.get("ai_advisory_skim_harder"),
        "confidence": fields.get("ai_advisory_confidence"),
        "rationale": fields.get("ai_advisory_rationale"),
        "competitor_pressure": fields.get("competitor_pressure"),
        "book_side_skew_label": fields.get("book_side_skew_label"),
    }
