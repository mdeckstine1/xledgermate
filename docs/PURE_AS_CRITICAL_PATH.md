# Pure A-S Critical Path

**Status:** Live soak on VPS — **WS + pure A-S** (`ws-engine`) · **HUD** `:8765`  
**Version:** v2.1.22 · **Branch:** `Ashigaru-Kaizen-II`  
**Last updated:** 2026-06-20 (peer lane shelved · empty band at live + E3 shadow · G6 v1.1 next)

Single checklist for WS + pure A-S. Other docs link here — do not duplicate task lists.

**Soak = timed test run.** Collect fills, toxicity, markout, G6 grades under real quoting. **M6 signed off** (2026-06-19). **v2.1.22** deployed. **Current segment:** boot **2026-06-19 ~13:24 UTC** — 6–8h wall-clock soak after spot-drop halt + clear-kill restart.

---

## Priority stack

Ordered by what live soaks proved matters. **Do not skip tiers** — finish P0 before P2 engine work; ship P2 HUD-only before the next timed segment.

| Pri | Item | Soak signal | Status |
|-----|------|-------------|--------|
| **P0** | **Segment #2 time soak** (6–8h wall-clock) | Validate v2.1.22 after spot-drop triage | **in progress** |
| — | Hourly operator strip | Skim Δ, wealth spot/skim/rebal, toxic@30s, cancel/fill, G6 tier | ongoing |
| — | Peer lane watch (optional) | Peer Cal / cal JSONL — **&gt; 0** peers in band? | passive |
| **P1** | Post-segment snapshot | `scripts/post_deploy_snapshot.py` + dated save | pending |
| **P1** | Segment #2 verdict vs gates | Compare to M6 baseline + segment #1 learnings | pending |
| **P2** | **G6 v1.1** (HUD-only) | False **hold** on thin edge (M6 92%/5 bps; #2 n&lt;15); 8 bps bar vs 5 bps join | [ ] after P1 — [spec](#g6-activation-grading) |
| **P2** | G6 v1.1 calibration soak | Confirm thin_edge / pilot_watch / hold semantics on live fills | after G6 v1.1 ship |
| **P3** | **G8** spot trend posture | Segment #1 spot P&amp;L vs skim; inventory skew under moves — **decision after P1 review** | spec only — [no build until decided](#spot--inventory-operator-stance) |
| **P3** | Stale-quote guard (if tail repeats) | 61s stale bid fill in #1; M6 logs age, no auto-cancel today | watch segment #2 fill-age p95 |
| **P3** | cancel/fill re-eval | M6 **2.92**; v2.1.22 preserve 8 bps — did churn improve? | watch in P1 verdict |
| **P3** | G6 Tier 2 (rolling window) | Full-session cumulative feels sticky after bad early fills | after one v1.1 soak |
| **P3** | G6→G2/G7 coupling (Tier 3) | Hold advisory-only; negative skim with neutral G2 in #1 | deferred until hold is rare |
| **P4** | L2/L3 ledger + `book_bids`/`book_asks` sync | Book tab shows L1; multi-level planned | post-soak |
| **P4** | I1–I4 regime channel (damped) | Book-wide intel; peer lane empty | post multiple soaks |
| **P4** | P7 async submit / tx rate | Cancel/replace can exceed 5s loop | M2/M3 review |
| **P4** | **E3** 11k funding + rebalance exec | Operator timeline | consistent gain + warm fuzzy |
| **P4** | H3–H7 arb paper/live | Separate wallet | G6 pass + H1 monitor |
| **P4** | F4 Grok → outcome correlation | Offline attribution | fill history depth |

### Optional shelf (no build unless signal)

Peer-lane / P4–P6 work **deprioritized** after Peer Cal soak: **0 peers in band** at live (~18 XRP) and E3 shadow (~424 XRP) — whale book, solo MM. G4 empty-lane neutral is correct; no queue-war automation needed today.

| Item | Watch trigger | Status |
|------|---------------|--------|
| **P4–P6** peer intel, G4 nudges, F2 hook, I7 in-band automation | `shadow_peer_lane_count` **or** live `peer_lane_count` **&gt; 0** sustained | **shelved** — [Peer Cal](#optional-shelf-no-build-unless-signal) tab + `peer_lane_calibration.jsonl` passive |
| Per-peer history (P1–P3) | Same — peers appear at touch | shelved with P4–P6 |
| Peer Cal HUD tab | Keep deployed; no new features | monitor only |

**Operator glance:** Peer Cal tab or `tail logs/peer_lane_calibration.jsonl` — if shadow or live peer count goes **&gt; 0**, revisit shelf (book structure may have changed).

**Discipline:** A-S sacred. **No P2+ code mid P0 segment.** G6 v1.1 is HUD-only (P2). G8 and engine knobs wait for **P1 soak review** — see [Spot & inventory](#spot--inventory-operator-stance).

### Spot & inventory (operator stance)

We are **not** building a spot-prediction or directional trading bot. Spot moves still move **inventory and wealth** (segment #1: most −2.6 RLUSD was spot, not skim). That tension is real and hard — G7/G2 today handle inventory **symmetrically** via skew labels, not forecast.

**Plan (2026-06-19):** Finish segment #2 → P1 verdict with **wealth decomposition** (spot vs skim vs rebal) → ship **G6 v1.1** → then decide whether G8 (or something lighter) is worth engine complexity. G8 spec in STRATEGY_MANUAL stays a **reference option**, not a committed build. Alternatives if soak says “no trend layer”: operator kill on judgment, tighter inventory targets, or G7-only defensive skew — no new prediction module required.

### P0 — segment #2 (operator now)

| Task | Status |
|------|--------|
| Deploy **v2.1.22** + restart `xledgermate` | [x] 2026-06-19 |
| Session-scoped G6 (HUD) | [x] deployed |
| Operator halt — spot-drop triage (#1) | [x] ~10:26 UTC |
| Fresh restart clear-kill + engine + HUD | [x] ~13:24 UTC |
| **Time soak 6–8 hours** | **in progress** |
| Hourly monitoring | ongoing |
| Post-segment snapshot | pending |

**Gates (this segment vs M6 baseline):**

| Metric | M6 (50 fills) | Watch #2 |
|--------|---------------|----------|
| Skim Δ | −0.175 XRP | Flatten or positive drift |
| Spread capture bps | 4.96 avg (92% pos) | **Primary** — session G6 |
| toxic@30s | 8.7% | ≤30% sustained |
| markout@30s | +0.001% | Not adverse |
| cancel/fill | 2.92 | Target &lt;2.5 sustained |
| G6 tier | v1.0 false hold on thin edge | v1.1 after P1 |
| Wealth spot Δ | — | Separate from skim — beta on XRP moves |

### P1 — segment close (next)

1. Run `post_deploy_snapshot.py` + `live_activation_grading --gate` — save dated output.
2. Write segment verdict: pass / watch / halt pattern for next window.
3. Sync [`PURE_AS_DEVELOPMENT_LOG.md`](PURE_AS_DEVELOPMENT_LOG.md) narrative.
4. Decide: G6 v1.1 ship before vs after any engine restart.
5. **G8 / spot posture:** go / no-go / defer — based on segment #2 wealth split and whether inventory pain repeats without a forecast layer.

### Soak findings → backlog (why this order)

| Finding | Segments | Drives |
|---------|----------|--------|
| G6 **hold** on good pos% + ~5 bps | M6, #2 | **P2 G6 v1.1** |
| Spot drop; wealth −2.6 RLUSD mostly spot | #1 | P1 review → maybe P3 G8 (not committed) |
| G2 neutral while skim negative | #1 | P3 G6→G2 (deferred) |
| 61s stale quote fill | #1 | P3 stale guard if repeats |
| cancel/fill elevated | M6, 113-fill | P3 re-eval after v2.1.22 |
| Inherited cumulative G6 after restart | pre-fix | [x] session-scoped G6 |
| Skim Δ / wallet Δ confusion | Jun soak | [x] HUD semantics fixed |
| Join 3 bps too tight | M6 | [x] G7 v1.1 5 bps floor |
| **Empty peer lane** (live + E3 shadow) | Peer Cal 2026-06-20 | **P4–P6 shelved** — watch for &gt; 0 |

---

## G6 activation grading (P2 spec)

**Priority:** P2 — ship after segment #2 close (HUD-only). Full stack: [Priority stack](#priority-stack).

**Code (v1.0 shipped):** `experimental/ws_feed/live_activation_grading.py`, `experimental/ws_feed/performance_metrics.py`  
**CLI:** `python -m experimental.ws_feed.live_activation_grading [--gate]`

### Role (measurement, not control)

| G6 **is** | G6 **is not** |
|-----------|----------------|
| Session-scoped §7 grades + activation tier for HUD / soak strip | A kill switch or auto halt |
| Recomputed every poll (not latched) | Wired to G2/G7 today |
| Post-soak / milestone gate (`--gate`) | A guarantee of profitability |

**Operator runbook:** `hold` + negative skim + judgment → **kill switch** (segment #1). G6 hold alone does **not** stop quoting.

### v1.0 diagnosis (consensus — Grok + Cursor, 2026-06-19)

| Issue | Detail |
|-------|--------|
| Not sticky | Tier recomputed from session CSV + runtime each poll |
| Feels sticky | **Full-session cumulative** stats; early bad fills dilute slowly |
| Chronic hold | **8 bps “good” bar** vs **G7 join floor ~5 bps** — M6 (92% pos, ~5 bps) → hold |
| Action gap | Advisory only until v1.1 calibration; **defer G6→G2/G7** until hold is rare |

**v1.0 hold rule:** `spread_capture = attention` (n≥8, not good bar) → tier **`hold`**, gate **FAIL**.

### G6 v1.1 — approved spec (ship after segment #2)

**Status:** [ ] pending — HUD-only (`performance_metrics.py`, `live_activation_grading.py`, HUD tier pill). **Do not ship mid-soak.**

**Philosophy:** Keep G6 **advisory** through calibration soak; gate fails on **bad economics**, not thin-book normal. No G6→G2/G7 coupling in v1.1.

#### Tier 1 (ship together)

1. **`thin_edge` band** — n ≥ 8, pos% ≥ **70%**, avg bps in **[5, 8)** (aligned with G7 join). Spread grade **`thin_edge`**; tier **`pilot_watch`** or **`thin_edge`**; **gate pass** (yellow UI, not red hold).

2. **`hold_min_fills = 15`** — hold only when n ≥ 15. For 8 ≤ n &lt; 15 with spread attention (outside thin_edge) → **`pilot_watch`**, gate pass.

3. **Hold = bad economics only** (n ≥ 15) — tier **`hold`**, gate **FAIL**, only if any of:
   - avg bps **&lt; 0**, or
   - pos% **&lt; 50%**, or
   - avg bps **&lt; 3** and pos% **&lt; 70%**

   Thin positive capture → **never hold**.

4. **Spread grade split** — §7 card: `good` | `thin_edge` | `attention` (not all sub-8 bps as red attention).

5. **Optional Tier 1:** zero-capture fills count **neutral** for pos% (not positive).

#### Tier 2 (after one v1.1 soak)

- Rolling window (last **25** fills or **2h**) for tier recovery; session totals still on HUD.
- Mean + **median** bps on Metrics; median for outlier guard only.

#### Tier 3 (deferred)

| Item | Status |
|------|--------|
| G6 → G2 min spread_mult on hold | After v1.1 soak proves hold is meaningful |
| G6 → G7 defensive | Same |
| Auto-halt on hold | **No** — kill stays operator-driven |

#### Gate semantics (v1.1)

| Tier | `gate_pass` |
|------|-------------|
| `warming_up` | **fail** |
| `thin_edge` / `pilot_watch` | **pass** (warn in UI) |
| `pilot` / `active` / `scale_ready` | **pass** |
| **`hold`** | **fail** |
| `halted` / `paper` | **fail** |

#### Target tier ladder

```
n < 8                          → warming_up (gate fail)
n ≥ 8, pos ≥ 70%, 5 ≤ bps < 8  → thin_edge / pilot_watch (gate pass)
8 ≤ n < 15, spread bad         → pilot_watch (gate pass)
n ≥ 15, bad economics          → hold (gate fail)
n ≥ 25/50, core good           → active / scale_ready
```

#### Sanity check (past segments)

| Segment | v1.0 | v1.1 expected |
|---------|------|----------------|
| M6: 50 fills, 92% / ~5 bps | hold | **thin_edge**, gate pass |
| #1: 83 fills, 51% / −0.14 bps | hold | **hold** ✓ |
| #2: 18 fills, 67% / 1.8 bps | hold | **pilot_watch** (n&lt;15), not hold |

**Implement checklist:** tests for M6-style thin_edge, segment #1 hold, segment #2 pilot_watch; bump `G6_VERSION`; HUD pill for `thin_edge`; update STRATEGY_MANUAL one-liner; deploy `xledgermate-ws-hud` only.

---

<details>
<summary>Prior segment #1 (v2.1.22, boot 03:40 UTC — archived)</summary>

~83 fills before operator halt. Mid **1.138 → 1.124** (−1.1% spot). Wealth Δ **−2.6 RLUSD** (mostly **spot** −3.3, skim −0.12). Session G6 → **`hold`** (51% pos, −0.14 bps). BUY-side bleed (−0.18 XRP capture); one fill **61s stale quote**. G2 stayed neutral (toxic@5%). Kill activated manually; offers cancelled.

**Learned:** G6 hold is advisory only; G2 does not brake on negative skim; preserve_touch_queue + low toxic keeps stale bids. G8 trend posture planned (see STRATEGY_MANUAL).

</details>

<details>
<summary>M6 eval verdict (2026-06-19, 50 fills v2.1.21) — archived</summary>

| Gate | Result |
|------|--------|
| M6 JSONL | PASS — 50/50 session fills logged |
| Fill age median | ~0.3 ms (88% instant); p95 36s (6 stale tail) |
| toxic@30s | PASS — 8.7% |
| markout@30s | PASS — +0.001% |
| cancel/fill | FAIL watch — 2.92 (&gt;2.5) |
| G7 mirror | PASS — rlusd_heavy bid join / ask passive |
| G6 | `hold` — spread capture 4.96 bps (attention) |
| Skim Δ | −0.175 XRP — thin edge, not toxic flow |

**Learned:** High positive % but low bps/fill → join too tight at 3 bps. Safety stack healthy. M6 measurement validated.

**v2.1.22 response:** G7 join floor 5 bps + 45% half-spread; `WS_MID_MOVE_REFRESH_BPS` 4→8; `book_bids`/`book_asks` on runtime; M6 clear tracker after fill; `session_boot_utc` for time-soak scripts.

</details>

<details>
<summary>Prior soak segment (v2.1.17 — archived TODO)</summary>

| # | Task | Status |
|---|------|--------|
| — | Post-deploy gates + 60-fill checkpoint | [x] done 2026-06-18 |
| — | Post-deploy gates + **113-fill checkpoint** | [x] done 2026-06-18 |
| — | G7 v1 soak A/B validation | [x] good enough through 113 fills |
| — | **Queue review** G7 A/B | [x] 61 + 113 fill data |
| — | **M6** implementation | [x] shipped in 2.1.18 |

</details>

<details>
<summary>Archive — soak checkpoints &amp; shipped bundles (v2.1.17–v2.1.22)</summary>

**G7 soak (2026-06-18, v2.1.17):** C2 PASS at 61 fills; G7 v1 good enough through **113 fills**. Both inventory mirrors validated. cancel/fill 1.77 → 2.35 drove M6 + v2.1.22 churn work.

| Metric | ~61 fills | ~113 fills |
|--------|-----------|------------|
| Skim Δ | −0.106 XRP | −0.101 XRP |
| toxic@30s | ~26% peak | 4.5% |
| cancel/fill | 1.77 | 2.35 |
| G7 | xrp_heavy asymmetric | rlusd_heavy mirror |

**v2.1.22 shipped (2026-06-19):** G7 join floor 5 bps; mid-move preserve 8 bps; book depth export; M6 tracker clear; `session_boot_utc`.

**M2–M5 shipped (v2.1.15):** fill age, stale-cross, sample_history, as_safety, fill economics.

<details>
<summary>G7 v1 A/B + design notes (2026-06-18)</summary>

| Metric | v2.1.15 baseline | v2.1.17 (~61 fills) |
|--------|------------------|---------------------|
| cancel/fill | ~1.5 | 1.77 |
| worst_vs_touch_bps | ~8.0 | ~9.0 (xrp_heavy) |
| markout@30s | −0.013% | −0.001% (recovered) |
| Skim Δ | small positive | −0.106 (join-side adverse flow) |

**Verdict:** [x] G7 v1 good enough. A-S reservation untouched. G7 + G2 are execution only — no mid-soak overrides from HUD intel.

<details>
<summary>G7 draft spec v1 (design reference)</summary>

**G7 soak checkpoint (2026-06-18, ~61 session fills on v2.1.17):** C2 sample_history gate now **PASS** (123 min, 86.8% presence, flip 0.141). G6 still `pilot_watch` (toxicity + empty peer lane) but gate PASS. Session Skim slipped to −0.106 XRP during xrp_heavy leg (adverse flow on the join-ask side) then inventory normalized. Markout@30s recovered to ~0. Full snapshot in `logs/post_deploy_snapshot.txt`. After HUD restart + hard refresh you will see:
- G7 queue: the correct decision e.g. "bid passive 9.0bps · ask join 3.4bps" (or ×G2 when braking), computed on the HUD side from the current inventory_label + g2_spread_mult that the engine *is* already writing.
- Queue vs touch: worst-bps or "at touch / back / join" summary computed from the planned quote ladder vs BBO in the snapshot (proxy until engine restart writes the real on-ledger visibility).
Full authoritative G7 + on-ledger visibility numbers will flow after the next engine restart (when the ws-engine writes them into runtime_state.json).

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

- **G8 Spot Trend Posture** — bounded offensive overlay for XRP spot moves (trend × inventory → G7 bias, asymmetric refresh, light reservation bias, trend P&L). Spec: [`STRATEGY_MANUAL.md`](STRATEGY_MANUAL.md#g8--spot-trend-posture-future-phase). Build after G7 + M6 soak sign-off.
- Markout-adaptive backoff (needs more M2 fill history)  
- F4 Grok correlation (offline)  
- Merge `execution_envelope` into `spread_quality_scaler.py` if we want one file later  

</details>

</details>

</details>

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
| **HUD ops** | Inventory nav restored; Metrics toxicity gray-zone fix; **Skim Δ** (not wallet/deposit); Wallet Δ on Inventory; **RLUSD wealth sidebar**; **Book tab** (L1–L3 ladder, depth chart); **G6 hold** card on Metrics |

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
| **Metrics → Total capture** | Session-scoped when `session_boot_utc` set; meta shows `N session fills · cumulative M fills` |
| **Wealth sidebar** | Session Δ = skim + spot + rebal (RLUSD-stable); spot = baseline XRP × mid move |

Balance-delta fills use implied price when coherent (±25% of mid, BBO band, min 0.01 XRP). Bogus composite deltas are rejected at detect time and excluded from G6 skim grading. **G6 grades session fills since boot** when `session_boot_utc` present (0–7 fills → `warming_up`). Historical CSV rows remain in file; HUD activation uses session scope.

---

## Recent ships (2026-06-19)

| Item | What |
|------|------|
| Session-scoped G6 | `performance_metrics.py` filters fills since `session_boot_utc`; HUD meta shows session vs cumulative |
| Operator halt | `scripts/_operator_halt.py` — kill + cancel (must run from project root / `chdir` to `logs/`) |
| Fresh soak segment | clear-kill → restart engine + HUD; boot ~13:24 UTC, mid ~1.129 |
| G8 spec | STRATEGY_MANUAL + critical path future pointer — not coded |

<details>
<summary>Prior ships (2026-06-18)</summary>

| Commit | What |
|--------|------|
| **v2.1.22** | G7 join 5 bps + book-aware, churn preserve 8 bps, book depth export, M6 fill cleanup, `session_boot_utc` |
| `06815c6` | Docs: operator manuals synced (Book, G6 hold, wealth) |
| `5b9cb9b` | RLUSD-stable wealth sidebar with session decomposition |
| `2fb597d` | Balance-delta coherence guard |
| `b463887` | HUD Skim Δ fix — stop CSV overwrite |

</details>

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
- **G:** G1–G6 peer lane, G2 scaler, intel JSONL, G4 quoting, G5 replay, G6 activation grading · **G7** execution envelope · **G8** spot trend posture (spec)

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
| **This file** | **Priority stack** + P0–P4 backlog + G6 v1.1 spec |
| [`PURE_AS_DEVELOPMENT_LOG.md`](PURE_AS_DEVELOPMENT_LOG.md) | **Posterity** — how we got here, soak learnings, decisions |
| [`G6_ACTIVATION_REFERENCE.md`](G6_ACTIVATION_REFERENCE.md) | v1.0 code reference (superseded for spec by G6 section above) |
| [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md) | Tester + HUD + Grok (tabs, G6, Book, wealth) |
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
5. G7 v1 + M6 measurement — done (2026-06-19)  
6. **Current:** segment #2 time soak (v2.1.22) → P1 verdict → **G6 v1.1** → calibration soak → **G8 decision** (optional) → **E3** on operator timeline

---

## Maintenance

When a checkbox ships: update this file + [`PURE_AS_DEVELOPMENT_LOG.md`](PURE_AS_DEVELOPMENT_LOG.md) (narrative) + FOR_AI milestone + THREAD. Do not commit `.env` / secrets.
