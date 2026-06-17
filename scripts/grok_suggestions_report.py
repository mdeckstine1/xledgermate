#!/usr/bin/env python3
"""Tail Grok analyze_competitor rows from intel_decisions.jsonl (F4)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from experimental.ws_feed.intel_decisions_log import INTEL_DECISIONS_PATH, tail_intel_records


def build_grok_suggestions_report(
    *,
    logs_dir: Optional[Path] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    logs = logs_dir or Path("logs")
    path = logs / "intel_decisions.jsonl" if logs.name != "intel_decisions.jsonl" else logs
    if logs_dir and (logs_dir / "intel_decisions.jsonl").exists():
        path = logs_dir / "intel_decisions.jsonl"
    elif not path.exists() and INTEL_DECISIONS_PATH.exists():
        path = INTEL_DECISIONS_PATH

    rows = [
        r
        for r in tail_intel_records(limit=limit * 3, path=path)
        if r.get("kind") == "grok_suggestion"
    ][-limit:]

    pending = sum(1 for r in rows if r.get("outcome_status") == "pending")
    in_lane = sum(1 for r in rows if r.get("in_peer_lane"))
    return {
        "generated_utc": datetime.now(tz=timezone.utc).isoformat(),
        "path": str(path),
        "total": len(rows),
        "pending_outcomes": pending,
        "in_peer_lane_count": in_lane,
        "rows": rows,
    }


def format_grok_suggestions_report(report: Dict[str, Any]) -> str:
    lines = [
        "=== Grok suggestions (intel_decisions.jsonl) ===",
        f"generated: {report.get('generated_utc')}",
        f"source: {report.get('path')}",
        f"rows: {report.get('total')} | pending outcomes: {report.get('pending_outcomes')}",
        f"in_peer_lane: {report.get('in_peer_lane_count')}",
        "",
    ]
    rows: List[Dict[str, Any]] = report.get("rows") or []
    if not rows:
        lines.append("No grok_suggestion rows yet — use Intelligence → Analyze with AI.")
        return "\n".join(lines)

    for row in rows:
        ts = (row.get("ts_utc") or "")[:19].replace("T", " ")
        addr = str(row.get("address") or "?")[:16]
        lane = "in" if row.get("in_peer_lane") else "out"
        src = row.get("scrape_source") or "?"
        status = row.get("outcome_status") or "pending"
        excerpt = str(row.get("result_excerpt") or "").replace("\n", " ")[:120]
        lines.append(f"[{ts}] {addr}… | lane={lane} | src={src} | {status}")
        if excerpt:
            lines.append(f"  excerpt: {excerpt}")
        brief = row.get("structured_briefing")
        if isinstance(brief, dict) and brief.get("lane_note"):
            lines.append(f"  lane_note: {brief.get('lane_note')}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Grok suggestion tail report (F4)")
    parser.add_argument("--logs-dir", default="logs", help="logs directory")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    report = build_grok_suggestions_report(logs_dir=Path(args.logs_dir), limit=args.limit)
    print(format_grok_suggestions_report(report))


if __name__ == "__main__":
    main()
