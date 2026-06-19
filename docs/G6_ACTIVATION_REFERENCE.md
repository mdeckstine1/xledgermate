# G6 Live Activation Grading — Code Reference (v1.0)

**Authoritative spec (v1.0 diagnosis + v1.1 approved):** [`PURE_AS_CRITICAL_PATH.md` — G6 activation grading](PURE_AS_CRITICAL_PATH.md#g6-activation-grading)

**Code:** `experimental/ws_feed/live_activation_grading.py`, `experimental/ws_feed/performance_metrics.py`  
**CLI:** `python -m experimental.ws_feed.live_activation_grading [--gate]`

This file is a **short v1.0 code map** only. Do not duplicate task lists or v1.1 spec here.

---

## v1.0 tier tree (shipped)

```
dry_run?          → paper
kill_switch?      → halted
n_fills < 8       → warming_up
spread_capture = attention AND n≥8  → hold   ← gate FAIL
core all good AND n≥50               → scale_ready
core all good AND n≥25               → active
no attention grades                  → pilot
else attention (not spread)          → pilot_watch
```

**Spread capture good bar (v1.0):** n ≥ 8, pos% ≥ 70%, avg bps ≥ **8.0**. Otherwise **attention** → **hold**.

**Core metrics** for `active` / `scale_ready`: spread_capture, toxicity, drawdown, inventory_health — all **good**. Peer lane excluded from core.

---

## Session scope

When `session_boot_utc` is on runtime, HUD grades fills since boot only (0–7 → `warming_up`). Cumulative CSV rows remain in file; activation uses session scope.

**Operator:** `hold` is advisory — use kill switch to stop quoting. See critical path for v1.1 calibration plan.
