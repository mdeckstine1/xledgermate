#!/usr/bin/env python3
"""Arb tab soak verdict from arb_universe.jsonl + clob_amm_spread.jsonl."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    logs = ROOT / "logs"
    p = logs / "arb_universe.jsonl"
    if not p.is_file():
        print("no arb_universe.jsonl")
        return

    n = 0
    net_pos_snapshots = 0
    best_nets: list[float] = []
    pair_stats: dict = defaultdict(lambda: {"n": 0, "pos": 0, "neg": 0, "disloc": 0, "edges": []})
    first = last = None

    with p.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            n += 1
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = r.get("ts_utc")
            if first is None:
                first = ts
            last = ts
            b = r.get("best_net")
            try:
                if b is not None:
                    best_nets.append(float(b))
            except (TypeError, ValueError):
                pass
            if int(r.get("net_positive_count") or 0) > 0:
                net_pos_snapshots += 1
            for pair in r.get("pairs") or []:
                if not isinstance(pair, dict):
                    continue
                pid = str(pair.get("id") or pair.get("label") or "?")
                st = pair_stats[pid]
                st["n"] += 1
                if pair.get("dislocation"):
                    st["disloc"] += 1
                try:
                    e = float(pair["net_edge_bps"]) if pair.get("net_edge_bps") is not None else None
                except (TypeError, ValueError):
                    e = None
                if e is None:
                    continue
                st["edges"].append(e)
                if e > 0:
                    st["pos"] += 1
                else:
                    st["neg"] += 1

    print("=== ARB UNIVERSE SOAK ===")
    print(f"snapshots={n}")
    print(f"span={first} -> {last}")
    print(
        f"snapshots_with_any_net_positive={net_pos_snapshots} "
        f"({100 * net_pos_snapshots / max(n, 1):.2f}%)"
    )
    if best_nets:
        bn = sorted(best_nets)
        pos = sum(1 for x in bn if x > 0)
        print(
            f"best_net min/med/mean/max="
            f"{bn[0]:.2f}/{bn[len(bn)//2]:.2f}/{sum(bn)/len(bn):.2f}/{bn[-1]:.2f}"
        )
        print(f"best_net>0: {pos} ({100 * pos / len(bn):.2f}%)")
        print(f"best_net>5bps: {sum(1 for x in bn if x > 5)}  >10bps: {sum(1 for x in bn if x > 10)}")

    print("\n=== PER PAIR net_edge_bps ===")
    for pid, st in sorted(pair_stats.items(), key=lambda x: -x[1]["n"]):
        ed = st["edges"]
        if not ed:
            print(f"{pid}: n={st['n']} (no edges)")
            continue
        ed_s = sorted(ed)
        pos = st["pos"]
        nn = st["n"]
        print(
            f"{pid}: n={nn} disloc={100*st['disloc']/nn:.1f}% "
            f"net+={pos} ({100*pos/nn:.2f}%) "
            f"med={ed_s[len(ed_s)//2]:.1f} mean={sum(ed)/len(ed):.1f} "
            f"max={ed_s[-1]:.1f} p95={ed_s[int(0.95*(len(ed_s)-1))]:.1f}"
        )

    cpath = logs / "clob_amm_spread.jsonl"
    if cpath.is_file():
        rows = []
        with cpath.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        print(f"\nclob_amm_spread.jsonl rows={len(rows)} bytes={cpath.stat().st_size}")
        nets = []
        for r in rows:
            try:
                if r.get("net_edge_bps") is not None:
                    nets.append(float(r["net_edge_bps"]))
            except (TypeError, ValueError):
                pass
        if nets:
            ns = sorted(nets)
            print(
                f"clob_amm net_edge: n={len(ns)} >0={sum(1 for x in ns if x>0)} "
                f"med={ns[len(ns)//2]:.2f} max={ns[-1]:.2f} mean={sum(ns)/len(ns):.2f}"
            )
        if rows:
            r = rows[-1]
            print(
                f"latest clob_amm: ts={r.get('ts_utc')} spread_bps={r.get('spread_bps')} "
                f"net={r.get('net_edge_bps')} disloc={r.get('dislocation')}"
            )

    print("\n=== VERDICT HINTS ===")
    if n < 100:
        print("insufficient_data")
    elif net_pos_snapshots == 0:
        print("no_net_positive_snapshots_in_soak — monitor OK, execution build NOT justified")
    elif net_pos_snapshots / n < 0.02:
        print("rare_net_positive — keep monitor-only, do not build live arb yet")
    else:
        print("recurring_net_positive — worth deeper fill-sim / paper path study")


if __name__ == "__main__":
    main()
