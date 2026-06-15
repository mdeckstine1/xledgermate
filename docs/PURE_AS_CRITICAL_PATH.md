# Pure A-S Critical Path

**Status:** Active — **WS + pure Avellaneda-Stoikov** is the production MM quoting model on VPS.  
**Version:** **v2.1.0** (`VERSION` + `experimental/ws_feed/WS_AS_VERSION`) · **Branch:** `Ashigaru` (VPS live MM)  
**Sacred corpus:** `grok-tier-2-collab` (Gate 2 replay + economics) · **E2 merged** 2026-06-15  
**Last updated:** 2026-06-15 (E1 + E2 complete; G2 shipped; E3 blocked by operator)

This is the **single checklist** for WS + pure A-S work. Other docs point here; do not duplicate task lists elsewhere.

---

## Direction

| From (legacy) | To (committed) |
|---------------|----------------|
| HTTP BookOffers poll | WS `BookFeed` / `WsBookFeed` |
| Hard `market_edge_met` + heuristic vetoes | Pure A-S: reservation inside book + optimal spread |
| Low presence on thin books (~11%) | Higher safe presence when math allows (~90%+ on sacred replay) |
| Grok/pressure as ideas | Advisory inputs to A-S (vol, spread anchor, size) — **never** override reservation |

**Safety contract:** `would_quote` = reservation inside live best bid/ask. Pressure, Grok, and AI only tune **inputs**.

**Sacred replay** on `grok-tier-2-collab` is for economics baseline only. **Live VPS MM** runs `Ashigaru` `ws-engine` (Phase E1 complete).

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

*Production MM = **`Ashigaru`** `ws-engine`. Sacred replay = **`grok-tier-2-collab`**. **Runbook:** [`PHASE_E_VPS_RUNBOOK.md`](PHASE_E_VPS_RUNBOOK.md) · **Branches:** [`E2_BRANCH_DISCIPLINE.md`](E2_BRANCH_DISCIPLINE.md)*

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
- [ ] **G3 (E.3)** Intel JSONL + Performance Metrics tab (HUD and/or Streamlit)
- [ ] **G4 (E.4)** Wire peer-lane signals into `PureQuotePath` size_mult / side bias (lab first; production `ws-engine` after E1 live sign-off)
- [ ] **G5 (E.5)** Replay validation — peer coverage %, neutral-fallback rate on sacred + WS samples
- [ ] **G6 (E.6)** Live activation graded by §7 (portfolio XRP-equiv from fills, capture, toxicity)

### Phase F — Grok exploitation & operator UX (after path solid)

*Hold until Phases B–D are running solid (fresh WS book, stable presence, D2 dry-run). Items stay on the critical path but are **not** in scope for current sprint. Advisory only — never overrides reservation.*

- [ ] **F1** Competitor nicknames (local JSON map; HUD display/edit) — *was C1*
- [ ] **F2** Grok exploitation output → optional `AIAdvisorySignal` (rate-limited; not every cycle) — *was C2*
- [ ] **F3** Prompt iteration from real analyses (one-sided bidder + defensive refresh patterns) — *was C3*
- [ ] **F4** Track "Grok suggestion → outcome" in runtime export — *was part of C4*

### Future strategy options (capture only — not in scope)

*WS + pure A-S remains the committed core. These are **enhancements and adjacent layers**, not replacements. Promote an item only after D2 live fills + markout on the WS path. Sacred/VPS data = calibration baselines, not WS PnL targets.*

**Priority order (growth leverage):**

1. **Fill-calibrated A-S (κ, γ from live data)** — Rolling fit of arrival intensity and adverse selection from WS-path fills and markouts; replace static defaults when n≥50 fills per regime.
2. **Markout / toxic feedback loop** — Post-fill markout (30s, 5m) → tune vol, `size_mult`, side skew; complement pressure/age with **own PnL** as ground truth.
3. **11k rebalance execution layer** — Scheduled ask-heavy rebalance (XRP-only → ~55% target); A-S for steady-state after balance (Almgren–Chriss–style scheduling, not continuous MM).
4. **Queue / level heuristics** — L1 vs L2 vs behind large walls; fill probability vs pickoff; refresh when BBO moves (matters more as L1 scales with capital).
5. **GLFT / refined AS family** — Explicit fill-intensity curves λ(δ); same role as A-S when λ is estimable from ledger fills.
6. **Regime-conditioned parameters** — Calm / toxic / skimmable regimes from pressure + vol + markout; formalize current hand-tuned multipliers.
7. **Contextual bandit / light RL on posture** — Discrete {tight, normal, wide, one-sided off} as **inputs to A-S only**; after hundreds of labeled WS fills (Phase F–adjacent).
8. **Competitor cancel/fill correlation** — WS tx stream: cancel-after-fill, reaction to our fills → adverse-selection proxy.

**Explicitly deferred / separate products:**

| Option | Why not now |
|--------|-------------|
| End-to-end deep RL quoting | Data-hungry; hard to debug on mainnet |
| Cross-venue / CEX–DEX arb | Different capital, latency, infra |
| AMM vs DEX arb | Separate stack |
| Pure trend / momentum | Conflicts with MM economics |

**New: Optional AMM Liquidity & Fee Earning (Future Extension)**

- **Status**: Deferred — future hybrid layer only.
- **How it works**: Deposit XRP + counter-asset into XLS-30 pools (with Swappable Curves when live) to earn trading fees pro-rata.
- **Impact on pure A-S**: None on core order-book quoting. Can run in parallel as complementary passive income.
- **Future-proofing**: Keep modular. Add `experimental/liquidity/amm_provider.py` later with config flag. Integrate inventory tracking but never touch reservation price.
- **When to consider**: After bag >30k XRP and stable order-book performance.

**Decision rule before any option ships:**

- [ ] C2 soak pass + D2 dry-run offers on WS path
- [ ] ≥50 WS-path fills with ledger-accurate markout
- [ ] Economics show extra presence does not destroy mean markout
- [ ] Change is **inputs to A-S** or **execution schedule** — never override reservation-inside-L1

**Offense vs defense (tuning note):** WS trades gated “sit out” for “quote if inside book.” Offense wins on **presence**; defense wins on **size/tightness** at high pressure. Future options should sharpen **when to lean in** (low pressure, good markout history), not reintroduce binary hard gates.

**Future review — MM posture vs kill switch (operator thesis, 2026-06-15):**

We are a **market maker**, not a trend-trading bot. Revisit after E1.5 live fills:

- [ ] **R1** Replace binary kill-first behavior with **continuous posture**: stay on book; **brighten** (size / tightness / presence) on good capture + markout runs; **dim** (wider spread, smaller size, one-sided skew) on bad runs — do **not** mirror competitors who cancel entirely on bad tape (exploitable flee).
- [ ] **R2** Good run: A-S reservation + optimal spread stay the core — no momentum chase; aggression = larger size / tighter *inside-book* quotes when own markout + peer pressure allow (competitor intel: others double down here).
- [ ] **R3** Bad run: session/drawdown limits become **graduated brakes** (caps on size, refresh cadence, side bias) before full halt; kill switch only for operator-defined catastrophe (RPC death, wallet integrity), not normal adverse selection.
- [x] **R4** Wire R1–R3 through **G2 spread-quality scaler** + markout loop — G2 shipped v2.1.0; kill decoupled; validate on ongoing live samples

*Until R1 ships: legacy kill switch remains a safety net from the poll era; config tunable but philosophically misaligned with pure MM.*

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
experimental/ws_feed/replay_long_run.py
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
