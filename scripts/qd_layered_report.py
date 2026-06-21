#!/usr/bin/env python3
"""
Layered quote decision operator report (L1–L5).

Primary HUD report for acquisition-centered monitoring: posture, intent,
edge, bleed, L5 permissions, and recent cycle mix.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from scripts.qd_final_report import build_qd_final_report
from scripts.qd_report_common import (
    fmt_bool,
    fmt_on_off,
    intent_mix_compact,
    operating_mode,
    side_permission_block,
)
from strategy.quote_decision_layers.edge import (
    SOLO_EDGE_ABSOLUTE_FLOOR_PCT,
    SOLO_EDGE_MULT,
)


def _load_runtime(logs_dir: Path) -> Dict[str, Any]:
    path = logs_dir / "runtime_state.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def build_qd_layered_report(
    *,
    logs_dir: Optional[Path] = None,
    limit: int = 60,
) -> Dict[str, Any]:
    logs = logs_dir or Path("logs")
    runtime = _load_runtime(logs)
    hud: Dict[str, Any] = {}
    if runtime:
        try:
            from experimental.ws_feed.qd_hud import build_qd_hud_fields

            hud = build_qd_hud_fields(runtime)
        except Exception:
            hud = {}

    final = build_qd_final_report(logs_dir=logs, limit=limit)
    return {
        "generated_utc": datetime.now(tz=timezone.utc).isoformat(),
        "runtime": runtime,
        "hud": hud,
        "final_tail": final,
        "solo_edge_mult": SOLO_EDGE_MULT,
        "solo_edge_floor_pct": SOLO_EDGE_ABSOLUTE_FLOOR_PCT,
    }


def format_qd_layered_report(report: Mapping[str, Any]) -> str:
    rt = report.get("runtime") or {}
    hud = report.get("hud") or {}
    snap = hud.get("qd_snapshot") or {}
    summary = hud.get("qd_decision_summary") or {}
    bid = snap.get("bid") or {}
    ask = snap.get("ask") or {}
    final = report.get("final_tail") or {}
    tail_summary = final.get("summary") or {}

    intent = str(snap.get("intent") or rt.get("qd_intent") or "")
    book_mode = str(snap.get("book_mode") or rt.get("qd_book_mode") or "")
    solo_mode = bool(snap.get("solo_mode", rt.get("solo_mode")))
    bid_allowed = rt.get("qd_bid_allowed", bid.get("allowed"))
    ask_allowed = rt.get("qd_ask_allowed", ask.get("allowed"))
    would_quote = rt.get("qd_would_quote", snap.get("would_quote"))

    mode_label, mode_hint = operating_mode(
        intent=intent,
        book_mode=book_mode,
        solo_mode=solo_mode,
        bid_allowed=bid_allowed,
        ask_allowed=ask_allowed,
        protection_active=bool(summary.get("protection_active")),
        would_quote=would_quote,
    )

    lines: List[str] = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║  LAYERED QUOTE DECISION — operator view (L1→L5)              ║",
        "╚══════════════════════════════════════════════════════════════╝",
        f"generated: {report.get('generated_utc')}",
        f"ws_as_version: {rt.get('ws_as_version') or '—'} | cycle: {rt.get('cycle_count') or '—'}",
        f"updated: {rt.get('updated_utc') or '—'}",
        "",
        "▶ OPERATING MODE",
        f"  {mode_label}",
        f"  {mode_hint}",
        f"  permissions: {hud.get('qd_permissions_summary') or summary.get('quoting_short') or '—'}",
        f"  status: {summary.get('status_hint') or '—'}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "L1 · POSTURE",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  book_mode: {book_mode or '—'} | solo_mode: {fmt_bool(solo_mode)}",
        f"  peer_lane: {snap.get('peer_lane_token') or rt.get('qd_peer_lane_token') or '—'}"
        f" (n={snap.get('peer_lane_count', rt.get('peer_lane_count', '—'))})",
        f"  drift: {snap.get('drift_label') or snap.get('drift_band') or rt.get('qd_drift_band') or '—'}",
        f"  reason: {snap.get('posture_reason') or rt.get('posture_reason') or '—'}",
        f"  {snap.get('posture_headline') or summary.get('posture_detail') or ''}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "L2 · INTENT",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  intent: {intent or '—'}",
        f"  label: {snap.get('intent_label') or '—'}",
        f"  why: {snap.get('intent_reason') or rt.get('qd_intent_reason') or '—'}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "L3 · EDGE (solo hard gate)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  solo gate: capture ≥ min_edge×{report.get('solo_edge_mult')} OR ≥ {report.get('solo_edge_floor_pct')}%",
        f"  crowded/sparse: size scales only — no hard gate",
    ]
    lines.extend(side_permission_block(
        "bid",
        allowed=bid_allowed,
        pause_cause=str(rt.get("qd_bid_pause_cause") or bid.get("block_cause") or ""),
        block_reason=str(rt.get("qd_bid_block_reason") or bid.get("block_reason") or ""),
        edge_viable=bid.get("edge_viable", rt.get("qd_bid_edge_viable")),
        edge_bps=bid.get("implied_bps") or rt.get("qd_bid_implied_bps"),
        bleeding=bid.get("bleeding", rt.get("qd_bid_bleeding")),
        size_mult=bid.get("size_mult"),
    ))
    lines.append("")
    lines.extend(side_permission_block(
        "ask",
        allowed=ask_allowed,
        pause_cause=str(rt.get("qd_ask_pause_cause") or ask.get("block_cause") or ""),
        block_reason=str(rt.get("qd_ask_block_reason") or ask.get("block_reason") or ""),
        edge_viable=ask.get("edge_viable", rt.get("qd_ask_edge_viable")),
        edge_bps=ask.get("implied_bps") or rt.get("qd_ask_implied_bps"),
        bleeding=ask.get("bleeding", rt.get("qd_ask_bleeding")),
        size_mult=ask.get("size_mult"),
    ))
    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "L4 · BLEED (side-local)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  bid_bleeding: {fmt_bool(bid.get('bleeding', rt.get('qd_bid_bleeding')))}"
        f" | ask_bleeding: {fmt_bool(ask.get('bleeding', rt.get('qd_ask_bleeding')))}",
        f"  protection_active: {fmt_bool(summary.get('protection_active'))}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "L5 · FINAL PERMISSIONS",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  qd_bid_allowed: {fmt_on_off(bid_allowed)} | qd_ask_allowed: {fmt_on_off(ask_allowed)}",
        f"  inventory_cb: {snap.get('inventory_cb_label') or snap.get('inventory_cb_mode') or rt.get('qd_inventory_cb_mode') or '—'}",
    ])
    inv_note = snap.get("inventory_cb_note") or rt.get("qd_inventory_cb_note") or ""
    if inv_note:
        lines.append(f"  note: {inv_note}")
    if snap.get("inventory_cb_mode") == "skipped_solo" or rt.get("qd_inventory_cb_mode") == "skipped_solo":
        lines.append("  inventory_cb_skipped_solo: yes — solo defers to L2 intent")
    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "DOWNSTREAM · quote path",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  would_quote: {fmt_on_off(would_quote)}",
        f"  zero_quote_reason: {rt.get('zero_quote_reason') or rt.get('edge_resolution_summary') or '—'}",
        f"  open_offers: {rt.get('open_offers_count') or len(rt.get('open_offers') or [])}",
    ])
    res_delta = rt.get("reservation_to_bbo_delta_bps")
    if res_delta is not None:
        lines.append(f"  reservation→BBO: {res_delta} bps | inside_l1: {fmt_bool(rt.get('inside_l1'))}")
    lines.append(f"  trace: {snap.get('layer_trace_raw') or rt.get('qd_layer_trace') or '—'}")
    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "RECENT CYCLES (QD_FINAL tail)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])
    mix = intent_mix_compact(tail_summary)
    if mix:
        lines.append(f"  mix: {mix}")
    if tail_summary:
        acc = tail_summary.get("solo_accumulate_total", 0)
        total = tail_summary.get("total", 0)
        if acc:
            pct = 100.0 * tail_summary.get("solo_accumulate_bid_on", 0) / acc
            lines.append(
                f"  accumulate cycles: {acc} | bid_on {tail_summary.get('solo_accumulate_bid_on', 0)} ({pct:.0f}%)"
            )
        lines.append(
            f"  bid_allowed: {tail_summary.get('bid_allowed_true', 0)}/{total}"
            f" | ask_allowed: {tail_summary.get('ask_allowed_true', 0)}/{total}"
        )
    records = final.get("records") or []
    for rec in records[-6:]:
        ts = rec.get("_ts", "?")
        lines.append(
            f"  [{ts}] {rec.get('intent', '?')} | bid={rec.get('bid_allowed')} ask={rec.get('ask_allowed')}"
            f" | edge={rec.get('bid_edge_pct')}%"
        )
    if not records:
        lines.append("  (no QD_FINAL rows yet)")
    lines.extend([
        "",
        "See also: Reports → L5 permission monitor (qd_final_diagnostics)",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Layered QD operator report (L1–L5)")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()
    report = build_qd_layered_report(logs_dir=Path(args.logs_dir), limit=args.limit)
    print(format_qd_layered_report(report))


if __name__ == "__main__":
    main()
