"""
D4 — Swap readiness report: sacred replay + economics + live soak + wiring parity.

Bundles evidence for wholesale VPS swap (E1) sign-off:
- replay_long_run wiring parity on sacred corpus (presence lift vs hard gate)
- sacred_economics baseline + marginal oracle
- C2 live soak gate (best passing ws_as_demo_runtime snapshot)
- WS runtime wiring parity (PureQuotePath export fields, D2 dry-run)

Run:
  python -m experimental.swap_readiness_report
  python -m experimental.swap_readiness_report --json --gate
  python -m experimental.ws_feed.replay_long_run --swap-readiness
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from experimental.pure_as_quote_path import make_would_quote_fn, would_quote_pure
from experimental.sacred_economics import (
    compute_baseline_economics,
    compute_marginal_economics,
    format_economics_ab_report,
    format_economics_report,
    load_decision_lines,
    load_trades_rows,
    resolve_trades_path,
    run_economics_ab,
)
from experimental.ws_runtime_analysis import SoakEvaluation, evaluate_soak_gate
from strategy.avellaneda_strategy import AvellanedaStrategy

# Runtime fields the WS lab must export for operator/GUI parity (WS_HANDOFF).
WIRING_PARITY_REQUIRED_KEYS: Tuple[str, ...] = (
    "as_mode",
    "ws_as_version",
    "quote_decision_summary",
    "quote_intents",
    "as_reservation",
    "as_optimal_spread_pct",
    "market_edge_met",
    "zero_quote_reason",
    "ws_book_age_s",
    "ws_message_count",
    "competitor_pressure",
    "inventory_label",
    "dry_run_execution",
    "open_offers",
)

# D4 gate defaults — operator sign-off bar before E1.
DEFAULT_MIN_REPLAY_PURE_PRESENCE_PCT = 50.0
DEFAULT_MIN_PRESENCE_LIFT_PP = 15.0
DEFAULT_MIN_REPLAY_SNAPSHOTS = 100


@dataclass
class SwapReadinessCriteria:
    min_replay_pure_presence_pct: float = DEFAULT_MIN_REPLAY_PURE_PRESENCE_PCT
    min_presence_lift_pp: float = DEFAULT_MIN_PRESENCE_LIFT_PP
    min_replay_snapshots: int = DEFAULT_MIN_REPLAY_SNAPSHOTS
    require_soak_pass: bool = True
    require_wiring_parity: bool = True
    require_dry_run: bool = True


@dataclass
class SwapReadinessReport:
    generated_utc: str = ""
    decisions_path: str = ""
    trades_path: str = ""
    ws_runtime_path: str = ""
    replay: Dict[str, Any] = field(default_factory=dict)
    presence: Dict[str, Any] = field(default_factory=dict)
    economics: Dict[str, Any] = field(default_factory=dict)
    economics_ab: Dict[str, Any] = field(default_factory=dict)
    soak: Dict[str, Any] = field(default_factory=dict)
    wiring_parity: Dict[str, Any] = field(default_factory=dict)
    dry_run: Dict[str, Any] = field(default_factory=dict)
    criteria: Dict[str, Any] = field(default_factory=dict)
    passed: bool = False
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def check_wiring_parity(runtime: Dict[str, Any]) -> Dict[str, Any]:
    missing = [k for k in WIRING_PARITY_REQUIRED_KEYS if k not in runtime or runtime[k] in (None, "", [])]
    intents = runtime.get("quote_intents") or []
    has_active_l1 = any(
        i.get("level") == 1 and i.get("active") for i in intents if isinstance(i, dict)
    )
    return {
        "passed": len(missing) == 0,
        "missing_keys": missing,
        "present_count": len(WIRING_PARITY_REQUIRED_KEYS) - len(missing),
        "required_count": len(WIRING_PARITY_REQUIRED_KEYS),
        "has_active_l1_intents": has_active_l1,
        "ws_as_version": runtime.get("ws_as_version"),
        "dry_run_enabled": bool(runtime.get("dry_run", runtime.get("dry_run_execution"))),
    }


def _presence_from_decisions(lines: Sequence[str], as_strat: AvellanedaStrategy) -> Dict[str, Any]:
    baseline = 0
    zero_quote = 0
    hard_gate_blocks = 0
    pure_presence = 0
    total = len(lines)

    for ln in lines:
        reasons = ""
        try:
            d = json.loads(ln)
            for e in d.get("events", []):
                reasons += " " + (e.get("message") or "")
        except json.JSONDecodeError:
            reasons = ln

        gen = 0
        m = re.search(r"Generated\s+(\d+)", reasons, re.I)
        if m:
            gen = int(m.group(1))
        if gen > 0:
            baseline += 1
        else:
            zero_quote += 1
            low = reasons.lower()
            if any(k in low for k in ("market_edge_met=false", "hard gate", "l1 too tight", "edge thin")):
                hard_gate_blocks += 1

        if would_quote_pure(as_strat, ln if ln.strip().startswith("{") else json.dumps({"events": [{"message": ln}]})):
            pure_presence += 1

    baseline_pct = round(100.0 * baseline / total, 1) if total else 0.0
    pure_pct = round(100.0 * pure_presence / total, 1) if total else 0.0
    return {
        "decision_lines": total,
        "baseline_presence_pct": baseline_pct,
        "baseline_presence_count": baseline,
        "zero_quote_count": zero_quote,
        "hard_gate_blocks": hard_gate_blocks,
        "pure_presence_pct": pure_pct,
        "pure_presence_count": pure_presence,
        "presence_lift_pp": round(pure_pct - baseline_pct, 1),
    }


def find_best_soak_pass(logs_dir: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return best passing C2 soak evaluation and source filename."""
    candidates: List[Tuple[float, str, SoakEvaluation]] = []
    paths = sorted(logs_dir.glob("ws_as_demo_runtime*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        hist = data.get("sample_history") or []
        if not hist:
            continue
        ev = evaluate_soak_gate(hist)
        if ev.passed:
            duration = float(ev.metrics.get("session_duration_minutes") or 0)
            candidates.append((duration, path.name, ev))

    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0]
    return {**best[2].as_dict(), "source_file": best[1]}, best[1]


def build_swap_readiness_report(
    *,
    decisions_path: Path,
    trades_path: Optional[Path] = None,
    ws_runtime_path: Optional[Path] = None,
    logs_dir: Optional[Path] = None,
    profile: str = "tight_spread",
    criteria: Optional[SwapReadinessCriteria] = None,
    include_economics_ab: bool = True,
) -> SwapReadinessReport:
    from datetime import datetime, timezone

    crit = criteria or SwapReadinessCriteria()
    logs = logs_dir or Path("logs")
    decisions_path = Path(decisions_path)
    ws_runtime_path = Path(ws_runtime_path or logs / "ws_as_demo_runtime.json")
    trades_file = trades_path or resolve_trades_path(logs)

    report = SwapReadinessReport(
        generated_utc=datetime.now(timezone.utc).isoformat(),
        decisions_path=str(decisions_path),
        trades_path=str(trades_file) if trades_file else "",
        ws_runtime_path=str(ws_runtime_path),
        criteria=asdict(crit),
    )

    # --- Sacred replay (wiring parity harness) ---
    if decisions_path.exists():
        from experimental.ws_feed.replay_long_run import replay

        replay_out = replay(
            decisions_path,
            profile=profile,
            simulate_ws_freshness=True,
            as_mode="pure",
        )
        report.replay = replay_out.get("summary", {})
        lines = load_decision_lines(decisions_path)
        as_strat = AvellanedaStrategy(None)
        report.presence = _presence_from_decisions(lines, as_strat)
    else:
        report.failures.append(f"decisions file missing: {decisions_path}")
        report.warnings.append("replay skipped — no decisions.jsonl")

    # --- Economics ---
    if trades_file and trades_file.exists():
        trades_rows = load_trades_rows(trades_file)
        baseline_eco = compute_baseline_economics(trades_rows, trades_path=str(trades_file))
        report.economics["baseline"] = baseline_eco.as_dict()
        if decisions_path.exists():
            lines = load_decision_lines(decisions_path)
            as_strat = AvellanedaStrategy(None)
            marginal = compute_marginal_economics(
                lines,
                trades_rows,
                lambda line: would_quote_pure(as_strat, line),
                baseline_capture_xrp=baseline_eco.capture_xrp,
            )
            report.economics["marginal"] = marginal.as_dict()
            if include_economics_ab:
                ab = run_economics_ab(
                    lines,
                    trades_rows,
                    [
                        ("pure A-S", make_would_quote_fn(as_strat, "pure")),
                        ("pure + pressure 0.25", make_would_quote_fn(as_strat, "pressure", 0.25)),
                        ("pure + pressure 0.50", make_would_quote_fn(as_strat, "pressure", 0.50)),
                        ("pure + pressure 0.85", make_would_quote_fn(as_strat, "pressure", 0.85)),
                    ],
                    trades_path=str(trades_file),
                )
                report.economics_ab = ab.as_dict()
    else:
        report.warnings.append("economics skipped — no trades CSV in logs/")

    # --- Live soak (C2) ---
    soak_dict, soak_source = find_best_soak_pass(logs)
    if soak_dict:
        report.soak = soak_dict
    else:
        report.warnings.append(
            "no passing C2 soak snapshot found in logs/ws_as_demo_runtime*.json "
            "(run live_pure_as_tester ≥30 min)"
        )
        if ws_runtime_path.exists():
            try:
                data = json.loads(ws_runtime_path.read_text(encoding="utf-8"))
                hist = data.get("sample_history") or []
                if hist:
                    latest = evaluate_soak_gate(hist).as_dict()
                    latest["source_file"] = ws_runtime_path.name
                    report.soak = latest
            except (OSError, json.JSONDecodeError):
                pass

    # --- Wiring parity + D2 dry-run ---
    if ws_runtime_path.exists():
        try:
            ws_rt = json.loads(ws_runtime_path.read_text(encoding="utf-8"))
            report.wiring_parity = check_wiring_parity(ws_rt)
            dry = ws_rt.get("dry_run_execution") or {}
            report.dry_run = {
                "enabled": bool(ws_rt.get("dry_run", dry)),
                "open_offers_count": ws_rt.get("open_offers_count"),
                "last_summary": ws_rt.get("last_execution_summary") or dry.get("summary"),
                "cycle": dry.get("cycle"),
            }
        except (OSError, json.JSONDecodeError) as exc:
            report.warnings.append(f"ws runtime unreadable: {exc}")
    else:
        report.warnings.append(f"ws runtime missing: {ws_runtime_path}")

    # --- Gate ---
    failures: List[str] = list(report.failures)
    replay_snaps = int(report.replay.get("total_historical_book_snapshots") or 0)
    if replay_snaps < crit.min_replay_snapshots:
        failures.append(f"replay snapshots {replay_snaps} < min {crit.min_replay_snapshots}")

    pure_pct = float(report.presence.get("pure_presence_pct") or report.replay.get("as_presence_pct") or 0)
    if pure_pct < crit.min_replay_pure_presence_pct:
        failures.append(
            f"replay pure presence {pure_pct:.1f}% < min {crit.min_replay_pure_presence_pct:.0f}%"
        )

    lift = float(report.presence.get("presence_lift_pp") or 0)
    if lift < crit.min_presence_lift_pp:
        failures.append(f"presence lift {lift:+.1f}pp < min {crit.min_presence_lift_pp:.0f}pp")

    if crit.require_soak_pass and not report.soak.get("passed"):
        soak_fail = report.soak.get("failures") or ["no passing soak"]
        failures.append(f"live soak: {soak_fail[0]}")

    if crit.require_wiring_parity and not report.wiring_parity.get("passed", False):
        missing = report.wiring_parity.get("missing_keys") or ["unknown"]
        failures.append(f"wiring parity missing: {', '.join(missing[:5])}")

    if crit.require_dry_run and not report.dry_run.get("enabled"):
        failures.append("D2 dry-run not present in ws runtime export")

    report.failures = failures
    report.passed = len(failures) == 0
    return report


def format_swap_readiness_report(report: SwapReadinessReport) -> str:
    lines: List[str] = [
        "=== D4 SWAP READINESS REPORT ===",
        f"Generated: {report.generated_utc}",
        f"Decisions: {report.decisions_path}",
        f"Trades:    {report.trades_path or '(none)'}",
        f"WS runtime: {report.ws_runtime_path}",
        "",
        "--- Sacred replay (wiring parity harness) ---",
    ]
    for key in (
        "total_historical_book_snapshots",
        "as_presence_pct",
        "historical_zero_quote_due_to_edge",
        "would_have_had_edge_with_simulated_ws",
        "flip_rate_pct",
    ):
        if key in report.replay:
            lines.append(f"  {key}: {report.replay[key]}")

    lines.extend(
        [
            "",
            "--- Presence (decision corpus) ---",
            f"  Baseline (hard gate): {report.presence.get('baseline_presence_pct')}% "
            f"({report.presence.get('baseline_presence_count')} / {report.presence.get('decision_lines')})",
            f"  WS + pure A-S:        {report.presence.get('pure_presence_pct')}% "
            f"({report.presence.get('pure_presence_count')} / {report.presence.get('decision_lines')})",
            f"  Lift:                 {(report.presence.get('presence_lift_pp') if report.presence.get('presence_lift_pp') is not None else 0):+} pp",
            f"  Hard-gate blocks:     {report.presence.get('hard_gate_blocks')}",
        ]
    )

    base = report.economics.get("baseline") or {}
    marg = report.economics.get("marginal") or {}
    if base:
        lines.extend(
            [
                "",
                "--- Sacred economics ---",
                f"  Baseline fills: {base.get('fill_count')}  capture_xrp: {base.get('capture_xrp')}  "
                f"neg_fill_pct: {base.get('neg_fill_pct')}%",
            ]
        )
    if marg:
        lines.append(
            f"  Marginal oracle: marginal_fills={marg.get('marginal_fill_count')}  "
            f"marginal_capture_xrp={marg.get('marginal_capture_xrp')}  "
            f"projected_upper_bound={marg.get('projected_capture_upper_bound')}"
        )

    lines.append("")
    lines.append("--- Live soak (C2) ---")
    if report.soak:
        lines.append(f"  Source: {report.soak.get('source_file', 'n/a')}")
        lines.append(f"  Passed: {'YES' if report.soak.get('passed') else 'NO'}")
        m = report.soak.get("metrics") or {}
        lines.append(
            f"  Duration: {m.get('session_duration_minutes')}m  samples: {m.get('sample_count')}  "
            f"presence: {m.get('presence_pct')}%  ws_age mean: {m.get('ws_age_mean_s')}s"
        )
        if report.soak.get("failures"):
            lines.append(f"  Failures: {report.soak['failures']}")
    else:
        lines.append("  (no soak data)")

    lines.extend(
        [
            "",
            "--- Wiring parity (WS runtime export) ---",
            f"  Passed: {'YES' if report.wiring_parity.get('passed') else 'NO'}",
            f"  Fields: {report.wiring_parity.get('present_count')}/"
            f"{report.wiring_parity.get('required_count')}",
        ]
    )
    if report.wiring_parity.get("missing_keys"):
        lines.append(f"  Missing: {report.wiring_parity['missing_keys']}")

    lines.extend(
        [
            "",
            "--- D2 dry-run ---",
            f"  Enabled: {report.dry_run.get('enabled')}",
            f"  Open offers: {report.dry_run.get('open_offers_count')}",
            f"  Last: {report.dry_run.get('last_summary', '—')}",
        ]
    )

    lines.append("")
    lines.append("=== GATE ===")
    if report.passed:
        lines.append("PASS — ready for operator review (E1 still requires explicit sign-off)")
    else:
        lines.append("FAIL")
        for f in report.failures:
            lines.append(f"  - {f}")

    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in report.warnings:
            lines.append(f"  - {w}")

    if report.economics_ab:
        lines.append("")
        lines.append("--- Economics A/B (summary) ---")
        for row in report.economics_ab.get("variants") or []:
            marg = row.get("marginal") or {}
            lines.append(
                f"  {row.get('label')}: presence={row.get('presence_pct')}%  "
                f"marginal_capture_xrp={marg.get('marginal_capture_xrp')}"
            )

    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="D4 swap readiness report (replay + economics + soak + wiring)")
    p.add_argument("--decisions", default="logs/decisions.jsonl")
    p.add_argument("--trades", default=None)
    p.add_argument("--ws-runtime", default="logs/ws_as_demo_runtime.json")
    p.add_argument("--profile", default="tight_spread")
    p.add_argument("--json", action="store_true", help="Print JSON to stdout")
    p.add_argument("--output", default=None, help="Write JSON report to path (default: logs/swap_readiness_report.json)")
    p.add_argument("--gate", action="store_true", help="Exit 1 if gate fails")
    p.add_argument("--no-ab", action="store_true", help="Skip economics A/B scenarios")
    p.add_argument("--no-soak-required", action="store_true", help="Do not require C2 soak pass")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    criteria = SwapReadinessCriteria(require_soak_pass=not args.no_soak_required)
    report = build_swap_readiness_report(
        decisions_path=Path(args.decisions),
        trades_path=Path(args.trades) if args.trades else None,
        ws_runtime_path=Path(args.ws_runtime),
        profile=args.profile,
        criteria=criteria,
        include_economics_ab=not args.no_ab,
    )

    out_path = Path(args.output) if args.output else Path("logs/swap_readiness_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_swap_readiness_report(report))
        print(f"\nWrote {out_path}")

    if args.gate and not report.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
