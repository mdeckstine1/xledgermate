# Full-stack code audit — XLedgerMate v1.4.4

**Auditor:** Grok (Cursor)  
**Scope:** Entire Python stack — config, connectors, core, engine, strategy, risk, monitoring, GUI, utils, scripts, tests  
**Method:** Static review, line counts, pytest run, cross-check with `docs/`, `CHANGELOG.md`, prior `AUDIT_REPORT.md`

---

## Executive summary

| Dimension | Grade | Summary |
|-----------|-------|---------|
| **Safety / risk isolation** | A− | Strong kill-switch layering, book-unreliable guards, credential sidecar; operator process gaps remain |
| **XRPL integration** | B+ | Async connector, offer lifecycle, book sanity checks; RPC book quality still a root risk |
| **Strategy fidelity** | C+ (naming) / B (behavior) | Behaves like a **rules-based defensive MM**, not a true Avellaneda–Stoikov implementation |
| **Execution engine** | B+ | Mature cycle loop, selective refresh, ledger fills; monolithic `trading_engine.py` |
| **Operator GUI** | B− | Feature-rich desk; **~2,900+ lines** in one file — maintainability debt |
| **Test suite** | B+ | 140 unit tests, good coverage on kills/drawdown/quotes; thin on live connector integration |
| **Ops / CI** | C | No visible GitHub Actions; main branch stale; logging-heavy manual gates |
| **Competitive MM readiness** | Pilot | Gate 1 signed off; Gate 2 (`tight_spread`) in progress — not field-competitive yet |

**Bottom line:** This is a **serious, mainnet-tested operator bot** with thoughtful defense-in-depth. It is **not yet** a latency- or queue-competitive MM in the Hummingbot/CeFi sense. The gap is architectural (poll-based, defensive profiles) and economic (time on touch, cancel/fill, realized bps), not missing “one more flag.”

---

## 1. System architecture

### 1.1 Layer map

```
┌─────────────────────────────────────────────────────────────────┐
│  Operator layer                                                  │
│  gui/streamlit_gui.py  ·  logs/runtime_state.json  ·  CLI       │
└────────────────────────────┬────────────────────────────────────┘
                             │ profile requests, config patches, engine PID/stop files
┌────────────────────────────▼────────────────────────────────────┐
│  Orchestration                                                   │
│  main.py (--mode engine|gui|once|…)  ·  engine/trading_engine.py │
└────────────────────────────┬────────────────────────────────────┘
                             │
     ┌───────────────────────┼───────────────────────┐
     ▼                       ▼                       ▼
┌─────────┐           ┌─────────────┐         ┌──────────────┐
│ strategy│           │ core        │         │ risk         │
│ spreads │◄──────────│ profiles    │────────►│ drawdown     │
│ quotes  │           │ perception  │         │ kill_switch  │
│ fills   │           │ policy/tox  │         │ inventory    │
└────┬────┘           └──────┬──────┘         └──────────────┘
     │                       │
     └───────────┬───────────┘
                 ▼
         ┌───────────────┐         ┌────────────────┐
         │ engine        │────────►│ connectors     │
         │ order_manager │         │ xrpl_connector │
         │ order_sync    │         │ (async JSON-RPC)│
         └───────────────┘         └────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │ monitoring    │  CSV, telegram, ledger_fills, balance_logger
         └───────────────┘
```

### 1.2 Code mass (Python, excl. `.venv`)

| Package | Files | ~Lines | Role |
|---------|-------|--------|------|
| `gui/` | 7 | 3,653 | Streamlit desk, engine control, ticker |
| `tests/` | 39 | 2,181 | Regression safety net |
| `engine/` | 4 | 1,913 | Trading loop, order sync |
| `utils/` | 23 | 1,634 | Config sync, validation, RPC health |
| `core/` | 11 | 1,211 | Profiles, policy, toxicity, runtime state |
| `strategy/` | 6 | 929 | Spreads, quote pipeline, fill quality |
| `monitoring/` | 7 | 652 | Fills, economics, alerts |
| `connectors/` | 2 | 583 | XRPL book + offers |
| `risk/` | 5 | 354 | Drawdown, inventory limits |
| **Total (approx.)** | **~105** | **~13,700** | |

### 1.3 Entry points and process model

- **`main.py`**: CLI with modes `engine`, `gui`, `once`, `cancel-offers`, `clear-kill`, `setup-trust`, `send`, `rebalance-check`.
- **Engine process**: writes `logs/engine.pid`; GUI signals stop via `logs/engine.stop` (stop does **not** auto-cancel offers — documented operator hazard).
- **Config hot-reload**: engine reloads `BotConfig` each cycle; profile changes via `utils/profile_request.py` without restart.
- **State**: `logs/runtime_state.json` bridges GUI ↔ engine (quotes, session PnL, toxic stats, cancel/fill).

### 1.4 GitHub vs local divergence (critical)

| | `origin/main` | Local `tier-2-polish` |
|--|---------------|------------------------|
| Version | 1.0.0 | 1.4.4 |
| Engine | None in `main.py` | Full `TradingEngine` |
| Tests | Minimal / absent on main | 140 tests |
| Docs | README only | `docs/*` manuals + gates |

**Risk:** External readers judge the project from stale `main`. Recommend merging or tagging `v1.4.4` and updating default branch README.

---

## 2. Component audit

### 2.1 `config/settings.py` — **Good**

**Strengths**

- Dataclass `BotConfig` with YAML load/save.
- **Credential preservation**: sidecar `credentials.local.yaml`, `.bak` recovery, `patch_config_file` excludes secrets.
- Network resolution (`testnet`, `private_node_url`, cluster warnings in `main.py`).

**Issues**

- Large flat config surface (~80+ fields) — easy for GUI and engine to drift (mitigated by presets, not schema validation).
- Example `config.example.yaml` on GitHub still shows **11,254 XRP** risk capital vs ~250 XRP pilot wallet — operator foot-gun (partially fixed in GUI sync).

**Recommendation:** JSON Schema or pydantic model + CI validate example config; split `config/pilot.yaml` vs `config/production.yaml`.

---

### 2.2 `connectors/xrpl_connector.py` — **Good with open P0**

**Strengths**

- Async `xrpl-py` client with retry wrapper (`utils/rpc_health.py`).
- **Book integrity**: `is_plausible_rlusd_per_xrp`, `is_book_crossed`, `is_trustworthy_rlusd_mid`.
- Offer create/cancel, trust line, payments, `BookOffers` normalization.

**Issues (severity)**

| ID | Severity | Issue |
|----|----------|-------|
| C-1 | **High** | Ghost/inverted **ask** from RPC (~0.28 RLUSD/XRP) — engine defends but root parser/filter incomplete (Tier 2.5 #6) |
| C-2 | Medium | Poll-only book — no WebSocket; cycle latency = profile poll interval (15–60s) |
| C-3 | Low | `datetime.utcnow()` deprecation in `risk/drawdown.py` (13 pytest warnings) |
| C-4 | Low | Optional `xrpl-py` import fallback — runtime fail late if missing |

**Recommendation:** Add integration test with **recorded** `BookOffers` JSON fixtures (inverted, crossed, raw quality).

---

### 2.3 `core/` — **Strong design**

| Module | Assessment |
|--------|------------|
| `perception.py` | Five profiles + `profit_mode`; well-documented toxicity thresholds |
| `dynamic_quoting_policy.py` | Single resolver for touch posture — fixes v1.4.1 dual-path bug |
| `market_conditions.py` | Auto-profile switching with defensive bias |
| `toxicity.py` | Shared adverse-ratio + min-fill gates (≥8 fills) |
| `quote_caps.py` | Unified `max_worse_than_touch` — good DRY |
| `runtime_state.py` | Persistence for GUI; v1.4.1 fixed partial `load()` |

**Issue:** Policy stack is **complex** — many interacting thresholds; hard to predict outcomes without `logs/decisions.jsonl` + ticker.

---

### 2.4 `strategy/` — **Mislabeled but competent**

**`avellaneda_strategy.py`**

- Computes spreads via `compute_effective_spreads_pct()` — profile multipliers × vol × liquidity.
- **No** reservation price, **no** γ (risk aversion), **no** κ (order arrival intensity), **no** inventory term in A-S sense.

**`quote_decision.py`**

- Long pipeline: inventory → momentum → fill quality → market edge → dynamic policy → spread adjustments.
- **Open:** quotes can still be built when `market_edge_met` is false (Tier 2.5 #5).

**`fill_quality.py`**

- Markout @ 30s / 5m drives toxic gates — appropriate for XRPL cadence.

---

### 2.5 `engine/trading_engine.py` — **Core asset, structural debt**

**Strengths (~1,600 lines)**

- Full cycle: balances → book → portfolio mark → preflight → market assessment → quote plan → validation → selective sync → place/cancel.
- Session baselines only on trustworthy mid (v1.4.3).
- Spread-fail kill **exempts** `book_unreliable` (v1.4.4).
- Ledger fill scanner + balance-delta fallback.

**Weaknesses**

| ID | Issue |
|----|-------|
| E-1 | **God module** — hard to unit-test full cycle; changes are high blast radius |
| E-2 | Reloads config every cycle — correct for ops, adds I/O latency |
| E-3 | GUI and engine share filesystem contracts (`runtime_state.json`, stop file) — race possible under fast clicks |
| E-4 | `dry_run` / `trading_enabled` must stay aligned — operator error if GUI shows quotes but engine dry |

**Recommendation:** Extract `CycleContext` dataclass + phase functions (`fetch_market`, `assess_risk`, `plan_quotes`, `execute_sync`).

---

### 2.6 `engine/order_manager.py` + `order_sync.py` — **Good**

- Clamps quotes to touch bands before submit.
- Selective cancel/replace vs full refresh — `cancel_per_fill` metric for Gate 2.
- Invisible off-touch cleanup (`utils/book_visibility.py`).

---

### 2.7 `risk/` — **Strong**

- `drawdown.py`: invalid mid skips false kill (v1.4.2).
- `kill_switch.py`: persisted reason in `logs/kill_switch.json`.
- `inventory_limits.py`: hard pause sides, cap leg size.
- Session balance loss kill (v1.4.3) — balance PnL, not MTM-only.

**Gap:** No on-chain position limit beyond config sizes; relies on offer sizes + inventory steering.

---

### 2.8 `monitoring/` — **Adequate for pilot**

- CSV trade log, balance logger, telegram (optional import).
- `ledger_fills.py` — important for truthful economics.
- **Gap:** `profit_xrp_equiv` often ~0 on balance-delta fills — scoreboard understates edge (known Gate 1 shortcoming).

---

### 2.9 `gui/streamlit_gui.py` — **Functional, fragile**

**Strengths**

- Professional desk: session insights, operator health, engine control, profile presets, kill settings.
- Credential form separation, risk capital sync button.

**Weaknesses**

| ID | Issue |
|----|-------|
| G-1 | **Monolith** (~2,900 lines) — highest maintenance cost in repo |
| G-2 | Streamlit rerun model → subtle state bugs (mitigated by `runtime_state.json`) |
| G-3 | Engine stop ≠ cancel offers — must be explicit in runbooks |
| G-4 | `importlib` reload paths for hot patches — clever but hard to trace |

**Recommendation:** Split into `gui/pages/` (dashboard, config, kills, ledger) + thin `app.py`.

---

### 2.10 `utils/` — **Broad, mostly cohesive**

23 modules — appropriate for operator tooling (`preflight`, `session_insights`, `weekly_skim_report` scripts). Watch for duplicated book/price helpers between `connectors` and `utils`.

---

### 2.11 `tests/` — **140 passed**

**Well covered**

- Drawdown, kill switch, quote validation, trustworthy mid, toxicity gates, order sync, profile execution, inventory.

**Gaps**

- No automated **connector integration** tests (mock RPC responses only in places).
- No end-to-end dry-run cycle test in CI.
- GUI untested (typical for Streamlit).

---

## 3. Security audit

| Check | Status | Notes |
|-------|--------|-------|
| Secrets in git | ✅ | `config.yaml`, `credentials.local.yaml`, `logs/` gitignored |
| Secret in logs | ⚠️ | Ensure decision logs never echo `bot_secret_key` |
| Key handling | ⚠️ | Plaintext YAML secret — standard for bot wallets; consider OS keychain for GUI |
| RPC trust | ⚠️ | Public RPC can return bad books — mitigated, not eliminated |
| Amendment blocked nodes | ✅ | Detected at startup (`rpc_reports_amendment_blocked`) |
| Main wallet isolation | ✅ | Design intent: bot account only — **policy**, not enforced in code |
| Telegram token | ⚠️ | Stored in config if enabled |

**Critical operator rule (not code):** Never point bot secret at “Mangie” main bag — no hard block prevents this.

---

## 4. Reliability & observability

| Mechanism | Present? |
|-----------|----------|
| Structured decision log | ✅ `logs/decisions.jsonl` |
| Runtime state for GUI | ✅ |
| Kill switch persistence | ✅ |
| RPC retry | ✅ |
| Health scripts | ✅ `weekly_skim_report`, `portfolio_bleed_analysis`, `analyze_session` |
| Metrics export (Prometheus) | ❌ Tier 3 |
| CI pipeline | ❌ Not in repo |
| WebSocket low-latency feed | ❌ Tier 3 |

---

## 5. Prior audit alignment (`docs/AUDIT_REPORT.md`)

Your June 2026 internal audit fixed **critical policy duplication** (dual touch resolvers, scattered toxicity, cap inconsistencies). This review **confirms** those fixes are reflected in code and tests.

**Still open from your audit + plan:**

1. BookOffers ask inversion (connector root cause)
2. Block quotes when `market_edge_met` false
3. `competitive_pilot` profile / preset
4. Persist fill-quality across restarts (optional)

---

## 6. Risk register (consolidated)

| ID | Risk | Likelihood | Impact | Mitigation status |
|----|------|------------|--------|-------------------|
| R1 | Bad RPC book → false PnL / kills | Medium | High | Mostly mitigated v1.4.2–1.4.4 |
| R2 | Stale GitHub `main` misleads deploy | High | Medium | Publish real branch |
| R3 | `safe` profile → 0 intents / no touch time | High | Medium (economic) | Gate 2 `tight_spread` |
| R4 | Cancel churn loses queue | Medium | Medium | order_sync + metrics |
| R5 | GUI/engine desync | Low | Medium | Operator manual sync |
| R6 | Secret committed | Low | Critical | gitignore + sidecar |
| R7 | Stop engine leaves offers on book | Medium | High | Document + optional stop-hook cancel |

---

## 7. Audit conclusions

**What is production-grade today**

- Risk kills and book-unreliable handling
- Layered quote validation before mainnet submit
- Profile system with auto-switch guardrails
- Operator tooling and session analytics
- Test-backed regression suite for core math/policy

**What is not production-grade for competitive MM**

- Poll-based 15–60s cycles vs sub-second competition
- Defensive-default profile economics
- Naming vs implementation gap (Avellaneda)
- Incomplete fill PnL attribution on balance-delta path
- Connector book feed root cause

**Suggested immediate engineering (see doc 02 & 03)**

1. Tier 2.5 items 4–6 from `IMPLEMENTATION_PLAN.md`
2. Split `trading_engine.py` / `streamlit_gui.py`
3. Tag release + sync GitHub `main`
4. Add CI: `pytest` + config lint

---

*End of full-stack audit.*