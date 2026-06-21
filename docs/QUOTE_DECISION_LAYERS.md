# Layered Quote Decision Stack

Replaces the overlapping gate + inventory `pause_bids` / `pause_asks` coupling with five explicit layers. North star unchanged: **skim-funded inventory growth on solo books** — accumulate on profitable buy edges, tolerate wide drift, protect against directional bleed without forcing the opposite side.

## Module layout

```
experimental/ws_feed/quote_decision/
├── types.py           # Dataclasses, enums, CycleQuoteInputs, QuotingDecision
├── layer1_posture.py  # Read-only posture snapshot (book, drift, fill quality)
├── layer2_intent.py   # Policy intent selection (what we're trying to do)
├── layer3_edge.py     # Net profitable edge filter (fees + adverse buffer)
├── layer4_bleed.py    # Side-local bleed protection (no opposite-side boost)
├── layer5_decision.py # Final bid/ask permissions — sole authority
├── pipeline.py        # run_quote_decision_pipeline()
└── adapter.py         # compute_quoting_decision(), shadow_compare_legacy()
```

Tests: `tests/test_quote_decision_layers.py`

## Layer responsibilities

### Layer 1 — Posture (`build_posture_snapshot`)

Single read-only view per cycle:

| Field | Purpose |
|-------|---------|
| `book.mode` | SOLO / SPARSE / CROWDED from peer lane count |
| `inventory.band` | Wide drift bands (±8% mild, ±16% heavy) — informational, not hard blocks |
| `buy_quality` / `sell_quality` | Recent fill economics for bleed detection |

**Why:** Downstream layers must not re-derive book/inventory from raw inputs. Prevents cascade bugs when one layer tweaks a shared flag another layer reads.

### Layer 2 — Intent (`select_quote_intent`)

Chooses operational intent — does **not** set final permissions:

| Intent | When |
|--------|------|
| `SOLO_ACCUMULATE_ON_EDGE` | Solo book + viable buy edge (default solo posture) |
| `PATIENT_SOLO` | Solo, no edge or toxic flow — wait |
| `TWO_SIDED_SKIM` | Crowded/sparse + edge on one or both sides |
| `PROTECT_BLEED` | Reserved for future explicit bleed posture labeling |
| `HOLD_OFF` | Both sides bleeding |

**Principle 3:** Solo + good buy edge → accumulate even when inventory is xrp-heavy drifted.

**Principle 4:** Single-side bleed is **not** handled here — Layer 4 pauses that side only without changing intent or enabling the opposite side.

### Layer 3 — Edge (`evaluate_edge`)

Net profitability after fees + adverse selection buffer:

- Solo: ~2.0 bps minimum (1.0 base + 0.5 fee + 0.5 adverse)
- Crowded: ~4.0 bps minimum (stricter)
- `edge_size_mult()` scales size up for stronger edges (0.65–1.15×)

### Layer 4 — Bleed (`apply_bleed_protection`)

When recent fills on a side show negative capture (≥3 fills, session cap < 0):

- Pause **that side only** (`bid_allowed_override=False` or ask equivalent)
- Never boost or enable the opposite side

Fixes the `effective_quote_sides` bailout bug where `pause_bids=true` accidentally forced ask-only quoting.

### Layer 5 — Final decision (`build_final_quoting_decision`)

Sole authority on `bid.allowed`, `ask.allowed`, `size_mult`. Combines intent, edge, bleed, and reservation allows.

Output type: `QuotingDecision` with `SidePermission` per side — **not** shared pause flags.

## Integration (Phase 0 — shadow)

`pure_quote_path.py` now runs the pipeline each cycle after L1 touch prices are known:

```python
qd = compute_quoting_decision(...)
shadow = shadow_compare_legacy(qd, legacy_pause_bids=..., legacy_pause_asks=..., ...)
```

Shadow fields on runtime/intel:

- `qd_intent`, `qd_bid_allowed`, `qd_ask_allowed`, `qd_would_quote`
- `qd_conflicts` — disagreements with legacy pause merge
- `qd_layer_summary`

Legacy ladder posting is unchanged. Use `qd_conflicts` in soak to validate before cutover.

## Migration plan

| Phase | Action |
|-------|--------|
| **0 (done)** | Shadow log QD vs legacy; soak on solo book; watch `qd_conflicts` |
| **1 (v2.2.0 live)** | Use `qd.bid/ask.allowed` + `size_mult` for ladder; drop inv `pause_*` merge |
| **2 (v2.2.1–2.2.2 done)** | Deleted gate modules; QD-only observability in runtime/intel |
| **3 (v2.2.3 done)** | Retired `pause_bids`/`pause_asks` — `qd_bid_allowed`/`qd_ask_allowed` everywhere |

### Phase 1 cutover sketch

```python
# Replace:
quote_bid, quote_ask, _ = effective_quote_sides(..., pause_bids=..., pause_asks=...)
# With:
quote_bid = qd.bid.allowed and allow_bid
quote_ask = qd.ask.allowed and allow_ask
bid_size *= qd.bid.size_mult
ask_size *= qd.ask.size_mult
```

Pass `recent_fill_records` from engine fill tracker for Layer 4 bleed accuracy.

## Files to review / retire after migration

| File | Issue |
|------|-------|
| `experimental/ws_feed/reservation_metrics.py` | `effective_quote_sides()` — inv bailout forces opposite side |
| `experimental/ws_feed/buy_edge_gate.py` | A2.2 — merged into Layer 3 |
| `experimental/ws_feed/acquire_ask_brake.py` | A2.3 — caused deadlock with inv pause_bids |
| `experimental/ws_feed/sell_edge_gate.py` | A2.3b — merged into Layer 3 |
| `experimental/ws_feed/pure_inventory_policy.py` | `pause_*` on ladder |
| `risk/inventory_limits.py` | xrp-heavy → pause_bids ("unload via asks") |
| `experimental/ws_feed/ws_pure_engine.py` | `_sync_offers` pause_asks param |
| `core/runtime_state.py`, `intel_decisions_log.py` | Legacy pause fields |

## Key test scenarios

1. **Solo xrp-heavy + buy edge** → bid allowed, ask off (no deadlock)
2. **Solo no edge** → patient off, both sides blocked
3. **Buy bleed on solo** → bid paused, ask not boosted by bleed
4. **Crowded both edges** → two-sided skim
5. **Shadow conflict** → legacy both paused, QD bid allowed at edge

Run: `python -m pytest tests/test_quote_decision_layers.py -v`

## Threshold tuning (later)

All constants are centralized per layer file:

- `DRIFT_MILD` / `DRIFT_HEAVY` — `layer1_posture.py`
- `MIN_EDGE_SOLO_BPS` / `MIN_EDGE_CROWDED_BPS` — `layer3_edge.py`
- `BLEED_RECENT_FILLS_MIN`, `BLEED_CAPTURE_XRP` — `layer1_posture.py` / `layer4_bleed.py`

Adjust after shadow soak correlates with purpose-pass fills.
