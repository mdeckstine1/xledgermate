#!/usr/bin/env python3
"""Tail QD_FINAL L5 permission diagnostics from xledgermate.log."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from scripts.qd_report_common import (
    fmt_bool,
    fmt_on_off,
    intent_mix_compact,
    operating_mode,
    side_permission_block,
)

QD_FINAL_MARKER = "QD_FINAL"


def parse_qd_final_line(line: str) -> Dict[str, str]:
    """Parse pipe-delimited key=value fields from a QD_FINAL log line."""
    idx = line.find(QD_FINAL_MARKER)
    if idx < 0:
        return {}
    rest = line[idx:]
    parts = [p.strip() for p in rest.split("|")]
    out: Dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        out[key.strip()] = value.strip()
    if len(line) >= 19 and line[4] == "-" and line[10] == " ":
        out["_ts"] = line[:19]
    return out


def tail_qd_final_lines(
    log_path: Path,
    *,
    limit: int = 40,
    read_bytes: int = 3_000_000,
) -> List[str]:
    """Return up to ``limit`` most recent log lines containing QD_FINAL."""
    if not log_path.exists():
        return []
    size = log_path.stat().st_size
    with log_path.open("rb") as handle:
        handle.seek(max(0, size - read_bytes))
        chunk = handle.read().decode("utf-8", errors="replace")
    matched = [line for line in chunk.splitlines() if QD_FINAL_MARKER in line]
    return matched[-limit:]


def _runtime_snapshot(logs_dir: Path) -> Dict[str, Any]:
    path = logs_dir / "runtime_state.json"
    if not path.exists():
        return {"present": False, "path": str(path)}
    try:
        runtime = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"present": False, "path": str(path), "error": str(exc)}

    hud: Dict[str, Any] = {}
    try:
        from experimental.ws_feed.qd_hud import build_qd_hud_fields

        hud = build_qd_hud_fields(runtime)
    except Exception:
        hud = {}

    snap = hud.get("qd_snapshot") or {}
    summary = hud.get("qd_decision_summary") or {}
    bid = snap.get("bid") or {}
    ask = snap.get("ask") or {}

    return {
        "present": True,
        "path": str(path),
        "cycle_count": runtime.get("cycle_count"),
        "updated_utc": runtime.get("updated_utc"),
        "intent": runtime.get("qd_intent") or snap.get("intent") or "",
        "book_mode": runtime.get("qd_book_mode") or snap.get("book_mode") or "",
        "solo_mode": runtime.get("solo_mode", snap.get("solo_mode")),
        "drift_band": runtime.get("qd_drift_band") or snap.get("drift_band") or "",
        "bid_allowed": runtime.get("qd_bid_allowed", bid.get("allowed")),
        "ask_allowed": runtime.get("qd_ask_allowed", ask.get("allowed")),
        "bid_pause_cause": runtime.get("qd_bid_pause_cause") or bid.get("block_cause") or "",
        "ask_pause_cause": runtime.get("qd_ask_pause_cause") or ask.get("block_cause") or "",
        "bid_block_reason": runtime.get("qd_bid_block_reason") or bid.get("block_reason") or "",
        "ask_block_reason": runtime.get("qd_ask_block_reason") or ask.get("block_reason") or "",
        "bid_edge_viable": runtime.get("qd_bid_edge_viable", bid.get("edge_viable")),
        "ask_edge_viable": runtime.get("qd_ask_edge_viable", ask.get("edge_viable")),
        "bid_edge_bps": runtime.get("qd_bid_implied_bps") or bid.get("implied_bps"),
        "ask_edge_bps": runtime.get("qd_ask_implied_bps") or ask.get("implied_bps"),
        "inventory_cb_mode": runtime.get("qd_inventory_cb_mode") or snap.get("inventory_cb_mode") or "",
        "inventory_cb_note": runtime.get("qd_inventory_cb_note") or snap.get("inventory_cb_note") or "",
        "bid_bleeding": runtime.get("qd_bid_bleeding", bid.get("bleeding")),
        "ask_bleeding": runtime.get("qd_ask_bleeding", ask.get("bleeding")),
        "layer_trace": runtime.get("qd_layer_trace") or snap.get("layer_trace_raw") or "",
        "would_quote": runtime.get("qd_would_quote", snap.get("would_quote")),
        "zero_quote_reason": runtime.get("zero_quote_reason") or runtime.get("edge_resolution_summary") or "",
        "status_hint": summary.get("status_hint") or "",
        "primary_block": summary.get("primary_block") or "",
        "permissions_summary": hud.get("qd_permissions_summary") or "",
    }


def _summarize_records(records: List[Mapping[str, str]]) -> Dict[str, Any]:
    if not records:
        return {}

    intent_counts = Counter(r.get("intent", "?") for r in records)
    bid_allowed = sum(1 for r in records if r.get("bid_allowed") == "true")
    ask_allowed = sum(1 for r in records if r.get("ask_allowed") == "true")

    accumulate = [r for r in records if r.get("intent") == "solo_accumulate_on_edge"]
    acc_bid_on = sum(1 for r in accumulate if r.get("bid_allowed") == "true")
    acc_ask_on = sum(1 for r in accumulate if r.get("ask_allowed") == "true")

    bid_causes = Counter(
        r.get("bid_cause", r.get("bid_block", "allowed"))
        for r in records
        if r.get("bid_allowed") != "true"
    )
    ask_causes = Counter(
        r.get("ask_cause", r.get("ask_block", "allowed"))
        for r in records
        if r.get("ask_allowed") != "true"
    )

    bleed_blocks = sum(
        1 for r in records if r.get("bid_bleed_blocked") == "true" or r.get("ask_bleed_blocked") == "true"
    )
    solo_skips = sum(1 for r in records if r.get("inventory_cb_mode") == "skipped_solo")

    return {
        "total": len(records),
        "intent_counts": dict(intent_counts),
        "bid_allowed_true": bid_allowed,
        "ask_allowed_true": ask_allowed,
        "solo_accumulate_total": len(accumulate),
        "solo_accumulate_bid_on": acc_bid_on,
        "solo_accumulate_ask_on": acc_ask_on,
        "bid_block_causes": dict(bid_causes.most_common(5)),
        "ask_block_causes": dict(ask_causes.most_common(5)),
        "bleed_blocked_rows": bleed_blocks,
        "inventory_cb_skipped_solo_rows": solo_skips,
    }


def build_qd_final_report(
    *,
    logs_dir: Optional[Path] = None,
    limit: int = 40,
) -> Dict[str, Any]:
    logs = logs_dir or Path("logs")
    log_path = logs / "xledgermate.log"
    raw_lines = tail_qd_final_lines(log_path, limit=limit)
    records = [parse_qd_final_line(line) for line in raw_lines]
    records = [r for r in records if r]

    return {
        "generated_utc": datetime.now(tz=timezone.utc).isoformat(),
        "log_path": str(log_path),
        "log_exists": log_path.exists(),
        "record_count": len(records),
        "records": records,
        "raw_lines": raw_lines,
        "summary": _summarize_records(records),
        "runtime": _runtime_snapshot(logs),
    }


def _format_runtime_section(runtime: Mapping[str, Any]) -> List[str]:
    if not runtime.get("present"):
        return [
            "CURRENT CYCLE",
            f"  No runtime snapshot ({runtime.get('path', 'logs/runtime_state.json')}).",
            *( [f"  Read error: {runtime['error']}"] if runtime.get("error") else [] ),
        ]

    mode_label, mode_hint = operating_mode(
        intent=str(runtime.get("intent") or ""),
        book_mode=str(runtime.get("book_mode") or ""),
        solo_mode=bool(runtime.get("solo_mode")),
        bid_allowed=runtime.get("bid_allowed"),
        ask_allowed=runtime.get("ask_allowed"),
        protection_active=bool(runtime.get("bid_bleeding") or runtime.get("ask_bleeding")),
        would_quote=runtime.get("would_quote"),
    )

    lines = [
        "CURRENT CYCLE (runtime_state.json)",
        f"  cycle: {runtime.get('cycle_count')} | updated: {runtime.get('updated_utc') or '—'}",
        f"  mode: {mode_label} — {mode_hint}",
        "",
        "L5 PERMISSIONS",
    ]
    lines.extend(side_permission_block(
        "bid",
        allowed=runtime.get("bid_allowed"),
        pause_cause=str(runtime.get("bid_pause_cause") or ""),
        block_reason=str(runtime.get("bid_block_reason") or ""),
        edge_viable=runtime.get("bid_edge_viable"),
        edge_bps=runtime.get("bid_edge_bps"),
        bleeding=runtime.get("bid_bleeding"),
    ))
    lines.append("")
    lines.extend(side_permission_block(
        "ask",
        allowed=runtime.get("ask_allowed"),
        pause_cause=str(runtime.get("ask_pause_cause") or ""),
        block_reason=str(runtime.get("ask_block_reason") or ""),
        edge_viable=runtime.get("ask_edge_viable"),
        edge_bps=runtime.get("ask_edge_bps"),
        bleeding=runtime.get("ask_bleeding"),
    ))
    lines.extend([
        "",
        "CIRCUIT BREAKER & BLEED",
        f"  inventory_cb_mode: {runtime.get('inventory_cb_mode') or '—'}",
    ])
    if runtime.get("inventory_cb_note"):
        lines.append(f"  inventory_cb_note: {runtime['inventory_cb_note']}")
    if runtime.get("inventory_cb_mode") == "skipped_solo":
        lines.append("  inventory_cb_skipped_solo: yes")
    lines.extend([
        "",
        "DOWNSTREAM",
        f"  would_quote: {fmt_on_off(runtime.get('would_quote'))}",
        f"  zero_quote_reason: {runtime.get('zero_quote_reason') or '—'}",
        f"  status: {runtime.get('status_hint') or '—'}",
    ])
    if runtime.get("permissions_summary"):
        lines.append(f"  permissions: {runtime['permissions_summary']}")
    if runtime.get("layer_trace"):
        lines.append(f"  trace: {runtime['layer_trace']}")
    return lines


def _format_summary_section(summary: Mapping[str, Any]) -> List[str]:
    lines = ["LOG TAIL SUMMARY (QD_FINAL)"]
    if not summary:
        lines.append("  No QD_FINAL rows — engine needs v2.3.2+ with L5 logging.")
        return lines

    mix = intent_mix_compact(summary)
    if mix:
        lines.append(f"  intent mix: {mix}")
    lines.append(
        f"  bid_allowed=true: {summary.get('bid_allowed_true', 0)}/{summary.get('total', 0)}"
        f" | ask_allowed=true: {summary.get('ask_allowed_true', 0)}/{summary.get('total', 0)}"
    )
    acc_total = summary.get("solo_accumulate_total", 0)
    if acc_total:
        lines.append(
            f"  solo_accumulate: bid_on {summary.get('solo_accumulate_bid_on', 0)}/{acc_total}"
        )
    bid_causes = summary.get("bid_block_causes") or {}
    ask_causes = summary.get("ask_block_causes") or {}
    if bid_causes:
        lines.append("  top bid blocks: " + ", ".join(f"{k}={v}" for k, v in bid_causes.items()))
    if ask_causes:
        lines.append("  top ask blocks: " + ", ".join(f"{k}={v}" for k, v in ask_causes.items()))
    if summary.get("bleed_blocked_rows"):
        lines.append(f"  bleed_blocked: {summary['bleed_blocked_rows']} cycles")
    if summary.get("inventory_cb_skipped_solo_rows"):
        lines.append(f"  inventory_cb_skipped_solo: {summary['inventory_cb_skipped_solo_rows']} cycles")
    return lines


def _format_record_line(record: Mapping[str, str]) -> str:
    ts = record.get("_ts", "?")
    intent = record.get("intent", "?")
    bid = record.get("bid_allowed", "?")
    ask = record.get("ask_allowed", "?")
    solo = record.get("solo_mode", "?")
    bid_cause = record.get("bid_cause", "")
    ask_cause = record.get("ask_cause", "")
    bid_block = record.get("bid_block", "")
    ask_block = record.get("ask_block", "")
    bid_edge = record.get("bid_edge_pct", "?")
    ask_edge = record.get("ask_edge_pct", "?")
    inv_cb = record.get("inventory_cb_mode", "?")

    detail_parts = [
        f"intent={intent}",
        f"solo={solo}",
        f"bid={bid}",
        f"ask={ask}",
        f"bid_edge={bid_edge}%",
        f"ask_edge={ask_edge}%",
        f"inv_cb={inv_cb}",
    ]
    if bid == "false" and (bid_cause or bid_block):
        detail_parts.append(f"bid→{bid_cause or bid_block}")
    if ask == "false" and (ask_cause or ask_block):
        detail_parts.append(f"ask→{ask_cause or ask_block}")
    if record.get("bid_bleed_blocked") == "true":
        detail_parts.append("bid_bleed=yes")
    if record.get("ask_bleed_blocked") == "true":
        detail_parts.append("ask_bleed=yes")
    return f"[{ts}] " + " | ".join(detail_parts)


def format_qd_final_report(report: Mapping[str, Any]) -> str:
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║  L5 PERMISSION MONITOR (QD_FINAL)                            ║",
        "╚══════════════════════════════════════════════════════════════╝",
        f"generated: {report.get('generated_utc')}",
        f"log: {report.get('log_path')} | exists: {report.get('log_exists')}",
        "",
    ]
    lines.extend(_format_runtime_section(report.get("runtime") or {}))
    lines.append("")
    lines.extend(_format_summary_section(report.get("summary") or {}))
    lines.append("")
    lines.append("RECENT CYCLES (oldest → newest)")

    records: List[Mapping[str, str]] = report.get("records") or []
    if not records:
        lines.append("  No QD_FINAL lines. Grep: Select-String 'QD_FINAL' logs\\xledgermate.log")
    else:
        for record in records:
            lines.append("  " + _format_record_line(record))

    lines.extend([
        "",
        "Block cause key: edge | intent | inventory | tape | bleed",
        "  bid ON + no offers → reservation / pure path / size mult",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="QD_FINAL L5 permission tail report")
    parser.add_argument("--logs-dir", default="logs", help="logs directory")
    parser.add_argument("--limit", type=int, default=40, help="max QD_FINAL rows to parse")
    args = parser.parse_args()
    report = build_qd_final_report(logs_dir=Path(args.logs_dir), limit=args.limit)
    print(format_qd_final_report(report))


if __name__ == "__main__":
    main()
