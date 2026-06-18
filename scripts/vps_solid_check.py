#!/usr/bin/env python3
"""VPS production solid check — ws-engine data + logic consistency."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
RUNTIME = LOGS / "runtime_state.json"
LOG = LOGS / "xledgermate.log"


def _run(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip() if exc.output else str(exc)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _last_engine_start_line() -> int:
    if not LOG.exists():
        return 0
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if "WsPureTradingEngine v" in lines[i]:
            return i
    return 0


def _log_since_start() -> List[str]:
    if not LOG.exists():
        return []
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    start = _last_engine_start_line()
    return lines[start:]


def check_processes() -> Tuple[bool, List[str]]:
    notes: List[str] = []
    out = _run("pgrep -af 'main.py' || true")
    if not out:
        return False, ["no main.py processes"]
    ok = True
    for line in out.splitlines():
        if "ws-engine" in line:
            notes.append(f"ws-engine: {line.split()[0]}")
        elif "ws-hud" in line:
            notes.append(f"ws-hud: {line.split()[0]}")
        elif "--mode engine" in line and "ws-engine" not in line:
            ok = False
            notes.append(f"LEGACY POLL: {line}")
    if not any("ws-engine" in n for n in notes):
        ok = False
        notes.append("ws-engine process missing")
    return ok, notes


def check_runtime(d: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if d.get("price_source") != "ws_book_feed":
        issues.append(f"price_source={d.get('price_source')!r} (want ws_book_feed)")
    if d.get("as_mode") != "pure":
        issues.append(f"as_mode={d.get('as_mode')!r} (want pure)")
    if d.get("kill_switch_active"):
        issues.append(f"kill_switch ON: {d.get('kill_switch_reason')}")
    if not d.get("preflight_ready"):
        issues.append(f"preflight not ready: {d.get('preflight_summary')}")
    if d.get("dry_run"):
        issues.append("dry_run=True (not live MM)")
    age = d.get("ws_book_age_s")
    if age is not None and float(age) > 20:
        issues.append(f"ws_book_age_s={age} (>20s stale)")
    updated = d.get("updated_utc")
    if updated:
        try:
            ts = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            age_s = (datetime.now(timezone.utc) - ts).total_seconds()
            if age_s > 30:
                issues.append(f"runtime_state stale {age_s:.0f}s")
        except ValueError:
            pass
    # G2/G7 fields present when quoting
    if d.get("zero_quote_reason") == "quoted" or d.get("would_quote"):
        if d.get("g2_spread_mult") is None:
            issues.append("g2_spread_mult missing while quoting")
        if not d.get("g7_summary") and not d.get("quote_visibility_summary"):
            issues.append("g7/visibility empty while quoting")
    return len(issues) == 0, issues


def check_log_errors(since: List[str]) -> Tuple[bool, List[str]]:
    bad: List[str] = []
    for line in since:
        low = line.lower()
        if "nameerror" in low or "traceback" in low:
            if "g4 competitor scrape failed" in low:
                continue
            bad.append(line[-200:])
        elif "| error |" in low or "kill switch triggered" in low:
            bad.append(line[-200:])
    # G4 failures after fix
    g4_fail = sum(1 for l in since if "G4 competitor scrape failed" in l)
    notes = []
    if g4_fail:
        notes.append(f"G4 scrape failures this session: {g4_fail}")
    return len(bad) == 0, bad[-10:] + notes


def check_m6(d: Dict[str, Any]) -> Tuple[bool, List[str]]:
    notes: List[str] = []
    jsonl = LOGS / "fill_quote_age.jsonl"
    recent = d.get("recent_fill_quote_ages") or []
    fills_sess = d.get("fills_session") or 0
    if fills_sess > 0 and not recent and not jsonl.exists():
        return False, ["fills_session>0 but no M6 recent_fill_quote_ages or JSONL"]
    if jsonl.exists():
        lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
        notes.append(f"fill_quote_age.jsonl: {len(lines)} records")
        if lines:
            last = json.loads(lines[-1])
            notes.append(
                f"last M6: age={last.get('quote_age_seconds')}s seq={last.get('offer_sequence')} v={last.get('ws_as_version')}"
            )
    notes.append(f"recent_fill_quote_ages in runtime: {len(recent)}")
    return True, notes


def main() -> int:
    print("=" * 60)
    print("VPS SOLID CHECK")
    print("=" * 60)
    ver = (ROOT / "VERSION").read_text().strip() if (ROOT / "VERSION").exists() else "?"
    ws_ver = (ROOT / "experimental/ws_feed/WS_AS_VERSION").read_text().strip()
    print(f"repo VERSION={ver} WS_AS={ws_ver}")
    print(f"HEAD: {_run('git rev-parse --short HEAD 2>/dev/null')}")
    print()

    proc_ok, proc_notes = check_processes()
    print("--- PROCESSES ---")
    for n in proc_notes:
        print(f"  {n}")
    print(f"  OK: {proc_ok}")
    print()

    d = _load_json(RUNTIME)
    if not d:
        print("FATAL: logs/runtime_state.json missing")
        return 2

    rt_ok, rt_issues = check_runtime(d)
    print("--- RUNTIME STATE ---")
    for k in (
        "updated_utc", "cycle_count", "ws_as_version", "price_source", "as_mode",
        "zero_quote_reason", "would_quote", "open_offers_count", "fills_session",
        "ws_book_age_s", "g2_spread_mult", "g4_size_mult", "g7_summary",
        "quote_visibility_summary", "capture_xrp_session", "toxic_ratio_session",
        "cancel_fill_ratio_session", "as_presence_pct",
    ):
        v = d.get(k)
        if v is not None and v != "":
            s = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            print(f"  {k}: {s[:100]}")
    if rt_issues:
        print("  ISSUES:")
        for i in rt_issues:
            print(f"    - {i}")
    print(f"  OK: {rt_ok}")
    print()

    since = _log_since_start()
    log_ok, log_notes = check_log_errors(since)
    print("--- LOG (current session) ---")
    for n in log_notes:
        print(f"  {n}")
    print(f"  OK: {log_ok}")
    print()

    m6_ok, m6_notes = check_m6(d)
    print("--- M6 FILL AGES ---")
    for n in m6_notes:
        print(f"  {n}")
    print(f"  OK: {m6_ok}")
    print()

    hist = d.get("sample_history") or []
    print("--- SAMPLE HISTORY ---")
    print(f"  len={len(hist)} presence={d.get('as_presence_pct')}%")
    for row in hist[-2:]:
        print(
            f"  {row.get('ts_utc')} wq={row.get('would_quote')} "
            f"zqr={row.get('zero_quote_reason')} spread={row.get('book_spread_pct')}"
        )
    print()

    kill = _load_json(LOGS / "kill_switch.json")
    print("--- KILL SWITCH ---")
    print(f"  active={kill.get('active', d.get('kill_switch_active'))} reason={kill.get('reason', d.get('kill_switch_reason'))}")
    print()

    all_ok = proc_ok and rt_ok and log_ok and m6_ok
    print("=" * 60)
    print("VERDICT:", "SOLID" if all_ok else "NEEDS ATTENTION")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
