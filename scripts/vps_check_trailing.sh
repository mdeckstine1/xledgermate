#!/bin/bash
set -eu
cd /root/xledgermate
echo "=== trailing config ==="
.venv/bin/python <<'PY'
import json
from pathlib import Path
from config.settings import BotConfig
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides, effective_config_snapshot

base = BotConfig.load()
ov = OperatorRuntimeStore().load_overrides()
eff = apply_overrides(base, ov)
snap = effective_config_snapshot(eff)
for k in (
    "bracket_trailing_enabled",
    "trailing_step_pct",
    "alpha_rlusd_price_decimals",
    "breakout_confirmation_tf",
    "breakout_lookback_candles",
):
    print(k, snap.get(k, getattr(eff, k, None)))
PY
echo "=== active brackets trailing state ==="
.venv/bin/python <<'PY'
import json
from pathlib import Path
from alpha.orders.state import BracketStateStore
from alpha.orders.types import BracketLifecycleState

store = BracketStateStore(persist_path=Path("logs/alpha_brackets.json"))
active = [r for r in store.iter_open() if r.state == BracketLifecycleState.BRACKET_ACTIVE]
print("bracket_active", len(active))
for r in active[:8]:
    print(
        r.bracket_id[:8],
        "entry", r.entry_price_rlusd_per_xrp,
        "be", r.breakeven_passed,
        "bo", r.breakout_confirmed,
        "mode", r.mode.value if r.mode else None,
        "peak", r.peak_mid_rlusd_per_xrp,
        "sl", r.sl_leg.price_rlusd_per_xrp if r.sl_leg else None,
        "tp", r.tp_leg.price_rlusd_per_xrp if r.tp_leg else None,
        "sl_seq", r.sl_leg.sequence if r.sl_leg else None,
        "tp_seq", r.tp_leg.sequence if r.tp_leg else None,
    )
PY
echo "=== recent trailing logs ==="
grep -E "trailing_|bracket_trail|bracket_breakeven|breakout_confirmed" logs/alpha_activity.jsonl 2>/dev/null | tail -20 || true
journalctl -u xledgermate-alpha -n 300 --no-pager 2>/dev/null | grep -E "trailing_|bracket_trail|bracket_breakeven|breakout_confirmed" | tail -25 || true
