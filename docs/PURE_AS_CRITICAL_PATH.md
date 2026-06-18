# Pure A-S Critical Path

**Status:** Live soak on VPS — **WS + pure A-S** (`ws-engine`) · **HUD** `:8765`  
**Version:** v2.1.17 · **Branch:** `Ashigaru-Kaizen-II`  
**Last updated:** 2026-06-18

Single checklist for WS + pure A-S. Other docs link here — do not duplicate task lists.

**Soak = timed test run.** Collect fills, toxicity, markout, G6 grades under real quoting. **M2–M5 shipped v2.1.15** (2026-06-18). **G7 execution envelope shipped v2.1.16+.** Post-deploy gates + baseline snapshot **2026-06-18** (`scripts/post_deploy_snapshot.py` on VPS).

---

## Active TODO

### Now (operator)

| # | Task | Status |
|---|------|--------|
| — | Post-deploy gates + 60-fill checkpoint | [x] done 2026-06-18 |
| — | G7 v1 soak A/B validation | [x] Good enough for current scale (operator call 2026-06-18). Keep eye on live data. Run until next engine restart needed. |
| — | Watch G6 tier, toxic@30s, markout@30s (v2.1.17 soak) | ongoing |
| — | **Queue review** — vs-touch bps, cancel/fill, fill age (G7 A/B) | [x] baseline captured + 61-fill data in intel JSONL |
| — | **Skim Δ** vs wallet Δ | [x] improved — coherence guard + HUD no longer overwrites |
| — | HUD: G7 queue + "Queue vs touch" visible in Session fills card | [x] HUD-only restart (soak-safe) now fully synthesizes G7 posture via compute_execution_envelope (using live inventory_label + g2_spread_mult) + queue visibility from planned ladder or suggested L1. Both rows populate immediately. (Authoritative on-ledger visibility numbers arrive after engine restart.) |

**G7 soak checkpoint (2026-06-18, ~61 session fills on v2.1.17):** C2 sample_history gate now **PASS** (123 min, 86.8% presence, flip 0.141). G6 still `pilot_watch` (toxicity + empty peer lane) but gate PASS. Session Skim slipped to −0.106 XRP during xrp_heavy leg (adverse flow on the join-ask side) then inventory normalized. Markout@30s recovered to ~0. See A/B below. Full snapshot in `logs/post_deploy_snapshot.txt`. After HUD restart + hard refresh you will see:
- G7 queue: the correct decision e.g. "bid passive 9.0bps · ask join 3.4bps" (or ×G2 when braking), computed on the HUD side from the current inventory_label + g2_spread_mult that the engine *is* already writing.
- Queue vs touch: worst-bps or "at touch / back / join" summary computed from the planned quote ladder vs BBO in the snapshot (proxy until engine restart writes the real on-ledger visibility).
Full authoritative G7 + on-ledger visibility numbers will flow after the next engine restart (when the ws-engine writes them into runtime_state.json).

### Next engine window — G7 execution envelope

| # | Item | Notes |
|---|------|--------|
| 1 | **G7** Execution envelope | **shipped** — `execution_envelope.py`; per-side touch × `g2.spread_mult` |
| 2 | Per-side touch | xrp-heavy → ask 3 bps / bid 8 bps; rlusd-heavy → opposite |
| 3 | G2 coupling | `backoff × max(1, g2.spread_mult)` |
| 4 | Visibility + debug | `worst_vs_touch_bps`, `quote_visibility_summary`, `g7_summary` on runtime |
| 5 | Validation | Soak A/B vs v2.1.15 — **in progress** (baseline 2026-06-18) |

**Blocker:** [x] accumulate v2.1.16+ data — done at 61 fills.  
**Status:** [x] G7 v1 — Good enough (see verdict below). Keep monitoring live data. No engine restart until necessary.

**Order:** monitor markout/toxic/cancel vs baseline → sign off or tune envelope.

### G7 A/B at 61-fill checkpoint (this run)

| Metric                  | v2.1.15 / early baseline (from initial soak data) | v2.1.17 this run (~61 session fills) | Notes |
|-------------------------|---------------------------------------------------|--------------------------------------|-------|
| cancel/fill             | ~1.5                                              | 1.77                                 | Slightly higher churn under G2 brakes |
| worst_vs_touch_bps      | ~8.0                                              | ~9.0 (during xrp_heavy; symmetric 9/9 when balanced) | G7 widens passive side as designed |
| markout@30s             | −0.013%                                           | −0.001% (recovered)                  | Adverse during heavy leg, improved as inventory normalized |
| toxic@30s               | ~14% (early)                                      | 26% (peak during skew)               | G2 correctly cautious (size×0.75, spread×1.12) |
| G7 posture              | balanced 8/8                                      | xrp_heavy asymmetric (bid passive 9, ask join ~3.4 ×G2) → balanced 9/9 | Execution knob reacting to inventory; A-S reservation untouched |
| Skim Δ (session)        | small positive early                              | −0.106 (slipped on adverse ask hits while heavy) | Expected cost of "join rebalance side" during one-sided flow |
| C2 gate                 | FAIL (short window, high flips)                   | PASS (123 min)                       | Longer stable run met flip-rate bar |
| Peer lane               | 0                                                 | 0                                    | No competitors at pilot size |
| Inventory behavior      | —                                                 | xrp_heavy → balanced without manual rebalance | G7 + G2 + natural flow handled it |

**Design note:** Pure A-S reservation math (would_quote only when inside live BBO, optimal spread from γ/κ/vol) remains the sacred core. G7 is a thin execution envelope (posted-price backoff only) + G2 as dynamic brake on size/spread. Other knobs (pressure, book age, G4) influence inputs only — never override the inside-book guard.

**Discipline rule:** A-S is what we do. G7 + G2 are execution only. The HUD self-audit and intel exist to verify the bot is executing the design (inventory-driven asymmetry, G2 coupling, reservation untouched). Visibility costs and regime signals are observed, not used for reactive overrides. We win by discipline.

**G7 v1 Checkpoint Verdict (2026-06-18):**  
[x] Good enough for current pilot scale.  

The envelope behaved as designed: wider passive side while xrp_heavy produced the expected visibility cost (~9 bps) and temporary session Skim drag on adverse flow. Inventory self-corrected without manual action. Markout recovered. C2 gate now passes. A-S core (reservation + inside-BBO `would_quote`) remained untouched throughout.  

Live data will continue to be watched. No engine restart until needed. Future windows can explore the rlusd_heavy mirror or longer-horizon stats if desired.

### Metrics to watch (next 24–48 hours, while this run continues)

Focus on consistency rather than perfection at pilot size:

- **Session Skim Δ** — direction and stability (look for flattening or positive drift as inventory stays near target).
- **mean_markout_30s_pct** — trend (ideally staying > −0.02% or improving).
- **toxic_ratio_30s** — staying ≤ 28–30% or trending down.
- **cancel_per_fill** — flat or slowly improving (currently ~1.77).
- **G7 posture vs inventory** — when inventory_label is "balanced", both sides should be symmetric (~8–9 bps). Confirm via HUD + runtime.
- **Queue vs touch / worst_vs_touch_bps** — visible in Session fills card after HUD restart + hard refresh.
- **Fills per hour** — rough consistency (thin book → 1–3/hr is normal).
- **Wallet balance PnL (session_pnl_balance_delta_xrp)** — the real "warm fuzzy" metric for E3.

Re-run `scripts/post_deploy_snapshot.py` and `live_activation_grading` periodically. Save dated outputs.

<details>
<summary><strong>G7 draft — execution envelope</strong> (spec v1 — minimal moving parts)</summary>

### Design goal

**Fewer parts, fewer breaks, easier debug.** No mode state machine, no hysteresis counters, no Grok/local NLP in the engine loop. G7 is **not a second brain** — it extends **G2** with **where** we post (per-side touch) and **what we log** (visibility).

### Sacred boundary (unchanged)

Execution only. Never changes `as_reservation`, `as_optimal_spread_pct`, or `would_quote`. Posted prices still clamp: bid ≤ best bid, ask ≥ best ask.

### v2.1.15 baseline (why we’re changing)

| Observation | Value | Fix in G7 |
|-------------|-------|-----------|
| Both sides ~8 bps off touch | uniform backoff | **Asymmetric:** join rebalance side only |
| xrp-heavy + 1 XRP bids | invisible bid, fat ask | Widen bid more; ask joins touch |
| G2 already widens on toxic | `spread_mult` | **Reuse** — don’t duplicate triggers |
| `preserve_touch` + mid move | in `resolve_ws_sync_tolerances` | **Keep** — no new sync state machine |

### The whole spec (three rules)

**Rule A — Per-side touch backoff (inventory)**

After `compute_avellaneda_quote`, set posted distance from touch **per side**:

| `inventory_label` | Bid backoff | Ask backoff | Intent |
|-------------------|-------------|-------------|--------|
| `xrp_heavy` / skew > 0.12 | **8 bps** | **3 bps** | Want RLUSD → join ask queue |
| `rlusd_heavy` / skew < −0.12 | **3 bps** | **8 bps** | Want XRP → join bid queue |
| else (balanced) | **8 bps** | **8 bps** | Match v2.1.15 default |

```
bid_post  = best_bid  × (1 − bid_backoff_bps  / 10_000)
ask_post  = best_ask  × (1 + ask_backoff_bps  / 10_000)
```

Min size: passive side may stay at `min_order_size_xrp`; join side uses full L1 from `dynamic_sizing` (already inventory-skewed).

**Rule B — Couple to G2 only (no separate toxic triggers)**

Multiply both backoffs by `max(1.0, g2.spread_mult)` from `compute_g2_adjustments`. When G2 is neutral, multiplier is 1.0 → no change. When G2 brakes, quotes move back automatically. **Do not** add parallel toxic/markout thresholds for G7.

**Rule C — Sync discipline (existing code, document don’t duplicate)**

`ws_pure_engine.resolve_ws_sync_tolerances` already sets `preserve_touch_queue` off on mid move / G2. G7 does **not** add triggers. Optional small improvement (same PR or follow-up): skip cancel/place when intent within tolerance **and** touch moved &lt; 2 bps.

### What we explicitly do NOT build

| Cut | Reason |
|-----|--------|
| neutral / aggressive / defensive modes | Hysteresis hard to tune and debug |
| Grok / NLP in engine loop | Non-deterministic; keep HUD/F4 offline |
| Separate `g7_active` state machine | `g2_summary` + visibility fields are enough |
| `build_g7_transition_intel_record` | Log envelope outputs on existing cycle intel row |

### Runtime / HUD (debug surface)

Single line operator can read:

| Field | Example |
|-------|---------|
| `g7_summary` | `G7 xrp_heavy: bid 8bps ask 3bps × G2 1.12` |
| `bid_touch_backoff_bps` / `ask_touch_backoff_bps` | 8.0 / 3.4 |
| `worst_vs_touch_bps` | from `quote_visibility()` |
| `quote_visibility_summary` | `ask at touch; bid 8bps back` |
| `g2_grade` / `g2_spread_mult` | already on runtime — primary brake indicator |

### Implementation (one module, one call site)

| Step | File |
|------|------|
| `compute_execution_envelope(g2, inventory_label, inventory_skew)` → bid/ask backoff bps | `experimental/ws_feed/execution_envelope.py` |
| Apply posted prices after A-S quote | `pure_quote_path.py` (post `compute_avellaneda_quote`) |
| Enrich visibility | `_persist_cycle` in `ws_pure_engine.py` via `utils/book_visibility.py` |
| Tests | `tests/test_execution_envelope.py` — table-driven per inventory + g2 mult |

### Validation

1. Unit tests: inventory rows + G2 mult 1.0 / 1.25 → expected bps  
2. Tester dry-run: log `g7_summary` + `worst_vs_touch_bps` each sample  
3. VPS soak A/B: v2.1.15 symmetric 8 bps vs G7 envelope  
4. **Gate:** markout@30s not worse than baseline; toxic@30s not &gt; +5 pp; cancel/fill not higher  

### Future (out of G7 v1 — only if soak asks for it)

- Markout-adaptive backoff (needs more M2 fill history)  
- F4 Grok correlation (offline)  
- Merge `execution_envelope` into `spread_quality_scaler.py` if we want one file later  

</details>

### Segment end — M2–M5 (shipped v2.1.15)

| # | Item | Notes |
|---|------|--------|
| 1 | **M2** Fill age live | **shipped** — `OfferAgeTracker` in `_sync_offers` + `_detect_fills`; HUD `effective_quote_age_at_fill_seconds` |
| 2 | **M3** Stale-cross flag | **shipped** — `reservation_crossed_after_ws_sample` pre/post intel BBO in `_run_cycle` |
| 3 | **M4** Production `sample_history` | **shipped** — `append_runtime_sample` in `_persist_cycle`; C1 soak metrics on runtime export |
| 4 | **M5** `as_safety` on production path | **confirmed** — `enforce_reservation_gate` in `pure_quote_path.py` (no engine change) |
| 5 | **Fill economics** | `fill_detection.py` implied price — **deploy with engine restart** |
| 6 | Post-deploy gates | `fill_quote_age_report.py`, `ws_runtime_analysis`, `live_activation_grading --gate` |

**Order:** deploy M2–M5 bundle → engine restart → post-deploy reports + G6 `--gate`.

### After segment (engine or separate windows)

| # | Item | Blocker |
|---|------|---------|
| **G7** | **Execution envelope** — shipped v2.1.16 | [x] soak A/B data at 61 fills; [x] Good enough for current scale (keep watching live data) |
| P1–P3 | Per-peer history, tx correlation, full L1–L3 in runtime | Engine + soak data |
| P4–P6 | Structured `PeerBriefing`, G4 nudges, F2 engine hook | P1 + markout |
| P7 | Async submit / tx rate instrumentation (L1–L4) | M2/M3 review |
| I1–I4 | Regime channel (book-wide pressure, damped) | Empty peer lane validated |
| I7 | In-band peer automation path | Real touch-band peers |
| E3 | 11k funding + rebalance execution | [ ] waiting for consistent gain + warm fuzzy on the bot (on operator timeline) |
| H3–H7 | Arb paper/live, USDC, path scanner | G6 pass + H1 monitor data |
| F4 | Grok suggestion → outcome correlation | Fill attribution |
| M6 | Per-sequence quote age | After M2 soak review |

---

## Soak-safe — complete (2026-06-17)

HUD-only deploys (`xledgermate-ws-hud` restart OK). No further soak-safe code required.

| Area | Shipped |
|------|---------|
| **M1** | Res→BBO delta, inside L1, hourly Telegram |
| **M2/M3 prep** | `fill_quote_age_report.py`, `offer_age_tracker.py`, `stale_cross.py`, analysis schema |
| **Intel HUD** | I5 side skew, I6 regime vs peer, F1 nicknames, F3a/F3b Grok briefing, F4 JSONL, F2 advisory stub |
| **Reports** | 11 soak-safe reports tab (`soak_dashboard`, `soak_dashboard_narrative`, `grok_suggestions`, `clob_amm_monitor`, …) |
| **H1/H2** | Read-only CLOB vs AMM monitor + `amm_provider.py` |
| **HUD ops** | Inventory nav restored; Metrics toxicity gray-zone fix; **Skim Δ** (not wallet/deposit); Wallet Δ on Inventory |

### Deploy discipline

| Change | Restart | During soak? |
|--------|---------|--------------|
| HUD / `ws_hud_production.py` / reports / `performance_metrics.py` | `xledgermate-ws-hud` | Yes |
| `fill_detection.py` / `fill_economics.py` / balance-delta coherence guard | `xledgermate` (engine) + `xledgermate-ws-hud` for CSV skim display | Yes (HUD-only until engine pull) |
| `ws_pure_engine.py` (M2–M5, fill age, `session_spread_capture_xrp`) | `xledgermate` | **No** — segment end |
| `vps_deploy_ashigaru.sh` full | ws-engine + HUD | **No** unless planned |

**Sacred rule:** `would_quote` = reservation inside live BBO. Measurement and HUD never override A-S math.

---

## Skim Δ / PnL display (operator)

| HUD field | Meaning |
|-----------|---------|
| **Skim Δ** | Session spread capture from **engine** `session_spread_capture_xrp` (incoherent balance-delta fills rejected; HUD does not overwrite with CSV sum) |
| **Wallet Δ** (Inventory) | Portfolio change since session start — **includes deposits** |
| **Metrics → Total capture** | CSV sum (all-time in month file); grades use toxic@30s |

Balance-delta fills use implied price when coherent (±25% of mid, BBO band, min 0.01 XRP). Bogus composite deltas are rejected at detect time and excluded from G6 skim grading. Historical CSV rows may remain; session HUD uses engine counters only.

---

## Recent ships (2026-06-18)

| Commit | What |
|--------|------|
| `2fb597d` | Balance-delta coherence guard — reject nonsense implied prices before fill log |
| `b463887` | HUD Skim Δ fix — stop CSV overwrite; strict `@ mid` for economics; session fills display |
| `4c38c65` / `b420437` | USD portfolio in sidebar; metric row alignment |
| `5b85263` + follow-ups | HUD "Analyze our bot" self-audit + prose reports (no JSON echo); G7 fields now explicitly in HUD payload for session fills card |

Post-deploy + 60-fill checkpoint: `scripts/post_deploy_snapshot.py` + `live_activation_grading --gate`. G7 A/B data logged via `ws_as_version` in intel JSONL. G7 queue/visibility now visible in HUD Session fills card (hard refresh recommended).

---

## Completed phases (reference)

<details>
<summary>Phase 0–G — foundation through live activation (click to expand)</summary>

- **0:** WS probe, pure A-S, sacred economics, live tester + HUD, Grok analyze
- **A:** Sacred A/B, `ws_runtime_analysis`, `as_calibration_grok`
- **B:** `PureQuotePath`, dynamic sizing, book-age modulator, zero-quote notes
- **C:** C1 pressure/presence metrics, C2 soak gate
- **D:** WS feed hardening, dry-run offers, Streamlit compare, swap readiness
- **E:** E1 live VPS ws-engine, E1.5 gate PASS, E2 merge, E4 `WsPureTradingEngine`
- **G:** G1–G6 peer lane, G2 scaler, intel JSONL, G4 quoting, G5 replay, G6 activation grading · **G7** execution envelope (planned)

</details>

---

## Direction

| Legacy | Committed |
|--------|-----------|
| HTTP BookOffers poll | WS `BookFeed` |
| Hard `market_edge_met` vetoes | Pure A-S reservation inside book |
| Grok as override | Advisory inputs only (vol, spread anchor, size) |

---

## Doc map

| File | Use |
|------|-----|
| **This file** | Critical path + TODO |
| [`PURE_AS_DEVELOPMENT_LOG.md`](PURE_AS_DEVELOPMENT_LOG.md) | **Posterity** — how we got here, soak learnings, decisions |
| [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md) | Tester + HUD + Grok |
| [`PHASE_E_VPS_RUNBOOK.md`](PHASE_E_VPS_RUNBOOK.md) | VPS swap ladder |
| [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md) | Branch roles |
| [`../experimental/ws_feed/WS_HANDOFF.md`](../experimental/ws_feed/WS_HANDOFF.md) | Architecture |
| [`../groks input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md`](../groks%20input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md) | Gate metrics |
| [`../experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md`](../experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md) | Phase G detail |

**Lab:**

```powershell
cd C:\Users\micha\xledgermate
.\.venv\Scripts\Activate.ps1
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 0 --verbose
```

Open http://127.0.0.1:8765

---

## Key files

```
experimental/ws_feed/ws_pure_engine.py       # VPS production loop
experimental/ws_feed/ws_hud_production.py    # HUD mirror (:8765)
experimental/ws_feed/hud/index.html          # Operator UI
monitoring/fill_detection.py               # Balance-delta fill infer
monitoring/fill_economics.py               # Spread capture + skim estimate
scripts/ws_path_session_report.py          # E1.5 + session skim CSV
experimental/ws_feed/performance_metrics.py  # G3 Metrics grades
experimental/ws_feed/live_activation_grading.py  # G6 tier
experimental/ws_feed/execution_envelope.py   # G7 per-side touch × G2
experimental/ws_feed/reservation_metrics.py  # M1
experimental/ws_feed/as_safety.py          # M5 (deploy at segment end)
experimental/arb/clob_amm_monitor.py       # H1 read-only
scripts/post_deploy_snapshot.py          # VPS gates + G7 baseline (one shot)
scripts/vps_deploy_ashigaru.sh             # VPS deploy (plan segment end)
```

---

## Promotion ladder

1. Sacred replay economics — done  
2. HUD + long runs — done  
3. Dry-run WS offers — done  
4. E1 live ws-engine — done (2026-06-15)  
5. **Current:** v2.1.17 live → [x] G7 v1 good enough (61 fills) → continue soak + watch metrics → E3 when consistent gain + warm fuzzy (operator timeline)

---

## Maintenance

When a checkbox ships: update this file + [`PURE_AS_DEVELOPMENT_LOG.md`](PURE_AS_DEVELOPMENT_LOG.md) (narrative) + FOR_AI milestone + THREAD. Do not commit `.env` / secrets.
