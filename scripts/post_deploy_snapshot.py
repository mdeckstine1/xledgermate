#!/usr/bin/env python3
"""Post-deploy gates + G7 queue/fill review (run on VPS from repo root)."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experimental.ws_feed.live_activation_grading import build_g6_report, format_g6_report
from experimental.ws_runtime_analysis import format_runtime_analysis_report, run_runtime_analysis
from scripts.fill_quote_age_report import build_fill_age_report, format_fill_age_report


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def _runtime_g7_snapshot(rt: Dict[str, Any]) -> None:
    keys = [
        "version",
        "ws_as_version",
        "session_fill_count",
        "session_spread_capture_xrp",
        "session_pnl_balance_delta_xrp",
        "cancel_per_fill",
        "toxic_ratio",
        "toxic_ratio_30s",
        "mean_markout_30s_pct",
        "effective_quote_age_at_fill_seconds",
        "g7_summary",
        "g2_grade",
        "g2_spread_mult",
        "g2_scaler_label",
        "g7_scaler_label",
        "bid_touch_backoff_bps",
        "ask_touch_backoff_bps",
        "worst_vs_touch_bps",
        "quote_visibility_summary",
        "quotes_at_touch",
        "inventory_label",
        "g6_activation_tier",
        "g6_scale_ready",
        "last_cycle_ts_utc",
        "dry_run",
        "trading_enabled",
    ]
    print("--- runtime_state (G7 + session) ---")
    for k in keys:
        if k in rt:
            print(f"  {k}: {rt[k]}")


def _intel_queue_review(logs: Path, *, tail: int = 2000) -> None:
    path = logs / "intel_decisions.jsonl"
    if not path.exists():
        print("MISSING intel_decisions.jsonl")
        return

    cycles: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("kind") == "cycle":
            cycles.append(row)

    if not cycles:
        print("No cycle rows in intel JSONL tail.")
        return

    versions = Counter(str(c.get("ws_as_version") or "?") for c in cycles)
    g2 = Counter(str(c.get("g2_grade") or "") for c in cycles)
    inv = Counter(str(c.get("inventory_label") or "") for c in cycles)
    wq = sum(1 for c in cycles if c.get("would_quote"))
    g2_on = sum(1 for c in cycles if c.get("g2_active"))
    last = cycles[-1]

    print(f"--- intel_decisions.jsonl (last {len(cycles)} cycles) ---")
    print(f"  ws_as_version: {dict(versions)}")
    print(f"  would_quote: {100.0 * wq / len(cycles):.1f}% ({wq}/{len(cycles)})")
    print(f"  g2_active: {100.0 * g2_on / len(cycles):.1f}%")
    print(f"  g2_grades: {dict(g2)}")
    print(f"  inventory_label: {dict(inv)}")
    print(
        f"  last cycle: {last.get('cycle')} toxic@30s={last.get('toxic_fill_ratio_30s')} "
        f"markout@30s={last.get('mean_markout_30s_pct')} fills_session={last.get('fills_session')}"
    )


def _offer_refresh_stats(logs: Path) -> None:
    placed = cancelled = refreshes = 0
    for path in sorted(logs.glob("trades_*.csv")):
        try:
            rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
        except OSError:
            continue
        for row in rows:
            if (row.get("event_type") or "").upper() != "OFFER_REFRESH":
                continue
            refreshes += 1
            notes = row.get("notes") or ""
            if "placed" in notes:
                try:
                    placed += int(notes.split("placed", 1)[1].split()[0])
                except (IndexError, ValueError):
                    pass
            if "cancelled" in notes:
                try:
                    part = notes.split("cancelled", 1)[1].split(",")[0].strip()
                    cancelled += int(part)
                except (IndexError, ValueError):
                    pass
    ratio = cancelled / max(1, placed)
    print("--- OFFER_REFRESH (all trades_*.csv) ---")
    print(f"  refresh_events: {refreshes} | placed: {placed} | cancelled: {cancelled}")
    print(f"  cancel/place ratio: {ratio:.2f} (runtime cancel_per_fill is session fills)")


def main() -> int:
    logs = ROOT / "logs"
    rt_path = logs / "runtime_state.json"

    print("POST-DEPLOY SNAPSHOT")
    print("utc_now:", datetime.now(timezone.utc).isoformat())
    print("repo:", ROOT)

    if not rt_path.exists():
        print("MISSING runtime_state.json", file=sys.stderr)
        return 1

    rt = json.loads(rt_path.read_text(encoding="utf-8"))
    _section("1. Runtime + G7 baseline")
    _runtime_g7_snapshot(rt)

    _section("2. Fill quote age (offline)")
    age_report = build_fill_age_report(logs_dir=logs)
    print(format_fill_age_report(age_report))

    _section("3. WS runtime analysis (sample_history)")
    analysis = run_runtime_analysis(path=rt_path, include_backups=False, logs_dir=logs)
    print(format_runtime_analysis_report(analysis, path_label=str(rt_path)))
    if analysis.soak:
        print(f"\nC2 soak gate: {'PASS' if analysis.soak.passed else 'FAIL'} — {analysis.soak.failures}")

    _section("4. G6 live activation grading")
    g6 = build_g6_report(runtime_path=rt_path, logs_dir=logs)
    print(format_g6_report(g6))
    print(f"\nG6 gate: {'PASS' if g6.passed else 'FAIL (expected pilot_watch early soak)'}")

    _section("5. Queue / fill review (intel + refresh)")
    _intel_queue_review(logs)
    _offer_refresh_stats(logs)

    out = logs / "post_deploy_snapshot.txt"
    # Re-run capture to file via stdout redirect is operator's job; write JSON summary
    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "version": rt.get("version"),
        "ws_as_version": rt.get("ws_as_version"),
        "session_fill_count": rt.get("session_fill_count"),
        "session_spread_capture_xrp": rt.get("session_spread_capture_xrp"),
        "cancel_per_fill": rt.get("cancel_per_fill"),
        "toxic_ratio_30s": rt.get("toxic_ratio_30s"),
        "mean_markout_30s_pct": rt.get("mean_markout_30s_pct"),
        "worst_vs_touch_bps": rt.get("worst_vs_touch_bps"),
        "g7_summary": rt.get("g7_summary"),
        "g6_activation_tier": rt.get("g6_activation_tier"),
        "g6_passed": g6.passed,
        "fill_age_median_s": age_report.age_seconds_median,
        "fill_count": age_report.fill_count,
    }
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
