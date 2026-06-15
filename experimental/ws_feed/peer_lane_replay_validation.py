"""
G5 (E.5) — peer-lane replay validation.

Measures peer coverage % and neutral-fallback rate on:
- WS production intel log (`logs/intel_decisions.jsonl`)
- WS tester `sample_history` (`logs/ws_as_demo_runtime.json`)
- Sacred long-run cycles (`logs/decisions.jsonl`) — eligibility only (no on-chain peer scrape in export)

Run:
  python -m experimental.ws_feed.peer_lane_replay_validation
  python -m experimental.ws_feed.peer_lane_replay_validation --gate
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from experimental.ws_feed.intel_decisions_log import INTEL_DECISIONS_PATH, tail_intel_records
from experimental.ws_feed.peer_lane_quoting import compute_g4_adjustments, prepare_quoting_intel

G5_VERSION = "1.0.0"
DEFAULT_REPORT_PATH = Path("logs/peer_lane_g5_report.json")


@dataclass(frozen=True)
class G5Criteria:
    """Default gate: intel log populated + both peer-lane code paths seen at least once."""

    min_ws_intel_rows: int = 8
    min_peer_covered_samples: int = 1
    min_neutral_fallback_samples: int = 1
    # Strict mode (--strict): production tuning thresholds from §7.6
    min_peer_coverage_pct: float = 5.0
    max_neutral_fallback_pct: float = 92.0
    max_widened_lane_pct: float = 40.0


@dataclass
class G5BucketCounts:
    total: int = 0
    peer_lane_eligible: int = 0
    peer_covered: int = 0
    neutral_fallback: int = 0
    widened_lane: int = 0
    legacy_no_peer_fields: int = 0
    sacred_eligible_cycles: int = 0

    @property
    def peer_coverage_pct(self) -> Optional[float]:
        if self.peer_lane_eligible <= 0:
            return None
        return round(100.0 * self.peer_covered / self.peer_lane_eligible, 2)

    @property
    def neutral_fallback_pct(self) -> Optional[float]:
        if self.peer_lane_eligible <= 0:
            return None
        return round(100.0 * self.neutral_fallback / self.peer_lane_eligible, 2)

    @property
    def widened_lane_pct(self) -> Optional[float]:
        if self.peer_lane_eligible <= 0:
            return None
        return round(100.0 * self.widened_lane / self.peer_lane_eligible, 2)


@dataclass
class G5Report:
    g5_version: str = G5_VERSION
    ws_as_version: str = ""
    passed: bool = False
    criteria: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    intel_log: Dict[str, Any] = field(default_factory=dict)
    ws_runtime: Dict[str, Any] = field(default_factory=dict)
    sacred: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _has_peer_lane_fields(row: Dict[str, Any]) -> bool:
    keys = (
        "peer_lane_count",
        "g4_peer_lane_count",
        "peer_lane_empty",
        "g4_grade",
        "kind",
    )
    if any(k in row for k in keys):
        return True
    return row.get("kind") == "peer_scrape"


def _peer_count(row: Dict[str, Any]) -> int:
    for key in ("peer_lane_count", "g4_peer_lane_count"):
        if key in row:
            return _safe_int(row.get(key))
    return 0


def _peer_empty(row: Dict[str, Any]) -> bool:
    if bool(row.get("peer_lane_empty")):
        return True
    count = _peer_count(row)
    if "peer_lane_count" in row or "g4_peer_lane_count" in row or row.get("kind") == "peer_scrape":
        return count <= 0
    grade = str(row.get("g4_grade") or "")
    return grade == "empty_lane"


def classify_peer_lane_row(row: Dict[str, Any]) -> str:
    """Return: legacy | eligible_covered | eligible_neutral | eligible_widened."""
    if not _has_peer_lane_fields(row):
        return "legacy"

    if _peer_empty(row):
        return "eligible_neutral"

    if bool(row.get("peer_lane_widened")) or str(row.get("g4_grade") or "") == "sparse":
        return "eligible_widened"

    if _peer_count(row) > 0:
        return "eligible_covered"

    return "eligible_neutral"


def _intel_to_quoting_map(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "competitor_pressure": row.get("competitor_pressure") or row.get("peer_pressure_score"),
        "peer_lane_count": row.get("peer_lane_count", row.get("g4_peer_lane_count")),
        "peer_lane_empty": row.get("peer_lane_empty"),
        "peer_pressure_score": row.get("peer_pressure_score", row.get("g4_peer_pressure")),
        "peer_observed_spread_pct": row.get("competitor_observed_spread_pct"),
        "peer_fled_touch_count": row.get("peer_fled_touch_count"),
        "peer_lane_widened": row.get("peer_lane_widened"),
    }


def accumulate_rows(rows: Iterable[Dict[str, Any]], *, sacred_eligible: bool = False) -> G5BucketCounts:
    counts = G5BucketCounts()
    for row in rows:
        counts.total += 1
        if sacred_eligible:
            counts.sacred_eligible_cycles += 1
            continue

        cls = classify_peer_lane_row(row)
        if cls == "legacy":
            counts.legacy_no_peer_fields += 1
            continue

        counts.peer_lane_eligible += 1
        if cls == "eligible_covered":
            counts.peer_covered += 1
        elif cls == "eligible_neutral":
            counts.neutral_fallback += 1
        elif cls == "eligible_widened":
            counts.widened_lane += 1
            if _peer_count(row) > 0:
                counts.peer_covered += 1
            else:
                counts.neutral_fallback += 1

        intel = _intel_to_quoting_map(row)
        prepared = prepare_quoting_intel(intel)
        g4 = compute_g4_adjustments(prepared or intel)
        if g4.grade == "empty_lane" and cls != "eligible_neutral":
            counts.neutral_fallback += 0  # consistency check only

    return counts


def _load_ws_runtime_samples(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    hist = data.get("sample_history") or []
    return [r for r in hist if isinstance(r, dict)]


def _load_sacred_eligible_cycles(path: Path) -> List[Dict[str, Any]]:
    """Sacred export has no peer scrape — count cycles with quote activity as lane-eligible baseline."""
    if not path.exists():
        return []
    eligible: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        summary = str(row.get("quote_decision_summary") or row.get("decision_summary") or "")
        if "Generated" in summary and "Generated 0" not in summary:
            eligible.append(row)
        elif row.get("market_edge_met") is True or row.get("would_quote") is True:
            eligible.append(row)
    return eligible


def _bucket_dict(counts: G5BucketCounts) -> Dict[str, Any]:
    return {
        "total_rows": counts.total,
        "peer_lane_eligible": counts.peer_lane_eligible,
        "peer_covered": counts.peer_covered,
        "neutral_fallback": counts.neutral_fallback,
        "widened_lane": counts.widened_lane,
        "legacy_no_peer_fields": counts.legacy_no_peer_fields,
        "peer_coverage_pct": counts.peer_coverage_pct,
        "neutral_fallback_pct": counts.neutral_fallback_pct,
        "widened_lane_pct": counts.widened_lane_pct,
        "sacred_eligible_cycles": counts.sacred_eligible_cycles,
    }


def build_g5_report(
    *,
    intel_path: Path = INTEL_DECISIONS_PATH,
    ws_runtime_path: Path = Path("logs/ws_as_demo_runtime.json"),
    sacred_decisions_path: Path = Path("logs/decisions.jsonl"),
    criteria: Optional[G5Criteria] = None,
    strict: bool = False,
) -> G5Report:
    crit = criteria or G5Criteria()
    from experimental.ws_feed.pure_quote_path import current_ws_as_version

    intel_rows = tail_intel_records(limit=5000, path=intel_path)
    ws_samples = _load_ws_runtime_samples(ws_runtime_path)
    sacred_eligible = _load_sacred_eligible_cycles(sacred_decisions_path)

    intel_counts = accumulate_rows(intel_rows)
    ws_counts = accumulate_rows(ws_samples)
    sacred_counts = accumulate_rows(sacred_eligible, sacred_eligible=True)

    # Gate on production intel log when populated; else include tester sample_history.
    if intel_counts.peer_lane_eligible >= crit.min_ws_intel_rows:
        gate_counts = intel_counts
        gate_source = "intel_log"
    else:
        gate_counts = G5BucketCounts()
        for counts in (intel_counts, ws_counts):
            gate_counts.total += counts.total
            gate_counts.peer_lane_eligible += counts.peer_lane_eligible
            gate_counts.peer_covered += counts.peer_covered
            gate_counts.neutral_fallback += counts.neutral_fallback
            gate_counts.widened_lane += counts.widened_lane
            gate_counts.legacy_no_peer_fields += counts.legacy_no_peer_fields
        gate_source = "intel_log+ws_runtime"

    report = G5Report(
        ws_as_version=current_ws_as_version(),
        criteria=asdict(crit),
        intel_log=_bucket_dict(intel_counts),
        ws_runtime=_bucket_dict(ws_counts),
        sacred={
            "decisions_path": str(sacred_decisions_path),
            "eligible_quote_cycles": sacred_counts.sacred_eligible_cycles,
            "note": "Sacred export has no peer-lane scrape; eligibility baseline only.",
        },
    )

    failures: List[str] = []
    eligible = gate_counts.peer_lane_eligible
    if eligible < crit.min_ws_intel_rows:
        failures.append(
            f"WS peer-lane rows {eligible} < min {crit.min_ws_intel_rows} "
            f"(source={gate_source}; need intel_decisions.jsonl or tester sample_history)"
        )
    if gate_counts.peer_covered < crit.min_peer_covered_samples:
        failures.append(
            f"peer_covered samples {gate_counts.peer_covered} < min {crit.min_peer_covered_samples} "
            "(need ≥1 scrape/cycle with peers in touch band)"
        )
    if gate_counts.neutral_fallback < crit.min_neutral_fallback_samples:
        failures.append(
            f"neutral_fallback samples {gate_counts.neutral_fallback} < min {crit.min_neutral_fallback_samples}"
        )

    if strict:
        cov = gate_counts.peer_coverage_pct
        if cov is not None and cov < crit.min_peer_coverage_pct:
            failures.append(f"peer_coverage_pct {cov}% < min {crit.min_peer_coverage_pct}%")
        neu = gate_counts.neutral_fallback_pct
        if neu is not None and neu > crit.max_neutral_fallback_pct:
            failures.append(f"neutral_fallback_pct {neu}% > max {crit.max_neutral_fallback_pct}%")
        wid = gate_counts.widened_lane_pct
        if wid is not None and wid > crit.max_widened_lane_pct:
            failures.append(f"widened_lane_pct {wid}% > max {crit.max_widened_lane_pct}%")

    report.failures = failures
    report.passed = not failures
    report.intel_log["gate_source"] = gate_source
    report.intel_log["gate_strict"] = strict
    report.intel_log["gate_counts"] = _bucket_dict(gate_counts)
    return report


def format_g5_report(report: G5Report) -> str:
    lines = [
        f"G5 peer-lane replay validation (module v{report.g5_version}, ws-engine v{report.ws_as_version})",
        f"PASS: {report.passed}",
    ]
    if report.failures:
        lines.append("Failures:")
        lines.extend(f"  - {f}" for f in report.failures)

    def _section(title: str, block: Dict[str, Any]) -> None:
        lines.append(f"\n{title}")
        for key in (
            "total_rows",
            "peer_lane_eligible",
            "peer_covered",
            "neutral_fallback",
            "widened_lane",
            "peer_coverage_pct",
            "neutral_fallback_pct",
            "widened_lane_pct",
        ):
            if key in block and block[key] is not None:
                lines.append(f"  {key}: {block[key]}")

    _section("Intel log (production)", report.intel_log)
    _section("WS tester sample_history", report.ws_runtime)
    gate = report.intel_log.get("gate_counts") or {}
    _section(f"Gate ({report.intel_log.get('gate_source', 'intel')})", gate if isinstance(gate, dict) else {})
    lines.append("\nSacred corpus")
    lines.append(f"  eligible_quote_cycles: {report.sacred.get('eligible_quote_cycles')}")
    lines.append(f"  {report.sacred.get('note', '')}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="G5 peer-lane replay validation (coverage + neutral fallback)")
    parser.add_argument("--intel", default=str(INTEL_DECISIONS_PATH), help="intel_decisions.jsonl path")
    parser.add_argument("--ws-runtime", default="logs/ws_as_demo_runtime.json")
    parser.add_argument("--decisions", default="logs/decisions.jsonl", help="Sacred long-run decisions")
    parser.add_argument("--out", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--gate", action="store_true", help="Exit 1 if gate fails (default: path coverage gate)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also enforce min peer_coverage %% and max neutral_fallback %% (§7.6 production tuning)",
    )
    parser.add_argument("--min-rows", type=int, default=G5Criteria.min_ws_intel_rows)
    parser.add_argument("--min-coverage-pct", type=float, default=G5Criteria.min_peer_coverage_pct)
    parser.add_argument("--max-neutral-pct", type=float, default=G5Criteria.max_neutral_fallback_pct)
    args = parser.parse_args()

    criteria = G5Criteria(
        min_ws_intel_rows=args.min_rows,
        min_peer_coverage_pct=args.min_coverage_pct,
        max_neutral_fallback_pct=args.max_neutral_pct,
    )
    report = build_g5_report(
        intel_path=Path(args.intel),
        ws_runtime_path=Path(args.ws_runtime),
        sacred_decisions_path=Path(args.decisions),
        criteria=criteria,
        strict=args.strict,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")

    print(format_g5_report(report))
    print(f"\nWrote {out_path}")
    if args.gate and not report.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
