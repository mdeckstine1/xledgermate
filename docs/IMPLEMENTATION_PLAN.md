# XLedgerMate — Implementation Plan: Good → Great MM

*Updated: 2026-05-29 · v1.4.4 on `tier-2-polish` · mainnet pilot ~250 XRP · **Tier 1 complete · Gate 1 complete (operator sign-off) · Gate 2 current** (`tight_spread` pilot)*

## North star

**Automate greatness:** max skim (spread + edge capture) while protecting balances.

| Pillar | Definition of “great” |
|--------|------------------------|
| **Skim** | Capture spread when edge is real; compete at the book without giving away queue position |
| **Protection** | Inventory, adverse selection, and drawdown bounded before they become operator emergencies |
| **Automation** | Closed feedback loops from fills → quotes → profile; minimal manual intervention |

**Field MM** (what we are building toward) is not more features on `safe` — it is **time on touch + positive realized spread bps + toxic &lt; 20% over 50 fills**, with capital and sizing aligned to the real wallet.

---

## Pilot vs field (honest posture)

The stack **looks** like a market maker (quotes, spread, inventory skew, ledger fills, markout) but **`safe` on ~250 XRP behaves like a survival pilot**, not competitive skim.

| Signal | Toy / pilot (typical) | Field-grade target |
|--------|----------------------|-------------------|
| **Posture** | Off-book, 1 leg, 0 offers for long stretches | **At or near touch** when market is favorable |
| **Profile** | `safe` — wide floors, quick off-book @ ~20% toxic | `tight_spread` after gates; `profit_mode` manual only |
| **Capital model** | `risk_capital_*` in config ≫ wallet (e.g. 11k vs ~246 XRP) | **Risk capital = live portfolio** in GUI |
| **Data** | Fragmented sessions (kills, restarts) | **≥50 fills** per stable config before tuning |
| **Kill** | False drawdown / inflated portfolio on crossed book (fixed v1.4.2–1.4.3) | Kill only on real marks + operator-understood triggers |

**Mainnet pilot reference (2026-06-03/04):** One continuous session **~80 fills**, **+0.41 XRP** logged spread capture, **~6%** negative-capture fills, balanced BUY/SELL — proves plumbing and spread economics; **not** sufficient alone to declare field-ready (toxic ~22%, defense-dominated visibility, false drawdown kill before fix).

---

## Field deployment gates

Operator promotion path while logging continues. Do **not** scale size or switch to `profit_mode` until the gate passes.

### Gate 1 — Validation run ✅ complete (2026-05-29)

*Operator sign-off: **plumbing stable** on mainnet; move to Gate 2. Formal metric bar was a pilot checklist — not all boxes hit cleanly in one uninterrupted session.*

**Setup** (baseline for future restarts)

- [x] Pull `tier-2-polish` through **v1.4.4** (drawdown fix, crossed-book truth, session balance kill, **no spread-kill on bad book feed**).
- [x] Clear kill switch → **Restart engine** (drawdown + session baselines = wallet).
- [x] Set **risk capital** in GUI to **~live portfolio XRP** ( **Sync risk capital to live portfolio** ; not 11k placeholder).
- [x] **`safe`** pilot: L1 **10–15 XRP**, L2/L3 **0**; dynamic min edge optional on tight books.
- [x] `toxic_fill_kill_enabled: false` (refresh pause / off-book only).
- [x] **Session balance kill** available (Advanced → Kill settings): default **0.35 XRP** after **25 fills** (`0` = off). Uses **balance PnL**, not MTM.

**Evidence (cumulative mainnet pilot, v1.4.3+)**

- [x] **Live fills, offers, kills, ledger sync** — mainnet-proven (~80-fill reference session **+0.41 XRP** capture).
- [x] Spread capture **positive** on best sessions (no phantom −12 lines after crossed-book fix).
- [x] **No false drawdown kill** post v1.4.2+; portfolio guards on bad book ticks.
- [~] **≥40 fills in one uninterrupted session** — achieved in aggregate; sessions often fragmented by kills/restarts.
- [~] Toxic ratio **&lt; 25%** — noisy on thin RLUSD + small samples; **advisory**, not proof of broken plumbing.
- [~] **Session balance PnL ≥ 0** — wallet ~flat (~246→250 XRP); multi-run bleed ~−0.45 XRP before fixes.
- [~] **Offers visible &gt; ~70%** — `safe` often defensive/off-book by design on tight books.

**Known shortcomings (carry into Gate 2)**

- Fill **`profit_xrp_equiv`** often ~0 on balance-delta fills; rake scoreboard needs ledger fill price.
- **Toxic @30s** hero metric hidden until 3 session fills; markout timing ≠ fill instant.
- **BookOffers** ghost/inverted ask still possible at RPC — engine defends; root fix Tier 2.5.
- **GUI vs ledger** can lag until sync; stop does not cancel offers.
- Gate 1 **formal toxic bar** misaligned with thin-market casino/rake reality — **balance Δ + capture** remain the scoreboard.

**Tools:** `python scripts/weekly_skim_report.py`, `python scripts/analyze_session.py`, `python scripts/portfolio_bleed_analysis.py`, Dashboard session insights, `logs/decisions.jsonl`.

### Gate 2 — Competitive pilot (`tight_spread`, same capital) **(current)**

*Gate 1 signed off — proceed with competitive pilot on same ~250 XRP capital.*

- [ ] **Apply `tight_spread`** in GUI (~0.06% base, dynamic edge on, larger touch size mult).
- [ ] Never auto-switch to `profit_mode`.
- [ ] Inventory within **±8%** of 55% XRP before expecting two-sided touch.

**Pass when (cumulative)**

- [ ] **≥100 fills** under stable `tight_spread` conditions.
- [ ] Toxic **&lt; 20%** over rolling **50 fills**.
- [ ] Realized spread **bps per fill** reviewed weekly (see metrics checklist).
- [ ] `cancel_per_fill` documented and not rising vs Gate 1.
- [ ] Inventory deviation **&gt;12%** from target rare and self-correcting.

### Gate 3 — Field skim (scale)

*Only after Gate 2 for 2+ weeks.*

- [ ] Increase L1 in steps (**15 → 20 → 25 XRP**), not hero clips.
- [ ] **`profit_mode`** only on calm, tight-book days — **manual** ack; still cap size on ~250 XRP book.
- [ ] Tier 3 engineering (WebSocket book, Avellaneda κ/γ, rolling edge tuner) as capital justifies.
- [ ] Do **not** scale toward narrative **~11k XRP** until Tier 2 verification is green on real metrics.

---

## What we already have (do not regress)

- [x] Layered quote pipeline (preflight → market → profile → inventory → momentum → fill quality → edge → spread check)
- [x] **Dynamic quoting policy** — at-touch / near-touch / spread-mid / off-book (`core/dynamic_quoting_policy.py`)
- [x] Five built-in profiles + auto-switch (never auto `profit_mode`)
- [x] Live spread validation before mainnet placement
- [x] Ledger fills + balance-delta fallback; multi-horizon markout (30s / 5m)
- [x] Portfolio drawdown kill (invalid mid guard v1.4.2) + toxic / spread / RPC / **session balance** kills
- [x] Crossed-book guard — no mid from inverted bid/ask; portfolio + session PnL use **last valid mid** (v1.4.3)
- [x] Selective order refresh + tiered book poll (`order_sync.py`, profile execution)
- [x] Inventory steering + hard pause sides (`risk/inventory_limits.py`)
- [x] Operator GUI — session insights, status marquee, engine restart / clear kill
- [x] Invisible off-touch offer cleanup (`utils/book_visibility.py`)
- [x] Strategy + execution tests (`test_defensive_mm`, `test_drawdown`, `test_ledger_fills`, …)

---

## Gap summary (audit 2026-06-04)

| Area | Core problem | Primary files |
|------|--------------|---------------|
| **Skim / competitive** | `safe` steps off touch early; defense stack often yields **0 intents**; not “compete at touch when favorable” | `core/dynamic_quoting_policy.py`, `strategy/quote_decision.py`, profiles in `core/perception.py` |
| **Capital truth** | `risk_capital_xrp` can dwarf wallet → sizing caps meaningless | `config/settings.py`, `gui/streamlit_gui.py` |
| **Assessment** | Weekly skim exists; Gate 1 signed off — log Gate 2 `tight_spread` sessions | `scripts/weekly_skim_report.py`, `scripts/portfolio_bleed_analysis.py` |
| **Book feed** | Inverted book (bid ~1.16, ask ~0.28) still appears on RPC — engine guards marks; **root BookOffers fix TBD** | `connectors/xrpl_connector.py` |
| **Skim gate** | Quotes still placed when `market_edge_met` false on thin books | `strategy/market_microstructure.py`, `quote_decision.py` |
| **Automation** | No `competitive_pilot` preset; no edge-required quoting | Tier 2.5 below |

*Resolved in v1.4.2:* false daily drawdown kill on stale/crossed book (`risk/drawdown.py`, `engine/trading_engine.py`). *Resolved in v1.4.3:* crossed book no longer marks portfolio at ~0.28 RLUSD/XRP; session PnL and fill capture use last valid mid; session baseline only on trustworthy mid; fill capture uses trustworthy mids. *Resolved in v1.4.2 stack:* toxic fill kill off by default; fill-quality reset when toxic pause + empty book; toxicity hysteresis (≥8 fills, enter 20% / exit 15%).

---

## Tier 1 — Config + quick wins

*Pilot capital ~246 XRP on mainnet.*

### Configuration

- [x] `dynamic_min_edge_enabled` in example + `BotConfig` default
- [x] Example L2 depth skim (`order_sizes: [50, 15, 0]` or pilot `[15, 0, 0]`)
- [x] `auto_rollover_enabled` removed (stub)
- [x] **Risk capital in GUI = wallet portfolio** (`utils/risk_capital_sync.py` + Advanced sync button)
- [ ] Confirm secrets only in local `config.yaml` (never committed)

### Code

- [x] Edge guard widens spread when edge thin
- [x] `profit_xrp_equiv` on fills in trade CSV
- [x] `capture_edge_pct` in favorable regime
- [x] Drawdown + kill switch tests

### Verification (Tier 1) ✅ complete

- [x] Kill/drawdown tests pass
- [x] Spread check pass rate stable on mainnet live (guards block bad books; occasional RPC inversion defended)
- [x] Trade CSV non-zero `profit_xrp_equiv` on fills (reference: **+0.41 XRP / ~80 fills**; balance-delta lines often ~0 — see Gate 1 shortcomings)
- [x] Decision log shows edge guard when book thin
- [x] Secrets only in local `config/config.yaml` (never commit real keys)

---

## Tier 2 — Execution + truth

*Shipped on `tier-2-fix` / `tier-2-polish`; verify on mainnet via **Field gates** above.*

### 1. Selective order maintenance

- [x] Map open offers; cancel/replace above epsilon — `engine/order_sync.py`
- [x] `cancel_per_fill` in runtime_state
- [ ] Production target: cancel/fill **falling** while fill rate **rises** (Gate 2)

### 2. Ledger-accurate fills

- [x] `account_tx` scan + balance-delta fallback — `monitoring/ledger_fills.py`

### 3. Multi-horizon markout

- [x] 30s / 5m markout → `FillQualityTracker` + GUI toxic display

### 4. Inventory circuit breakers

- [x] Hard pause bids/asks by deviation
- [ ] Optional: pause all quoting if deviation &gt; Y% until operator ack

### 5. Smarter refresh cadence

- [x] Tiered poll vs full refresh; selective refresh; toxic refresh pause
- [x] Fill-quality window reset after N empty cycles while paused

### 6. Multi-trigger kill switch

- [x] Spread failures, toxic ratio (configurable), RPC streak
- [x] Daily drawdown — **skip mark when mid invalid** (v1.4.2)
- [x] **Session balance loss kill** — balance PnL &lt; limit after N fills (v1.4.3; GUI Advanced)
- [x] `toxic_fill_kill_enabled: false` default for safe pilot

### 7. Auto-switch guard

- [x] Defensive-only bias + confirm cycles + cooldown

### Verification (Tier 2 — use for Gate 2)

- [ ] Realized spread bps per fill logged and reviewable weekly
- [ ] Toxic fill ratio **&lt; 20%** over rolling **50 fills**
- [ ] Inventory deviation **&gt; 12%** rare and self-correcting
- [ ] Cancel churn documented and falling vs pilot baseline (~1.66 cancel/fill on 80-fill session)

---

## Tier 2.5 — Field competitive (next code + ops)

*Bridge from “MM-shaped bot” to “competitive MM on XRPL” without jumping to Tier 3 or ML.*

Priority order:

| # | Item | Why |
|---|------|-----|
| 1 | **Risk capital = live portfolio** sync (GUI save + engine sizing) | [x] GUI warn + **Sync risk capital to live portfolio** (`utils/risk_capital_sync.py`) |
| 2 | **Toxicity hysteresis + min fills** | [x] ≥8 fills before gates; enter 20% / exit 15% off-book on `safe` |
| 3 | **Weekly skim report** script | [x] `scripts/weekly_skim_report.py` — Gate 1/2 checklist, bps, visibility proxy |
| 3b | **Portfolio bleed analysis** script | [x] `scripts/portfolio_bleed_analysis.py` — balance drift per mainnet run |
| 4 | **`competitive_pilot` profile or preset** | Higher touch relevance; widen/shrink before off-book / refresh-stop |
| 5 | **Join-touch when favorable + edge met** | Use queue preservation at L1 when health high (`join_touch`, `order_sync`) |
| 5b | **Block live quotes when `market_edge_met` false** | Stop paying for fills on books tighter than edge |
| 6 | **Fix BookOffers ask inversion** (~0.28 RLUSD/XRP ghost ask) | Stops spread-check storms and inverted-book cycles at source |
| 7 | **Persist fill-quality / toxic rolling stats** across restarts (optional decay) | Less noisy re-entry after restart |

**Explicitly not required for field Gate 2:** local ML / neural model — use logs + caps first.

**Files (expected):** `core/perception.py`, `core/dynamic_quoting_policy.py`, `config/settings.py`, `gui/streamlit_gui.py`, `scripts/weekly_skim_report.py` (new), `utils/session_insights.py`.

---

## Tier 3 — Later (institutional-grade)

**WS + pure A-S (committed future path — experimental only until after Gate 2)**

All WS + pure A-S work happens in `experimental/ws_feed/` (and safe GUI stubs). The sacred long-run (HTTP poll + hard gate) is never modified.

Current evidence (as of latest replay/grokster on sacred data):
- Pure A-S (reservation inside book, no hard gate): 90.7–93.8% presence vs ~10.7% baseline hard-gate ( +80+ pp lift).
- 93.5% flip rate on the exact historical "Generated 0 quotes / edge thin" cases.
- 0% modeled high-tox risk in the sims.
- Full long-run wiring (assess_inventory + build_quote_adjustments + dynamic policy, toxicity, momentum, inventory strings) is preserved for log/GUI parity.
- Live tester + dedicated real-time HUD (Inventory tab with bot address + QR + demo funding; new Intelligence tab for on-chain competitor scraping + Grok-powered address trending/analysis) provides the observation surface.
- Grok/xAI API integration live (Config tab for keys + real /analyze_competitor endpoint for competitor ledger address analysis; fully advisory, no impact on A-S).

Remaining (stay in experimental/ + docs):
- [ ] Harden WsBookFeed (reconnect, age/trust guards, run_forever) — partial.
- [ ] Production gamma/κ calibration from full current run data.
- [ ] Quote level realism on tight live books.
- [ ] Engine adapter prototype + BookFeed protocol usage sketch (see experimental/ws_feed/engine_adapter_example.py).
- [ ] 30+ min probes + full swap readiness report from replay.
- [ ] Update this plan + OPERATOR_MANUAL with the post-Gate-2 swap procedure.
- [ ] Wholesale remote server replace (only after explicit Gate 2 sign-off + operator opt-in).
- [ ] Grok / xAI API tokens for Intelligence tab competitor address trending & analysis (Config-driven provider/key/model; real calls in /analyze_competitor endpoint; advisory only — never mutates pure A-S reservation math). More details / token rotation / cost controls / prompt iteration to come later. Llama3 stub is deprecated for this path.

Other Tier 3 items (after the above is solid):
- Auto edge / profile tuning from rolling skim bps.
- Optional on-chain rebalance helper.
- CI + external health.

See:
- `experimental/ws_feed/WS_HANDOFF.md` (detailed committed direction + current focus)
- `experimental/ws_feed/replay_long_run.py --as-mode pure`
- `experimental/grokster.py`
- `experimental/ws_feed/live_pure_as_tester.py --serve-hud` (the live observation surface)
- `docs/WS_AS_MANUAL.md` (how to run the WS + pure A-S tester/HUD + Intelligence tab)
- `docs/STRATEGY_MANUAL.md` (plain-English strategy, including the new competitor intel layer)

**11k XRP-Only Funding + WS A-S Scaling to Predator (observations from live deployment planning + ledger queries, June 2026)**

- **Funding & rebalance model**: 11k XRP only (no initial RLUSD) → 100% XRP heavy at start. Bot uses L1/L2/L3 asks (heavily skewed per inventory logic, with "XRP-only mode → competitive asks until RLUSD balance builds") to sell ~4.5–5.5k XRP and build RLUSD toward 55% target ratio. This front-loads positive skim (spread capture on sells) during the rebalance window (estimated 60–120 days depending on fill flow hitting the ladder). Once balanced, two-sided quoting sustains the skim. WS live book + competitor_pressure make the timing and sizing of these competitive asks smarter than polled + gated long-run behavior.

- **No outer hard gate in WS pure path**: Unlike the sacred long-run (high "0 quotes" / low presence from "L1 too tight (e.g. 0.047% < need 0.070%)", "market_edge_met=false — hard gate; no live quotes", "book too tight → defensive only", toxicity no-touch, edge guard size reduction, momentum pauses), the WS A-S relies on pure A-S built-in math only (reservation price inside live WS best bid/ask via gamma for inventory risk; optimal spread via kappa + vol for adverse selection). WS feed provides fresher mid/L1/depth/age/message_count (vs HTTP polls). Expected presence lift: 90%+ quoting time vs ~11% baseline on the same thin-book corpus (validated in grokster replays; 93%+ flip rate on historical "Generated 0 quotes / edge thin" cases, 0% modeled high-tox among extra quotes). "Too tight" / edge checks remain useful operator signals but are not blockers in the pure path.

- **Scaling, inventory, skim & compounding**: More inventory (post-rebalance + realized skim) directly enables larger absolute order_sizes / leg depth under the 0.12 max_leg cap (L1 dominant for skim capture on best prices; L2/L3 for book presence, queue position, and depth). As capital grows (e.g. 11k → 30–60k+ XRP equivalent by year-end via rebalance turnover + skim), pull scales proportionally (L1 to low thousands XRP possible while staying reasonable vs live depth). This yields higher *absolute* skim (more XRP/RLUSD volume turned over per hit rate) and compounding (larger sizes → more hits/fills → more skim → even larger capital base for next cycle's pull). Does *not* automatically produce wider spreads (A-S optimal spread is driven by observed book spread + volatility + kappa; more inventory mainly affects reservation shade and volume, not width). On tight books (common in long-run data), pure A-S + live WS still only quotes when math supports — but far more often than the gated regime.

- **Live ledger reality (book_offers queries on mainnet)**: Individual offers up to 36k+ XRP exist on both sides; sampled total depth ~208k XRP asks / ~282k XRP bids. Inside market remains tight (0.04–0.13% L1 spreads consistent with long-run observations). This is *supportive* of scaling: the bot can grow L1/L2/L3 depth significantly (hundreds → thousands XRP) without being the sole liquidity or moving the book excessively. Large existing offers (deeper) provide "cover"/absorption for rebalance sells. Top-of-book is still competitive (small-to-medium offers often set the tight inside), so WS freshness + competitor_pressure ("use observed spread as real for A-S calibration" when pressure low) are critical for detecting real edges vs. noise and for "skim harder" decisions.

- **P&L / presence targets & predator implications** (extrapolated from long-run +3.957 XRP net skim / 429 fills on small cap + WS uplift + no-gate higher presence + user's live observation of ~500 XRP equivalent / 24h potential in favorable conditions):
  - Conservative blended daily (rebalance high + steady growing with compounding, tempered for tight markets / flow limits): 150–300 XRP skim (vs long-run scaled baseline ~70–80 XRP/day).
  - Rebalance (first 60–120 days): +8k–15k XRP P&L (front-loaded from ask turnover on L1/L2/L3 while heavy).
  - Steady + compounding: additional +15–30k+ XRP (larger L1/L2/L3 as capital grows → more absolute volume).
  - Year-end total net P&L (skim): +25k to +45k XRP equivalent (conservative; higher end if 400+ daily sustained in good periods).
  - Year-end bot value: 36k–56k XRP equivalent (11k start + P&L; now includes RLUSD component at target ratio after rebalance).
  - Predator ("skim harder / beat competitors"): Low competitor pressure (defensive observed spreads / weak makers) → use as signal to be more aggressive (tighter effective reservation via observed spread, larger L1 size, more presence on those books). High pressure → A-S math naturally more defensive. Live WS + pressure lets the bot react to real competitor behavior (not just internal math) for timing and sizing. Large existing orders on ledger are opportunities (cover for our ladder) rather than pure threats.

- **Current code position & gaps for achieving the target**:
  - Architecture good: experimental/ws_feed/ (ws_book_feed, real_time_as_hud, engine_adapter_example, live_pure_as_tester) + grokster validation + avellaneda_strategy (pure A-S) + competitor_intel in market_analysis/ + Intelligence tab in HUD. Explicit commitment: "WS + pure A-S (built-in protections ONLY) ... No hard gate. No legacy heuristic guards." Higher presence validated. XRP-only rebalance handling exists ("competitive asks").
  - Gaps (main engine still carries legacy; need to close for full pure/predator scaling): market_edge_met, "thin book → near-touch backoff", "edge guard size reduction", "market edge thin → widen", "hostile + weak edge → pause", "defensive only" still active in dynamic_quoting_policy.py, quote_decision.py, market_microstructure.py, trading_engine, etc. (even if experimental path aims to bypass). Competitor_pressure mostly advisory/display (HUD/ticker/skim_advice) — not yet first-class input to A-S (gamma/kappa, min_edge, size_multiplier, reservation). No automatic dynamic order_size ramp tied to current capital + pressure. WS age used for monitoring but not yet aggression modulator.
  - To hit P&L / be the predator (skim harder, higher presence, beat competitors): ensure the WS pure path *actually* bypasses legacy outer gates for this deployment (force market_edge_met=True + skip size/edge reductions when as_mode=="pure"). Wire competitor_pressure deeply (low pressure → lower effective gamma / use observed spread / boost L1 size / more presence exactly where competitors are weak). Add dynamic sizing (L1 = min(configured, 0.06–0.08 * current XRP bal); boost asks during XRP-heavy rebalance). Use live WS (fresh age + depth) + pressure to decide "predator mode" (quote more / size up). Leverage AI/Grok (already in Config + /analyze_competitor) for competitor address trending to inform "go harder on this maker/level" (advisory). These turn the bot from "safe high-presence MM" into the aggressive skimmer that capitalizes on defensive books/competitors while the A-S math protects.

This section captures the June 2026 observations (11k XRP-only funding, no outer hard gate, scaling/compounding math, live ledger depth vs bot sizes, P&L extrapolations, predator wiring needs) for implementation. All WS pure A-S work remains in experimental/ (sacred long-run untouched). Update cross-refs in WS_AS_MANUAL.md / STRATEGY_MANUAL.md as the pure path hardens.

**Immediate next actions for this 11k XRP WS A-S instance (post this plan update)**:
- Config tweaks (aggressive L1/L2/L3 sizes, dynamic_min_edge low/false for pure path, XRP-heavy rebalance boost).
- Patch in experimental/ws_feed/ (engine_adapter / live tester / real_time_as_hud) to enforce pure A-S decision (bypass legacy market_edge / edge guard reductions).
- Extend AvellanedaStrategy / policy to accept + use competitor_pressure as aggression input (e.g. adjust reservation or size_mult).
- Add simple dynamic size helper tied to current XRP bal + pressure.
- Run live tester/HUD against the funded instance; measure presence / fills vs long-run baseline.
- Monitor ws_book_age + large existing orders (36k+ XRP); use pressure to decide when to be the predator.

**11k XRP-Only Funding + WS A-S Scaling to Predator (observations from live deployment planning + ledger queries, June 2026)**

- **Funding & rebalance model**: 11k XRP only (no initial RLUSD) → 100% XRP heavy at start. Bot uses L1/L2/L3 asks (heavily skewed per inventory logic, with "XRP-only mode → competitive asks until RLUSD balance builds") to sell ~4.5–5.5k XRP and build RLUSD toward 55% target ratio. This front-loads positive skim (spread capture on sells) during the rebalance window (estimated 60–120 days depending on fill flow hitting the ladder). Once balanced, two-sided quoting sustains the skim. WS live book + competitor_pressure make the timing and sizing of these competitive asks smarter than polled + gated long-run behavior.

- **No outer hard gate in WS pure path**: Unlike the sacred long-run (high "0 quotes" / low presence from "L1 too tight (e.g. 0.047% < need 0.070%)", "market_edge_met=false — hard gate; no live quotes", "book too tight → defensive only", toxicity no-touch, edge guard size reduction, momentum pauses), the WS A-S relies on pure A-S built-in math only (reservation price inside live WS best bid/ask via gamma for inventory risk; optimal spread via kappa + vol for adverse selection). WS feed provides fresher mid/L1/depth/age/message_count (vs HTTP polls). Expected presence lift: 90%+ quoting time vs ~11% baseline on the same thin-book corpus (validated in grokster replays; 93%+ flip rate on historical "Generated 0 quotes / edge thin" cases, 0% modeled high-tox among extra quotes). "Too tight" / edge checks remain useful operator signals but are not blockers in the pure path.

- **Scaling, inventory, skim & compounding**: More inventory (post-rebalance + realized skim) directly enables larger absolute order_sizes / leg depth under the 0.12 max_leg cap (L1 dominant for skim capture on best prices; L2/L3 for book presence, queue position, and depth). As capital grows (e.g. 11k → 30–60k+ XRP equivalent by year-end via rebalance turnover + skim), pull scales proportionally (L1 to low thousands XRP possible while staying reasonable vs live depth). This yields higher *absolute* skim (more XRP/RLUSD volume turned over per hit rate) and compounding (larger sizes → more hits/fills → more skim → even larger capital base for next cycle's pull). Does *not* automatically produce wider spreads (A-S optimal spread is driven by observed book spread + volatility + kappa; more inventory mainly affects reservation shade and volume, not width). On tight books (common in long-run data), pure A-S + live WS still only quotes when math supports — but far more often than the gated regime.

- **Live ledger reality (book_offers queries on mainnet)**: Individual offers up to 36k+ XRP exist on both sides; sampled total depth ~208k XRP asks / ~282k XRP bids. Inside market remains tight (0.04–0.13% L1 spreads consistent with long-run observations). This is *supportive* of scaling: the bot can grow L1/L2/L3 depth significantly (hundreds → thousands XRP) without being the sole liquidity or moving the book excessively. Large existing offers (deeper) provide "cover"/absorption for rebalance sells. Top-of-book is still competitive (small-to-medium offers often set the tight inside), so WS freshness + competitor_pressure ("use observed spread as real for A-S calibration" when pressure low) are critical for detecting real edges vs. noise and for "skim harder" decisions.

- **P&L / presence targets & predator implications** (extrapolated from long-run +3.957 XRP net skim / 429 fills on small cap + WS uplift + no-gate higher presence + user's live observation of ~500 XRP equivalent / 24h potential in favorable conditions):
  - Conservative blended daily (rebalance high + steady growing with compounding, tempered for tight markets / flow limits): 150–300 XRP skim (vs long-run scaled baseline ~70–80 XRP/day).
  - Rebalance (first 60–120 days): +8k–15k XRP P&L (front-loaded from ask turnover on L1/L2/L3 while heavy).
  - Steady + compounding: additional +15–30k+ XRP (larger L1/L2/L3 as capital grows → more absolute volume).
  - Year-end total net P&L (skim): +25k to +45k XRP equivalent (conservative; higher end if 400+ daily sustained in good periods).
  - Year-end bot value: 36k–56k XRP equivalent (11k start + P&L; now includes RLUSD component at target ratio after rebalance).
  - Predator ("skim harder / beat competitors"): Low competitor pressure (defensive observed spreads / weak makers) → use as signal to be more aggressive (tighter effective reservation via observed spread, larger L1 size, more presence on those books). High pressure → A-S math naturally more defensive. Live WS + pressure lets the bot react to real competitor behavior (not just internal math) for timing and sizing. Large existing orders on ledger are opportunities (cover for our ladder) rather than pure threats.

- **Current code position & gaps for achieving the target**:
  - Architecture good: experimental/ws_feed/ (ws_book_feed, real_time_as_hud, engine_adapter_example, live_pure_as_tester) + grokster validation + avellaneda_strategy (pure A-S) + competitor_intel in market_analysis/ + Intelligence tab in HUD. Explicit commitment: "WS + pure A-S (built-in protections ONLY) ... No hard gate. No legacy heuristic guards." Higher presence validated. XRP-only rebalance handling exists ("competitive asks").
  - Gaps (main engine still carries legacy; need to close for full pure/predator scaling): market_edge_met, "thin book → near-touch / edge guard size reduction", "market edge thin → widen", "hostile + weak edge → pause", "defensive only" still active in dynamic_quoting_policy.py, quote_decision.py, market_microstructure.py, trading_engine, etc. (even if experimental path aims to bypass). Competitor_pressure mostly advisory/display (HUD/ticker/skim_advice) — not yet first-class input to A-S (gamma/kappa, min_edge, size_multiplier, reservation). No automatic dynamic order_size ramp tied to current capital + pressure. WS age used for monitoring but not yet aggression modulator.
  - To hit P&L / be the predator (skim harder, higher presence, beat competitors): ensure the WS pure path *actually* bypasses legacy outer gates for this deployment (force market_edge_met=True + skip size/edge reductions when as_mode=="pure"). Wire competitor_pressure deeply (low pressure → lower effective gamma / use observed spread / boost L1 size / more presence exactly where competitors are weak). Add dynamic sizing (L1 = min(configured, 0.06–0.08 * current XRP bal); boost asks during XRP-heavy rebalance). Use live WS (fresh age + depth) + pressure to decide "predator mode" (quote more / size up). Leverage AI/Grok (already in Config + /analyze_competitor) for competitor address trending to inform "go harder on this maker/level" (advisory). These turn the bot from "safe high-presence MM" into the aggressive skimmer that capitalizes on defensive books/competitors while the A-S math protects.

This section captures the June 2026 observations (11k XRP-only funding, no outer hard gate, scaling/compounding math, live ledger depth vs bot sizes, P&L extrapolations, predator wiring needs) for implementation. All WS pure A-S work remains in experimental/ (sacred long-run untouched). Update cross-refs in WS_AS_MANUAL.md / STRATEGY_MANUAL.md as the pure path hardens.

**Immediate next actions for this 11k XRP WS A-S instance (post this plan update)**:
- Config tweaks (aggressive L1/L2/L3 sizes, dynamic_min_edge low/false for pure path, XRP-heavy rebalance boost).
- Patch in experimental/ws_feed/ (engine_adapter / live tester / real_time_as_hud) to enforce pure A-S decision (bypass legacy market_edge / edge guard reductions).
- Extend AvellanedaStrategy / policy to accept + use competitor_pressure as aggression input (e.g. adjust reservation or size_mult).
- Add simple dynamic size helper tied to current XRP bal + pressure.
- Run live tester/HUD against the funded instance; measure presence / fills vs long-run baseline.
- Monitor ws_book_age + large existing orders (36k+ XRP); use pressure to decide when to be the predator.

This work is now in the plan for implementation. Commit/push the update, then we can discuss the exact next code/config steps or measurements.

## How the Implementation Plan Looks Now (Post-Recent Work)

The plan is in solid shape and now properly reflects the evolution we are executing:

- Clear, repeated emphasis on the sacred long-run (hard-gate + HTTP poll on VPS) as the **untouchable data generator** only. All WS + pure A-S + Intelligence work stays in `experimental/ws_feed/` (plus safe GUI stubs).
- Tier 3 section for "WS + pure A-S (committed future path)" is updated and current:
  - Evidence from replays/grokster on real sacred data: 90.7–93.8% presence (vs ~10.7% baseline), 93.5% flip rate on historical "Generated 0 quotes / edge thin" cases, 0% modeled high-tox.
  - Full long-run wiring parity preserved for log/GUI/operator trust.
  - Live tester + dedicated real-time HUD (Inventory tab with bot address + QR + demo funding; new **Intelligence tab** for on-chain competitor scraping + Grok-powered address trending/analysis).
  - Grok/xAI API integration live (Config tab for keys + real `/analyze_competitor` endpoint for competitor ledger address analysis; fully advisory, no impact on A-S).
- Progress log has an up-to-date "(current)" row capturing the commit-push state: Grok/xAI + Intelligence tab + pure A-S HUD now functional in experimental (on-chain scraper + real Grok endpoint; llama3 stub deprecated for intel path).
- Metrics checklist and operating rules remain strong (heavy on realized spread bps, toxic <20% over 50 fills, session balance PnL as the real scoreboard, visibility, and "keep logging through Gate 2").
- Good cross-references to the new `WS_AS_MANUAL.md`, updated `STRATEGY_MANUAL.md`, `WS_HANDOFF.md`, replay/grokster/tester, etc.

**Strengths of the current plan**:
- It has moved beyond generic "Tier 3 later" language and now owns the competitive intelligence angle (on-chain scraping + Grok for "trending on ledger address") that directly supports "scrape harder / skim harder / beat competitors."
- Strong protection of the pure A-S core (reservation inside the WS book is still the only quoting decision) + replicated wiring.
- Explicit advisory-only contract for AI/Grok.
- Measurement and operating rules are operator-aligned and safety-first.

**Gaps for becoming the best, most profitable, competitive market making bot**:
The current Tier 3 focus (WS + pure A-S + basic competitor scraping + advisory Grok) gets us from "safe but low presence" to "high safe presence with a data/intel edge." To truly dominate (highest realized spread bps net of fees/toxic, best capital efficiency, consistent outperformance vs other MMs on the same book, and operator leverage that lets a human be the best MM), we need to turn the Intelligence layer into a true moat and close the loop on measurement/automation — without ever adding hard gates on top of A-S.

**Core philosophy for dominance**:
- **Data moat first**: See what competitors are actually doing (on-chain + their "trending" behavior) better and faster than they see us.
- **Intelligence layer (advisory)**: Use Grok + (later) distilled models + external signals only to inform A-S inputs (vol, pressure, "is this edge real?") and operator decisions. Never hard rules or overrides on the reservation math.
- **Measurement obsession**: Every change measured by realized spread bps, toxic ratio, balance PnL, and "our capture vs what a naive competitor would have got."
- **Reliability + cost control**: The intel layer (especially Grok tokens) must be production-grade (rate limits, fallbacks, budgets) or it becomes a liability.

## To Become the Best, Most Profitable, Competitive Market Making Bot

**Suggested elements to add (proposed for Tier 3 / new "Competitive Dominance" pillar — stay experimental until post-Gate 2 + operator sign-off):**

1. **Advanced Competitor Counter-Intelligence**  
   Full historical profiling of top makers (spreads over time, size ladders, cancel-after-fill patterns, reaction to our fills/price moves). "Competitor heat map" in Intelligence tab (who is providing the real liquidity right now, who is fading). Predictive signals: "This maker usually widens 15-30s before adverse tape" → feed as extra adverse-selection input to A-S or dynamic policy. Grok prompts specifically for "how would this competitor's observed behavior change our optimal reservation/spread right now?"

2. **External + Cross-Venue Signal Fusion (beyond Anodos)**  
   CEX XRP/RLUSD (or BTC) vol, order book imbalance, large trade flow as leading indicators for XRPL moves. Other XRPL DEXes / AMM state (liquidity migration signals). On-chain flow: large holder transfers, AMM arbitrage activity as toxicity or opportunity signals. Fuse into A-S vol input and the "is edge real?" assessment (Grok can help synthesize noisy external data).

3. **Realized Spread & Profitability Optimization Loop**  
   Not just "presence" metric — track per-fill realized bps (vs mid at quote time) net of fees, vs what competitors posted. Weekly "what would a dumb competitor have captured on the same fills?" comparison. Use Grok (offline on batches) to analyze "our fills + competitor behavior" and suggest gamma/κ tweaks or quote size rules (still advisory; validated in replay before any change). Goal: push average realized spread bps higher while keeping toxic <15-20%.

4. **Predictive / Proactive Risk (beyond current drawdown & session balance)**  
   Early warning for "this setup + competitor pressure + momentum looks like the prelude to a toxic wave." Grok-generated rebalance recommendations with "why now" rationale (competitor pressure + our skew + expected edge). Hard safety rails (never auto-move more than X% without operator ack). Better mark-to-market and kill logic that incorporates "what competitors are doing right now."

5. **Grok / Intelligence Layer Productionization**  
   Token budget + rotation + cost tracking (per day/week, with alerts). Fallbacks: local distilled model (trained on Grok labels) when API is down/slow/expensive. Prompt library + versioning (system prompts for "competitor strategy", "skim opportunity", "toxicity risk", "daily brief"). Batch offline labeling of new run data (Grok labels 100-200 cycles overnight → use to improve stub or train tiny model). "Daily Competitor Brief" generated by Grok from last 24h scrape + our fills (pushed to Telegram or HUD).

6. **Superior Observability & Operator Leverage (make the human the best MM)**  
   In Intelligence tab: what-if simulator ("if we had quoted 2bp tighter with current competitor pressure, what would our expected capture have been?"). "Beat the book" leaderboard: our fills vs the best competitor posted price at the time. One-click "load this cycle into Grok for deep analysis" from the decision log. Competitor "known accounts" mapping (seed with public data, let Grok help label new high-activity addresses). Full audit trail of every AI suggestion + whether operator followed it + outcome.

7. **Backtesting & Simulation Rigor with Real Competitor Injection**  
   Replay harness must be able to inject historical competitor profiles + their actual posted ladders (not just simulated WS freshness). Monte-Carlo or historical "what if we had run with this Grok-derived vol adjustment" on the full corpus. Measure not just presence, but net P&L after realistic adverse selection (using actual competitor behavior as the "taker" model).

8. **Capital Efficiency & Semi-Automated Rebalancing (advisory first)**  
   Grok-generated rebalance recommendations with "why now" rationale based on competitor pressure + our skew + expected edge. Hard safety rails around any auto-rebalance (never move more than X% without operator ack). Target: minimize manual swaps while still hitting ~55% XRP target faster than pure A-S skew alone.

9. **Reliability, Cost & Multi-Instance Considerations for the Intel Layer**  
   Grok token budgets with graceful degradation to local model. Rate-limit aware calls, retry with backoff, circuit breaker. Ability to run "shadow" Grok analysis (log what it would have suggested without using it) for measurement. Later: multi-bot coordination if we scale capital (different instances see slightly different competitors?).

10. **Measurement Upgrades for Dominance**  
    New metrics: "Competitor beat rate" (% of our aggressive quotes that were better than the best competitor at the time), "adverse selection vs observed competitor flow", "Grok suggestion acceptance rate + outcome delta". Weekly "vs other MMs" report (inferred from on-chain data — how much spread did we capture vs what was available from competitor offers). Explicit "presence when competitors are defensive" vs "presence when they are aggressive" buckets.

These turn the Intelligence layer from "nice to have visibility" into a true data moat that lets pure A-S quote more profitably and safely than any peer on the same book. The sacred long-run data + our replays + live tester give us the perfect closed-loop measurement environment to validate each addition before it ever touches production.

**Prioritization suggestion (for the plan):**  
Short-term (next 1-2 phases after basic swap readiness): 1 (counter-intel), 5 (Grok productionization), 6 (observability), 3 (realized spread loop).  
Medium-term: 2 (external fusion), 4 (predictive risk), 7 (backtesting rigor), 8 (measurement + capital).  

Keep everything experimental + advisory until operator sign-off. Pure A-S math (reservation inside the WS book) + replicated wiring remains the core. The intel layer is the moat that lets A-S quote more profitably and safely than peers.

Add the above as a new "Competitive Dominance" subsection in Tier 3 (right after the current WS + pure A-S bullets and remaining list). Prioritize 1-5 for the next phase. Update the metrics checklist and operating rules as appropriate to reflect the new elements. See also the new `docs/WS_AS_MANUAL.md` for how the current Intelligence + Grok surface already implements the first steps of this vision.

## Related docs (already referenced)

- [`STRATEGY_MANUAL.md`](STRATEGY_MANUAL.md) — strategy, profiles, defense (plain language)
- [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md) — GUI, kill switch, go-live
- [`AUDIT_REPORT.md`](AUDIT_REPORT.md) — policy / posture conflicts (v1.4.1)
- [`CHANGELOG.md`](../CHANGELOG.md) — release history

## Quick reference — key code paths (already present)

```
Cycle:     engine/trading_engine.py::_run_cycle
Policy:    core/dynamic_quoting_policy.py::resolve_dynamic_quoting_policy
Quotes:    strategy/quote_decision.py::build_quote_adjustments
Edge:      strategy/market_microstructure.py::resolve_effective_min_edge_pct
Fills:     monitoring/ledger_fills.py + monitoring/fill_detection.py
Orders:    engine/trading_engine.py::_refresh_orders + engine/order_sync.py
Drawdown:  risk/drawdown.py (invalid mid → skip mark + no kill)
Book mid:  connectors/xrpl_connector.py (is_trustworthy_rlusd_mid, is_book_crossed)
Insights:  utils/session_insights.py + scripts/analyze_session.py
Reports:   scripts/weekly_skim_report.py, scripts/portfolio_bleed_analysis.py
Config:    config/settings.py, config/config.yaml (local, gitignored)
Kill GUI:  gui/streamlit_gui.py (Advanced → Kill settings)
```

## To Become the Best, Most Profitable, Competitive Market Making Bot

The current Tier 3 focus (WS + pure A-S + basic competitor scraping + advisory Grok) gets us from "safe but low presence" to "high safe presence with data advantage." To truly dominate (highest realized spread bps net of fees/toxic, best capital efficiency, consistent outperformance vs other MMs on the book), we need to push the data + intelligence edge much further while keeping the deterministic pure A-S core + replicated wiring for safety and operator trust.

**Core philosophy for dominance:**
- **Data moat first**: See what competitors are actually doing (on-chain + their "trending" behavior) better and faster than they see us.
- **Intelligence layer (advisory)**: Use Grok + (later) distilled models + external signals only to inform A-S inputs (vol, pressure, "is this edge real?") and operator decisions. Never hard rules or overrides on the reservation math.
- **Measurement obsession**: Every change measured by realized spread bps, toxic ratio, balance PnL, and "our capture vs what a naive competitor would have got."
- **Reliability + cost control**: The intel layer (especially Grok tokens) must be production-grade (rate limits, fallbacks, budgets) or it becomes a liability.

**Suggested elements to add (proposed for Tier 3 / new "Competitive Dominance" pillar — stay experimental until post-Gate 2):**

1. **Advanced Competitor Counter-Intelligence**
   - Full historical profiling of top makers (spreads over time, size ladders, cancel-after-fill patterns, reaction to our fills/price moves).
   - "Competitor heat map" in Intelligence tab (who is providing the real liquidity right now, who is fading).
   - Predictive signals: "This maker usually widens 15-30s before adverse tape" → feed as extra adverse-selection input to A-S or dynamic policy.
   - Grok prompts specifically for "how would this competitor's observed behavior change our optimal reservation/spread right now?"

2. **External + Cross-Venue Signal Fusion (beyond Anodos)**
   - CEX XRP/RLUSD (or BTC) vol, order book imbalance, funding rates, large trade flow as leading indicators for XRPL moves.
   - Other XRPL DEXes / AMM state (liquidity migration signals).
   - On-chain flow: large holder transfers, AMM arbitrage activity as toxicity or opportunity signals.
   - Fuse into A-S vol input and the "is edge real?" assessment (Grok can help synthesize noisy external data).

3. **Realized Spread & Profitability Optimization Loop**
   - Not just "presence" metric — track per-fill realized bps (vs mid at quote time) net of fees, vs what competitors posted.
   - Weekly "what would a dumb competitor have captured on the same fills?" comparison.
   - Use Grok to analyze batches of our fills + competitor behavior to suggest gamma/kappa tweaks or quote size rules (still advisory; operator or replay validates before any change).
   - Goal: push average realized spread bps higher while keeping toxic <15-20%.

4. **Predictive / Proactive Risk (beyond current drawdown & session balance)**
   - Early warning for "this book looks like the setup for a toxic wave" using competitor + momentum + external signals.
   - Inventory "pre-skew" suggestions when Grok sees building pressure on one side.
   - Auto-suggested (but operator-approved) profile switches or size caps based on 30-60m competitor heat.
   - Better mark-to-market and kill logic that incorporates "what competitors are doing right now."

5. **Grok / Intelligence Layer Productionization**
   - Token budget + rotation + cost tracking (per day/week, with alerts).
   - Fallbacks: local distilled model (trained on Grok labels) when API is down/slow/expensive.
   - Prompt library + versioning (system prompts for "competitor strategy", "skim opportunity", "toxicity risk", "daily brief").
   - Batch offline labeling of new run data (Grok labels 100-200 cycles overnight → use to improve stub or train tiny model).
   - "Daily Competitor Brief" generated by Grok from last 24h scrape + our fills (pushed to Telegram or HUD).

6. **Superior Observability & Operator Leverage (make the human the best MM)**
   - In Intelligence tab: what-if simulator ("if we had quoted 2bp tighter with current competitor pressure, what would our expected capture have been?").
   - "Beat the book" leaderboard: our fills vs the best competitor posted price at the time.
   - One-click "load this cycle into Grok for deep analysis" from the decision log.
   - Competitor "known accounts" mapping (seed with public data, let Grok help label new high-activity addresses).
   - Full audit trail of every AI suggestion + whether operator followed it + outcome.

7. **Backtesting & Simulation Rigor with Real Competitor Injection**
   - Replay harness must be able to inject historical competitor profiles + their actual posted ladders (not just simulated WS freshness).
   - Monte-Carlo or historical "what if we had run with this Grok-derived vol adjustment" on the full corpus.
   - Measure not just presence, but net P&L after realistic adverse selection (using actual competitor behavior as the "taker" model).

8. **Capital Efficiency & Semi-Automated Rebalancing (advisory first)**
   - Grok-generated rebalance recommendations with "why now" rationale based on competitor pressure + our skew + expected edge.
   - Hard safety rails around any auto-rebalance (never move more than X% without operator ack).
   - Target: minimize manual swaps while still hitting ~55% XRP target faster than pure A-S skew alone.

9. **Reliability, Cost & Multi-Instance Considerations for the Intel Layer**
   - Grok token budgets with graceful degradation to local model.
   - Rate-limit aware calls, retry with backoff, circuit breaker.
   - Ability to run "shadow" Grok analysis (log what it would have suggested without using it) for measurement.
   - Later: multi-bot coordination if we scale capital (different instances see slightly different competitors?).

10. **Measurement Upgrades for Dominance**
    - New metrics: "Competitor beat rate" (% of our aggressive quotes that were better than the best competitor at the time), "adverse selection vs observed competitor flow", "Grok suggestion acceptance rate + outcome delta".
    - Weekly "vs other MMs" report (inferred from on-chain data — how much spread did we capture vs what was available from competitor offers).
    - Explicit "presence when competitors are defensive" vs "presence when they are aggressive" buckets.

These turn the Intelligence layer from "nice to have visibility" into a true data moat that lets pure A-S quote more profitably and safely than any peer on the same book. The sacred long-run data + our replays + live tester give us the perfect closed-loop measurement environment to validate each addition before it ever touches production.

Add these under a new "Competitive Dominance" subsection in Tier 3 (after the current WS + pure A-S bullets). Prioritize 1-5 for the next phase after basic swap readiness. Keep everything experimental + advisory until operator sign-off.

See also the new `docs/WS_AS_MANUAL.md` for how the current Intelligence + Grok surface already implements the first steps of this vision.

---

## Metrics checklist (track weekly)

Use with Gate 1/2 pass criteria. Copy to spreadsheet or `logs/review_YYYY-MM-DD.md`.

### Skim

- [ ] Realized spread per fill (**bps vs mid at quote time**)
- [ ] Spread captured when `market_edge_met` true vs false at fill
- [ ] XRP fee drag vs spread earned (session)
- [ ] Fills per hour; fills per cycle with active levels
- [ ] **Policy mix** — % cycles at-touch / near-touch / off-book (decisions log or ticker)

### Protection

- [ ] Toxic fill ratio — target **&lt; 20%** over **50 fills** (not 9)
- [ ] Markout @ 30s mean by side
- [ ] Hours outside ±6% of inventory target (55% XRP)
- [ ] Max intraday inventory deviation (%)
- [ ] Drawdown % vs limit; kill activations (note false kills pre-v1.4.3)
- [ ] **Session balance PnL** vs limit (Gate 1 scoreboard; not MTM alone)
- [ ] Portfolio readout stable (spot-check: no 400+ XRP on ~247 wallet)

### Execution & automation

- [ ] Spread validation pass rate
- [ ] Cycles with **0 quote intents** vs placed offers
- [ ] `cancel_per_fill` (lower is better)
- [ ] **Minutes with ≥1 open offer** (visibility proxy)
- [ ] Auto vs manual profile switches
- [ ] Cycle time p50/p95 vs profile poll/refresh intervals

### Data sufficiency (assessment)

| Question | Minimum data |
|----------|----------------|
| Go / no-go pilot (continue on `safe`?) | **≥40 fills**, positive capture, **balance PnL ≥ 0**, one post-v1.4.3 session |
| Parameter / profile tuning | **≥50 fills**, one stable config, toxic &lt; 25% |
| Declare field-ready competitive MM | Gate 2 + **≥100 fills** `tight_spread`, toxic &lt; 20% / 50 fills, 2+ weeks |
| ML / auto-learning | **Not yet** — need clean continuous logs first |

---

## Operating rules

1. **`profit_mode`** — manual only; use **`tight_spread`** when book is ideal (Gate 2).
2. **Inventory &gt; ~15% off target** — manual swap consideration + `safe`; don’t tighten to chase spread.
3. **Spread check FAIL** — fix profile or stay dry-run; never override on mainnet.
4. **Session red + high toxic** — step down profile or pause; don’t widen into pickoff.
5. **Scale capital or L1 size** only after **Gate 2** metrics stable **2+ weeks**.
6. **After kill clear** — restart engine so drawdown + **session** baselines reset; read kill reason in `logs/kill_switch.json`.
7. **Scoreboard = balance PnL**; use MTM only when book is sane (bid/ask not inverted).
8. **Keep logging** through Gate 2 even if economics look good — visibility and policy mix matter as much as capture XRP.
9. **Growing holdings** — target **weekly balance PnL ≥ 0** under Gate 2 `tight_spread`; scale L1 only after Gate 2 metrics stable **2+ weeks**.

---

## Progress log

| Date | Milestone | Notes |
|------|-----------|-------|
| 2026-05-30 | Plan created | Audit → this document |
| 2026-05-30 | v1.3.9 / v1.4.0 | Tier 1 + Tier 2 execution on `good-to-great` / `tier-2-fix` |
| 2026-06-03 | v1.4.1 | Unified dynamic quoting policy; audit cleanup |
| 2026-06-04 | v1.4.2 | False drawdown kill fix; GUI stack, session insights, toxic kill default off |
| 2026-06-04 | Mainnet pilot | ~80-fill session +0.41 XRP capture; false 40% drawdown kill diagnosed |
| 2026-06-04 | **Field gates** | Merged pilot assessment + deployment path into this plan |
| 2026-06-04 | **Gate 1 ~pass** | ~76 fills, +0.29 XRP capture, toxic 25% — sync risk capital; Gate 2 when stable |
| 2026-06-04 | **v1.4.3** | Crossed-book portfolio truth; session balance kill; fill capture + baseline fixes |
| 2026-06-05 | **v1.4.4** | Spread-fail kill exempts bad book feed (Gate 1 can survive inverted-mid nights) |
| 2026-06-05 | **Gate 1 open** | 16 fills, capture +, balance PnL +; toxic 25% + spread-kill blocked run — stay on `safe` |
| 2026-05-29 | **Tier 1 + Gate 1 complete** | Operator sign-off: plumbing stable on mainnet; formal metric bar partial; shortcomings logged; **Gate 2 current** |
| | Gate 2 pass | `tight_spread` competitive pilot (≥100 fills, toxic &lt; 20%) |
| | Tier 2.5 next | `competitive_pilot`, edge-met gate, BookOffers ask fix |
| (current) | Grok/xAI + Intelligence tab + pure A-S HUD | Config-driven Grok API tokens for competitor address trending (advisory AI); on-chain scraper + Intelligence nav tab live in HUD; real /analyze_competitor Grok endpoint; llama3 stub deprecated for intel path. Commit push: WS + pure A-S observation surface + competitor intel + real Grok support now functional in experimental (no sacred long-run impact). More token details / rotation / prompts to come later. |
| 2026-06 (this session) | 11k XRP-only WS A-S deployment observations captured in plan | Only-XRP funding (100% heavy rebalance via competitive L1/L2/L3 asks); WS pure A-S (no outer hard gate / "L1 too tight" blocker — higher presence via live WS book + competitor_pressure calibration); scaling math (more inventory → higher absolute skim via larger pull + compounding as capital grows from rebalance + skim; not auto-wider spreads); live ledger (36k+ XRP single offers, 200k+/280k+ total depth — supportive of scaling to predator L1 in low thousands XRP); P&L targets (conservative year-end +25–45k XRP skim / 36–56k value from 11k start, with ~150–500 XRP/day blended potential per user live view); predator enablers (wire pressure as aggression dial, dynamic sizing, bypass legacy gates in pure path, XRP-heavy competitive asks, AI for competitor trending). Gaps: legacy market_edge_met/edge guards still in main engine; pressure mostly advisory not A-S input. Immediate changes listed in plan for implementation. |

---

## Related docs

- [`STRATEGY_MANUAL.md`](STRATEGY_MANUAL.md) — strategy, profiles, defense (plain language)
- [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md) — GUI, kill switch, go-live
- [`AUDIT_REPORT.md`](AUDIT_REPORT.md) — policy / posture conflicts (v1.4.1)
- [`CHANGELOG.md`](../CHANGELOG.md) — release history

---

## Quick reference — key code paths

```
Cycle:     engine/trading_engine.py::_run_cycle
Policy:    core/dynamic_quoting_policy.py::resolve_dynamic_quoting_policy
Quotes:    strategy/quote_decision.py::build_quote_adjustments
Edge:      strategy/market_microstructure.py::resolve_effective_min_edge_pct
Fills:     monitoring/ledger_fills.py + monitoring/fill_detection.py
Orders:    engine/trading_engine.py::_refresh_orders + engine/order_sync.py
Drawdown:  risk/drawdown.py (invalid mid → skip mark + no kill)
Book mid:  connectors/xrpl_connector.py (is_trustworthy_rlusd_mid, is_book_crossed)
Insights:  utils/session_insights.py + scripts/analyze_session.py
Reports:   scripts/weekly_skim_report.py, scripts/portfolio_bleed_analysis.py
Config:    config/settings.py, config/config.yaml (local, gitignored)
Kill GUI:  gui/streamlit_gui.py (Advanced → Kill settings)
```
