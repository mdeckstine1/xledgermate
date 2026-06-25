#!/bin/bash
set -eu
cd /root/xledgermate
.venv/bin/python <<'PY'
from pathlib import Path
from collections import Counter
from alpha.orders.state import BracketStateStore

store = BracketStateStore(persist_path=Path("logs/alpha_brackets.json"))
open_recs = list(store.iter_open())
hist = Counter(r.state.value for r in store.all_records())
print("open_brackets", len(open_recs))
print("state_hist", dict(hist))
for r in open_recs[:10]:
    print(
        r.bracket_id[:8],
        r.state.value,
        "seq", r.buy_sequence,
        "entry", r.entry_price_rlusd_per_xrp,
    )
PY
systemctl is-active xledgermate-alpha xledgermate-alpha-hud
