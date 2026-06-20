# Pure A-S Critical Path

**Status:** Live soak — **Segment #5** · **v2.1.38** on VPS · **HUD** `:8765`  
**Version:** v2.1.38 · **Branch:** `Ashigaru-Kaizen-II`  
**Last updated:** 2026-06-20 (A2.3 acquire ask brake built)

Single checklist for WS + pure A-S. Other docs link here — do not duplicate task lists. Narrative + archaeology: [`PURE_AS_DEVELOPMENT_LOG.md`](PURE_AS_DEVELOPMENT_LOG.md).

---

## North star (read this first)

**Bot purpose:** skim-funded **inventory growth** — buy XRP below fair from a wide whale book, not RLUSD↔XRP conversion at mid.

| Layer | Role |
|-------|------|
| **G7 posture** | *Where* to quote (solo edge acquire: passive bid / wide ask) |
| **A2 enforcement** | *Whether* to quote (min edge on bids **and asks**; acquire ask brake) |
| **G2 / A3** | Brakes (toxic, stale age) — never override A-S reservation |
| **G6** | Measurement only (HUD) — not a kill switch |

**Purpose pass gate (soak verdict):** all required — fill count is diagnostic only.

| # | Metric | Meaning |
|---|--------|---------|
| 1 | `session_spread_capture_xrp > 0` | MM added value |
| 2 | **`buy_capture_xrp > 0`** | growth funded by buy skim, not sells |
| 3 | **`at_edge: True`** | Δ XRP &gt; 0 **and** buy capture &gt; 0 |
| 4 | MTM Δ &gt; 0 (spot aside) | wealth actually up |

**Anti-pattern:** positive session skim with **SELL-led** capture and `at_edge=False` — v2.1.36 @ 18 fills (+0.029 skim, BUY −0.013 / SELL +0.042). Do **not** stop a soak on headline skim alone; check `by side:` in `_session_diag_quick.py`.

---

## Active sprint (NOW)

| Step | Item | Status | Notes |
|------|------|--------|-------|
| **1** | **Segment #4 soak** | **closed** | v2.1.37 — BUY +0.025, both sides positive; `at_edge` still false (Δ XRP ↓) |
| **2** | **Deploy v2.1.38 + Segment #5** | **ongoing** | A2.3 ask brake — bid-only in solo acquire |
| **3** | **M-Purpose HUD strip** | **shipped** | HUD-only: `at_edge`, buy cap, Δ XRP front and center |
| **4** | **A2.4 — realized buy-edge feedback** | planned | Post-fill brake; implied fill price (M2) |
| **5** | **A2.5 — tune constants** | planned | `MIN_BUY_EDGE_BPS`, G7 backoffs from Segment #4 |

**Soak stop rule:** 50 fills **or** 2–3h · no mid-soak engine tweaks unless kill-switch.

**Segment #4 baseline to beat:** v2.1.36 final — BUY **−0.013**, SELL **+0.042**, `at_edge=False`.

---

## Skim-funded inventory roadmap (cohesive path)

One line of development — each phase unlocks the next. Do not skip ahead to scale (E3) or spot (G8) until **purpose pass** on live size.

```
Phase 1 — Hygiene (shipped)     A1 sell-defense · A2 presence · A3 stale guard
Phase 2 — Edge enforcement      A2.2 buy gate [x] → A2.3 ask brake [x] → A2.3b sell gate → A2.4 realized edge → A2.5 tune
Phase 3 — Operator clarity      M-Purpose HUD (at_edge scoreboard)
Phase 4 — Scale proof           E3 funding · larger L1 — only after at_edge on soak
```

| Phase | Build | Version | Status |
|-------|-------|---------|--------|
| **1** | A1 G7 sell-defense | v2.1.23 | [x] closed Fail (economics) |
| **1** | A2 G7 solo + G4 solo_acquire | v2.1.27 | [x] deployed |
| **1** | A3 stale-quote guard | v2.1.27 | [x] deployed |
| **1** | G7 v1.6 edge-positive acquire | v2.1.36 | [x] deployed — posture only |
| **2** | **A2.2 buy-side skim gate** | **v2.1.37** | **[x] deployed Segment #4** |
| **2** | **A2.3b sell-side skim gate** | **v2.1.39** | **[x] deployed Segment #6** |
| **2** | **A2.3 acquire ask brake** | **v2.1.38** | **[x] deployed Segment #5** |
| **2** | **A2.4 realized buy-edge feedback** | TBD | [ ] after A2.3 or parallel |
| **2** | **A2.5 tune MIN_BUY_EDGE / G7 backoffs** | TBD | [ ] after Segment #4 |
| **3** | **M-Purpose HUD strip** | HUD-only | **[x] shipped — HUD restart only** |
| **4** | E3 11k funding | ops | [ ] deferred |
| — | G8 spot, peer P4–P6, G6 Tier 2/3, arb | — | shelved — [below](#optional-shelf-no-build-unless-signal) |

---

## Priority stack (backlog)

| Pri | Item | Status |
|-----|------|--------|
| **P0** | Segment #4 soak (v2.1.37) | closed — buy gate validated |
| **P0** | Deploy v2.1.38 + Segment #5 soak | **ongoing** |
| **P1** | A2.3 acquire ask brake | [x] v2.1.38 built |
| **P1** | M-Purpose HUD strip | planned |
| **P1** | A2.4 realized buy-edge feedback | planned |
| **P2** | G6 v1.1 (HUD-only) | [x] shipped |
| **P3** | G8 spot trend posture | deferred — [stance](#spot--inventory-operator-stance) |
| **P3** | cancel/fill tune | deferred |
| **P3** | G6 Tier 2 / G6→G2 coupling | deferred |
| **P4** | L2/L3 ledger sync, I1–I4, P7 async, E3, H3–H7, F4 | post purpose-pass |
| — | Peer lane P4–P6 | shelved |

### Optional shelf (no build unless signal)

Peer-lane / P4–P6 work **deprioritized** after Peer Cal soak: **0 peers in band** at live (~18 XRP) and E3 shadow (~424 XRP) — whale book, solo MM. G4 empty-lane neutral is correct; no queue-war automation needed today.

| Item | Watch trigger | Status |
|------|---------------|--------|
| **P4–P6** peer intel, G4 nudges, F2 hook, I7 in-band automation | `shadow_peer_lane_count` **or** live `peer_lane_count` **&gt; 0** sustained | **shelved** — [Peer Cal](#optional-shelf-no-build-unless-signal) tab + `peer_lane_calibration.jsonl` passive |
| Per-peer history (P1–P3) | Same — peers appear at touch | shelved with P4–P6 |
| Peer Cal HUD tab | Keep deployed; no new features | monitor only |

**Operator glance:** Peer Cal tab or `tail logs/peer_lane_calibration.jsonl` — if shadow or live peer count goes **&gt; 0**, revisit shelf (book structure may have changed).

**Discipline:** A-S sacred. **G6 v1.1 is HUD-only** — no engine restart for P2. G8 **deferred** (#2 wealth positive, spot-led). Peer lane **shelved**.

### Spot & inventory (operator stance)

We are **not** building a spot-prediction or directional trading bot. Spot moves still move **inventory and wealth** (#1: most −2.6 RLUSD was spot). G7/G2 handle inventory **symmetrically** via skew, not forecast.

**After #2:** Wealth **+1.28 RLUSD** (spot-led) — **G8 deferred**. No engine trend layer until inventory pain repeats without spot help. G8 spec in STRATEGY_MANUAL stays reference only.

### Segment #2 verdict (2026-06-20) — closed

**Boot:** 2026-06-19 13:24 UTC · **~4h 15m** · **57 fills** · v2.1.22 · snapshot `post_deploy_snapshot.txt`

| Metric | M6 | Segment #2 | Gate |
|--------|-----|------------|------|
| Skim Δ | −0.175 XRP | **+0.024 XRP** | **Pass** |
| Spread bps / pos% | 4.96 / 92% | **1.28 / 67%** | **Fail** (real weak capture) |
| toxic@30s | 8.7% | **28.6%** | Borderline pass (≤30%) |
| markout@30s | +0.001% | **−0.022%** | Watch |
| cancel/fill | 2.92 | **2.96** | Fail (&lt;2.5 target) |
| Wealth Δ (RLUSD) | — | **+1.28** (spot +1.36, skim +0.03) | Pass — no G8 signal |
| G6 (v1.0) | hold (thin-edge false) | **hold** (economics real) | Fail gate — advisory |

**Verdict: Watch** — positive skim &amp; wealth on whale book; SELL-side bleed and low bps are the real issues. **Sufficient sample — stop segment.** G8 deferred. Peer lane shelved.

**Next:** Deploy G6 v1.1 HUD → ~50-fill calibration soak → **acquisition phase** build (solo whale book).

### Acquisition phase — detail (reference)

Full ordered roadmap: [Skim-funded inventory roadmap](#skim-funded-inventory-roadmap-cohesive-path). Legacy A1–A3 detail below.

**Operator check:** `python scripts/_session_diag_quick.py` → `by side:` BUY vs SELL capture. HUD Metrics: `g6_version` **1.1.0**.

| Order | Build | Status |
|-------|-------|--------|
| A1 | SELL-side bleed (G7 v1.2) | [x] closed Fail |
| A2 | Presence / fill rate | [x] v2.1.27 |
| A3 | Stale-quote tail | [x] v2.1.27 |
| A2.2 | Buy-side skim gate | [x] v2.1.37 |
| A2.3 | Acquire ask brake | [x] v2.1.38 |
| A2.4 | Realized buy-edge feedback | [ ] planned |
| A2.5 | Tune constants | [ ] after Segment #4 |
| M-Purpose | HUD purpose strip | [ ] next HUD |

#### A1 — SELL-side bleed (shipped v2.1.23 / G7 v1.2)

**VPS baseline (2026-06-19 session, 83 fills):** BUY **+0.072** / SELL **−0.035** XRP · mean **1.38 bps** · worst-8 **7/8 SELL**.

**Shipped — G7 v1.2 ask sell-defense** (`execution_envelope.py`):

- Triggers when: G2 brake (`spread_mult>1` or cautious/stressed/defensive), `toxic@30s ≥ 15%`, or `markout@30s < −0.005%` with n≥8 fills.
- Action: demote ask **join → passive**; add **+2 bps** ask-only backoff. Bids unchanged (preserve BUY acquisition).
- Observability: `g7_ask_sell_defense`, `g7_sell_defense_reason` on runtime + G7 summary.

**Deploy:** segment-end `systemctl restart xledgermate` (engine). HUD synth picks up defense from runtime fill-quality fields without engine restart.

**A1 segment verdict (2026-06-20):** **Fail** — 78 fills / ~10.3h · BUY **+0.096** / SELL **−0.197** XRP · bps **0.43** · pos **69%** · toxic@30s **20%** (pass). Defense ran; SELL bleed worsened vs pre-A1 baseline. Proceed to A2+A3.

**Done when:** Session `by side` SELL capture ≥ 0; session bps ≥ 3 with pos ≥ 70% → G6 off `hold`. *(Not met — segment closed.)*

#### A2 — presence / fill rate (deployed v2.1.27 / G7 v1.3 + G4 v1.1)

Solo whale book — no peer queue war. **Deployed 2026-06-20** with A3 bundle.

**G7 v1.3 solo acquisition** (`execution_envelope.py`):

- When `peer_lane_empty` and toxic@30s &lt; 20% and no G2 brake:
  - **balanced** / **rlusd_heavy:** bid **join** (5 bps), ask **passive** (8 bps)
  - **xrp_heavy:** passive both (no ask join — A1 lesson)
- Skips when G2 braking or toxic elevated.
- Observability: `g7_solo_acquisition`, `· solo acquire` in G7 summary.

**G4 v1.1 solo_acquire** (`peer_lane_quoting.py`):

- Empty lane + low toxic + G2 not defensive → bid size **+6%**, ask **+2%** (`grade=solo_acquire`).
- Falls back to neutral `empty_lane` when toxic ≥20% or G2 size brake.

**Deploy:** [x] segment-end `systemctl restart xledgermate` 2026-06-20 (bundled with A3).

**Done when:** Sustained presence ≥75% with toxic@30s ≤30% and improving fill rate vs A1 baseline (~7.6/h).

#### A2.2 — buy-side skim gate (built v2.1.37 · deploy Segment #4)

**North star:** skim-funded inventory growth — not RLUSD↔XRP conversion at mid. G7 v1.6 posture alone cannot enforce this; pure path had no min-edge gate (Segment #3: +67 XRP, **−0.009 skim**, `at_edge=False`).

**Shipped — `buy_edge_gate.py`:**

- After G7 `touch_prices_from_backoff`, block bids when implied buy edge &lt; **`MIN_BUY_EDGE_BPS`** (1.0 bps default).
- **Scope:** `g7_solo_acquisition` + accumulate postures (`balanced`, `rlusd_heavy`, `slight_rlusd_heavy`) only — not `xrp_heavy` hold, not peer-present lane.
- **Session brake (layer 2):** if session `buy_capture_xrp` &lt; 0, pause bids until capture recovers.
- Action: `pause_bids=True` on ladder; ask side unchanged.
- Observability: `buy_edge_gate_blocked`, `buy_edge_implied_bps`, `buy_edge_gate_reason` on runtime + intel JSONL + HUD.

**Deploy:** [x] Segment #4 restart 2026-06-20 ~18:05 UTC (`2ec5c36`).

**Done when (soak):** `at_edge=True`, `buy_capture_xrp > 0`, `session_spread_capture_xrp > 0` — fill count secondary.

#### A2.3 — acquire ask brake (shipped v2.1.38)

**Problem:** Segment #4 — positive skim on both sides but **Δ XRP still falling** (sells leak inventory). A2.2 fixed buys; asks still posted in solo acquire.

**Shipped — `acquire_ask_brake.py`:**

- When `g7_solo_acquisition` + accumulate postures → **`pause_asks=True`** (bid-only acquire).
- Same scope as A2.2; no ask posts while accumulating XRP at edge.
- Observability: `acquire_ask_brake_active`, `acquire_ask_brake_blocked`, `acquire_ask_brake_reason` on runtime + intel + HUD.

**Deploy:** [x] Segment #5 restart 2026-06-20 ~20:21 UTC (`bd086cc`).

**Done when:** soak shows **buy-funded Δ XRP** — `at_edge=True`, no SELL volume in solo acquire cycles.

#### A2.3b — sell-side skim gate (shipped v2.1.39)

**Problem:** Segment #4 — SELL +0.042 while BUY −0.013; skew `xrp_heavy` ask-only outside solo acquire still leaked inventory at sub-edge asks.

**Shipped — `sell_edge_gate.py`:**

- When `peer_lane_empty=True` (solo whale book) → block asks if implied sell edge &lt; `MIN_SELL_EDGE_BPS` (1.0) or session sell capture &lt; 0.
- Broader scope than A2.3 (covers skew ask-only, not just solo acquire postures).
- Wired: `effective_pause_asks = inv_policy | acquire_ask_brake | sell_edge_gate`.
- Observability: `sell_edge_gate_active`, `sell_edge_gate_blocked`, `sell_edge_implied_bps`, `sell_edge_gate_reason`.

**Deploy:** [x] Segment #6 restart 2026-06-20 ~23:17 UTC (`1b28e2f`).

**Done when:** soak shows **SELL capture ≥ 0**, `at_edge=True`, buy-funded Δ XRP.

#### A2.4 — realized buy-edge feedback (planned)

**Problem:** A2.2 checks **posted** bid vs mid; fills can be worse (adverse selection, balance-delta lag). v2.1.36 worst leg: BUY 20.7 XRP @ **−0.051** capture.

**Spec (draft):**

- Rolling realized buy bps from session fills → tighten gate or extend session buy brake after bad streak.
- Tie-in: implied fill price (`fill_detection.py` / M2) for accurate capture at fill time.
- **Done when:** post-fill bleed triggers bid pause within one cycle.

#### A2.5 — tune constants (planned · after Segment #4)

- `MIN_BUY_EDGE_BPS` (1.0 today — may need 2–3 bps).
- G7 solo backoffs (8/10 bps) if gate blocks all bids or still bleeds.
- Soak-driven only — not A-S γ/κ.

#### M-Purpose HUD strip (shipped · HUD-only)

- **Purpose strip** on Live health bar: **Purpose PASS/FAIL**, **`at_edge`**, **buy cap**, **sell cap**, **Δ XRP**, **skim** — primary pass/fail without scripts.
- **`purpose_hud.py`** — computes from `fill_quote_age.jsonl` + runtime baselines (same as acquisition report).
- **Deploy:** `git pull` → `systemctl restart xledgermate-ws-hud` only — **no engine restart**.
- **Done when:** operator can glance HUD and see purpose gate without running scripts. [x]

#### Segment #4 — active (v2.1.37)

**Boot:** 2026-06-20 ~18:05 UTC · **A2.2 buy gate live** · compare to v2.1.36 baseline above.

**Verdict:** pending — stop at 50 fills / 2–3h; run `_session_diag_quick.py` + `acquisition_metrics_report.py`.

#### Segment #3 verdict (2026-06-20) — closed Fail (skim goal)

**Boot:** ~15:54 UTC · **~11 fills** · v2.1.35 G7 v1.5 join-acquire · stopped early.

| Metric | Result | Gate |
|--------|--------|------|
| Δ XRP | **+67** | inventory up |
| Session skim | **−0.009 XRP** | **Fail** |
| Buy capture | **−0.009** | **Fail** |
| `at_edge` | **False** | **Fail** |
| MTM | flat (~373.7 XRP-equiv) | **Fail** |
| Side mix | 6 BUY / 2 SELL | better than prior, but paying ~mid on buys |

**Verdict:** conversion soak, not skim. Pivot → G7 v1.6 edge acquire (v2.1.36) + A2.2 gate (v2.1.37).

#### v2.1.36 soak — closed (2026-06-20) · **Watch** (purpose Fail)

**Boot:** 2026-06-20 16:33 UTC · **~1h 30m** · **18 fills** · v2.1.36 G7 v1.6 edge acquire · stopped for Segment #4 deploy.

| Metric | Result | Purpose gate |
|--------|--------|--------------|
| Session skim | **+0.029 XRP** | Pass (headline) |
| Spread bps (nonzero) | mean **2.75**, median **~4** | OK |
| toxic@30s | **22%** | Borderline (solo off ≥20%) |
| **BUY capture** | **−0.013** (12 fills) | **Fail** |
| **SELL capture** | **+0.042** (6 fills) | SELL carries session |
| Δ XRP | **+4.8** | inventory up, but not at edge |
| `at_edge` | **False** | **Fail** |
| `buy_cost_vs_mid_bps` | **+1.97** mean | **Fail** |
| MTM Δ (approx) | **~flat / slight +** | inconclusive |
| Worst leg | BUY 20.7 XRP **−0.051** | toxic buy dominated BUY P&amp;L |

**Verdict: Watch** — net MM economics improved vs Segment #3 (positive skim, decent bps). **Purpose gate Fail:** SELL-led skim, buys still above/below fair wrong way on net, `at_edge=False`. G7 v1.6 posture alone insufficient — **deploy v2.1.37 A2.2 gate** for Segment #4.

**vs interim @ 16 fills:** skim +0.026→+0.029, toxic 27%→22%, BUY cap −0.016→−0.013 — same shape, stable enough to stop.

**Deploy:** [x] **v2.1.37** Segment #4 fresh boot 2026-06-20 ~18:05 UTC.

#### A3 — stale-quote tail (deployed v2.1.27)

#1 61s stale bid; #2 127s–4876s tail (often **ask**). `OfferAgeTracker` + M6 logs exist.

**Deployed 2026-06-20** with A2 bundle.

- **`stale_quote_guard.py`** — max ask age **60s** ( **45s** when toxic@30s ≥ 25%), bid **90s**, mid-move coupling (≥8 bps + age >30s).
- Wired in `_sync_offers`: stale cancels merge into cancel path even when `preserve_touch_queue=True`.
- Observability: `A3 stale-quote: cancel seq …` in decision log.
- **Done when (soak):** fill_age p95 &lt; 60s; stale fills no longer in worst-8.

**Discipline:** No G6 Tier 2/3, no G8, no peer intel until A1–A3 addressed or operator reprioritizes.

### Acquisition phase (context)

### P0 — segment #2 (archived)

| Task | Status |
|------|--------|
| Deploy **v2.1.22** + restart `xledgermate` | [x] 2026-06-19 |
| Session-scoped G6 (HUD) | [x] deployed |
| Operator halt — spot-drop triage (#1) | [x] ~10:26 UTC |
| Fresh restart clear-kill + engine + HUD | [x] ~13:24 UTC |
| Time soak (57 fills — sufficient) | [x] 2026-06-20 closed |
| Post-segment snapshot | [x] `logs/post_deploy_snapshot.txt` |
| Segment verdict | [x] **Watch** (above) |

### Soak findings → backlog (why this order)

| Finding | Segments | Drives |
|---------|----------|--------|
| G6 **hold** on good pos% + ~5 bps | M6 only | **P2 G6 v1.1** (M6-style false hold) |
| SELL-side skim bleed | #2 | **A1** (next engine) |
| Weak session bps → G6 hold | #2 ongoing | **A1** fixes economics; hold is correct until then |
| Stale-quote fill-age tail | #1, #2 | **A3** |
| Low presence opportunity | solo book | **A2** |
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

### G6 v1.1 — shipped (HUD-only)

**Status:** [x] **v1.1.0** — `performance_metrics.py`, `live_activation_grading.py`, HUD tier pill. Restart `xledgermate-ws-hud` only.

**Philosophy:** Advisory measurement; gate fails on **bad economics**, not thin-book normal. **No G6→G2/G7.** One ~50-fill soak to validate labels, then **acquisition phase** — no further grading churn.

#### G6 v1.1 macro effect (why ship · what it does *not* do)

| Layer | v1.1 net effect |
|-------|-----------------|
| **Engine / quoting** | **None** — G2, G7, reservation unchanged |
| **Operator kill** | **None** — judgment + skim still drive halt |
| **Gate semantics** | **Fixes false FAIL** on M6-style thin edge (92%/5 bps → `thin_edge`, pass) |
| **Hold meaning** | **Hold = bad economics** — #2 at 57 fills/1.28 bps still **hold** under v1.1 ✓ |
| **E3 / scale** | Does **not** auto-unlock 11k — `thin_edge` is yellow, not `scale_ready` |
| **Arb (H3–H7)** | Gate pass becomes **trustworthy** when it happens (fewer false blocks/false greens) |
| **Future Tier 3** | G6→G2 coupling only worth it when **hold is rare and real** — v1.1 enables that |
| **Peer / G4 shelf** | **Unchanged** — empty lane; G4 neutral correct |

**Risk to manage:** `thin_edge` + gate **pass** must not be read as “scale up” — UI yellow + operator discipline. `scale_ready` still needs n≥50 and core good.

**Segment replay under v1.1:**

| Segment | v1.0 | v1.1 expected |
|---------|------|----------------|
| M6: 92% / ~5 bps | hold (false) | **thin_edge**, gate pass |
| #1: 51% / −0.14 bps | hold | **hold** ✓ |
| #2: 67% / 1.28 bps, n=57 | hold | **hold** ✓ (bps&lt;3, pos&lt;70%) |

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
| **M-Purpose HUD strip** | `xledgermate-ws-hud` only | **Yes** — soak continues |

**Sacred rule:** `would_quote` = reservation inside live BBO. Measurement and HUD never override A-S math.

### VPS restart notes (operator)

**Segment #6 (v2.1.39, 2026-06-20 ~23:17 UTC):** A2.3b sell edge gate — `git pull` + `systemctl restart xledgermate` + `xledgermate-ws-hud` via `vps_deploy_ashigaru.sh`. Commit `1b28e2f`. **Resets soak** (new segment).

**Windows deploy (use every time — plain `ssh root@…` hangs):**

```powershell
ssh -i $env:USERPROFILE\.ssh\hetzner_xledgermate -o BatchMode=yes root@188.245.50.229 "bash /root/xledgermate/scripts/vps_deploy_ashigaru.sh"
```

- **Key:** `$env:USERPROFILE\.ssh\hetzner_xledgermate` — without `-i`, SSH waits for password and the agent session hangs (no output).
- **On VPS directly:** `cd /root/xledgermate && bash scripts/vps_deploy_ashigaru.sh`
- **HUD-only (soak-safe):** `ssh … "systemctl restart xledgermate-ws-hud"` — does **not** reset fills/skim/session baselines.
- **Engine restart:** required for `ws_pure_engine.py`, quote-path gates (A2.x), G7, fill detection — **always** starts a new soak segment.
- **After HUD deploy:** hard refresh browser (`index.html` loaded at HUD process start).
- **Avoid:** `ssh root@188.245.50.229 "python -c '…'"` from PowerShell — quoting breaks; use `grep`, deploy script, or `.venv/bin/python scripts/_session_diag_quick.py` on VPS.

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
