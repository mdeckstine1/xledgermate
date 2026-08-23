#!/usr/bin/env python3
import json
from pathlib import Path

p = Path("logs/alpha_runtime_state.json")
raw = p.read_text(encoding="utf-8")
print("bytes", len(raw.encode("utf-8")))
d = json.loads(raw)
print("top keys", len(d))


def size_of(obj) -> int:
    return len(json.dumps(obj, default=str).encode("utf-8"))


rows = []
for k, v in d.items():
    n = 0
    if isinstance(v, (list, dict)):
        n = len(v)
    rows.append((size_of(v), n, k, type(v).__name__))
rows.sort(reverse=True)
print("largest fields:")
for sz, n, k, t in rows[:20]:
    print(f"  {sz:9d} bytes  n={n:<8} {t:6} {k}")
print("updated_utc", d.get("updated_utc"))
print("xrp", d.get("xrp"), "mid", d.get("mid"))
print("bag available", (d.get("bag_growth") or {}).get("available"))
