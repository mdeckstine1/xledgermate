# Pure A-S Development Log

**Purpose:** Posterity — how we got here, what we learned, and why decisions were made.  
**Companion:** [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md) is the live priority stack; this file is the narrative + archaeology.

**Branch:** `Ashigaru-Kaizen-II` · **VPS:** `188.245.50.229` `/root/xledgermate` · **Version:** v2.1.22  
**Last updated:** 2026-06-20

---

## Executive arc (one paragraph)

We moved from a **sacred HTTP-poll Gate 2 engine** (replay corpus, economics gates) to a **live WS-fed pure Avellaneda–Stoikov market maker** on XRPL mainnet (`ws-engine` + production HUD `:8765`). The committed safety contract is: **`would_quote` only when reservation is inside the live BBO** — Grok, competitor pressure, and book-wide intel tune *inputs*, never override reservation. After E1 live flip (2026-06-15) and E1.5 fill gate PASS, the **Ashigaru Kaizen** line ran a **timed soak** on VPS to collect fills, toxicity, markout, and G6 activation grades. While the engine ran uninterrupted, we shipped a large **soak-safe HUD/operator batch** (measurement, intel UX, reports, read-only arb monitor). Operator funding (~130 XRP) during soak exposed HUD PnL and sizing confusion; we fixed display semantics and documented balance-delta fill economics limitations pending an **engine-window** deploy (M2–M5).

---

## Timeline

| When | Milestone |
|------|-----------|
| 2026-05–06 | Sacred corpus + `replay_long_run --as-mode pure`; grokster economics; presence lift on replay |
| 2026-06-07 | Dual-branch discipline: `grok-tier-2-collab` = corpus; Ashigaru = production WS path |
| 2026-06-15 | **E1** VPS live flip (`dry_run: false`); E1.5 ≥50 WS fills + markout PASS; E2 merge |
| 2026-06-16 | Kaizen soak hardening: kill-switch decoupled from sacred session-balance trip; lean MM (ws-engine + ws-hud only); feature flags; HUD auth |
| 2026-06-16–17 | **Live soak segment** on VPS; soak-safe operator batch (see below) |
| 2026-06-19 | **M6 signed off** (50 fills v2.1.21); **v2.1.22** deployed; session-scoped G6; spot-drop segment + operator halt; fresh soak segment #2 |
| 2026-06-20 | Peer Cal empty lane → P4–P6 shelved; segment #2 closed (57 fills, Watch); **G6 v1.1** HUD shipped; **acquisition phase** primary |
| 2026-06-19 | **G8 Spot Trend Posture** spec — STRATEGY_MANUAL (future offensive overlay for XRP volatility) |

---

## Architecture decisions (why it looks like this)

### Pure A-S as the only touch gate

Legacy path used `market_edge_met` and heuristic vetoes → low presence (~11% on sacred replay). Pure path quotes when **reservation ∈ [best bid, best ask]** with optimal spread from γ, κ, vol. Pressure/Grok adjust γ, κ, vol, size — not the inside-book guard.

### WS book feed vs HTTP poll

`BookFeed` / `WsBookFeed` gives sub-second book freshness for reservation math. HTTP poll remains for sacred replay baseline only on collab branch.

### Balance-delta fill detection

WS engine infers fills by comparing wallet balances cycle-to-cycle (`detect_fill_from_balance_delta`). **Pros:** no extra RPC per fill; works with current connector. **Cons:** fill is detected ≥1 cycle late; fill price was often recorded as **mid** → `profit_xrp_equiv ≈ 0` for most rows; deposits (XRP-only) do not register as fills but move wallet Δ.

**Planned fix (segment end):** implied fill price when both XRP and RLUSD legs move (`fill_detection.py`, commit `5aec668`); M2 fill age; ledger path deferred.

### G2 spread-quality scaler (brake only)

Rolling toxicity / markout dims size and spread — never sizes up on hot runs. During soak, `toxic_fill_ratio_30s` ~27–31% → G2 **cautious** at 0.75× size. Operator saw “leaning toxic” — engine was behaving as designed.

### Peer lane vs book-wide regime

`prepare_quoting_intel()` neutralizes to 0.5 when **peer lane empty** so back-book whales (120k XRP touch 0) do not steer touch competition. Book-wide scrape still feeds **regime** briefings (I5/I6 HUD) and Grok analyze — post-soak I1–I4 will add a **damped** regime channel to A-S inputs.

### HUD mirror (no duplicate scrape)

`ws_hud_production.py` reads `logs/runtime_state.json` only — competitor intel comes from engine scrape. Restarting HUD is soak-safe; restarting engine is not.

---

## Soak-safe operator batch (2026-06-16 / 17)

Shipped without `ws-engine` restart. Representative commits on `Ashigaru-Kaizen-II`:

| Commit | Theme |
|--------|--------|
| `869277b` | Fill-age report, I6 HUD, F1 nicknames, stale-cross analysis schema |
| `f423f74` | HUD Reports tab (soak-safe operator reports) |
| `ac42e59` | I5 book side skew, F3b structured briefing, F4 grok JSONL, F2 advisory stub, H1 CLOB/AMM monitor, lab M2/M3 |
| `e796fc9` | Restore Inventory nav tab (dropped when Reports added) |
| `5aec668` | Skim Δ vs wallet Δ, toxicity grade fix, fill economics, critical path cleanup |

### What each bucket was for

- **M1** — Res→BBO delta bps + `inside_l1` on Live tab; proves A-S is inside/outside book each cycle.
- **M2/M3 prep** — offline `fill_quote_age_report.py`, `offer_age_tracker.py`, `stale_cross.py`; engine wires at segment end.
- **Intel HUD** — grounded Grok analyze, structured JSON briefing, nicknames, advisory stub, I5/I6 pills.
- **Reports** — nine read-only `logs/` reports (hourly trend, grok suggestions, clob/amm, etc.).
- **H1/H2** — read-only CLOB vs AMM spread log; no trades; future Phase H arb line.

---

## Live soak operator learnings (Jun 2026)

### Funding and L1 sizing

Operator added ~130 XRP to bot inventory. **Balance** updated immediately; **L1** did not jump 1:1 because:

- `L1 = min(configured_l1, 7% × XRP balance)` (`dynamic_sizing.py`)
- G2 cautious 0.75× on size
- Bid/ask asymmetric (inventory skew — larger bid, smaller ask)
- Queue preservation: `order_size_tolerance_xrp` 0.75 — resting offers kept if within tolerance

**Our lane** display uses `max(bid, ask)` at L1 — watch the bid leg for balance-driven sizing.

### Bal Δ showed deposit as “PnL”

Health bar **Bal Δ** used `session_pnl_balance_xrp` = portfolio at mid minus session baseline — **includes deposits**. ~129.8 XRP displayed after ~130 XRP fund.

**Fix:** Renamed to **Skim Δ** (spread capture estimate); moved **Wallet Δ** to Inventory with explicit tooltip.

### Skim Δ accuracy (~0.145 → ~0.67 → ~1.13)

Auditing VPS CSV: **199 of 207** session fills had `profit_xrp_equiv = 0` because balance-delta path stored fill price = mid → zero spread capture in CSV.

**Interim HUD model:** sum stored capture + for zero rows use `fill_volume × half_book_spread_bps` (from live `book_spread_pct`). Directionally useful; not ledger PnL.

**After segment end:** engine persists `session_spread_capture_xrp`; implied fill price on new fills; reconcile against CSV.

### Metrics toxicity “unknown”

Grading had a **20–25% gray zone** (neither good nor attention). Live toxic@30s ~27% should show **attention**. Fixed threshold to `>20%` = attention; inventory grade falls back to computed XRP % when enrich field missing.

### Inventory nav missing

Reports tab addition accidentally dropped Inventory link in `hud/index.html` — restored `e796fc9`.

### Downtime during soak

VPS intel: ~122 min gap 2026-06-16 (cycle reset); brief Jun 17 restarts ~1–2 min. Main engine segment otherwise continuous.

---

## VPS runtime snapshot (2026-06-17, illustrative)

| Field | Typical soak value |
|-------|-------------------|
| `fills_session` | ~200+ |
| `toxic_fill_ratio_30s` | ~27–31% |
| `g2_grade` | cautious (0.75×) |
| `balance_xrp` | ~220+ after funding |
| `session_baseline_xrp` | ~113 |
| Spread capture CSV sum (stored) | ~0.15 XRP session (undercount) |
| Skim Δ HUD (estimated) | ~0.7–1.1 XRP (model) |
| G6 tier | `pilot_watch` (toxicity + peer lane attention) |

---

## Known limitations (honest ops)

1. **Balance-delta fills** — late vs ledger; age not live until M2.
2. **`profit_xrp_equiv`** — mostly zero in CSV until implied-price engine deploy.
3. **Skim Δ during soak** — estimate, not wallet or tax PnL.
4. **Peer lane often empty** at pilot size — regime intel useful; G4 touch competition waits for scale.
5. **Sequence-bound ledger** — cancel/replace wall time can exceed 5s loop; P7 async submit post-soak.
6. **E3** — full 11k capital deployment blocked until operator/dev sign-off; pilot ~234 XRP-equiv on ledger.

---

## Engine-window bundle (2026-06-18 — deployed v2.1.15)

Single `xledgermate` restart deployed M2–M5 on VPS. Post-deploy: gates + queue soak for **G7** spec.

---

## G7 execution envelope (shipped v2.1.16)

**Problem:** v2.1.15 posted both sides ~8 bps behind touch; xrp-heavy 1 XRP bids invisible.

**Shipped:** Three-rule envelope in `execution_envelope.py` — per-side touch from inventory, widen via `g2.spread_mult` only, visibility on runtime. No modes, no Grok in hot path.

---

## Balance-delta coherence + HUD Skim fix (2026-06-18 — v2.1.17)

**Problem:** Composite balance deltas in one cycle produced nonsense implied prices (e.g. BUY @ 7.74 vs mid ~1.16). Engine logged artifacts; HUD **overwrote** `session_spread_capture_xrp` with a CSV sum and fell back to all-time capture — Skim Δ showed −14.9 / +28 swings while soak was fine.

**Shipped (`2fb597d`, `b463887`):**

- `balance_delta_fill_reject_reason` / `is_coherent_fill_price` — reject before fill log (±25% mid, BBO band, min 0.01 XRP).
- HUD stops overwriting engine Skim Δ; no all-time fallback in `sessionSkimDeltaXrp()`.
- `mid_at_quote_from_fill_notes` strict `@ mid` for economics; G6 grading skips incoherent rows.

**Post-fix soak:** Skim Δ ~0.005 XRP, session fills ~8, G6 `pilot_watch` → `scale_ready` on cumulative CSV as fill count grew.

---

## Post-deploy gates + G7 baseline (2026-06-18)

Ran `scripts/post_deploy_snapshot.py` on VPS (`.venv/bin/python`). Snapshot written to `logs/post_deploy_snapshot.txt`.

| Metric | Value |
|--------|-------|
| Version | 2.1.17 |
| Session fills | ~8 |
| Skim Δ (engine) | ~0.005 XRP |
| cancel/fill | 1.5 |
| markout@30s | −0.013% |
| toxic@30s | 14% |
| G7 (balanced) | bid/ask 8 bps · worst_vs_touch 8.0 bps |
| Last fill quote age | ~11.7 s |
| Intel would_quote | 92.2% (922 cycles) |
| G6 gate | PASS (`scale_ready` on cumulative fills) |

C2 `sample_history` soak gate still **FAIL** on short window (13 min, flip rate) — expected until longer post-restart run.

---

## 60-fill G7 checkpoint (2026-06-18, this run)

**Reached ~61 session fills.** 

- C2 gate **PASS** (123 min, flip rate 0.141 under the bar).
- Inventory moved xrp_heavy (asymmetric G7: wider passive bid, tighter join ask) → balanced (G7 symmetric 9/9 × G2 1.12).
- Session Skim slipped to −0.106 during the heavy leg on adverse ask flow (as designed for rebalance-side posting), then recovered.
- Markout@30s improved from more negative to ~0.
- Toxic@30s peaked ~26-27% → G2 cautious/brakes active.
- No peer lane entire window.
- G6 `pilot_watch` (toxicity + empty lane) but gate PASS on cumulative metrics (spread capture 95.7% pos, 8.5 bps avg).

**HUD note:** G7 queue (`g7-scaler`) and visibility (`queue-visibility`) are now explicitly wired through the production HUD payload so they appear in the Session fills card. Hard refresh the page.

**Design philosophy reminder (sacred core):** Pure A-S decides `would_quote` and reservation inside live BBO. G7 (and G2, pressure, age, G4) are **dynamic knobs** that influence vol, size, and posted prices only. Never override the inside-book guard.

**Discipline rule (operator):** A-S is what we do. We will win by discipline. The self-audit and HUD cards are mirrors to confirm the bot is running the designed behavior, not sources for mid-soak overrides.

**A/B verdict (preliminary — more hours welcome):** G7 v1 behaved as specified. The visibility cost and temporary Skim slip while heavy were the expected price of the asymmetric envelope. Data is now in intel JSONL tagged by `ws_as_version`. Ready to call "good enough for current pilot scale" or schedule a follow-up window for the mirror (rlusd_heavy) case.

**Operator call (2026-06-18):** G7 v1 — good enough. Keep an eye on live data. Run this instance until the next required engine restart. E3 is deferred until consistent gain and a warm fuzzy on the bot. HUD G7 fields (queue + queue vs touch) are wired; restart HUD service (soak-safe) + hard refresh to surface them in Session fills card.

Full numbers and table in `PURE_AS_CRITICAL_PATH.md`.

---

## 113-fill checkpoint (2026-06-18, same soak segment)

**Reached ~113–114 session fills** on v2.1.17 without engine restart.

- **Skim Δ** −0.101 XRP (slightly better than −0.106 at 61 fills).
- **Wallet Δ** +0.102 XRP — spot/MTM; not edge.
- **toxic@30s** 4.5% (down from ~26% peak during xrp_heavy leg).
- **markout@30s** +0.017%.
- **cancel/fill** 2.35 (up from 1.77 at 61 — watch).
- **presence** 93.4%.
- **Inventory / G7:** rlusd_heavy — bid join 3 bps, ask passive 8 bps (mirror of xrp_heavy case at 61 fills).
- **G2** neutral (×1.0).

**Verdict:** G7 v1 confirmed through both inventory mirrors. Continue soak; no mid-soak overrides.

**Next dev:** **M6** per-sequence quote age — **deployed v2.1.18**; 50-fill eval soak started 2026-06-18.

---

## Post-soak backlog (condensed)

| Track | Items |
|-------|--------|
| Intel automation | P1–P7 per-peer history, tx correlation, async submit |
| Regime channel | I1–I4 damped book-wide inputs; I7 in-band peers |
| Capital | E3 funding + rebalance execution |
| Arb line | H3–H7 (separate wallet; H1 monitor already logging) |
| UX | F4 grok suggestion outcome correlation |

Full IDs and blockers: critical path [Priority stack](PURE_AS_CRITICAL_PATH.md#priority-stack).

---

## Key files (where to read the code)

| Concern | File |
|---------|------|
| Production loop | `experimental/ws_feed/ws_pure_engine.py` |
| Pure A-S decision | `experimental/ws_feed/pure_quote_path.py` |
| L1 sizing | `experimental/ws_feed/dynamic_sizing.py` |
| Fill infer | `monitoring/fill_detection.py` |
| Spread capture | `monitoring/fill_economics.py` |
| HUD mirror | `experimental/ws_feed/ws_hud_production.py` |
| Operator UI | `experimental/ws_feed/hud/index.html` |
| G6 grades | `experimental/ws_feed/live_activation_grading.py` |
| G7 envelope | `experimental/ws_feed/execution_envelope.py` |
| Session fills gate | `scripts/ws_path_session_report.py` |
| Post-deploy gates | `scripts/post_deploy_snapshot.py` |
| Intel JSONL | `experimental/ws_feed/intel_decisions_log.py` |

| 2026-06-19 | M6 signed off (50 fills); **v2.1.22** engine bundle for spread-capture + churn; 6–8h time soak next |

---

## 2026-06-19 — M6 sign-off + v2.1.22 engine bundle

**M6 verdict (50 fills, v2.1.21):** Measurement PASS. Economics: 92% pos but 4.96 bps → G6 `hold`, Skim Δ −0.175 XRP. Toxicity/markout healthy. cancel/fill 2.92 elevated.

**v2.1.22 (next restart):** G7 join floor 5 bps + book-aware; mid-move preserve 8 bps; `book_bids`/`book_asks` export; M6 tracker clear on fill; `session_boot_utc`.

**Next soak:** 6–8 hours wall-clock, not fill-count gated.

---

**Deploy:** `xledgermate-ws-hud` only — ws-engine left running through M6 eval soak.

**Shipped:**
- **Wealth sidebar:** `wealth_hud_payload()` wired through `_hud_market_payload` so spot/rebal/XRP@mid fields reach `/state` (enrichment alone was stripped).
- **Book tab:** depth chart, split ladder, our L1–L3 from `quote_intents` (L2/L3 planned until multi-level ledger sync). `book_bids`/`book_asks` forward-ready for next engine restart.
- **Metrics:** spread capture 5–8 bps band grades `attention` (not `unknown`); G6 **hold** card with red tier, attention triggers, gate FAIL when spread capture blocks activation.
- **Bugfix:** duplicate `deltaEl` in HUD JS broke entire render loop (blank cards).

**Live soak signal (~41 session fills):** G6 tier **`hold`** — 92% positive capture but 5.35 bps avg (&lt; 8 bps bar). Toxicity/drawdown good. Posture: conservative size, review G2/G4 brakes; no strategy override.

---

## 2026-06-19 — v2.1.22 time soak + G8 spec

### M6 sign-off + v2.1.22 engine bundle

50-fill eval on v2.1.21: measurement PASS; economics thin (4.96 bps, G6 hold, Skim Δ −0.175). v2.1.22: G7 join floor 5 bps, `WS_MID_MOVE_REFRESH_BPS` 8, book depth export, M6 tracker clear on fill, `session_boot_utc`.

### Session-scoped G6 (HUD)

`build_performance_metrics()` grades fills since `session_boot_utc`. Fixes inherited cumulative **hold** after engine restart. HUD meta: session vs cumulative fill counts. Test: `test_session_boot_scopes_g6_to_warming_up_not_cumulative_hold`.

### Soak segment #1 (spot drop) — archived

Boot 03:40 UTC → ~83 fills. Mid 1.138 → 1.124. Wealth Δ −2.6 RLUSD (spot −3.3, skim −0.12). Session G6 **hold** (51% pos, −0.14 bps). BUY-side capture bleed; 61s stale bid fill. G2 neutral at toxic@5%. Operator halt via kill + cancel.

**Takeaways:** G6 hold advisory only; G2 brakes on markout/toxic not negative skim; preserve_touch_queue + tight book vol proxy miss directional drops. **G8** spec drafted to lean into spot moves offensively (bounded).

### Peer Cal — empty lane verdict (2026-06-20)

Peer Cal tab deployed (`89c89f7`). VPS calibration JSONL: **live ~18 XRP** and **shadow E3 ~424 XRP** both **0 peers in band** — whale book, solo MM at touch. **P4–P6 peer intel shelved**; passive watch if `peer_lane_count` or `shadow_peer_lane_count` &gt; 0. G4 empty-lane neutral validated.

### Soak segment #2 — closed (Watch)

Clear-kill + restart ~13:24 UTC · **57 fills** · ~4h15m · v2.1.22. Snapshot `logs/post_deploy_snapshot.txt`.

| Metric | M6 | Segment #2 |
|--------|-----|--------------|
| Skim Δ | −0.175 XRP | **+0.024 XRP** |
| Spread bps / pos% | 4.96 / 92% | **1.28 / 67%** |
| toxic@30s | 8.7% | 28.6% |
| cancel/fill | 2.92 | 2.96 |
| Wealth Δ RLUSD | — | **+1.28** (spot-led) |
| G6 v1.0 | hold (thin-edge false) | hold (economics real) |

**Verdict: Watch** — positive skim and wealth on solo whale book; weak spread capture and SELL-side bleed are real. G8 **deferred** (spot helped). Sufficient sample — segment stopped.

**Patterns:** SELL skim bleed vs BUY; stale fill-age tail (127s–4876s); G2 cautious at ~29% toxic. v2.1.22 churn window did not improve cancel/fill vs M6.

### G6 v1.1 shipped (HUD-only) — last optics update for a while

Operator consensus: stop grading churn; fix false **hold** on thin join-aligned capture (M6 92%/5 bps); keep **hold** meaningful for bad economics (#2 1.28 bps / 67% still holds).

**Shipped v1.1.0:** `thin_edge` grade (5–8 bps, ≥70% pos) → tier **`thin_edge`**, gate PASS (yellow); `hold_min_fills=15`; hold = bad economics only (bps&lt;0, pos&lt;50%, or bps&lt;3 and pos&lt;70%); zero-capture neutral for pos%. HUD tier pill + soak strip. **No engine change** — restart `xledgermate-ws-hud` only.

**Next:** one ~50-fill calibration soak on v1.1 labels, then **acquisition phase** — optimize fill acquisition on empty peer band (presence, size, join), not HUD cosmetics. G6 Tier 2/3, G8, peer intel remain deferred.

---

## How to extend this log

When shipping a meaningful chunk:

1. Add a dated subsection under **Timeline** or a new **Learnings** bullet.
2. Note commit hash, VPS deploy (HUD-only vs engine), and operator-visible behavior.
3. Keep [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md) TODO tables in sync.
4. Optional: one line in `CHANGELOG.md` for versioned releases.
5. Optional: `groks input/collab/THREAD.md` for Grok ↔ Cursor session handoff.

Do not duplicate the full task checklist here — link to critical path instead.

---

## Related docs

- [`PURE_AS_CRITICAL_PATH.md`](PURE_AS_CRITICAL_PATH.md) — priority stack + backlog  
- [`PHASE_E_VPS_RUNBOOK.md`](PHASE_E_VPS_RUNBOOK.md) — E1–E3 ladder  
- [`../experimental/ws_feed/WS_HANDOFF.md`](../experimental/ws_feed/WS_HANDOFF.md) — wiring parity  
- [`../CHANGELOG.md`](../CHANGELOG.md) — versioned release notes  
- [`../groks input/collab/THREAD.md`](../groks%20input/collab/THREAD.md) — collaboration log  
