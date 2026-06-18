#!/usr/bin/env python3
"""
Fill → quote-age report.

Primary source: M6 live stream `logs/fill_quote_age.jsonl` (engine at detect-fill).
Fallback: OFFER_REFRESH join in trades_*.csv (M2 proxy) for legacy fills.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experimental.ws_feed.fill_quote_age_log import tail_fill_quote_age_records

WS_FILL_MARKER = "WS pure fill"
DEFAULT_CYCLE_S = 5.0
_M6_AGE_RE = re.compile(r"quote_age_m6=([0-9.]+)s")


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_trade_rows(logs_dir: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for path in sorted(logs_dir.glob("trades_*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows.extend(csv.DictReader(handle))
        except OSError:
            continue
    return rows


def _is_ws_fill(row: Dict[str, str]) -> bool:
    side = (row.get("side") or row.get("event_type") or "").upper()
    if side not in ("BUY", "SELL"):
        return False
    return WS_FILL_MARKER in (row.get("notes") or "")


def _refresh_rows(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        if (row.get("event_type") or "").upper() != "OFFER_REFRESH":
            continue
        ts = _parse_ts(row.get("timestamp_utc", ""))
        if ts is None:
            continue
        try:
            cycle = int(float(row.get("cycle") or 0))
        except (TypeError, ValueError):
            cycle = 0
        notes = row.get("notes") or ""
        placed = 0
        cancelled = 0
        if "placed" in notes:
            try:
                placed = int(notes.split("placed", 1)[1].split()[0])
            except (IndexError, ValueError):
                placed = 0
        if "cancelled" in notes:
            try:
                cancelled = int(notes.split("cancelled", 1)[1].split(",")[0].strip())
            except (IndexError, ValueError):
                cancelled = 0
        out.append(
            {
                "ts": ts,
                "cycle": cycle,
                "placed": placed,
                "cancelled": cancelled,
                "notes": notes,
            }
        )
    out.sort(key=lambda r: (r["ts"], r["cycle"]))
    return out


def _last_refresh_before(
    refreshes: List[Dict[str, Any]],
    *,
    ts: datetime,
    cycle: int,
) -> Optional[Dict[str, Any]]:
    candidate: Optional[Dict[str, Any]] = None
    for row in refreshes:
        if row["ts"] <= ts:
            candidate = row
        elif row["ts"] > ts:
            break
    if candidate is not None:
        return candidate
    if cycle <= 0:
        return None
    by_cycle = [r for r in refreshes if r["cycle"] > 0 and r["cycle"] <= cycle]
    return by_cycle[-1] if by_cycle else None


@dataclass
class FillAgeRow:
    timestamp_utc: str
    side: str
    xrp_amount: float
    cycle: int
    age_seconds_since_refresh: Optional[float]
    age_cycles_since_refresh: Optional[int]
    refresh_placed: int = 0
    refresh_cancelled: int = 0
    method: str = "timestamp"
    caveat: str = "lower_bound"


@dataclass
class FillAgeReport:
    generated_utc: str
    logs_dir: str
    cycle_seconds_assumed: float
    fill_count: int = 0
    with_refresh_match: int = 0
    m6_live_count: int = 0
    m2_proxy_count: int = 0
    rows: List[FillAgeRow] = field(default_factory=list)
    age_seconds_mean: Optional[float] = None
    age_seconds_median: Optional[float] = None
    age_seconds_p95: Optional[float] = None
    caveat: str = (
        "Primary: M6 live JSONL from engine at fill detect. "
        "Fallback: OFFER_REFRESH join (M2 proxy) for fills before M6 logging."
    )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _m6_index(
    records: List[Dict[str, Any]],
) -> Dict[Tuple[int, str], Dict[str, Any]]:
    """Map (cycle, SIDE) -> M6 JSONL row."""
    out: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for row in records:
        try:
            cycle = int(row.get("cycle") or 0)
        except (TypeError, ValueError):
            cycle = 0
        side = str(row.get("side") or "").upper()
        if cycle > 0 and side:
            out[(cycle, side)] = row
    return out


def _m6_from_csv_notes(notes: str) -> Optional[float]:
    match = _M6_AGE_RE.search(notes or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def build_fill_age_report(
    *,
    logs_dir: Optional[Path] = None,
    cycle_seconds: float = DEFAULT_CYCLE_S,
    since: Optional[datetime] = None,
) -> FillAgeReport:
    logs = logs_dir or (ROOT / "logs")
    all_rows = _load_trade_rows(logs)
    refreshes = _refresh_rows(all_rows)
    fills = [r for r in all_rows if _is_ws_fill(r)]
    if since is not None:
        fills = [r for r in fills if (_parse_ts(r.get("timestamp_utc", "")) or since) >= since]

    m6_records = tail_fill_quote_age_records(
        limit=5000,
        path=logs / "fill_quote_age.jsonl",
        since=since,
    )
    m6_by_cycle = _m6_index(m6_records)

    report_rows: List[FillAgeRow] = []
    ages: List[float] = []
    m6_live = 0
    m2_proxy = 0
    for fill in fills:
        ts = _parse_ts(fill.get("timestamp_utc", ""))
        if ts is None:
            continue
        try:
            cycle = int(float(fill.get("cycle") or 0))
        except (TypeError, ValueError):
            cycle = 0
        side = (fill.get("side") or fill.get("event_type") or "").upper()
        notes = fill.get("notes") or ""

        age_s: Optional[float] = None
        age_cycles: Optional[int] = None
        placed = 0
        cancelled = 0
        method = "none"

        m6_row = m6_by_cycle.get((cycle, side)) if cycle > 0 else None
        if m6_row is not None and m6_row.get("quote_age_seconds") is not None:
            age_s = float(m6_row["quote_age_seconds"])
            method = str(m6_row.get("tracking") or "m6_live")
            m6_live += 1
            ages.append(age_s)
        else:
            csv_m6 = _m6_from_csv_notes(notes)
            if csv_m6 is not None:
                age_s = csv_m6
                method = "m6_csv_notes"
                m6_live += 1
                ages.append(age_s)
            else:
                refresh = _last_refresh_before(refreshes, ts=ts, cycle=cycle)
                if refresh is not None:
                    placed = int(refresh.get("placed") or 0)
                    cancelled = int(refresh.get("cancelled") or 0)
                    age_s = max(0.0, (ts - refresh["ts"]).total_seconds())
                    if cycle > 0 and refresh.get("cycle"):
                        age_cycles = max(0, cycle - int(refresh["cycle"]))
                    method = "m2_proxy_refresh"
                    m2_proxy += 1
                    ages.append(age_s)
                elif cycle > 0:
                    method = "m2_proxy_cycle_gap"
                    age_cycles = cycle
                    age_s = age_cycles * cycle_seconds
                    m2_proxy += 1
                    ages.append(age_s)

        report_rows.append(
            FillAgeRow(
                timestamp_utc=ts.isoformat(),
                side=side,
                xrp_amount=float(fill.get("xrp_amount") or 0),
                cycle=cycle,
                age_seconds_since_refresh=round(age_s, 2) if age_s is not None else None,
                age_cycles_since_refresh=age_cycles,
                refresh_placed=placed,
                refresh_cancelled=cancelled,
                method=method,
            )
        )

    matched = m2_proxy
    ts_ages = [r.age_seconds_since_refresh for r in report_rows if r.age_seconds_since_refresh is not None]
    p95 = None
    if ts_ages:
        ordered = sorted(ts_ages)
        idx = min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))
        p95 = round(ordered[idx], 2)

    return FillAgeReport(
        generated_utc=datetime.now(tz=timezone.utc).isoformat(),
        logs_dir=str(logs),
        cycle_seconds_assumed=cycle_seconds,
        fill_count=len(report_rows),
        with_refresh_match=matched,
        m6_live_count=m6_live,
        m2_proxy_count=m2_proxy,
        rows=report_rows,
        age_seconds_mean=round(mean(ts_ages), 2) if ts_ages else None,
        age_seconds_median=round(median(ts_ages), 2) if ts_ages else None,
        age_seconds_p95=p95,
    )


def format_fill_age_report(report: FillAgeReport) -> str:
    lines = [
        "=== Fill quote age (M6 live + M2 fallback) ===",
        "",
        f"Generated: {report.generated_utc}",
        f"Logs: {report.logs_dir}",
        f"WS fills: {report.fill_count} | M6 live: {report.m6_live_count} | M2 proxy: {report.m2_proxy_count}",
        f"Age (s) mean={report.age_seconds_mean} median={report.age_seconds_median} p95={report.age_seconds_p95}",
        "",
        f"Source: {report.caveat}",
        "",
    ]
    if not report.rows:
        lines.append("No WS fills in trades_*.csv yet.")
        return "\n".join(lines)
    lines.append("Recent fills:")
    for row in report.rows[-20:]:
        age = (
            f"{row.age_seconds_since_refresh:.1f}s"
            if row.age_seconds_since_refresh is not None
            else "n/a"
        )
        lines.append(
            f"  {row.timestamp_utc[:19]} {row.side} {row.xrp_amount:.4f} XRP "
            f"cycle={row.cycle} age≈{age} ({row.method}; placed={row.refresh_placed})"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="WS fill quote-age report (M6 JSONL + M2 fallback)")
    parser.add_argument("--logs-dir", type=Path, default=None, help="Logs directory (default: repo/logs)")
    parser.add_argument("--cycle-seconds", type=float, default=DEFAULT_CYCLE_S)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--since", type=str, default="", help="ISO timestamp lower bound for fills")
    args = parser.parse_args()

    since_dt = _parse_ts(args.since) if args.since else None
    report = build_fill_age_report(
        logs_dir=args.logs_dir,
        cycle_seconds=args.cycle_seconds,
        since=since_dt,
    )
    if args.as_json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_fill_age_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
