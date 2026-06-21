#!/usr/bin/env python3
"""
Layered quote decision operator report (L1–L5).

Acquisition-centered view: posture, intent, edge gate, bleed, L5 permissions,
inventory CB, and recent cycle mix from QD_FINAL log tail.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from scripts.qd_final_report import build_qd_final_report
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


def _fmt_bool(value: Any) -> str:
    if value is True or value == "true":
        return "yes"
    if value is False or value == "false":
        return "no"
    return str(value) if value not in (None, "") else "—"


def _side_line(label: str, side: Mapping[str, Any]) -> str:
    allowed = side.get("allowed")
    on_off = "ON" if allowed else "OFF"
    cause = side.get("block_cause") or "—"
    reason = side.get("block_reason") or "—"
    edge_v = _fmt_bool(side.get("edge_viable"))
    edge_bps = side.get("implied_bps")
    edge_txt = f"{edge_bps:.1f}bps" if isinstance(edge_bps, (int, float)) else "—"
    mult = side.get("size_mult")
    mult_txt = f"×{mult:.2f}" if isinstance(mult, (int, float)) else "—"
    bleed = "BLEEDING" if side.get("bleeding") else "clear"
    return (
        f"  {label}: {on_off} | cause={cause} | edge={edge_v} @{edge_txt} | size {mult_txt} | {bleed}"
        + (f"\n         block: {reason}" if reason and reason != "—" and not allowed else "")
    )


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

    lines: List[str] = [
        "=== Layered Quote Decision — operator report (L1–L5) ===",
        f"generated: {report.get('generated_utc')}",
        f"ws_as_version: {rt.get('ws_as_version') or '—'}",
        f"cycle: {rt.get('cycle_count') or '—'} | updated: {rt.get('updated_utc') or '—'}",
        "",
        "--- Layer 1 · Posture ---",
        f"  book_mode: {snap.get('book_mode') or rt.get('qd_book_mode') or '—'}",
        f"  solo_mode: {_fmt_bool(snap.get('solo_mode', rt.get('solo_mode')))}",
        f"  peer_lane: {snap.get('peer_lane_token') or rt.get('qd_peer_lane_token') or '—'}"
        f" (count={snap.get('peer_lane_count', rt.get('peer_lane_count', '—'))})",
        f"  posture_reason: {snap.get('posture_reason') or rt.get('posture_reason') or '—'}",
        f"  drift_band: {snap.get('drift_band') or rt.get('qd_drift_band') or '—'}"
        f" ({snap.get('drift_label') or '—'})",
        f"  headline: {snap.get('posture_headline') or summary.get('posture_detail') or '—'}",
        "",
        "--- Layer 2 · Intent ---",
        f"  intent: {snap.get('intent') or rt.get('qd_intent') or '—'}",
        f"  label: {snap.get('intent_label') or '—'}",
        f"  reason: {snap.get('intent_reason') or rt.get('qd_intent_reason') or '—'}",
        f"  subtext: {snap.get('intent_subtext') or summary.get('intent_subtext') or '—'}",
        "",
        "--- Layer 3 · Edge (solo hard gate) ---",
        f"  solo_edge_mult: {report.get('solo_edge_mult')} (pass if capture >= min_edge × mult)",
        f"  solo_absolute_floor: {report.get('solo_edge_floor_pct')}%",
        f"  crowded/sparse: no hard gate — edge scales size only",
        _side_line("bid", bid),
        _side_line("ask", ask),
        "",
        "--- Layer 4 · Bleed protection (side-local) ---",
        f"  bid_bleeding: {_fmt_bool(bid.get('bleeding', rt.get('qd_bid_bleeding')))}",
        f"  ask_bleeding: {_fmt_bool(ask.get('bleeding', rt.get('qd_ask_bleeding')))}",
        f"  protection_active: {_fmt_bool(summary.get('protection_active'))}",
        "",
        "--- Layer 5 · Final permissions ---",
        f"  qd_bid_allowed: {_fmt_bool(rt.get('qd_bid_allowed', bid.get('allowed')))}",
        f"  qd_ask_allowed: {_fmt_bool(rt.get('qd_ask_allowed', ask.get('allowed')))}",
        f"  permissions: {hud.get('qd_permissions_summary') or summary.get('quoting_short') or '—'}",
        f"  inventory_cb: {snap.get('inventory_cb_mode') or rt.get('qd_inventory_cb_mode') or '—'}",
    ]
    inv_note = snap.get("inventory_cb_note") or rt.get("qd_inventory_cb_note") or ""
    if inv_note:
        lines.append(f"  inventory_cb_note: {inv_note}")
    if snap.get("heavy_drift_l5_deferred") or rt.get("qd_heavy_drift_l5_deferred"):
        lines.append("  heavy_drift_l5_deferred: yes (crowded/sparse — L5 owns permission)")
    lines.extend(
        [
            f"  status: {summary.get('status_hint') or '—'}",
            f"  layer_trace: {snap.get('layer_trace_raw') or rt.get('qd_layer_trace') or '—'}",
            "",
            "--- Downstream quote path ---",
            f"  would_quote: {_fmt_bool(rt.get('qd_would_quote', snap.get('would_quote')))}",
            f"  zero_quote_reason: {rt.get('zero_quote_reason') or rt.get('edge_resolution_summary') or '—'}",
            f"  market_edge_met: {_fmt_bool(rt.get('market_edge_met'))}",
        ]
    )
    res_delta = rt.get("reservation_to_bbo_delta_bps")
    if res_delta is not None:
        lines.append(f"  reservation_to_bbo: {res_delta} bps | inside_l1: {_fmt_bool(rt.get('inside_l1'))}")

    lines.extend(["", "--- Recent cycles (QD_FINAL tail) ---"])
    if not tail_summary:
        lines.append("  No QD_FINAL rows — engine needs v2.3.1+ with L5 debug logging.")
    else:
        total = tail_summary.get("total", 0)
        intents = tail_summary.get("intent_counts") or {}
        intent_line = ", ".join(f"{k}={v}" for k, v in sorted(intents.items(), key=lambda kv: -kv[1]))
        lines.append(f"  rows: {total} | intents: {intent_line}")
        acc = tail_summary.get("solo_accumulate_total", 0)
        if acc:
            pct = 100.0 * tail_summary.get("solo_accumulate_bid_on", 0) / acc
            lines.append(
                f"  solo_accumulate_on_edge: {acc} cycles | bid_on {tail_summary.get('solo_accumulate_bid_on', 0)}"
                f" ({pct:.0f}%) | ask_on {tail_summary.get('solo_accumulate_ask_on', 0)}"
            )
        unload = intents.get("inventory_unload", 0)
        if unload and total:
            lines.append(f"  inventory_unload (trim): {unload} cycles ({100.0 * unload / total:.0f}% of tail)")
        lines.append(
            f"  bid_allowed: {tail_summary.get('bid_allowed_true', 0)}/{total}"
            f" | ask_allowed: {tail_summary.get('ask_allowed_true', 0)}/{total}"
        )
        if tail_summary.get("bleed_blocked_rows"):
            lines.append(f"  bleed_blocks (L4→L5): {tail_summary['bleed_blocked_rows']}")
        if tail_summary.get("inventory_cb_skipped_solo_rows"):
            lines.append(f"  inventory_cb_skipped_solo: {tail_summary['inventory_cb_skipped_solo_rows']}/{total}")

    records = final.get("records") or []
    if records:
        lines.append("")
        lines.append("  last 8 cycles:")
        for rec in records[-8:]:
            ts = rec.get("_ts", "?")
            intent = rec.get("intent", "?")
            bid_a = rec.get("bid_allowed", "?")
            ask_a = rec.get("ask_allowed", "?")
            be = rec.get("bid_edge_pct", "?")
            lines.append(f"    [{ts}] {intent} | bid={bid_a} ask={ask_a} | edge={be}%")

    lines.extend(
        [
            "",
            "Operator notes:",
            "  • Accumulate cycles should show bid=ON when edge clears solo gate (≥ floor or ≥ min×mult).",
            "  • Unload trim cycles block both sides when no edge — expected idle on solo heavy drift.",
            "  • L5 inventory CB skipped on solo; crowded/sparse use L5 CB instead of L2 unload.",
            "  • Deep L5 debug: Reports → QD L5 final permissions (QD_FINAL grep).",
        ]
    )
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
