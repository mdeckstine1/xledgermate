#!/usr/bin/env python3
"""Project 24h arb P&L from logs/clob_amm_spread.jsonl soak data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from experimental.arb.clob_amm_monitor import augment_clob_amm_row, summarize_clob_amm_rows


def _parse_ts(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_rows(path: Path) -> list[tuple[datetime, dict]]:
    out: list[tuple[datetime, dict]] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") != "ok" or row.get("spread_bps") is None:
            continue
        ts = row.get("ts_utc")
        if not ts:
            continue
        dt = _parse_ts(str(ts))
        if dt is None:
            continue
        out.append((dt, row))
    out.sort(key=lambda x: x[0])
    return out


def _default_spread_pct(logs_dir: Path) -> float | None:
    path = logs_dir / "alpha_runtime_state.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        val = (data.get("book") or {}).get("spread_pct")
        return float(val) if val is not None else None
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def pnl_rlusd(notional: float, bps: float) -> float:
    return notional * (bps / 10_000.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument("--notional", type=float, default=1000.0, help="RLUSD per roundtrip")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--all", action="store_true", help="Use entire JSONL (ignore --hours)")
    parser.add_argument(
        "--measured-only",
        action="store_true",
        help="Only rows with live clob_spread_pct and amm_fee_bps (no cost backfill)",
    )
    args = parser.parse_args()

    rows = _load_rows(args.logs_dir / "clob_amm_spread.jsonl")
    if not rows:
        print("No ok samples in clob_amm_spread.jsonl")
        return

    end = rows[-1][0]
    if args.all:
        window = list(rows)
        window_label = "all samples"
    else:
        start = end - timedelta(hours=args.hours)
        window = [(dt, r) for dt, r in rows if dt >= start]
        window_label = f"last {args.hours:g}h"
    spread_pct = _default_spread_pct(args.logs_dir)
    raw_window = window
    if args.measured_only:
        raw_window = [
            (dt, r)
            for dt, r in window
            if r.get("clob_spread_pct") is not None and r.get("amm_fee_bps") is not None
        ]
        if not raw_window:
            print("No measured-only samples (need clob_spread_pct + amm_fee_bps on rows)")
            return
    enriched = [augment_clob_amm_row(r, default_clob_spread_pct=spread_pct) for _, r in raw_window]
    summary = summarize_clob_amm_rows(enriched, default_clob_spread_pct=spread_pct)

    net_edges = [float(r["net_edge_bps"]) for r in enriched if r.get("net_edge_bps") is not None]
    net_pos = [r for r in enriched if r.get("net_positive")]
    pos_edges = [float(r["net_edge_bps"]) for r in net_pos]

    span_h = max((raw_window[-1][0] - raw_window[0][0]).total_seconds() / 3600.0, 0.01) if len(raw_window) > 1 else args.hours

    def bucket_best(interval_min: int) -> list[dict]:
        best: dict[tuple, dict] = {}
        for dt, raw in raw_window:
            row = augment_clob_amm_row(raw, default_clob_spread_pct=spread_pct)
            if not row.get("net_positive"):
                continue
            key = (
                dt.year,
                dt.month,
                dt.day,
                dt.hour,
                dt.minute // interval_min if interval_min < 60 else 0,
            ) if interval_min < 60 else (dt.year, dt.month, dt.day, dt.hour)
            prev = best.get(key)
            if prev is None or float(row["net_edge_bps"]) > float(prev["net_edge_bps"]):
                best[key] = row
        return list(best.values())

    scenarios = [
        ("Every NET+ poll", pos_edges),
        ("Max 1 / 15m on NET+", [float(r["net_edge_bps"]) for r in bucket_best(15)]),
        ("Max 1 / hour on NET+", [float(r["net_edge_bps"]) for r in bucket_best(60)]),
        ("Every poll (avg net incl. negatives)", net_edges),
    ]

    print("=== ARB P&L PROJECTION (soak data) ===")
    print(f"generated_utc: {datetime.now(tz=timezone.utc).isoformat()}")
    print(f"window: {window_label}{' (measured costs only)' if args.measured_only else ''} | {raw_window[0][0].isoformat()} -> {end.isoformat()} ({span_h:.2f}h sampled)")
    print(f"samples: {len(enriched)} | notional: {args.notional:.0f} RLUSD roundtrip")
    print()
    print("--- Stats ---")
    print(f"gross dislocation: {summary['dislocation_pct']}%")
    print(f"net positive:      {summary['net_positive_pct']}%")
    print(f"avg gross bps:     {summary['avg_spread_bps']}")
    print(f"avg net bps:       {summary['avg_net_edge_bps']}")
    print(f"max net bps:       {summary['max_net_edge_bps']}")
    if pos_edges:
        med = sorted(pos_edges)[len(pos_edges) // 2]
        print(f"avg net when NET+: {round(sum(pos_edges) / len(pos_edges), 2)} bps (median {med:.2f})")
    print()
    print("--- 24h scenarios (scaled to 24h) ---")
    scale = 24.0 / span_h
    for name, edges in scenarios:
        if not edges:
            print(f"{name}: 0 trades -> 0.0000 RLUSD / 24h")
            continue
        raw_pnl = sum(pnl_rlusd(args.notional, e) for e in edges)
        pnl_24h = raw_pnl * scale
        trades_24h = len(edges) * scale
        avg_bps = sum(edges) / len(edges)
        print(
            f"{name}: {len(edges)} trades in window -> "
            f"{pnl_24h:+.4f} RLUSD / 24h (~{trades_24h:.0f} trades, avg {avg_bps:+.2f} bps) "
            f"= {pnl_24h / args.notional * 100:+.3f}% on notional"
        )
    print()
    if pos_edges:
        for label, bps in [
            ("avg NET+ trade", sum(pos_edges) / len(pos_edges)),
            ("median NET+ trade", sorted(pos_edges)[len(pos_edges) // 2]),
            ("best NET+ in window", max(pos_edges)),
        ]:
            print(f"Per trade @ {label}: {pnl_rlusd(args.notional, bps):+.4f} RLUSD")


if __name__ == "__main__":
    main()
