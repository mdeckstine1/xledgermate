#!/usr/bin/env python3
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experimental.arb.clob_amm_monitor import summarize_clob_amm_rows, tail_clob_amm_records
import experimental.arb.fill_simulator as fs

logs = ROOT / "logs"
print("fill_sim exports", [a for a in dir(fs) if not a.startswith("_")])

rows = tail_clob_amm_records(limit=3000, path=logs / "clob_amm_spread.jsonl")
print("clob_amm recent rows", len(rows))
if rows:
    print(json.dumps(summarize_clob_amm_rows(rows), indent=2, default=str)[:2000])

pos = [r for r in rows if float(r.get("net_edge_bps") or -999) > 0]
print("net+ in recent3000", len(pos))

fn = getattr(fs, "build_arb_fill_simulation_payload", None)
if fn is None:
    fn = getattr(fs, "build_fill_simulation_payload", None)
if fn and pos:
    print("fill_sim sample", json.dumps(fn(latest=pos[-1], logs_dir=logs), default=str)[:1500])

by_day = Counter()
by_day_pos = Counter()
by_day_strong = Counter()
path = logs / "arb_universe.jsonl"
with path.open(encoding="utf-8", errors="replace") as fh:
    for line in fh:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        day = str(r.get("ts_utc") or "")[:10]
        if not day:
            continue
        by_day[day] += 1
        bn = float(r.get("best_net") or -999)
        if bn > 0:
            by_day_pos[day] += 1
        if bn > 5:
            by_day_strong[day] += 1

print("last 14 days: day pos/total pct strong>5")
for d in sorted(by_day.keys())[-14:]:
    tot = by_day[d]
    p = by_day_pos[d]
    s = by_day_strong[day] if False else by_day_strong[d]
    pct = 100.0 * p / tot if tot else 0.0
    print("%s  %d/%d  %.1f%%  strong=%d" % (d, p, tot, pct, s))
