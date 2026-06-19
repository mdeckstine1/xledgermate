"""
G6 (E.6) — live activation grading per Phase E §7.

Portfolio XRP-equiv from fills + runtime, spread capture, toxicity, drawdown,
peer lane, and G2/G4 structural signal rates. Produces activation tier for
gradual live MM (pilot → active → scale_ready).

Run:
  python -m experimental.ws_feed.live_activation_grading
  python -m experimental.ws_feed.live_activation_grading --gate
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from experimental.ws_feed.intel_decisions_log import tail_intel_records
from experimental.ws_feed.performance_metrics import build_performance_metrics

G6_VERSION = "1.1.0"
DEFAULT_REPORT_PATH = Path("logs/g6_activation_report.json")


@dataclass(frozen=True)
class G6Criteria:
    min_fills_pilot: int = 8
    min_fills_active: int = 25
    min_fills_scale: int = 50
    hold_min_fills: int = 15
    require_live: bool = True
    require_kill_clear: bool = True


@dataclass
class G6Report:
    g6_version: str = G6_VERSION
    generated_utc: str = ""
    ws_as_version: str = ""
    activation_tier: str = "unknown"
    activation_summary: str = ""
    passed: bool = False
    failures: List[str] = field(default_factory=list)
    portfolio: Dict[str, Any] = field(default_factory=dict)
    structural_signals: Dict[str, Any] = field(default_factory=dict)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    criteria: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_runtime(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _portfolio_block(runtime: Dict[str, Any], capture: Dict[str, Any]) -> Dict[str, Any]:
    rt = runtime or {}
    cap = capture or {}
    try:
        portfolio_now = float(rt.get("portfolio_value_xrp") or 0)
    except (TypeError, ValueError):
        portfolio_now = 0.0
    try:
        baseline = float(rt.get("session_baseline_portfolio_xrp") or 0)
    except (TypeError, ValueError):
        baseline = 0.0
    try:
        bal_pnl = float(rt.get("session_pnl_balance_xrp") or 0)
    except (TypeError, ValueError):
        bal_pnl = None
    try:
        mtm_pnl = float(rt.get("session_pnl_mtm_xrp") or rt.get("session_pnl_xrp_estimate") or 0)
    except (TypeError, ValueError):
        mtm_pnl = None

    mtm_drift = (portfolio_now - baseline) if baseline > 0 and portfolio_now > 0 else None
    fill_capture = cap.get("total_capture_xrp")

    return {
        "portfolio_xrp_equiv": round(portfolio_now, 4) if portfolio_now > 0 else None,
        "session_baseline_xrp_equiv": round(baseline, 4) if baseline > 0 else None,
        "session_mtm_drift_xrp": round(mtm_drift, 4) if mtm_drift is not None else None,
        "session_balance_pnl_xrp": round(bal_pnl, 4) if bal_pnl is not None else None,
        "session_mtm_pnl_xrp": round(mtm_pnl, 4) if mtm_pnl is not None else None,
        "fill_capture_xrp": fill_capture,
        "inventory_xrp_pct": rt.get("inventory_xrp_ratio_pct"),
        "inventory_label": rt.get("inventory_label"),
    }


def _structural_signals_block(intel_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    cycles = [r for r in intel_rows if r.get("kind") == "cycle"]
    if not cycles:
        return {
            "cycle_rows": 0,
            "g2_active_pct": None,
            "g4_active_pct": None,
            "would_quote_pct": None,
            "g2_grades": {},
            "g4_grades": {},
        }

    g2_active = sum(1 for r in cycles if r.get("g2_active"))
    g4_active = sum(1 for r in cycles if r.get("g4_active"))
    would_q = sum(1 for r in cycles if r.get("would_quote"))
    n = len(cycles)

    g2_grades: Dict[str, int] = {}
    g4_grades: Dict[str, int] = {}
    for row in cycles:
        g2 = str(row.get("g2_grade") or "neutral")
        g4 = str(row.get("g4_grade") or "neutral")
        g2_grades[g2] = g2_grades.get(g2, 0) + 1
        g4_grades[g4] = g4_grades.get(g4, 0) + 1

    return {
        "cycle_rows": n,
        "g2_active_pct": round(100.0 * g2_active / n, 1),
        "g4_active_pct": round(100.0 * g4_active / n, 1),
        "would_quote_pct": round(100.0 * would_q / n, 1),
        "g2_grades": g2_grades,
        "g4_grades": g4_grades,
    }


def _grade_by_id(grades: List[Dict[str, str]], grade_id: str) -> str:
    for row in grades:
        if row.get("id") == grade_id:
            return str(row.get("grade") or "unknown")
    return "unknown"


def _bad_spread_economics(capture: Dict[str, Any]) -> bool:
    """v1.1: hold only on bad economics (n≥hold_min_fills enforced by caller)."""
    cap = capture or {}
    pos_pct = cap.get("positive_capture_pct")
    avg_bps = cap.get("avg_capture_bps")
    if pos_pct is None or avg_bps is None:
        return False
    try:
        pos_f = float(pos_pct)
        bps_f = float(avg_bps)
    except (TypeError, ValueError):
        return False
    if bps_f < 0:
        return True
    if pos_f < 50.0:
        return True
    if bps_f < 3.0 and pos_f < 70.0:
        return True
    return False


def resolve_activation_tier(
    *,
    grades: List[Dict[str, str]],
    n_fills: int,
    runtime: Dict[str, Any],
    criteria: G6Criteria,
    capture: Optional[Dict[str, Any]] = None,
) -> tuple[str, str]:
    """Return (tier, human summary)."""
    rt = runtime or {}
    cap = capture or {}
    if bool(rt.get("dry_run")):
        return "paper", "dry_run=true — not live activation"
    if bool(rt.get("kill_switch_active")):
        return "halted", "kill switch active — clear and restart before grading"

    if n_fills < criteria.min_fills_pilot:
        return "warming_up", f"{n_fills} WS fills — need ≥{criteria.min_fills_pilot} for pilot grade"

    capture_g = _grade_by_id(grades, "spread_capture")

    if capture_g == "thin_edge":
        return (
            "thin_edge",
            "thin spread capture (5–8 bps, join-aligned) — gate pass; not scale_ready",
        )

    if capture_g == "attention":
        if n_fills < criteria.hold_min_fills:
            return (
                "pilot_watch",
                f"spread capture below good bar — {n_fills} fills; need ≥{criteria.hold_min_fills} before hold",
            )
        if _bad_spread_economics(cap):
            return (
                "hold",
                "spread capture economics weak — keep size conservative; review fills",
            )
        return (
            "pilot_watch",
            "spread capture below good bar — thin positive; not bad economics",
        )

    core_ids = ("spread_capture", "toxicity", "drawdown", "inventory_health")
    core_good = all(_grade_by_id(grades, gid) == "good" for gid in core_ids)

    if n_fills >= criteria.min_fills_scale and core_good:
        return "scale_ready", "§7 core metrics good with 50+ fills — eligible for scale review (E3)"

    if n_fills >= criteria.min_fills_active and core_good:
        return "active", "§7 core metrics good — live activation confirmed"

    attention = [g for g in grades if g.get("grade") == "attention"]
    if not attention:
        return "pilot", "live pilot — metrics neutral/good; accumulate fills for active tier"

    names = ", ".join(g.get("label", g.get("id", "?")) for g in attention[:3])
    return "pilot_watch", f"live pilot with attention on: {names}"


def summarize_activation(
    *,
    runtime: Dict[str, Any],
    performance_metrics: Dict[str, Any],
    intel_rows: Optional[List[Dict[str, Any]]] = None,
    criteria: Optional[G6Criteria] = None,
) -> Dict[str, Any]:
    """Compact block for HUD `performance_metrics.activation`."""
    crit = criteria or G6Criteria()
    pm = performance_metrics or {}
    cap = pm.get("capture") or {}
    grades = pm.get("grades") or []
    n_fills = int(cap.get("ws_fills") or 0)
    intel = intel_rows if intel_rows is not None else []
    tier, summary = resolve_activation_tier(
        grades=grades,
        n_fills=n_fills,
        runtime=runtime,
        criteria=crit,
        capture=cap,
    )
    attention_on = [
        str(g.get("label") or g.get("id") or "?")
        for g in grades
        if g.get("grade") == "attention"
    ]
    return {
        "tier": tier,
        "summary": summary,
        "g6_version": G6_VERSION,
        "ws_fills": n_fills,
        "grades_attention": len(attention_on),
        "grades_good": sum(1 for g in grades if g.get("grade") == "good"),
        "attention_on": attention_on,
        "gate_pass": tier not in ("hold", "halted", "paper", "warming_up", "unknown"),
    }


def build_g6_report(
    *,
    runtime_path: Path = Path("logs/runtime_state.json"),
    logs_dir: Path = Path("logs"),
    criteria: Optional[G6Criteria] = None,
) -> G6Report:
    crit = criteria or G6Criteria()
    rt = _load_runtime(runtime_path)
    pm = build_performance_metrics(runtime=rt, logs_dir=logs_dir)
    intel_rows = tail_intel_records(limit=2000, path=logs_dir / "intel_decisions.jsonl")

    from experimental.ws_feed.pure_quote_path import current_ws_as_version

    cap = pm.get("capture") or {}
    grades = pm.get("grades") or []
    n_fills = int(cap.get("ws_fills") or 0)
    tier, summary = resolve_activation_tier(
        grades=grades,
        n_fills=n_fills,
        runtime=rt,
        criteria=crit,
        capture=cap,
    )

    failures: List[str] = []
    if crit.require_live and bool(rt.get("dry_run")):
        failures.append("dry_run=true — live activation grading requires dry_run=false")
    if crit.require_kill_clear and bool(rt.get("kill_switch_active")):
        failures.append("kill_switch_active — clear kill before activation gate")
    if tier in ("hold", "halted", "paper"):
        failures.append(f"activation_tier={tier}: {summary}")
    if n_fills < crit.min_fills_pilot:
        failures.append(f"ws_fills {n_fills} < min {crit.min_fills_pilot} for pilot")

    return G6Report(
        generated_utc=datetime.now(timezone.utc).isoformat(),
        ws_as_version=current_ws_as_version(),
        activation_tier=tier,
        activation_summary=summary,
        passed=not failures,
        failures=failures,
        portfolio=_portfolio_block(rt, cap),
        structural_signals=_structural_signals_block(intel_rows),
        performance_metrics=pm,
        criteria=asdict(crit),
    )


def format_g6_report(report: G6Report) -> str:
    lines = [
        f"G6 live activation grade (v{report.g6_version}) · ws-engine v{report.ws_as_version}",
        f"tier: {report.activation_tier}",
        f"summary: {report.activation_summary}",
        f"PASS: {report.passed}",
    ]
    if report.failures:
        lines.append("Failures:")
        lines.extend(f"  - {f}" for f in report.failures)

    p = report.portfolio
    lines.append("\nPortfolio (§7.2 — from fills + runtime)")
    for key in (
        "portfolio_xrp_equiv",
        "session_baseline_xrp_equiv",
        "session_mtm_drift_xrp",
        "session_balance_pnl_xrp",
        "fill_capture_xrp",
        "inventory_xrp_pct",
        "inventory_label",
    ):
        if p.get(key) is not None:
            lines.append(f"  {key}: {p[key]}")

    cap = report.performance_metrics.get("capture") or {}
    lines.append("\nSpread capture (§7.1)")
    lines.append(
        f"  ws_fills: {cap.get('ws_fills')} | pos: {cap.get('positive_capture_pct')}%"
        f" | avg bps: {cap.get('avg_capture_bps')} | total: {cap.get('total_capture_xrp')} XRP"
    )

    lines.append("\n§7 grades")
    for g in report.performance_metrics.get("grades") or []:
        lines.append(f"  [{g.get('grade')}] {g.get('label')}: {g.get('value')}")

    sig = report.structural_signals
    lines.append("\nStructural signals (§7.4 — intel cycles)")
    lines.append(f"  cycle_rows: {sig.get('cycle_rows')}")
    if sig.get("g2_active_pct") is not None:
        lines.append(
            f"  g2_active: {sig.get('g2_active_pct')}% | g4_active: {sig.get('g4_active_pct')}%"
            f" | would_quote: {sig.get('would_quote_pct')}%"
        )
        lines.append(f"  g2_grades: {sig.get('g2_grades')}")
        lines.append(f"  g4_grades: {sig.get('g4_grades')}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="G6 live activation grading (Phase E §7)")
    parser.add_argument("--runtime", default="logs/runtime_state.json")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--out", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--gate", action="store_true", help="Exit 1 if activation gate fails")
    parser.add_argument("--allow-paper", action="store_true", help="Grade even when dry_run=true")
    args = parser.parse_args()

    criteria = G6Criteria(require_live=not args.allow_paper)
    report = build_g6_report(
        runtime_path=Path(args.runtime),
        logs_dir=Path(args.logs_dir),
        criteria=criteria,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")

    print(format_g6_report(report))
    print(f"\nWrote {out_path}")
    if args.gate and not report.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
