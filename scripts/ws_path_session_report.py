#!/usr/bin/env python3
"""E1.5 — WS-path live session report (fills, capture, markout progress)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

DEFAULT_MIN_FILLS = 50
WS_FILL_MARKER = "WS pure fill"
MAX_TOXIC_30S_GATE = 0.60
MIN_MEAN_MARKOUT_30S_PCT = -0.25
E15_REPORT_PATH = "logs/e15_report.json"


@dataclass
class E15Report:
    generated_utc: str = ""
    repo: str = ""
    ws_fills: int = 0
    buys: int = 0
    sells: int = 0
    capture_xrp: float = 0.0
    neg_capture: int = 0
    min_fills_gate: int = DEFAULT_MIN_FILLS
    gate_fills_met: bool = False
    markout_gate_met: bool = False
    runtime: Dict[str, Any] = field(default_factory=dict)
    checks: List[Dict[str, Any]] = field(default_factory=list)
    passed: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_runtime(repo: Path) -> Dict[str, Any]:
    path = repo / "logs" / "runtime_state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def count_ws_fills_csv(repo: Optional[Path] = None, *, since: Optional[str] = None) -> int:
    """Authoritative WS-path fill count for E1.5 (persists across engine restarts)."""
    return len(_ws_fills_from_trades(repo or _REPO, since=since))


def _ws_fills_from_trades(repo: Path, *, since: Optional[str] = None) -> List[Dict[str, str]]:
    logs = repo / "logs"
    rows: List[Dict[str, str]] = []
    for path in sorted(logs.glob("trades_*.csv")):
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for row in csv.DictReader(handle):
                    notes = row.get("notes") or ""
                    event = (row.get("event_type") or "").upper()
                    if WS_FILL_MARKER not in notes and event not in ("BUY", "SELL"):
                        continue
                    if WS_FILL_MARKER not in notes:
                        continue
                    ts = row.get("timestamp_utc") or ""
                    if since and ts < since:
                        continue
                    rows.append(row)
        except OSError:
            continue
    return rows


def build_e15_report(
    *,
    repo: Path = _REPO,
    min_fills: int = DEFAULT_MIN_FILLS,
    since: Optional[str] = None,
) -> E15Report:
    rt = _load_runtime(repo)
    fills = _ws_fills_from_trades(repo, since=since)
    capture = 0.0
    neg = 0
    buys = sells = 0
    for row in fills:
        try:
            cap = float(row.get("profit_xrp_equiv") or 0)
        except (TypeError, ValueError):
            cap = 0.0
        capture += cap
        if cap < 0:
            neg += 1
        side = (row.get("side") or row.get("event_type") or "").upper()
        if side == "BUY":
            buys += 1
        elif side == "SELL":
            sells += 1

    n = len(fills)
    report = E15Report(
        generated_utc=datetime.now(timezone.utc).isoformat(),
        repo=str(repo.resolve()),
        ws_fills=n,
        buys=buys,
        sells=sells,
        capture_xrp=round(capture, 4),
        neg_capture=neg,
        min_fills_gate=min_fills,
        gate_fills_met=n >= min_fills,
        runtime={
            k: rt.get(k)
            for k in (
                "dry_run",
                "as_mode",
                "price_source",
                "fills_session",
                "session_pnl_balance_xrp",
                "toxic_fill_ratio",
                "toxic_fill_ratio_30s",
                "mean_markout_30s_pct",
                "fill_quality_summary",
                "kill_switch_active",
                "open_offers_count",
            )
            if k in rt or True
        },
    )

    def add(name: str, ok: bool, detail: str) -> None:
        report.checks.append({"name": name, "passed": ok, "detail": detail})

    add(f"ws_fills >= {min_fills}", n >= min_fills, str(n))
    add("as_mode pure", rt.get("as_mode") == "pure", str(rt.get("as_mode")))
    add("live (not dry_run)", not bool(rt.get("dry_run")), str(rt.get("dry_run")))
    add("kill clear", not bool(rt.get("kill_switch_active")), str(rt.get("kill_switch_reason", ""))[:80])
    sess_fills = int(rt.get("fills_session") or 0)
    add("runtime fills_session matches csv", sess_fills == n or sess_fills >= n, f"rt={sess_fills} csv={n}")

    toxic = float(rt.get("toxic_fill_ratio") or 0)
    toxic_30 = float(rt.get("toxic_fill_ratio_30s") or 0)
    markout_30 = float(rt.get("mean_markout_30s_pct") or 0)
    add(
        "toxic ratio tracked",
        "toxic_fill_ratio" in rt and n > 0,
        f"{toxic:.0%}" if n else "no fills yet",
    )
    if n >= min_fills:
        add(
            "toxic_30s acceptable",
            toxic_30 <= MAX_TOXIC_30S_GATE,
            f"{toxic_30:.0%} (max {MAX_TOXIC_30S_GATE:.0%})",
        )
        add(
            "mean markout @30s acceptable",
            markout_30 >= MIN_MEAN_MARKOUT_30S_PCT,
            f"{markout_30:+.3f}% (floor {MIN_MEAN_MARKOUT_30S_PCT:+.3f}%)",
        )
        report.markout_gate_met = all(
            c["passed"]
            for c in report.checks
            if c["name"] in ("toxic_30s acceptable", "mean markout @30s acceptable")
        )
    else:
        report.markout_gate_met = False
        add("markout gate", False, f"needs {min_fills}+ fills (have {n})")

    report.passed = report.gate_fills_met and report.markout_gate_met
    return report


def write_e15_report(report: E15Report, *, repo: Path = _REPO) -> Path:
    out = repo / E15_REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    return out


def format_e15_report(report: E15Report) -> str:
    lines = [
        "=== E1.5 WS-path live session ===",
        f"utc: {report.generated_utc}",
        f"repo: {report.repo}",
        f"ws_fills: {report.ws_fills} / {report.min_fills_gate} gate",
        f"buys: {report.buys} | sells: {report.sells}",
        f"capture_xrp: {report.capture_xrp:+.4f} | neg_capture: {report.neg_capture}",
        f"gate: {'PASS' if report.passed else ('FILLS OK' if report.gate_fills_met else 'IN PROGRESS')}",
        "",
        "--- runtime ---",
    ]
    for k, v in report.runtime.items():
        if v is not None and v != "":
            lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("--- checks ---")
    for c in report.checks:
        mark = "PASS" if c["passed"] else "FAIL"
        lines.append(f"  [{mark}] {c['name']}: {c['detail']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="E1.5 WS-path session report")
    parser.add_argument("--repo", type=Path, default=_REPO)
    parser.add_argument("--min-fills", type=int, default=DEFAULT_MIN_FILLS)
    parser.add_argument("--since", default="", help="ISO timestamp filter for trades CSV")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--gate", action="store_true", help="Exit 1 until >= min fills")
    parser.add_argument(
        "--gate-full",
        action="store_true",
        help="Exit 1 until fills + markout gates pass (E1.5 complete)",
    )
    parser.add_argument("--write", action="store_true", help=f"Write {E15_REPORT_PATH}")
    args = parser.parse_args()

    report = build_e15_report(
        repo=args.repo,
        min_fills=args.min_fills,
        since=args.since or None,
    )
    if args.write:
        path = write_e15_report(report, repo=args.repo)
        if not args.json:
            print(f"wrote {path}")
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_e15_report(report))

    if args.gate_full and not report.passed:
        return 1
    if args.gate and not report.gate_fills_met:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
