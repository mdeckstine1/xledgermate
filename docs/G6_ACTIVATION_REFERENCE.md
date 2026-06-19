# G6 Live Activation Grading — Code Reference

**Authoritative spec:** [`PURE_AS_CRITICAL_PATH.md` — G6 activation grading](PURE_AS_CRITICAL_PATH.md#g6-activation-grading)

**Code:** `experimental/ws_feed/live_activation_grading.py`, `experimental/ws_feed/performance_metrics.py`  
**CLI:** `python -m experimental.ws_feed.live_activation_grading [--gate]`  
**Shipped:** **v1.1.0** (HUD-only)

---

## v1.1 tier tree (shipped)

```
dry_run?                    → paper
kill_switch?                → halted
n_fills < 8                 → warming_up
spread_capture = thin_edge  → thin_edge   ← gate PASS (yellow)
spread_capture = attention:
  n < 15                    → pilot_watch ← gate PASS
  bad economics (n ≥ 15)    → hold        ← gate FAIL
  else thin positive        → pilot_watch ← gate PASS
core all good AND n≥50      → scale_ready (spread must be good, not thin_edge)
core all good AND n≥25      → active
no attention grades         → pilot
else attention (not spread) → pilot_watch
```

**Spread grades:** `good` (≥70% pos, ≥8 bps) · `thin_edge` (≥70% pos, 5–8 bps) · `attention` · `unknown` (n&lt;8).

**Bad economics (hold):** avg bps &lt; 0 · pos% &lt; 50% · (avg bps &lt; 3 and pos% &lt; 70%).

**Session scope:** fills since `session_boot_utc` when present. **Operator:** `hold` is advisory — kill switch stops quoting.
