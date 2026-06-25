#!/usr/bin/env python3
"""One-shot VPS audit: knobs, recent SL exits, open brackets."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides, effective_config_snapshot
from alpha.orders.state import BracketStateStore
from alpha.orders.types import BracketLifecycleState
from config.settings import BotConfig

KEYS = [
    "alpha_deferred_sl_enabled",
    "alpha_deferred_sl_arm_buffer_pct",
    "initial_stop_loss_pct",
    "take_profit_rr",
    "bracket_trailing_enabled",
    "alpha_risk_per_trade_pct",
    "alpha_buy_limit_offset_pct",
    "alpha_stale_pending_buy_max_drift_pct",
    "alpha_max_pending_buys",
    "inventory_target_xrp_ratio",
    "alpha_weakness_deviation",
    "alpha_reentry_enabled",
    "dry_run",
]

b = BotConfig.load()
o = OperatorRuntimeStore().load_overrides()
s = effective_config_snapshot(apply_overrides(b, o))
print("=== EFFECTIVE KNOBS ===")
for k in KEYS:
    print(f"{k}: {s.get(k)}")

store = BracketStateStore(persist_path=Path("logs/alpha_brackets.json"))
records = store.all_records()
print("\n=== BRACKET HISTORY ===")
for st, n in Counter(r.state.value for r in records).most_common():
    print(st, n)

cut = datetime.now(timezone.utc) - timedelta(hours=72)
recent_sl = [
    r
    for r in records
    if r.state == BracketLifecycleState.SL_FILLED and (r.updated_at or r.created_at) >= cut
]
recent_sl.sort(key=lambda r: r.updated_at or r.created_at, reverse=True)
print(f"\n=== SL_FILLED last 72h: {len(recent_sl)} ===")
for r in recent_sl[:12]:
    print(
        r.bracket_id[:8],
        "entry",
        r.entry_price_rlusd_per_xrp,
        "xrp",
        round(r.filled_xrp, 2),
        "at",
        (r.updated_at or r.created_at),
    )

print(f"\n=== OPEN NOW: {len(list(store.iter_open()))} ===")
for r in store.iter_open():
    sl_seq = r.sl_leg.sequence if r.sl_leg else None
    print(r.bracket_id[:8], r.state.value, "entry", r.entry_price_rlusd_per_xrp, "sl_on_book", sl_seq is not None)
