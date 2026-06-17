# Pure A-S Critical Path

**Status:** Active — **WS + pure Avellaneda-Stoikov** is the production MM quoting model on VPS.  
**Version:** **v2.1.14** (`VERSION` + `experimental/ws_feed/WS_AS_VERSION`) · **Branch:** `Ashigaru-Kaizen` (VPS live MM)  
**Sacred corpus:** `grok-tier-2-collab` (Gate 2 replay + economics) · **E2 merged** 2026-06-15  
**Last updated:** 2026-06-17 (soak-safe batch: fill-age report, I6 HUD, F1 nicknames, stale-cross analysis, Telegram Res→BBO)

This is the **single checklist** for WS + pure A-S work. Other docs point here; do not duplicate task lists elsewhere.

---

## Soak deploy discipline

| Change type | Restart | Safe during live soak? |
|-------------|---------|----------------------|
| HUD HTML / `ws_hud_production.py` / `reservation_metrics.py` | `xledgermate-ws-hud` only | **Yes** |
| `pure_quote_path.py` / `as_safety.py` (lab + CI) | — until engine pull | **Yes** (VPS ws-engine unchanged) |
| `ws_pure_engine.py` logging / fill age / stale-cross | `xledgermate` | **No** — plan segment boundary |
| `vps_deploy_ashigaru.sh` full deploy | ws-engine + HUD | **No** unless intended |

**Sacred rule:** reservation inside live BBO = `would_quote` gate. Measurement and HUD never override A-S math.

---

## Direction

| From (legacy) | To (committed) |
|---------------|----------------|
| HTTP BookOffers poll | WS `BookFeed` / `WsBookFeed` |
| Hard `market_edge_met` + heuristic vetoes | Pure A-S: reservation inside book + optimal spread |
| Low presence on thin books (~11%) | Higher safe presence when math allows (~90%+ on sacred replay) |
| Grok/pressure as ideas | Advisory inputs to A-S (vol, spread anchor, size) — **never** override reservation |

**Safety contract:** `would_quote` = reservation inside live best bid/ask. Pressure, Grok, and AI only tune **inputs**.

**Sacred replay** on `grok-tier-2-collab` is for economics baseline only. **Live VPS MM** runs `Ashigaru-Kaizen` `ws-engine` (Phase E1 complete).

---

## Doc map (read order)

| # | File | Use |
|---|------|-----|
| 1 | **This file** | Critical path checklist |
| 2 | [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md) | Run tester + HUD + Grok |
| 2b | [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md) | Branch roles (Ashigaru vs collab) |
| 3 | [`PHASE_E_VPS_RUNBOOK.md`](PHASE_E_VPS_RUNBOOK.md) | VPS swap ladder (E1–E3) |
| 3b | [`../groks input/FOR_AI_AND_FUTURE_SESSIONS.md`](../groks%20input/FOR_AI_AND_FUTURE_SESSIONS.md) | VPS ops, milestones |
| 4 | [`../experimental/ws_feed/WS_HANDOFF.md`](../experimental/ws_feed/WS_HANDOFF.md) | Architecture + wiring parity |
| 5 | [`../groks input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md`](../groks%20input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md) | Gate pass metrics (doc 05) |
| 6 | [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | Tiers 1–2 history + field gates |
| 7 | [`../experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md`](../experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md) | **Phase G** — posted-touch peer lane + intel rollout (E.1–E.6) |
| 8 | [`../groks input/collab/THREAD.md`](../groks%20input/collab/THREAD.md) | Grok ↔ Cursor log |

**Session quick start:** [`../groks input/CURSOR_HANDOFF_ROADMAP.md`](../groks%20input/CURSOR_HANDOFF_ROADMAP.md) (run commands + file pack only).

---

## Run the lab (daily)

```powershell
cd C:\Users\micha\xledgermate
.\.venv\Scripts\Activate.ps1
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 300 --sample-interval 4 --verbose
```
(Grok key: `.env` → `XLG_GROK_KEY`. No `--profile` — PureQuotePath **v2.1.0**.)

```powershell
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 0 --verbose
```

Open http://127.0.0.1:8765 · Artifacts: `logs/ws_as_demo_runtime.json`

**Measure sacred corpus:**

```powershell
python experimental/grokster.py
python -m experimental.ws_feed.replay_long_run --as-mode pure --economics
python -m experimental.ws_runtime_analysis
python -m experimental.ws_runtime_analysis --include-backups
python -m experimental.swap_readiness_report
python -m experimental.ws_feed.replay_long_run --swap-readiness --gate
python -m experimental.as_calibration_grok --dry-run
python -m experimental.as_calibration_grok
python -m experimental.ws_feed.peer_lane_replay_validation
python -m experimental.ws_feed.replay_long_run --peer-lane-g5 --gate
```

---

## Critical path checklist

Update checkboxes when items ship. Mark **FOR_AI § Milestones** + **THREAD** on major completions.

### Phase 0 — Done (foundation)

- [x] WS probe validated (`experimental/ws_feed/PROBE_RESULTS.md`)
- [x] Pure A-S strategy (`strategy/avellaneda_strategy.py`)
- [x] Replay + grokster on sacred corpus (presence lift)
- [x] `sacred_economics.py` — capture, neg-fill %, balance-delta, marginal oracle
- [x] `competitor_pressure.py` + tests — monotonic vol/gamma/size/spread inputs
- [x] `engine_adapter_example.py` — PureQuotePath sketch (pressure + AI advisory hook)
- [x] Live tester + HUD (`:8765`) — Intelligence tab, competitor scrape
- [x] Real Grok on-demand (`grok-3`, model dropdown, `/analyze_competitor`)
- [x] Unlimited tester runs (`--seconds 0`)

### Phase A — Measurement (do before predator / scale claims)

- [x] **A1** Sacred economics A/B: baseline vs pure vs pure+pressure scenarios (`grokster --ab` default on; `replay_long_run --economics --ab`). **Grok/xAI excluded** from A/B — advisory + competition research only until post-swap.
- [x] **A2** Runtime analysis script over `logs/ws_as_demo_runtime.json` (`python -m experimental.ws_runtime_analysis`; `--include-backups` for prior sessions). Tester now appends `sample_history` for long-run stats.
- [x] **A3** Grok advisory calibration session (`python -m experimental.as_calibration_grok`) — bundles A2 + sacred presence + competitor intel → suggested gamma/kappa/vol trials + validation commands. **Does not** set would_quote. Check in `experimental/ws_as_calibration.yaml` only after operator validates trials.

### Phase B — Production-shaped pure path (experimental only)

- [x] **B1** Unify `live_pure_as_tester` on `WSBookFeedAdapter` / `pure_quote_path.PureQuotePath` — **no trading profiles**, no `build_quote_adjustments`. Version `experimental/ws_feed/WS_AS_VERSION` = 0.1.0.
- [x] **B2** Dynamic sizing helper (`L1 = min(config, k × XRP bal)`; ask boost when XRP-heavy + low ask-pressure) — `dynamic_sizing.py`, wired in `PureQuotePath` v0.1.2
- [x] **B3** WS book age modulator (stale → higher effective vol; fresh + low pressure → allow aggression) — `ws_book_age_modulator.py`, wired in `PureQuotePath` v0.1.3
- [x] **B4** Tight-book decision notes (explain 0 quotes: spread floor vs reservation outside book — operator clarity) — `zero_quote_notes.py`, HUD note + summary, v0.1.4

### Phase C — Validation & metrics (after Phase B; before infra)

*Focus: prove the pure path on live WS data. No new Grok exploitation or nickname UX yet.*

- [x] **C1** Track presence when pressure low vs high + `zero_quote_reason` breakdown in runtime export / `ws_runtime_analysis` — `compute_c1_metrics`, `presence_by_pressure` + `zero_quote_breakdown` on each sample append; analysis report + `--json`
- [x] **C2** Long-run soak criteria (30+ min, presence %, book-age distribution, flip rate) — gate before D2; `evaluate_soak_gate` + `soak_evaluation` on runtime export; `python -m experimental.ws_runtime_analysis --soak-gate` (exit 1 if fail). Defaults: ≥30 min, ≥50% presence, flip rate ≤0.20, WS age mean ≤12s / p95 ≤20s, ≥80% samples fresh (<12s)

### Phase D — Infrastructure (pre-swap)

- [x] **D1** `WsBookFeed` hardening (reconnect backoff, `is_fresh` / max age guards, 30+ min soak) — `is_fresh`, exponential `run_forever` backoff, stale refresh in run loop; C2 soak passed
- [x] **D2** Promotion step: dry-run offers on WS path (same PureQuotePath, no sacred engine edits) — `pure_dry_run_executor.py`, `--dry-run-offers` (default on) in live tester
- [x] **D3** Streamlit side-by-side demo (`ws_as_demo_runtime.json` vs sacred runtime) — **WS compare** tab in `streamlit_gui.py`
- [x] **D4** Swap readiness report from `replay_long_run` (wiring parity + economics summary) — `python -m experimental.swap_readiness_report` or `replay_long_run --swap-readiness`; writes `logs/swap_readiness_report.json`

### Phase E — VPS swap (complete 2026-06-15)

*Production MM = **`Ashigaru-Kaizen`** `ws-engine`. Sacred replay = **`grok-tier-2-collab`**. **Runbook:** [`PHASE_E_VPS_RUNBOOK.md`](PHASE_E_VPS_RUNBOOK.md) · **Branches:** [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md)*

- [x] **E1** Wholesale VPS replace with WS + pure A-S — **live quoting** 2026-06-15 (`dry_run: false`)
  - [x] E1.1 VPS on Ashigaru + `ws-engine` systemd
  - [x] E1.2 Dry-run smoke ≥30 cycles (`cycle_count`)
  - [x] E1.3 `python scripts/vps_ws_engine_signoff.py --gate` PASS (2026-06-15)
  - [x] E1.4 Flip `dry_run: false` + restart — **live** 2026-06-15
  - [x] E1.5 ≥50 WS-path live fills + markout — **PASS** (`logs/e15_report.json`, `scripts/ws_path_session_report.py --gate-full`; CSV authoritative after restarts)
  - [x] E1.6 Operator sign-off — positive 30s markout; inventory skew → rebalance layer (E3)
- [x] **E2** Merge `Ashigaru` → `grok-tier-2-collab` — 2026-06-15; P0 `market_edge_met` gate = legacy replay only; VPS stays `ws-engine`
- [ ] **E3** 11k funding + rebalance execution — **operator blocked** until dev complete; pilot ~234 XRP-equiv on bot ledger only
- [x] **E4** `WsPureTradingEngine` via **`python main.py --mode ws-engine`**

### Phase G — Peer-lane intelligence (experimental)

*Operator-locked: **posted touch** defines peer lane; **portfolio XRP-equiv** grades success. Full spec: [`PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md`](../experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md). Advisory only — never overrides reservation. G4+ unblocked after E1 sign-off (2026-06-15).*

- [x] **G1 (E.1)** Posted-touch peer band in `competitor_intel.py` — `our_lane_xrp` from L1 intents; filter scrape by touch band; peer-only pressure; HUD peer vs book-wide lists
- [x] **G2 (E.2)** Spread-quality scaler — `spread_quality_scaler.py` v2.1.0; brake on toxicity/markout (size× + vol/spread×); **no** win-chase, **no** kill coupling; wired in `PureQuotePath` + `ws-engine`
- [x] **G3 (E.3)** Intel JSONL + Performance Metrics tab (HUD and/or Streamlit)
- [x] **G4 (E.4)** Wire peer-lane signals into `PureQuotePath` size_mult / side bias — `peer_lane_quoting.py` v2.1.4; production `ws-engine` scrapes peer lane ~15s
- [x] **G5 (E.5)** Replay validation — `peer_lane_replay_validation.py`; peer coverage % + neutral-fallback rate on `intel_decisions.jsonl` + WS samples; sacred eligibility baseline
- [x] **G6 (E.6)** Live activation graded by §7 — `live_activation_grading.py` (portfolio XRP-equiv, capture, toxicity, G2/G4 rates); HUD Metrics tab; `python -m experimental.ws_feed.live_activation_grading --gate`

### Phase M — Execution measurement (active soak)

*Instrumentation only — **no change** to reservation/optimal spread math in `avellaneda_strategy.py`. Advisory paths remain inputs. Fill age is **detected** (balance-delta), not ledger fill time.*

**Philosophy:** Measure before automating (sync policy, async submit P7, regime I1–I4). HUD-first where possible.

- [x] **M1** **Reservation → BBO delta (soak-safe)** — `reservation_metrics.py`; signed bps + `inside_l1`; HUD Live card via `ws_hud_production._enrich_runtime_for_hud`; `pure_quote_path` + tester `sample_history` (lab); **ws-hud restart only** on VPS
- [ ] **M2** **Quote age @ detected fill** — `effective_quote_age_at_fill_seconds` on decision/runtime; populate in `ws_pure_engine._detect_fills` (last side place timestamp v1); label honestly in HUD + CSV
- [ ] **M3** **Stale-cross flag** — `reservation_crossed_after_ws_sample` in `ws_pure_engine` (frozen reservation vs pre/post-scrape BBO); `zero_quote_notes.py` operator string; `ws_runtime_analysis` bucket — **engine restart** (analysis schema + operator string **shipped** soak-safe)
- [ ] **M4** **Production `sample_history`** — parity with tester `append_runtime_sample`; enables soak breakdowns on VPS — **engine restart**
- [x] **M5** **Advisory guard (narrow)** — `as_safety.py` enforces reservation-inside-L1 only; wired in `pure_quote_path`; production when engine deploys
- [ ] **M6** **Per-sequence quote age** — `_offer_placed_utc[sequence]` after M2 data reviewed — post-soak

**HUD during current soak (M1):** Res → BBO Δ each cycle (derived). Fill age / stale-cross show `—` until M2/M3 engine deploy.

**Soak-safe batch (2026-06-17, no ws-engine restart):** `scripts/fill_quote_age_report.py` (offline M2 prep); hourly Telegram Res→BBO; I6 HUD labels; F1 nicknames; M3 analysis bucket in `ws_runtime_analysis` + `zero_quote_notes`.

**Limitations (document in ops):** balance-delta fills ≥1 cycle late; kept offers understate age until M6; stale-cross = intel scrape window only.

### Phase H — On-ledger arbitrage & multi-pair (separate product line)

*Deferred until **G6 soak** + live activation gate pass. **Not** a tweak to ws-engine MM — a **second stack** (taker / path / AMM), optionally on a **second wallet**. Reuses sensors (WS book, competitor intel, fill economics); different execution (`Payment` + path, `AMMSwap`, not standing `OfferCreate`). Advisory intel today: HUD “Active Makers” = RLUSD/XRP CLOB accounts seen in ~5 min (not whole-ledger census).*

**Operator thesis:** Thin RLUSD/XRP CLOB can still show **CLOB↔AMM** or **stable-basis** edges when book-wide MM grinds. Arb does not fix thin MM; it is an adjacent PnL line when mispricings exceed fees + inventory risk.

**On-ledger paths (priority order for XLedgerMate):**

| Priority | Path | Venue | Reuse from MM stack | Main new work |
|----------|------|-------|----------------------|---------------|
| **H1** | XRP/RLUSD **CLOB vs AMM** | Order book + XLS-30 pool | Same pair, trust line, WS mid | Pool quote feed, `AMMSwap` / LP txs, edge vs CLOB |
| **H2** | **RLUSD ↔ USDC** basis via XRP | Two stables + bridge leg | Connector, portfolio XRP-equiv | Second trust line, dual-book scrape, path `Payment` |
| **H3** | **Triangular / path arb** | Path engine (offers + AMM) | RPC, wallet, logging | `path_find` scanner, atomic `Payment`, sim before send |
| **H4** | Cross-pair stat (RLUSD book vs USDC book) | Two CLOBs | Intel scraper pattern | Multi-pair config, correlated spread monitor |

**Explicitly out of scope (Phase H):** meme/community IOUs, CEX↔XRPL (latency/custody), bridge/wXRP arb, RWA pools — different risk and infra.

**Wallet architecture (required before live H2+):**

| Wallet | Role | Why separate |
|--------|------|--------------|
| **A — MM** | ws-engine, resting offers | Sequence-bound; refresh churn competes with taker txs |
| **B — Arb** (optional) | path payments, AMM swaps | Snipe dislocations without canceling MM quotes |

Shared: RPC, WS feeds, HUD/intel scrape, CSV logging. **Do not** mix MM offer sync and arb `Payment` on one account at high frequency.

**Operator UI (decided — not built):** One HUD (`:8765`), separate `ws-engine` + `ws-arb` processes; nested `state.arb` in `/state`; **Arb** tab — see Phase H checklist.

**Gate before any Phase H live tx:**

- [ ] G6 `--gate` pass on current soak (or successor activation tier)
- [ ] Read-only monitor shows edge > threshold for ≥N hours (see H1 below)
- [ ] Arb wallet funded separately; MM soak uninterrupted
- [ ] Trust-line / No-Ripple parity for any new stable (same discipline as RLUSD)

**Phase H checklist (future dev):**

- [ ] **H1** Read-only **CLOB vs AMM monitor** — log each cycle: CLOB mid (WS), AMM implied XRP/RLUSD price, spread bps, fees; artifact `logs/clob_amm_spread.jsonl`; HUD or Metrics tab pill; **no trades**
- [ ] **H2** `experimental/liquidity/amm_provider.py` — fetch pool state (XRP/RLUSD), normalize to RLUSD/XRP; config flag `amm_monitor_enabled`
- [ ] **H3** CLOB↔AMM **paper executor** — simulate round-trip PnL after pool fee + ledger fee; gate on min edge (e.g. 8–15 bps net)
- [ ] **H4** Live **arb wallet** + `AMMSwap` / two-leg path prototype (XRP/RLUSD CLOB vs AMM only)
- [ ] **H5** USDC trust line + dual-book scrape (RLUSD + USDC vs XRP); stable-basis monitor (read-only first)
- [ ] **H6** Path-arb scanner (`path_find` + `Payment`) — separate process; rate-limited; optional second stable
- [ ] **H7** Operator runbook + kill: max daily arb loss, min net edge, inventory caps per asset

**H1 monitor pass/fail (suggested defaults — tune after data):**

- Log when `|clob_mid − amm_implied_mid| / mid × 10_000 ≥ 8` bps (before fees)
- Report: count/hour, max bps, time-of-day distribution
- **Promote to H3** only if ≥5 events/hour above 12 bps net for 24h paper window

**Relation to AMM LP extension:** Passive LP (fee earning) stays under “Optional AMM Liquidity” below — complementary, not arb. Phase H **H1–H4** is **active dislocation capture**; LP is **passive**.

### Phase F — Grok exploitation & operator UX

*Advisory only — never overrides reservation. **During soak:** HUD-only changes (`ws-hud` restart OK; do **not** restart `ws-engine`).*

- [x] **F1** Competitor nicknames (local JSON map; HUD display/edit) — `competitor_nicknames.py`, Intelligence tab, `/competitor_nicknames` API
- [ ] **F2** Grok exploitation output → optional `AIAdvisorySignal` (rate-limited; not every cycle)
- [x] **F3a** Grounded `/analyze_competitor` — scrape profile + peer-band context in prompt; evidence header in HUD (`hud_intel_support.py` + `real_time_as_hud.py`; **ws-hud only**, 2026-06-17)
- [ ] **F3b** Structured JSON peer briefing + prompt iteration from validated analyses
- [ ] **F4** Track "Grok suggestion → outcome" in runtime export / `intel_decisions.jsonl`

### Post-soak work (requires `ws-engine` restart — defer until soak ends)

*Do not interrupt live MM soak for these. Peer band scales automatically with `our_lane_xrp` — no separate whale/peer mode.*

**Intel measurement (engine)**

- [ ] **P1** Per-peer event history in `competitor_intel.py` — touch changes, fled-touch series, cancel-after-fill timing (not snapshot-only)
- [ ] **P2** WS tx stream correlation — cancel-after-fill, reaction to our fills → adverse-selection proxy (was Future §8)
- [ ] **P3** Persist full L1–L3 ladder in `runtime_state.json` for HUD (planned depth visible without fraction fallback)

**Intel → action (engine + optional G4)**

- [ ] **P4** Structured `PeerBriefing` schema from Grok (holes, posture, confidence) — log + HUD badges
- [ ] **P5** Optional G4 hook: per-peer posture nudges when briefing + fled-touch align (still advisory inputs only)
- [ ] **P6** F2 + F4: rate-limited `AIAdvisorySignal` + suggestion outcome tracking

**Ledger execution (scale)**

- [ ] **P7** L1–L4 from operator note — instrument tx rate, async submit path, RPC latency (see § Ledger cadence below; **Phase M** data gates timing)

**Execution measurement (links Phase M)**

- [ ] **M2–M4** engine window — fill age, stale-cross, `sample_history` (see Phase M)
- [ ] Correlate M2/M3 with markout before changing `resolve_ws_sync_tolerances` or P7 async submit

**Gates before promoting post-soak intel to automation**

- [ ] Current G6 soak / activation gate pass
- [ ] In-band peer analyze shows scrape evidence header (not “No scrape row”)
- [ ] ≥N analyzed peers with logged outcomes vs markout

### Intelligence boost (post-soak — regime + empty peer lane)

*Future development. **Soak validation (2026-06-17):** With `peer_lane_count=0`, grounded Grok analyze on book-wide passive makers (touch 0 at BBO, ~0 cancels on 3k+ offers, ~190k XRP depth, aggregate pressure ~0.24, L1 ~0.08% vs maker avg ~0.20%) produces useful **regime/macro** briefings. HUD + skim advice use book-wide pressure; quoting path currently **neutralizes** to 0.5 via `prepare_quoting_intel()` when peer lane is empty (Phase G — whales must not steer touch competition). These items add a **separate, damped regime channel** so defensive macro conditions can nudge A-S inputs without conflating back-book liquidity with in-band peers. Full G4 aggression stays for real touch-band peers as `our_lane_xrp` scales.*

**Regime inputs (engine — advisory to A-S only)**

- [ ] **I1** **Book regime channel** — When `peer_lane_empty`, expose `book_regime_pressure` (from aggregate scrape, e.g. 0.24) with **capped** influence on vol / `size_mult` / spread inputs (e.g. 50% of peer-lane effect). Do **not** treat book-wide makers as touch peers; keep `prepare_quoting_intel()` peer-lane purity for G4.
- [ ] **I2** **Spread regime gap** — Metric: `observed_L1_spread − avg_competitor_spread` (tight touch vs wide passive depth). Large gap + low book cancel rate → mild confidence to hold `as_optimal_spread_pct` (avoid unnecessary widening when back-book is static).
- [ ] **I3** **Passive-depth sync policy** — Book-wide `avg_competitor_cancel_rate` or share of makers with zero cancels. When very passive → `resolve_ws_sync_tolerances`: preserve queue longer, fewer cancel/replace cycles (sequence + fee savings; matches “don’t cancel-race static ladders”).
- [ ] **I4** **Depth-buffer size nudge** — High `competitor_depth_xrp` + empty peer lane → small capped `size_mult` bump (passive depth absorbs flow; less pickoff panic). Hard cap; G2 markout brake still wins.

**Regime context (measurement + operator)**

- [ ] **I5** **Book-wide side skew aggregate** — Roll up scrape `sides` (bid vs ask offer counts) for macro inventory context; log + HUD pill only until validated against own markout (do not override `dynamic_sizing` inventory policy without data).
- [x] **I6 (HUD)** **Regime vs peer split** — `regime_intel_hud_fields()`; Intelligence + Metrics tabs; `book_regime_pressure` in scrape export — JSONL logging deferred to engine window

**When in-band peers appear (touch competition — builds on G4)**

- [ ] **I7** In-band grounded analyze + fled-touch + G4 skim grade as the **primary** automation path; regime channel (I1–I4) remains background modulation, not a substitute for peer-lane signals.

**Explicitly defer / validate before automating**

- Do not wire Grok prose tactics (fixed bps inside, 1.2–1.5× size rules) directly — use structured briefing (P4) + markout gates.
- Do not use book-wide whale profiles for queue-jump or touch-lane sizing; `touch_xrp=0` means back-book only.


*WS + pure A-S remains the committed core. These are **enhancements and adjacent layers**, not replacements. Promote an item only after D2 live fills + markout on the WS path. Sacred/VPS data = calibration baselines, not WS PnL targets.*

**Priority order (growth leverage):**

1. **Fill-calibrated A-S (κ, γ from live data)** — Rolling fit of arrival intensity and adverse selection from WS-path fills and markouts; replace static defaults when n≥50 fills per regime.
2. **Markout / toxic feedback loop** — Post-fill markout (30s, 5m) → tune vol, `size_mult`, side skew; complement pressure/age with **own PnL** as ground truth.
3. **11k rebalance execution layer** — Scheduled ask-heavy rebalance (XRP-only → ~55% target); A-S for steady-state after balance (Almgren–Chriss–style scheduling, not continuous MM).
4. **Queue / level heuristics** — L1 vs L2 vs behind large walls; fill probability vs pickoff; refresh when BBO moves (matters more as L1 scales with capital).
5. **GLFT / refined AS family** — Explicit fill-intensity curves λ(δ); same role as A-S when λ is estimable from ledger fills.
6. **Regime-conditioned parameters** — Calm / toxic / skimmable regimes from pressure + vol + markout; formalize current hand-tuned multipliers. **See Intelligence boost I1–I6** (empty peer lane + book-wide regime).
7. **Contextual bandit / light RL on posture** — Discrete {tight, normal, wide, one-sided off} as **inputs to A-S only**; after hundreds of labeled WS fills (Phase F–adjacent).
8. ~~**Competitor cancel/fill correlation**~~ → **Post-soak P2** (WS tx stream; engine restart required)

**Explicitly deferred / separate products:**

| Option | Why not now | Track in |
|--------|-------------|----------|
| End-to-end deep RL quoting | Data-hungry; hard to debug on mainnet | Future strategy §7 |
| Cross-venue / CEX–DEX arb | Different capital, latency, infra | Out of scope |
| AMM vs DEX arb | Separate stack; taker not maker | **Phase H** (H1–H4) |
| RLUSD ↔ USDC basis | Second trust line + dual book | **Phase H** (H5) |
| Path / triangular arb | Sequence + scanner infra | **Phase H** (H6) |
| Pure trend / momentum | Conflicts with MM economics | — |

**New: Optional AMM Liquidity & Fee Earning (Future Extension)**

- **Status**: Deferred — future hybrid layer only (passive LP; distinct from **Phase H** active arb).
- **How it works**: Deposit XRP + counter-asset into XLS-30 pools (with Swappable Curves when live) to earn trading fees pro-rata.
- **Impact on pure A-S**: None on core order-book quoting. Can run in parallel as complementary passive income.
- **Future-proofing**: Keep modular. Add `experimental/liquidity/amm_provider.py` later with config flag. Integrate inventory tracking but never touch reservation price.
- **When to consider**: After bag >30k XRP and stable order-book performance; after **H1** monitor proves pool vs CLOB linkage.

**New: Self-Diagnostic & Trap Building (long-term)**

- Self-evaluation on own address + optional trap tactics — **after** Phase M measurement + peer band stable. Advisory-only initially.

**Decision rule before any option ships:**

- [x] C2 soak pass + D2 dry-run offers on WS path
- [x] ≥50 WS-path fills with ledger-accurate markout (E1.5)
- [ ] Economics show extra presence does not destroy mean markout (ongoing soak / G6)
- [ ] Change is **inputs to A-S** or **execution schedule** — never override reservation-inside-L1

**Offense vs defense (tuning note):** WS trades gated “sit out” for “quote if inside book.” Offense wins on **presence**; defense wins on **size/tightness** at high pressure. Future options should sharpen **when to lean in** (low pressure, good markout history), not reintroduce binary hard gates.

**Future review — MM posture vs kill switch (operator thesis, 2026-06-15):**

We are a **market maker**, not a trend-trading bot. Revisit after E1.5 live fills:

- [ ] **R1** Replace binary kill-first behavior with **continuous posture**: stay on book; **brighten** (size / tightness / presence) on good capture + markout runs; **dim** (wider spread, smaller size, one-sided skew) on bad runs — do **not** mirror competitors who cancel entirely on bad tape (exploitable flee).
- [ ] **R2** Good run: A-S reservation + optimal spread stay the core — no momentum chase; aggression = larger size / tighter *inside-book* quotes when own markout + peer pressure allow (competitor intel: others double down here).
- [ ] **R3** Bad run: session/drawdown limits become **graduated brakes** (caps on size, refresh cadence, side bias) before full halt; kill switch only for operator-defined catastrophe (RPC death, wallet integrity), not normal adverse selection.
- [x] **R4** Wire R1–R3 through **G2 spread-quality scaler** + markout loop — G2 shipped v2.1.0; kill decoupled; validate on ongoing live samples

*Until R1 ships: legacy kill switch remains a safety net from the poll era; config tunable but philosophically misaligned with pure MM.*

**Future consideration — XRPL ledger vs quote refresh cadence (operator note, 2026-06-15):**

XRPL has **no dedicated “quotes per second” rate limit** for market makers. `OfferCreate` / `OfferCancel` are normal account transactions. Practical ceilings:

| Constraint | Effect on ws-engine |
|------------|---------------------|
| **Account sequence** | One validated tx at a time per bot wallet; next submit waits on prior `Sequence`. |
| **Ledger close ~3–5s** | Each `submit_and_wait` in `connectors/xrpl_connector.py` blocks until validation — not a separate quote API throttle. |
| **Sequential sync** | `_sync_offers` cancels then places in series; full churn (2 cancel + 2 place) ≈ **12–20s wall time** even when the **decision loop is 5s** (v2.1.3). |
| **Object reserve** | ~250 open offers/account (not binding at L1-only ~2 offers). |
| **Public RPC** | `amendmentBlocked` / node health (`utils/rpc_health.py`) — not a quote quota. |

**Implication:** Faster WS book + shorter cycle improves *intent* freshness; **ledger confirm latency** can still leave resting offers stale until cancel/replace lands. Toxicity from stale quotes (pre-2.1.3) was a software refresh issue, not ledger rate limits. At ~234 XRP / ~7 XRP L1, current tx volume is far below network capacity.

**Promote to implementation when:** heavy churn cycles routinely exceed one loop interval, or `terQUEUED` / failed submits appear in logs. **Tracked as Post-soak P7.**

- [ ] **L1** Instrument ledger tx rate (`OFFER_REFRESH` CSV + `decisions.jsonl` cancel/place counts per hour).
- [ ] **L2** Async submit path (submit without blocking full ledger close on every leg; poll `tx` / sequence) so 5s loop is not extended by 4× `submit_and_wait`.
- [ ] **L3** Optional private rippled / lower-latency RPC if public round-trip becomes the bottleneck at scale.
- [ ] **L4** Re-evaluate after E3 scale — whether cancel-all-then-place beats selective sync when sequence-bound.

*Related:* v2.1.3 `resolve_ws_sync_tolerances` (5s cycle, mid-move + G2 refresh) addresses **software-side** staleness; L1–L4 address **ledger-side** execution if we outrun confirms.*

---

## Promotion ladder (hard gate → pure A-S)

1. Sacred replay economics (Phase A)  
2. HUD observe-only + long runs (running now)  
3. Dry-run offers on WS path (D2)  
4. Shadow: WS pure vs HTTP gated on same wallet (optional)  
5. Wholesale server swap (E1) — **done** 2026-06-15 (live ws-engine; E1.5 gate PASS)

---

## Key files

```
experimental/ws_feed/live_pure_as_tester.py   # live loop
experimental/ws_feed/ws_pure_engine.py      # VPS production loop (ws-engine)
experimental/ws_feed/e1_vps_signoff.py      # E1 sign-off checks
scripts/vps_ws_engine_signoff.py            # E1 CLI (VPS)
scripts/ws_path_session_report.py           # E1.5 fills + markout gate
experimental/ws_feed/engine_adapter_example.py # PureQuotePath
experimental/competitor_pressure.py
experimental/sacred_economics.py
experimental/grokster.py
experimental/ws_runtime_analysis.py
experimental/as_calibration_grok.py
experimental/ws_feed/spread_quality_scaler.py   # G2 brake-only dimmer (v2.1.0)
experimental/ws_feed/pure_quote_path.py
experimental/ws_feed/ws_book_age_modulator.py
experimental/ws_feed/zero_quote_notes.py
experimental/ws_feed/pure_dry_run_executor.py
experimental/swap_readiness_report.py
experimental/PHASE_E_INTELLIGENCE_IMPLEMENTATION_PLAN.md
experimental/ws_feed/peer_lane_replay_validation.py   # G5 peer coverage + neutral-fallback gate
experimental/ws_feed/live_activation_grading.py       # G6 §7 live activation tier + gate
experimental/ws_feed/peer_lane_quoting.py          # G4; I1 regime channel will extend prepare_quoting_intel
experimental/ws_feed/hud_intel_support.py          # grounded analyze briefing + lane HUD fields
experimental/ws_feed/real_time_as_hud.py           # /analyze_competitor
experimental/ws_feed/reservation_metrics.py      # M1 signed BBO delta + inside_l1
experimental/ws_feed/as_safety.py                # M5 reservation gate guard
experimental/ws_feed/replay_long_run.py
# Phase H (planned — not shipped)
experimental/liquidity/amm_provider.py              # H2 pool quotes + H1 monitor
experimental/arb/clob_amm_monitor.py              # H1 read-only CLOB vs AMM log
scripts/vps_deploy_ashigaru.sh              # VPS pull + restart (version + HUD)
experimental/ai_analysis/grok_analyzer.py
strategy/avellaneda_strategy.py
```

---

## Weekly scoreboard (pure path)

Use [`groks input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md`](../groks%20input/docs/05_MASTER_ROADMAP_REALISTIC_METRICS.md) for Gate 2 VPS. For **experimental pure path**, track:

- Marginal capture oracle delta (A/B)
- Neg-fill % on attributed fills
- `would_quote` % on live HUD samples
- Spread vs `as_optimal_spread_pct` (why 0 quotes)
- Realized fills from funded account (when quoting)

**Do not** use presence alone as success.

---

## Maintenance

When a checkbox ships: update this file, FOR_AI milestone, THREAD (`— Cursor`), and progress row in IMPLEMENTATION_PLAN Tier 3.
