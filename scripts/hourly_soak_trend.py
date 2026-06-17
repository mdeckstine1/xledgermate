#!/usr/bin/env python3
"""Hourly soak trend: fills + toxicity from trades CSV + intel_decisions.jsonl."""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
WS_MARKER = "WS pure fill"
HOURS = 24


def parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def hour_key(dt: datetime) -> str:
    h = dt.replace(minute=0, second=0, microsecond=0)
    return h.strftime("%Y-%m-%d %H:00")


def main() -> int:
    now = datetime.now(tz=timezone.utc)
    since = now - timedelta(hours=HOURS)

    # --- fills from CSV ---
    fill_buckets: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(LOGS.glob("trades_*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if WS_MARKER not in (row.get("notes") or ""):
                    continue
                ts = parse_ts(row.get("timestamp_utc", ""))
                if ts is None or ts < since:
                    continue
                fill_buckets[hour_key(ts)].append(row)

    # --- toxicity from intel cycle log ---
    toxic_buckets: dict[str, list[float]] = defaultdict(list)
    toxic30_buckets: dict[str, list[float]] = defaultdict(list)
    markout_buckets: dict[str, list[float]] = defaultdict(list)
    book_age_buckets: dict[str, list[float]] = defaultdict(list)

    intel_path = LOGS / "intel_decisions.jsonl"
    if intel_path.exists():
        with intel_path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("kind") != "cycle":
                    continue
                ts = parse_ts(str(row.get("ts_utc") or ""))
                if ts is None or ts < since:
                    continue
                hk = hour_key(ts)
                t = row.get("toxic_fill_ratio")
                t30 = row.get("toxic_fill_ratio_30s")
                mo = row.get("mean_markout_30s_pct")
                if t is not None:
                    toxic_buckets[hk].append(float(t) * 100.0)
                if t30 is not None:
                    toxic30_buckets[hk].append(float(t30) * 100.0)
                if mo is not None:
                    markout_buckets[hk].append(float(mo))

    # ws_book_age may be in decisions.jsonl
    dec_path = LOGS / "decisions.jsonl"
    if dec_path.exists():
        with dec_path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = parse_ts(str(row.get("ts_utc") or row.get("timestamp_utc") or ""))
                if ts is None or ts < since:
                    continue
                age = row.get("ws_book_age_s")
                if age is None:
                    continue
                try:
                    book_age_buckets[hour_key(ts)].append(float(age))
                except (TypeError, ValueError):
                    pass

    # ordered hours
    hours: list[str] = []
    cursor = since.replace(minute=0, second=0, microsecond=0)
    end = now.replace(minute=0, second=0, microsecond=0)
    while cursor <= end:
        hours.append(hour_key(cursor))
        cursor += timedelta(hours=1)

    def avg(xs: list[float]) -> float | None:
        return statistics.mean(xs) if xs else None

    def p90(xs: list[float]) -> float | None:
        if not xs:
            return None
        xs = sorted(xs)
        i = int(0.9 * (len(xs) - 1))
        return xs[i]

    def fill_stats(rows: list[dict]) -> tuple[int, float, float]:
        n = len(rows)
        cap = sum(float(r.get("profit_xrp_equiv") or 0) for r in rows)
        vol = sum(float(r.get("xrp_amount") or 0) for r in rows)
        bps = (cap / vol * 10000.0) if vol else 0.0
        return n, cap, bps

    print(f"=== Hourly soak trend (last {HOURS}h UTC) ===")
    print(f"now: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print()
    hdr = (
        f"{'Hour UTC':<17} {'Fills':>5} {'Capture':>9} {'bps':>5} "
        f"{'Tox%':>6} {'Tox30':>6} {'Mk30':>7} {'BookP90':>8}"
    )
    print(hdr)
    print("-" * len(hdr))

    total_fills = 0
    total_cap = 0.0
    for hk in hours:
        fills = fill_buckets.get(hk, [])
        n, cap, bps = fill_stats(fills)
        total_fills += n
        total_cap += cap
        tox = avg(toxic_buckets.get(hk, []))
        tox30 = avg(toxic30_buckets.get(hk, []))
        mk = avg(markout_buckets.get(hk, []))
        bage = p90(book_age_buckets.get(hk, []))

        def fmt(v: float | None, w: int, suffix: str = "") -> str:
            if v is None:
                return "—".rjust(w)
            return f"{v:.{1}f}{suffix}".rjust(w)

        mk_s = fmt(mk, 7, "%") if mk is not None else "—".rjust(7)
        ba_s = fmt(bage, 7, "s") if bage is not None else "—".rjust(8)

        print(
            f"{hk:<17} {n:5d} {cap:+9.4f} {bps:5.1f} "
            f"{fmt(tox, 5, '%')} {fmt(tox30, 5, '%')} {mk_s} {ba_s}"
        )

    print("-" * len(hdr))
    print(f"{'TOTAL':<17} {total_fills:5d} {total_cap:+9.4f}")
    print()
    print("Legend: Tox/Tox30 = avg from cycle intel log | Mk30 = mean markout @30s | BookP90 = p90 ws_book_age_s")

    # annotate known events
    print()
    print("=== Notes ===")
    print("- Book freshness fix deployed ~Jun 17 (expect BookP90 drop after restart ~10:23 UTC)")
    print("- Fills with +0.0000 capture still count; balance PnL may lag per-fill column")

    return 0


if __name__ == "__main__":
    sys.exit(main())
