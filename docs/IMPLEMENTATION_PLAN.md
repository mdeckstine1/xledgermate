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

- [ ] Real Avellaneda–Stoikov half-spread (γ, inventory q, κ) — `strategy/avellaneda_strategy.py`
- [ ] WebSocket book + fill stream (lower latency than poll-only loop)
- [ ] Auto edge / profile tuning from rolling 7-day skim bps (caps + manual override)
- [ ] Optional on-chain rebalance helper (explicit operator gate)
- [ ] CI: connector integration + dry-run full cycle
- [ ] Prometheus / external health for unattended ops

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
