"""
E1 — VPS ws-engine sign-off checks (dry-run smoke → live flip).

Evaluates logs/runtime_state.json, recent decisions.jsonl, and optional systemd status.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from experimental.swap_readiness_report import WIRING_PARITY_REQUIRED_KEYS, check_wiring_parity

DEFAULT_REPO = Path(".")

# E1 bar before flipping dry_run off on VPS (operator can tighten later).
DEFAULT_MIN_CYCLES = 30
DEFAULT_MIN_WOULD_QUOTE_PCT = 35.0
DEFAULT_MAX_WS_BOOK_AGE_S = 15.0
DEFAULT_MIN_DECISION_LINES = 20
DEFAULT_MIN_WIRING_KEYS = 8  # production runtime omits lab-only keys (competitor_pressure, etc.)


@dataclass
class E1SignoffCriteria:
    min_cycles: int = DEFAULT_MIN_CYCLES
    min_would_quote_pct: float = DEFAULT_MIN_WOULD_QUOTE_PCT
    max_ws_book_age_s: float = DEFAULT_MAX_WS_BOOK_AGE_S
    min_decision_lines: int = DEFAULT_MIN_DECISION_LINES
    min_wiring_keys: int = DEFAULT_MIN_WIRING_KEYS
    require_kill_clear: bool = True
    require_dry_run: bool = True  # True = pre-live smoke; False = post-live monitoring


@dataclass
class E1Check:
    name: str
    passed: bool
    detail: str


@dataclass
class E1SignoffReport:
    generated_utc: str = ""
    repo: str = ""
    passed: bool = False
    ready_for_live_flip: bool = False
    checks: List[E1Check] = field(default_factory=list)
    runtime: Dict[str, Any] = field(default_factory=dict)
    presence: Dict[str, Any] = field(default_factory=dict)
    wiring: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _tail_jsonl(path: Path, limit: int = 500) -> List[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:] if len(lines) > limit else lines


def _would_quote_from_decisions(lines: Sequence[str]) -> Dict[str, Any]:
    total = 0
    would = 0
    dry_sync = 0
    for ln in lines:
        if not ln.strip():
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if rec.get("as_mode") != "pure":
            continue
        total += 1
        events = rec.get("events") or []
        blob = " ".join(
            str(e.get("message") or "") for e in events if isinstance(e, dict)
        )
        blob += " " + str(rec.get("execution") or "")
        if re.search(r"would sync \d+ pure", blob, re.I):
            dry_sync += 1
            would += 1
        elif re.search(r"would_quote[=:]?\s*true|Live WS pure: placed", blob, re.I):
            would += 1
        elif bool(rec.get("would_quote")):
            would += 1
    pct = round(100.0 * would / total, 1) if total else 0.0
    return {
        "pure_decision_lines": total,
        "would_quote_lines": would,
        "would_quote_pct": pct,
        "dry_sync_lines": dry_sync,
    }


def evaluate_e1_signoff(
    *,
    repo: Path = DEFAULT_REPO,
    criteria: Optional[E1SignoffCriteria] = None,
    systemd_active: Optional[bool] = None,
) -> E1SignoffReport:
    crit = criteria or E1SignoffCriteria()
    logs = repo / "logs"
    rt_path = logs / "runtime_state.json"
    report = E1SignoffReport(
        generated_utc=datetime.now(timezone.utc).isoformat(),
        repo=str(repo.resolve()),
    )

    if not rt_path.exists():
        report.checks.append(E1Check("runtime_state.json", False, "missing"))
        return report

    rt = json.loads(rt_path.read_text(encoding="utf-8"))
    report.runtime = {
        k: rt.get(k)
        for k in (
            "version",
            "dry_run",
            "as_mode",
            "price_source",
            "active_profile",
            "kill_switch_active",
            "cycle_count",
            "ws_book_age_s",
            "mid_price",
            "offers_placed_last_cycle",
            "last_execution_summary",
            "fills_session",
            "quote_decision_summary",
            "zero_quote_reason",
        )
        if k in rt or True
    }

    report.wiring = check_wiring_parity(rt)
    dec_lines = _tail_jsonl(logs / "decisions.jsonl")
    report.presence = _would_quote_from_decisions(dec_lines)

    def add(name: str, ok: bool, detail: str) -> None:
        report.checks.append(E1Check(name, ok, detail))

    add(
        "as_mode pure",
        rt.get("as_mode") == "pure",
        str(rt.get("as_mode")),
    )
    add(
        "price_source ws_book_feed",
        rt.get("price_source") == "ws_book_feed",
        str(rt.get("price_source")),
    )
    if crit.require_kill_clear:
        add(
            "kill switch clear",
            not bool(rt.get("kill_switch_active")),
            str(rt.get("kill_switch_reason", ""))[:120],
        )
    if crit.require_dry_run:
        add("dry_run smoke", bool(rt.get("dry_run")), f"dry_run={rt.get('dry_run')}")
    else:
        add("live mode", not bool(rt.get("dry_run")), f"dry_run={rt.get('dry_run')}")

    cycles = int(rt.get("cycle_count") or 0)
    add(
        f"cycles >= {crit.min_cycles}",
        cycles >= crit.min_cycles,
        str(cycles),
    )

    ws_age = rt.get("ws_book_age_s")
    if ws_age is not None:
        add(
            f"ws_book_age_s <= {crit.max_ws_book_age_s}",
            float(ws_age) <= crit.max_ws_book_age_s,
            f"{float(ws_age):.2f}",
        )

    wpct = float(report.presence.get("would_quote_pct") or 0)
    plines = int(report.presence.get("pure_decision_lines") or 0)
    add(
        f"would_quote >= {crit.min_would_quote_pct}% (decisions)",
        plines >= crit.min_decision_lines and wpct >= crit.min_would_quote_pct,
        f"{wpct}% over {plines} pure lines",
    )

    w_present = int(report.wiring.get("present_count") or 0)
    add(
        f"wiring parity >= {crit.min_wiring_keys} keys",
        w_present >= crit.min_wiring_keys,
        f"{w_present}/{report.wiring.get('required_count')} missing={report.wiring.get('missing_keys')}",
    )

    if systemd_active is not None:
        add("systemd xledgermate active", systemd_active, str(systemd_active))

    report.passed = all(c.passed for c in report.checks)
    report.ready_for_live_flip = report.passed and bool(rt.get("dry_run"))
    return report


def format_e1_report(report: E1SignoffReport) -> str:
    lines = [
        "=== E1 VPS ws-engine sign-off ===",
        f"utc: {report.generated_utc}",
        f"repo: {report.repo}",
        f"overall: {'PASS' if report.passed else 'FAIL'}",
        f"ready_for_live_flip: {report.ready_for_live_flip}",
        "",
        "--- checks ---",
    ]
    for c in report.checks:
        lines.append(f"  [{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}")
    lines.extend(
        [
            "",
            "--- runtime snapshot ---",
        ]
    )
    for k, v in report.runtime.items():
        if v is not None and v != "":
            lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append(f"presence: {report.presence}")
    return "\n".join(lines)
