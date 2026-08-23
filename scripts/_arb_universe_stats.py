import json
from collections import defaultdict
from pathlib import Path

rows = []
path = Path("logs/arb_universe.jsonl")
if path.is_file():
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            rows.append(json.loads(line))

print(f"universe polls: {len(rows)}")
if not rows:
    raise SystemExit(0)

pairs = defaultdict(list)
pos_counts = defaultdict(int)
for r in rows:
    for p in r.get("pairs", []):
        pid = p.get("id") or p.get("label")
        net = p.get("net_edge_bps")
        if net is None:
            continue
        v = float(net)
        pairs[pid].append(v)
        if v > 0:
            pos_counts[pid] += 1

for pid in sorted(pairs):
    vals = pairs[pid]
    pos = [v for v in vals if v > 0]
    print(
        f"{pid}: n={len(vals)} NET+={len(pos)} ({100*len(pos)/len(vals):.1f}%) "
        f"avg={sum(vals)/len(vals):+.2f} max={max(vals):+.2f} "
        f"avg_pos={sum(pos)/len(pos) if pos else 0:+.2f}"
    )
