# Layered Quote Decision Stack

Replaces the overlapping gate + inventory `pause_bids` / `pause_asks` coupling with five explicit layers. North star unchanged: **skim-funded inventory growth on solo books** — accumulate on profitable buy edges, tolerate wide drift, protect against directional bleed without forcing the opposite side.

## Module layout (canonical)

```
strategy/quote_decision_layers/     # Canonical L1–L5 logic (sacred engine + WS)
├── types.py
├── posture.py                      # L1 — book mode, drift, fill quality
├── intent.py                       # L2 — intent selection
├── edge.py                         # L3 — net edge filter
├── bleed.py                        # L4 — side-local bleed
├── decision.py                     # L5 — final permissions
├── pipeline.py                     # run_layered_quote_decision()
└── ops_log.py                      # Grep-friendly operator visibility

experimental/ws_feed/quote_decision/  # WS I/O only — delegates to strategy stack
├── types.py                        # CycleQuoteInputs, QuotingDecision
├── _strategy_bridge.py             # CycleQuoteInputs ↔ strategy layers
├── adapter.py                      # compute_quoting_decision()
└── pipeline.py                     # run_quote_decision_pipeline()
```

**Removed (Ashigaru-Shoshin):** `layer1_posture.py` … `layer5_decision.py` under `ws_feed/quote_decision/` — logic moved to `strategy/quote_decision_layers/`.

Tests: `tests/test_strategy_quote_decision_layers.py` (canonical), `tests/test_quote_decision_layers.py`

## Layer responsibilities

### Layer 1 — Posture (`build_posture`)

Single read-only view per cycle:

| Field | Purpose |
|-------|---------|
| `book.mode` | SOLO / SPARSE / CROWDED from peer lane + solo resolver |
| `inventory.band` | Wide drift bands (±8% mild, ±16% heavy) — informational, not hard blocks |
| `buy_quality` / `sell_quality` | Recent fill economics for bleed detection |

**Peer lane → book mode defaults:**

| Condition | `book.mode` | `posture_reason` |
|-----------|-------------|------------------|
| `peer_lane_empty=True` (confirmed intel) | SOLO | `confirmed_empty` |
| No peer intel / missing fields | CROWDED (conservative) | `missing_intel` |
| `peer_lane_count==1` + low book pressure | SOLO | `sparse_low_pressure` |
| Peers present, not solo | SPARSE (≤2) or CROWDED | `crowded_default` |

**Why:** Downstream layers must not re-derive book/inventory from raw inputs.

### Layer 2 — Intent (`select_intent`)

Chooses operational intent — does **not** set final permissions:

| Intent | When |
|--------|------|
| `SOLO_ACCUMULATE_ON_EDGE` | Solo book + viable buy or sell edge (drift ignored) |
| `PATIENT_SOLO` | Solo, no edge or toxic flow — wait |
| `TWO_SIDED_SKIM` | Crowded/sparse + edge on one or both sides |
| `INVENTORY_UNLOAD` | Heavy drift + edge on unload side |
| `HOLD_OFF` | Both sides bleeding |

On solo books, inventory circuit breaker is **skipped** (Layer 5 logs `inventory_cb_skipped_solo`).

### Layer 3 — Edge (`evaluate_side_edge`)

Net profitability after fees + adverse selection buffer:

- Solo: ~2.0 bps minimum (1.0 base + 0.5 fee + 0.5 adverse)
- Crowded: ~4.0 bps minimum (stricter)
- `edge_size_mult()` scales size up for stronger edges (0.65–1.15×)

### Layer 4 — Bleed (`apply_bleed_protection`)

When recent fills on a side show toxic ratio or negative markout (≥3 fills):

- Pause **that side only**
- Never boost or enable the opposite side

### Layer 5 — Final decision (`build_layer_decision`)

Sole authority on `bid.allowed`, `ask.allowed`, `size_mult`. Combines intent, edge, bleed, inventory CB (crowded only), and tape guards.

## Operator grep guide (ops visibility)

Structured logs use prefix `QD_OPS` at INFO. Tail production logs and grep:

| Token | Meaning |
|-------|---------|
| `QD_OPS posture` | Layer 1 outcome each cycle |
| `QD_OPS peer_lane_resolve` | Intel → `peer_lane_empty` / count at consumption |
| `peer_intel=present\|missing\|stale` | Fresh scrape vs no fields vs cached-after-failure |
| `peer_lane=empty\|missing\|crowded` | Lane classification for posture |
| `solo_mode=true\|false` | Solo resolver result |
| `book_mode=solo\|sparse\|crowded` | Final L1 book mode |
| `posture_reason=confirmed_empty\|missing_intel\|sparse_low_pressure\|crowded_default` | Why that mode was chosen |
| `intent=SOLO_ACCUMULATE_ON_EDGE` | Solo accumulate selected (+ edge viability fields) |
| `inventory_cb_skipped_solo=true` | Inventory bailout deferred on solo book |
| `path=engine\|ws` | Sacred engine vs WS pure path |
| `peer_intel_source=live\|stale_cache\|missing` | Engine `decision_log` category `peer_lane` |

Example (solo empty lane):

```
QD_OPS peer_lane_resolve | peer_intel=present | peer_lane=empty | peer_lane_empty=true | peer_lane_count=0 | path=ws
QD_OPS posture | peer_intel=present | peer_lane=empty | peer_lane_empty=true | peer_lane_count=0 | solo_mode=true | book_mode=solo | posture_reason=confirmed_empty | path=ws
QD_OPS inventory_cb_skipped_solo=true | reason=solo_book_deferred_to_intent | path=ws
QD_OPS intent=SOLO_ACCUMULATE_ON_EDGE | peer_lane=empty | solo_mode=true | book_mode=solo | favor_bid=true | buy_edge_viable=true | sell_edge_viable=false | bid_edge_pct=0.042 | ask_edge_pct=0.010 | drift_band=heavy_xrp | path=ws
```

Implementation: `strategy/quote_decision_layers/ops_log.py` (shared by engine + WS bridge).

## Integration

**Sacred engine:** `strategy/quote_decision.py` → `run_layered_quote_decision(..., ops_path="engine")`

**WS pure path:** `pure_quote_path.py` → `compute_quoting_decision()` → `_strategy_bridge.run_strategy_layers(..., ops_path="ws")`

Peer lane inputs: `experimental/ws_feed/peer_lane_quoting.resolve_peer_lane_params()` (logs `peer_lane_resolve`).

## Key test scenarios

1. **Solo xrp-heavy + buy edge** → bid allowed, ask off (no deadlock)
2. **Solo no edge** → patient off, both sides blocked
3. **Buy bleed on solo** → bid paused, ask not boosted by bleed
4. **Crowded both edges** → two-sided skim
5. **Missing peer intel** → crowded default, `posture_reason=missing_intel`

Run: `python -m pytest tests/test_strategy_quote_decision_layers.py tests/test_quote_decision_layers.py -v`

## Threshold tuning (later)

Constants centralized per layer file:

- `DRIFT_MILD` / `DRIFT_HEAVY` — `posture.py`
- `MIN_EDGE_SOLO_BPS` / `MIN_EDGE_CROWDED_BPS` — `edge.py`
- Bleed thresholds — `posture.py` / `bleed.py`

Adjust after soak correlates with purpose-pass fills.
