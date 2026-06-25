#!/bin/bash
set -eu
cd /root/xledgermate

echo "=== services ==="
systemctl is-active xledgermate-alpha xledgermate-alpha-hud

echo ""
echo "=== portfolio / mid (runtime state) ==="
.venv/bin/python <<'PY'
import json
from pathlib import Path
p = Path("logs/alpha_runtime_state.json")
if p.is_file():
    d = json.loads(p.read_text(encoding="utf-8"))
    print("updated_utc", d.get("updated_utc"))
    print("mid", d.get("mid"), "xrp", d.get("xrp"), "rlusd", d.get("rlusd"))
    print("portfolio_xrp_equiv", d.get("portfolio_xrp_equiv"))
    inv = d.get("inventory") or {}
    print("inventory", inv.get("label"), "dev", inv.get("deviation"))
    dec = d.get("decision") or {}
    print("decision", dec.get("action"), dec.get("reason"))
    br = d.get("brackets") or {}
    summ = br.get("summary") or {}
    print("hud_bracket_summary", summ)
    recs = br.get("records") or []
    print("hud_bracket_records", len(recs))
    for r in recs[:12]:
        print(
            " ",
            r.get("bracket_id"),
            r.get("state"),
            "entry", r.get("entry"),
            "filled", r.get("filled_xrp"),
            "buy_seq", r.get("buy_sequence"),
            "tp", r.get("tp_price"),
            "sl", r.get("sl_price"),
            "be", r.get("breakeven_passed"),
        )
    print("open_offers_count", len(d.get("open_offers") or []))
    for o in (d.get("open_offers") or [])[:8]:
        print("  offer", o.get("side"), o.get("price"), "size", o.get("size_xrp"), "seq", o.get("sequence"))
PY

echo ""
echo "=== bracket store (disk) ==="
.venv/bin/python <<'PY'
import json
from pathlib import Path
from collections import Counter
from alpha.orders.state import BracketStateStore
from alpha.orders.types import BracketLifecycleState

store = BracketStateStore(persist_path=Path("logs/alpha_brackets.json"))
open_recs = list(store.iter_open())
hist = Counter(r.state.value for r in store.all_records())
print("state_hist", dict(hist))
print("open_count", len(open_recs))
for r in open_recs[:15]:
    print(
        r.bracket_id[:8],
        r.state.value,
        "buy_seq", r.buy_sequence,
        "entry", r.entry_price_rlusd_per_xrp,
        "filled", r.filled_xrp,
        "target", r.target_size_xrp,
        "tp_seq", r.tp_leg.sequence if r.tp_leg else None,
        "sl_seq", r.sl_leg.sequence if r.sl_leg else None,
    )
PY

echo ""
echo "=== recent fills / bracket events (activity 48h) ==="
grep -E '"event":|"bracket_|entry_buy|buy_filled|leg_fill|place_legs|place_bid|execution' logs/alpha_activity.jsonl 2>/dev/null | tail -30 || true

echo ""
echo "=== journal fills last 6h ==="
journalctl -u xledgermate-alpha --since '6 hours ago' --no-pager 2>/dev/null | grep -E 'bracket_buy_filled|bracket_register|entry_buy_placed|bracket_place_legs|bracket_leg_fill|execution.*place_bid|place_bid|pending_buy|order_manager_sync' | tail -40 || true

echo ""
echo "=== operator knobs (effective) ==="
.venv/bin/python <<'PY'
from config.settings import BotConfig
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides, effective_config_snapshot

b = BotConfig.load()
o = OperatorRuntimeStore().load_overrides()
e = apply_overrides(b, o)
s = effective_config_snapshot(e)
keys = [
    "alpha_max_pending_buys",
    "alpha_buy_limit_offset_pct",
    "alpha_stale_pending_buy_max_drift_pct",
    "alpha_stale_pending_buy_enabled",
    "initial_stop_loss_pct",
    "take_profit_rr",
    "bracket_trailing_enabled",
    "alpha_rlusd_price_decimals",
]
for k in keys:
    print(k, s.get(k))
PY

echo ""
echo "=== recent sl_filled (last 5, not shown in HUD) ==="
.venv/bin/python <<'PY'
from pathlib import Path
from alpha.orders.state import BracketStateStore
from alpha.orders.types import BracketLifecycleState

store = BracketStateStore(persist_path=Path("logs/alpha_brackets.json"))
sl = [r for r in store.all_records() if r.state == BracketLifecycleState.SL_FILLED]
sl.sort(key=lambda r: r.updated_at or r.created_at, reverse=True)
for r in sl[:5]:
    print(
        r.bracket_id[:8],
        "entry", r.entry_price_rlusd_per_xrp,
        "filled", r.filled_xrp,
        "updated", r.updated_at,
    )
PY

echo ""
echo "=== ledger open offers vs tracked ==="
.venv/bin/python <<'PY'
import asyncio
import json
from config.settings import BotConfig
from alpha.dry_run import DryRunGuard
from alpha.ledger.xrpl_adapter import XrplLedgerAdapter
from alpha.orders.state import BracketStateStore
from alpha.orders.types import BracketLifecycleState
from pathlib import Path

async def main():
    cfg = BotConfig.load()
    g = DryRunGuard(dry_run=cfg.dry_run, network=cfg.network)
    ad = XrplLedgerAdapter.from_config(cfg, dry_run_guard=g)
    await ad.connect()
    offers = await ad.get_open_offers()
    print("ledger_offers", len(offers))
    for o in offers:
        print(" ", o.get("side"), o.get("price"), "xrp", round(float(o.get("size_xrp", 0)), 4), "seq", o.get("sequence"))
    store = BracketStateStore(persist_path=Path("logs/alpha_brackets.json"))
    pending = [r for r in store.iter_open() if r.state == BracketLifecycleState.PENDING_BUY]
    active = [r for r in store.iter_open() if r.state == BracketLifecycleState.BRACKET_ACTIVE]
    print("tracked_pending", len(pending), "tracked_active", len(active))
    offer_seqs = {int(o["sequence"]) for o in offers if o.get("sequence")}
    for r in pending:
        on_book = r.buy_sequence in offer_seqs if r.buy_sequence else False
        print(" pending", r.bracket_id[:8], "seq", r.buy_sequence, "entry", r.entry_price_rlusd_per_xrp, "on_book", on_book)
asyncio.run(main())
PY
