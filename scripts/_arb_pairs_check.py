#!/usr/bin/env python3
import json
from pathlib import Path

p = Path("logs/arb_universe.jsonl")
line = p.read_text(encoding="utf-8", errors="replace").splitlines()[-1]
r = json.loads(line)
pairs = r.get("pairs") or []
print("n_pairs", len(pairs))
print("ids", [x.get("id") for x in pairs])
for x in pairs:
    print(
        x.get("id"),
        "status=",
        x.get("status"),
        "net=",
        x.get("net_edge_bps"),
        "fill500=",
        x.get("fill_profit_bps_500"),
        "flag=",
        x.get("discovery_flag"),
    )
