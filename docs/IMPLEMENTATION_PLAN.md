# XLedgerMate — Implementation Plan: Good → Great MM

*Updated: 2026-05-30 · v1.4.0 Tier 2 on `tier-2-fix`*

## North star

**Automate greatness:** max skim (spread + edge capture) while protecting balances.

| Pillar | Definition of “great” |
|--------|------------------------|
| **Skim** | Capture spread when edge is real; compete at the book without giving away queue position |
| **Protection** | Inventory, adverse selection, and drawdown bounded before they become operator emergencies |
| **Automation** | Closed feedback loops from fills → quotes → profile; minimal manual intervention |

---

## What we already have (do not regress)

- [x] Layered quote pipeline (preflight → market → profile → inventory → momentum → fill quality → edge → spread check)
- [x] Five built-in profiles + auto-switch (never auto `profit_mode`)
- [x] Live spread validation before mainnet placement
- [x] Fill-quality dampening (coarse balance-delta fills)
- [x] Portfolio drawdown → persistent kill switch → cancel offers
- [x] Inventory steering toward target XRP ratio (default 55%)
- [x] Operator GUI + decision log + runtime state
- [x] Strategy unit tests (`test_defensive_mm`, market conditions, quote validation)

---

## Gap summary (audit 2026-05-30)

| Area | Core problem | Primary files |
|------|--------------|---------------|
| **Skim** | Cancel-all-replace every cycle; edge guard shrinks size only; `capture_edge_pct` unused | `engine/trading_engine.py`, `strategy/quote_decision.py` |
| **Protection** | Coarse fill inference; single-tick markout; no inventory hard stops; kill = drawdown only | `monitoring/fill_detection.py`, `strategy/fill_quality.py`, `risk/` |
| **Automation** | No per-fill P&L in CSV; dynamic min edge off; dead flags (`auto_rollover_enabled`) | `config/settings.py`, `monitoring/csv_logger.py` |

---

## Tier 1 — This week (config + small code)

*Pilot capital ~234 XRP; low risk, high learning.*

### Configuration (no code)

- [x] Enable `dynamic_min_edge_enabled: true` in `config.example.yaml` (defaults on in `BotConfig`)
- [x] Add L2 size for depth skim in example (`order_sizes: [50, 15, 0]`)
- [ ] Document operator rule: widen or return to `safe` if toxic fill ratio rises (manual until Tier 2 metrics exist)
- [x] Remove `auto_rollover_enabled` (was unimplemented stub)
- [ ] Confirm secrets only in local `config.yaml` (never committed)

### Code — skim & protection quick wins

- [x] **Edge guard widens spread** when edge thin — `strategy/quote_decision.py`
- [x] Wire **`profit_xrp_equiv`** on fill in trade CSV — `monitoring/fill_economics.py`, `csv_logger.py`, `trading_engine.py`
- [x] Use **`capture_edge_pct`** in favorable regime — `strategy/quote_decision.py`
- [x] Tests: **`DrawdownMonitor`** + **`KillSwitch`** — `tests/test_drawdown.py`, `tests/test_kill_switch.py`, `tests/test_great_mm.py`

### Verification (Tier 1 done when)

- [ ] Spread check pass rate unchanged or improved on mainnet dry-run/live
- [ ] Trade CSV shows non-zero `profit_xrp_equiv` on fills
- [ ] Decision log shows “edge guard → widen” when book is thin
- [x] Kill/drawdown tests pass in local `pytest`

---

## Tier 2 — This month (execution + truth)

*Required before scaling toward ~11k XRP.*

### 1. Selective order maintenance (queue preservation)

- [x] Map open offers by side/sequence from connector
- [x] Cancel/replace only when price or size change exceeds epsilon — `engine/order_sync.py`
- [x] Log: offers cancelled vs kept per cycle
- [ ] Metric target: **cancelled offers per fill** trending down (measure in production) — **tracked in runtime_state `cancel_per_fill`**

**Files:** `engine/trading_engine.py`, `connectors/xrpl_connector.py`, `engine/order_sync.py`, `core/profile_execution.py`

### 2. Ledger-accurate fills

- [x] Poll or parse `account_tx` / OfferFilled for bot account
- [x] Match fills to quote intents; store tx hash + real fill price
- [x] Balance-delta fallback when ledger scan misses (deduped)
- [x] Tests with mocked XRPL JSON-RPC responses

**Files:** `monitoring/fill_detection.py`, `monitoring/ledger_fills.py`

### 3. Multi-horizon markout

- [x] Record markout at +30s and +5m after fill (not only next cycle mid)
- [x] Feed improved markout into `FillQualityTracker`
- [x] Surface toxic ratio in GUI Dashboard or Logs tab

**Files:** `strategy/fill_quality.py`, `engine/trading_engine.py`, `gui/streamlit_gui.py`

### 4. Inventory circuit breakers

- [x] Hard stop bids if XRP share > target + max deviation (default 12pp)
- [x] Hard stop asks if XRP share < target − max deviation
- [ ] Optional: pause all quoting if deviation > Y% until operator ack
- [x] Tests for boundary behavior — `tests/test_great_mm.py`

**Files:** `risk/inventory_limits.py`, `strategy/quote_decision.py`

### 5. Smarter refresh cadence

- [x] Tiered loop: fast book/momentum check (profile-owned poll) vs full refresh (profile-owned)
- [x] Skip full cancel/replace when quotes unchanged (`selective_order_refresh`)
- [x] Pause refresh after toxic-fill cluster (profile threshold)

**Files:** `engine/trading_engine.py`, `config/settings.py`, `core/profile_execution.py`, `core/perception.py` (profile fields)

### 6. Multi-trigger kill switch

- [x] Trigger on N consecutive spread-check failures (live mode)
- [x] Trigger on toxic-fill ratio > threshold over last M fills
- [x] Trigger on RPC failure streak (optional circuit breaker)
- [x] Tests — `tests/test_kill_switch.py`, `tests/test_drawdown.py`

**Files:** `risk/kill_switch.py`, `engine/trading_engine.py`

### 7. Auto-switch guard

- [x] Aggressive auto-switch requires +2 extra confirm cycles (`is_more_defensive_than`)
- [x] Log every auto profile switch with before/after + market snapshot

**Files:** `core/market_conditions.py`, `engine/trading_engine.py`

### Verification (Tier 2 done when)

- [ ] Realized spread bps per fill logged and reviewable weekly
- [ ] Toxic fill ratio < 20% over rolling 50 fills (or operator widens profile)
- [ ] Inventory deviation > 12% from target rare and self-correcting via quotes
- [ ] Cancel churn metric documented and falling vs Tier 1 baseline

---

## Tier 3 — Later (institutional-grade)

- [ ] Real Avellaneda–Stoikov half-spread (γ, inventory q, κ) replacing static spread table — `strategy/avellaneda_strategy.py`
- [ ] WebSocket book + fill stream (lower latency than 60s poll)
- [ ] Auto edge / profile tuning from rolling 7-day skim bps (with caps and manual override)
- [ ] Optional on-chain rebalance helper (explicit operator gate; never silent swaps)
- [ ] CI: connector integration tests + dry-run full cycle test
- [ ] Prometheus / external health endpoint for unattended monitoring

---

## Metrics checklist (track weekly)

Copy to a spreadsheet or append to `logs/` review notes.

### Skim

- [ ] Realized spread per fill (bps vs mid at **quote** time)
- [ ] Spread captured when `market_edge_met` was true vs false at fill
- [ ] XRP fee drag (ledger fees) vs spread earned (session)
- [ ] Fills per cycle × active levels (fill rate)

### Protection

- [ ] Toxic fill ratio (`toxic / recent fills`) — target **< 20%**
- [ ] Markout @ 30s after fill (mean by side)
- [ ] Hours outside ±6% of inventory target (55% XRP default)
- [ ] Max intraday inventory deviation (%)
- [ ] Drawdown % vs `max_daily_drawdown_percent`; kill switch activations

### Execution & automation

- [ ] Spread validation pass rate
- [ ] Live-blocked cycles (`live_blocked_by_spread`)
- [ ] Offers cancelled per fill (lower is better)
- [ ] Auto vs manual profile switches
- [ ] Cycle time p50 / p95 vs `order_refresh_time_seconds`

---

## Operating rules (until Tier 2 ships)

1. **`profit_mode`** — manual only; use `tight_spread` when book is ideal.
2. **Inventory > ~15% off target** — consider manual swap + `safe`; don’t tighten to chase spread.
3. **Spread check FAIL** — stay dry-run or fix profile; never override on mainnet.
4. **Session red + high toxic ratio** — step down profile, don’t tighten.
5. **Scale capital** only after Tier 2 metrics stable for 2+ weeks.

---

## Progress log

| Date | Milestone | Notes |
|------|-----------|-------|
| 2026-05-30 | Plan created | Audit → this document; GUI redesign v1.3.8 |
| 2026-05-30 | v1.3.9 on `good-to-great` | Tier 1 MM gaps: edge widen, selective refresh, inventory limits, fill P&L, kill triggers |
| 2026-05-30 | **v1.3.9 great-MM** | Edge widen, selective refresh, inventory limits, fill P&L, multi-trigger kill |
| | Tier 1 live verify | Spread check + profit_xrp_equiv on mainnet fills |
| 2026-05-30 | **v1.4.0 tier-2-fix** | Profile-owned execution, ledger fills, markout 30s/5m, tiered refresh, RPC kill |
| 2026-05-30 | Tier 2 started | Branch `tier-2-fix` from `good-to-great` |
| | Tier 2 live verify | Cancel/fill ratio + toxic @30s on mainnet pilot |
| | Tier 3 item started | |

---

## Related docs

- [`STRATEGY_MANUAL.md`](STRATEGY_MANUAL.md) — what the bot is trying to do (plain language)
- [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md) — buttons, tabs, go-live gate
- [`CHANGELOG.md`](../CHANGELOG.md) — release history

---

## Quick reference — key code paths

```
Cycle:  engine/trading_engine.py::_run_cycle
Quotes: strategy/quote_decision.py::build_quote_adjustments
Edge:   strategy/market_microstructure.py::resolve_effective_min_edge_pct
Fills:  monitoring/ledger_fills.py + monitoring/fill_detection.py (fallback)
Orders: engine/trading_engine.py::_refresh_orders  ← profile-aware selective sync
Profile execution: core/profile_execution.py + core/perception.py Profile fields
Risk:   risk/drawdown.py, risk/kill_switch.py
Config: config/settings.py, config/config.yaml (local, gitignored)
```
