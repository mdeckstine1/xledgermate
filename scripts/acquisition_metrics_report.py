#!/usr/bin/env python3
"""Session acquisition metrics report — edge-positive inventory vs spot."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.wealth_metrics import compute_wealth_metrics
from experimental.ws_feed.acquisition_metrics import (
    build_acquisition_metrics,
    format_acquisition_report,
)
from experimental.ws_feed.fill_quote_age_log import tail_fill_quote_age_records
from experimental.ws_feed.intel_decisions_log import tail_intel_records


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_runtime(logs_dir: Path) -> Dict[str, Any]:
    path = logs_dir / "runtime_state.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _session_intel_cycles(
    logs_dir: Path,
    *,
    since: Optional[datetime],
    ws_as_version: Optional[str],
) -> List[Dict[str, Any]]:
    rows = tail_intel_records(limit=5000, path=logs_dir / "intel_decisions.jsonl")
    out: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("kind") != "cycle":
            continue
        if ws_as_version and str(row.get("ws_as_version") or "") not in ("", ws_as_version):
            continue
        if since is not None:
            ts = _parse_ts(str(row.get("ts_utc") or ""))
            if ts is not None and ts < since:
                continue
        out.append(row)
    return out


@dataclass
class AcquisitionReport:
    generated_utc: str
    logs_dir: str
    runtime_ws_as_version: str = ""
    session_boot_utc: str = ""
    fills_count: int = 0
    intel_cycles_count: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_acquisition_report(
    *,
    logs_dir: Optional[Path] = None,
    since: Optional[datetime] = None,
) -> AcquisitionReport:
    logs = logs_dir or (ROOT / "logs")
    runtime = _load_runtime(logs)
    boot_raw = str(runtime.get("session_boot_utc") or "")
    boot_dt = _parse_ts(boot_raw) if boot_raw else None
    since_dt = since or boot_dt
    ws_ver = str(runtime.get("ws_as_version") or "")

    fills = tail_fill_quote_age_records(
        limit=5000,
        path=logs / "fill_quote_age.jsonl",
        since=since_dt,
        ws_as_version=ws_ver or None,
    )
    intel_cycles = _session_intel_cycles(logs, since=since_dt, ws_as_version=ws_ver or None)

    runtime_for_metrics = dict(runtime)
    runtime_for_metrics.update(
        {k: v for k, v in compute_wealth_metrics(runtime).items() if v is not None}
    )
    metrics = build_acquisition_metrics(
        runtime=runtime_for_metrics,
        session_fills=fills,
        intel_cycles=intel_cycles,
    )

    return AcquisitionReport(
        generated_utc=datetime.now(tz=timezone.utc).isoformat(),
        logs_dir=str(logs),
        runtime_ws_as_version=ws_ver,
        session_boot_utc=boot_raw,
        fills_count=len(fills),
        intel_cycles_count=len(intel_cycles),
        metrics=metrics,
    )


def format_acquisition_report_cli(report: AcquisitionReport) -> str:
    runtime = {
        "session_boot_utc": report.session_boot_utc,
        "ws_as_version": report.runtime_ws_as_version,
        "fills_session": report.fills_count,
    }
    body = format_acquisition_report(report.metrics, runtime=runtime)
    header = [
        f"Generated: {report.generated_utc}",
        f"Logs: {report.logs_dir}",
        f"M6 fills: {report.fills_count} | intel cycles: {report.intel_cycles_count}",
        "",
    ]
    return "\n".join(header) + body


def main() -> int:
    parser = argparse.ArgumentParser(description="Session acquisition metrics report")
    parser.add_argument("--logs-dir", type=Path, default=None)
    parser.add_argument("--since", type=str, default="", help="ISO lower bound (default: session boot)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    since_dt = _parse_ts(args.since) if args.since else None
    report = build_acquisition_report(logs_dir=args.logs_dir, since=since_dt)
    if args.as_json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_acquisition_report_cli(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
