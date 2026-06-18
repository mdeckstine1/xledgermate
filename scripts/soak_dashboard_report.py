#!/usr/bin/env python3
"""Soak dashboard — factual bundle + optional Grok narrative (HUD Reports tab)."""

from __future__ import annotations

import csv
import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experimental.ws_feed.live_activation_grading import build_g6_report, format_g6_report
from experimental.ws_runtime_analysis import format_runtime_analysis_report, run_runtime_analysis
from scripts.fill_quote_age_report import build_fill_age_report, format_fill_age_report
from scripts.hourly_soak_trend import format_hourly_soak_trend

SOAK_NARRATIVE_PROMPT = """You are reviewing a live pure Avellaneda–Stoikov market maker soak on XRPL.

Below is a FACT BUNDLE from logs (runtime, gates, fills, G7/G2). Use ONLY these numbers. Do not invent metrics.

Your job:
1. What phase is this soak in? (warming, inventory skew, recovering, stable)
2. Is behavior consistent with G7 v1 + G2 design? (cite g7_summary, inventory_label if present)
3. Separate trading edge (Skim Δ / session_spread_capture, markout, toxic) from spot/MTM (portfolio, wallet Δ)
4. Gate status (G6, C2) in plain English
5. One short paragraph: discipline — "nothing to do" vs "watch these 2 metrics"

Rules:
- Max 4 short paragraphs. Plain prose only — no ## headers, no JSON, no code fences.
- Do NOT recommend changing G7, tightening quotes, or overriding A-S reservation.
- Do NOT suggest exploitative tactics or mid-soak strategy overrides.
- If data is missing, say so briefly.

FACT BUNDLE:
"""


def _section(title: str) -> str:
    return f"\n{'=' * 60}\n{title}\n{'=' * 60}\n"


def _runtime_snapshot_lines(rt: Dict[str, Any]) -> List[str]:
    keys = [
        "version",
        "ws_as_version",
        "fills_session",
        "session_fill_count",
        "session_spread_capture_xrp",
        "session_pnl_balance_xrp",
        "portfolio_value_xrp",
        "cancel_per_fill",
        "toxic_fill_ratio",
        "toxic_fill_ratio_30s",
        "mean_markout_30s_pct",
        "effective_quote_age_at_fill_seconds",
        "g7_summary",
        "g7_scaler_label",
        "g2_grade",
        "g2_spread_mult",
        "g2_scaler_label",
        "bid_touch_backoff_bps",
        "ask_touch_backoff_bps",
        "worst_vs_touch_bps",
        "quote_visibility_summary",
        "quotes_at_touch",
        "inventory_label",
        "g6_activation_tier",
        "as_presence_pct",
        "mid_price",
        "dry_run",
        "trading_enabled",
        "cycle_count",
    ]
    lines = ["--- runtime_state (session + G7/G2) ---"]
    for k in keys:
        if k in rt and rt[k] is not None and rt[k] != "":
            lines.append(f"  {k}: {rt[k]}")
    return lines


def _intel_queue_review_lines(logs: Path, *, tail: int = 2000) -> List[str]:
    path = logs / "intel_decisions.jsonl"
    if not path.exists():
        return ["--- intel_decisions.jsonl ---", "  MISSING"]

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
        return ["--- intel_decisions.jsonl ---", "  No cycle rows in tail."]

    versions = Counter(str(c.get("ws_as_version") or "?") for c in cycles)
    g2 = Counter(str(c.get("g2_grade") or "") for c in cycles)
    inv = Counter(str(c.get("inventory_label") or "") for c in cycles)
    wq = sum(1 for c in cycles if c.get("would_quote"))
    g2_on = sum(1 for c in cycles if c.get("g2_active"))
    last = cycles[-1]

    lines = [
        f"--- intel_decisions.jsonl (last {len(cycles)} cycles) ---",
        f"  ws_as_version: {dict(versions)}",
        f"  would_quote: {100.0 * wq / len(cycles):.1f}% ({wq}/{len(cycles)})",
        f"  g2_active: {100.0 * g2_on / len(cycles):.1f}%",
        f"  g2_grades: {dict(g2)}",
        f"  inventory_label: {dict(inv)}",
        (
            f"  last cycle: {last.get('cycle')} toxic@30s={last.get('toxic_fill_ratio_30s')} "
            f"markout@30s={last.get('mean_markout_30s_pct')} fills_session={last.get('fills_session')}"
        ),
    ]
    return lines


def _offer_refresh_lines(logs: Path) -> List[str]:
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
    return [
        "--- OFFER_REFRESH (all trades_*.csv) ---",
        f"  refresh_events: {refreshes} | placed: {placed} | cancelled: {cancelled}",
        f"  cancel/place ratio: {ratio:.2f} (runtime cancel_per_fill is session fills)",
    ]


def build_soak_dashboard_facts(*, logs_dir: Optional[Path] = None) -> str:
    """Deterministic soak fact bundle (no Grok)."""
    logs = logs_dir or (ROOT / "logs")
    rt_path = logs / "runtime_state.json"
    buf = io.StringIO()

    buf.write("SOAK DASHBOARD — facts\n")
    buf.write(f"generated_utc: {datetime.now(tz=timezone.utc).isoformat()}\n")
    buf.write(f"logs_dir: {logs}\n")

    if not rt_path.exists():
        buf.write("\nMISSING logs/runtime_state.json — start ws-engine or wait for first cycle.\n")
        return buf.getvalue()

    rt = json.loads(rt_path.read_text(encoding="utf-8"))

    buf.write(_section("1. Runtime + G7/G2 session"))
    buf.write("\n".join(_runtime_snapshot_lines(rt)))
    buf.write("\n")

    buf.write(_section("2. Fill quote age (offline)"))
    age_report = build_fill_age_report(logs_dir=logs)
    buf.write(format_fill_age_report(age_report))
    buf.write("\n")

    buf.write(_section("3. WS runtime analysis + C2 gate"))
    analysis = run_runtime_analysis(path=rt_path, include_backups=False, logs_dir=logs)
    buf.write(format_runtime_analysis_report(analysis, path_label=str(rt_path)))
    if analysis.soak:
        status = "PASS" if analysis.soak.passed else "FAIL"
        buf.write(f"\nC2 soak gate: {status} — {analysis.soak.failures}\n")

    buf.write(_section("4. G6 activation grade"))
    g6 = build_g6_report(runtime_path=rt_path, logs_dir=logs)
    buf.write(format_g6_report(g6))
    buf.write(f"\nG6 gate: {'PASS' if g6.passed else 'FAIL'}\n")

    buf.write(_section("5. Hourly soak trend (24h UTC)"))
    buf.write(format_hourly_soak_trend(logs_dir=logs))
    buf.write("\n")

    buf.write(_section("6. Queue / fill review (intel + refresh)"))
    buf.write("\n".join(_intel_queue_review_lines(logs)))
    buf.write("\n")
    buf.write("\n".join(_offer_refresh_lines(logs)))
    buf.write("\n")

    buf.write(_section("Discipline note"))
    buf.write(
        "Pure A-S reservation is sacred. G7/G2 are execution only. "
        "Skim Δ = trading edge; Wallet Δ / Port include spot MTM. "
        "Narrative (if requested) explains — it does not override strategy.\n"
    )

    return buf.getvalue()


def fetch_grok_soak_narrative(
    facts: str,
    *,
    api_key: str,
    model: str = "grok-3",
    timeout_s: float = 45.0,
) -> str:
    """Call Grok API with discipline-bound soak narrative prompt."""
    import requests

    url = "https://api.x.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    # Trim very long bundles to control tokens
    fact_body = facts if len(facts) <= 12000 else facts[:12000] + "\n\n[... truncated for token limit ...]"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": SOAK_NARRATIVE_PROMPT + fact_body}],
        "max_tokens": 500,
        "temperature": 0.3,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    choice = resp.json().get("choices", [{}])[0] or {}
    content = (choice.get("message") or {}).get("content") or ""
    return content.strip() or "(Grok returned empty narrative.)"


def build_soak_dashboard_report(
    *,
    logs_dir: Optional[Path] = None,
    narrative: bool = False,
    grok_key: str = "",
    grok_model: str = "grok-3",
    grok_enabled: bool = True,
) -> str:
    """Facts bundle; optionally append Grok narrative when key present."""
    facts = build_soak_dashboard_facts(logs_dir=logs_dir)
    if not narrative:
        return facts

    buf = io.StringIO()
    buf.write(facts)
    buf.write(_section("Grok soak narrative (advisory — on demand)"))

    if not grok_enabled:
        buf.write(
            "Grok disabled (ws_hud_grok_enabled=false). Facts-only report above.\n"
        )
        return buf.getvalue()

    key = (grok_key or "").strip()
    if not key:
        buf.write(
            "No Grok API key configured. Set XLG_GROK_KEY in .env or Config tab → Apply, "
            "then refresh this report.\n"
        )
        return buf.getvalue()

    try:
        narrative_text = fetch_grok_soak_narrative(facts, api_key=key, model=grok_model or "grok-3")
        buf.write(narrative_text)
        buf.write("\n")
    except Exception as exc:
        buf.write(f"Grok narrative failed: {type(exc).__name__}: {exc}\n")

    return buf.getvalue()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Soak dashboard report (facts + optional Grok narrative)")
    parser.add_argument("--narrative", action="store_true", help="Append Grok narrative (requires API key)")
    parser.add_argument("--logs-dir", type=Path, default=ROOT / "logs")
    args = parser.parse_args()

    grok_key = ""
    grok_model = "grok-3"
    if args.narrative:
        from utils.env_secrets import resolve_intel_ai_config

        prov, grok_key, grok_model = resolve_intel_ai_config()
        if prov.lower() != "grok" and grok_key:
            pass  # still use key if present

    text = build_soak_dashboard_report(
        logs_dir=args.logs_dir,
        narrative=args.narrative,
        grok_key=grok_key,
        grok_model=grok_model,
    )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
