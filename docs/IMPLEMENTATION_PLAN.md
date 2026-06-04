# XLedgerMate — Implementation Plan: Good → Great MM

*Updated: 2026-06-04 · v1.4.2 on `tier-2-polish` · mainnet pilot ~246 XRP*

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
| **Kill** | False drawdown on stale mid (fixed v1.4.2) | Kill only on real marks + operator-understood triggers |

**Mainnet pilot reference (2026-06-03/04):** One continuous session **~80 fills**, **+0.41 XRP** logged spread capture, **~6%** negative-capture fills, balanced BUY/SELL — proves plumbing and spread economics; **not** sufficient alone to declare field-ready (toxic ~22%, defense-dominated visibility, false drawdown kill before fix).

---

## Field deployment gates

Operator promotion path while logging continues. Do **not** scale size or switch to `profit_mode` until the gate passes.

### Gate 1 — Validation run (current)

*v1.4.2+ on mainnet; collect clean post-fix data.*

**Setup**

- [ ] Pull `tier-2-polish` (drawdown stale-mid fix + GUI/safety stack).
- [ ] Clear kill switch → **Restart engine** (drawdown baseline = wallet).
- [ ] Set **risk capital** in GUI to **~live portfolio XRP** (not Flare roll-up placeholder).
- [ ] Stay **`safe`**: L1 **10–15 XRP**, L2/L3 **0**; optional **dynamic min edge ON** if book routinely tight.
- [ ] `toxic_fill_kill_enabled: false` (refresh pause / off-book only).

**Pass when (one uninterrupted session)**

- [ ] **≥40 fills** logged in trades CSV since engine start.
- [ ] Toxic ratio **&lt; 25%** over rolling window (Dashboard / runtime).
- [ ] Spread capture (sum `profit_xrp_equiv`) **positive**.
- [ ] **No false drawdown kill**; decision log may show `Skipped daily drawdown mark` on bad book ticks.
- [ ] **Offers visible &gt; ~70%** of runtime (not stuck 0 offers + off-book).

**Tools:** `python scripts/analyze_session.py`, Dashboard session insights, `logs/decisions.jsonl`.

### Gate 2 — Competitive pilot (`tight_spread`, same capital)

*Only after Gate 1.*

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
- [x] Portfolio drawdown kill (invalid mid guard v1.4.2) + toxic / spread / RPC kills
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
| **Assessment** | No weekly skim rollup (bps/fill, time-on-book, policy mix) | `scripts/analyze_session.py` (partial), new report TBD |
| **Protection** | Toxic gates on **small N** (≥3 fills) still flip off-book at 20–22% | `strategy/fill_quality.py`, profile toxicity fields |
| **Automation** | No hysteresis on toxicity exit; no `competitive_pilot` preset | Tier 2.5 below |

*Resolved in v1.4.2:* false daily drawdown kill on stale/crossed book (`risk/drawdown.py`, `engine/trading_engine.py`). *Resolved in v1.4.2 stack:* toxic fill kill off by default; fill-quality reset when toxic pause + empty book.

---

## Tier 1 — Config + quick wins

*Pilot capital ~246 XRP on mainnet.*

### Configuration

- [x] `dynamic_min_edge_enabled` in example + `BotConfig` default
- [x] Example L2 depth skim (`order_sizes: [50, 15, 0]` or pilot `[15, 0, 0]`)
- [x] `auto_rollover_enabled` removed (stub)
- [ ] **Risk capital in GUI = wallet portfolio** (operator rule until code sync)
- [ ] Confirm secrets only in local `config.yaml` (never committed)

### Code

- [x] Edge guard widens spread when edge thin
- [x] `profit_xrp_equiv` on fills in trade CSV
- [x] `capture_edge_pct` in favorable regime
- [x] Drawdown + kill switch tests

### Verification (Tier 1)

- [x] Kill/drawdown tests pass
- [ ] Spread check pass rate stable on mainnet live
- [ ] Trade CSV non-zero `profit_xrp_equiv` on fills (pilot: **yes**, +0.41 XRP / 80 fills)
- [ ] Decision log shows edge guard when book thin

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
| 1 | **Risk capital = live portfolio** sync (GUI save + engine sizing) | Sizing and `max_leg_size_pct` match ~246 XRP reality |
| 2 | **`competitive_pilot` profile or preset** | Higher touch relevance; toxicity **hysteresis** (exit defense below enter); widen/shrink before off-book / refresh-stop |
| 3 | **Weekly skim report** script | bps/fill, toxic %, time-on-book estimate, policy mix %, capture XRP — Gate 1/2 decisions from data |
| 4 | **Join-touch when favorable + edge met** | Use queue preservation at L1 when health high (`join_touch`, `order_sync`) |
| 5 | **Persist fill-quality / toxic rolling stats** across restarts (optional decay) | Less noisy re-entry after restart |

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
- [ ] Drawdown % vs limit; kill activations (note false kills pre-v1.4.2)

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
| Go / no-go pilot (continue on `safe`?) | **≥40 fills**, positive capture, one post-v1.4.2 session |
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
6. **After kill clear** — restart engine so drawdown baseline resets; read kill reason in `logs/kill_switch.json`.
7. **Keep logging** through Gate 1 even if economics look good — visibility and policy mix matter as much as capture XRP.

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
| | Gate 1 pass | Post-v1.4.2 validation session (≥40 fills, stable visibility) |
| | Gate 2 pass | `tight_spread` competitive pilot (≥100 fills, toxic &lt; 20%) |
| | Tier 2.5 started | Risk capital sync, competitive_pilot, weekly skim report |

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
Insights:  utils/session_insights.py + scripts/analyze_session.py
Config:    config/settings.py, config/config.yaml (local, gitignored)
```
