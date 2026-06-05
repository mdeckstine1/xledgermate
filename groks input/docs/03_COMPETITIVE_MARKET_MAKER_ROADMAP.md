# Roadmap: pilot MM → competitive XRPL market maker

> **Superseded for pass/fail metrics and gates:** see **[05_MASTER_ROADMAP_REALISTIC_METRICS.md](05_MASTER_ROADMAP_REALISTIC_METRICS.md)** (toxic 20%, 70% visibility, 100-fill gate revised for RLUSD pilot reality). This doc remains useful for phase framing.

**Context:** XLedgerMate v1.4.4, ~250 XRP mainnet pilot, XRP/RLUSD on XRPL  
**North star (from your plan):** Automate greatness — **skim spread when edge is real**, protect inventory, minimize operator panic.

This document defines what **competitive** means on XRPL (not Binance HFT), maps gaps vs your codebase, and gives a **phased execution plan** aligned with your existing Gate 1/2/3 framework.

---

## 1. Define “competitive” on XRPL

CeFi competitive MM implies microsecond co-location. **XRPL competitive MM** is different:

| Dimension | XRPL reality | Your bot today |
|-----------|--------------|----------------|
| **Latency** | Seconds (ledger close ~3–4s); poll loop 15–60s | Poll — acceptable for XRPL if touch time is high |
| **Queue** | OfferCreate sequence; amending price loses queue | Selective sync ✅ — need lower cancel/fill |
| **Adverse selection** | Thin RLUSD, informed flow | Toxic gates ✅ — tune thresholds for Gate 2 |
| **Inventory** | Two-asset + trust lines | Skew + pause ✅ |
| **Edge** | Must exceed fees + pickoff | `market_edge` exists — **not fully gating live quotes** |
| **Visibility** | Offers must appear in book | Off-book defense dominates on `safe` |

### Competitive MM scorecard (field-grade)

A competitive XRPL MM on your capital scale should demonstrate **all** of the following over **2+ weeks**:

| Metric | Target |
|--------|--------|
| Fills | ≥ 100 under stable `tight_spread` config |
| Toxic ratio (30s markout) | < 20% over rolling 50 fills |
| Realized spread | Positive **bps per fill** vs mid at quote time |
| Session balance PnL | ≥ 0 weekly (primary scoreboard) |
| Time on touch | At/near touch > 50% of favorable-market cycles |
| Cancel/fill | Falling vs Gate 1 baseline (~1.66) while fill rate stable or up |
| Inventory | > 12% deviation from 55% XRP target rare |
| Kill events | Only operator-understood, real losses |

**You do not need ML** to pass Gate 2. You need **economics + feed quality + edge discipline**.

---

## 2. Competitive gap analysis (vs state of art)

### 2.1 What you already have (do not regress)

From `docs/IMPLEMENTATION_PLAN.md` — shipped on `tier-2-polish`:

- [x] Layered quote pipeline with preflight
- [x] Dynamic quoting policy (touch posture)
- [x] Live spread validation before submit
- [x] Selective order refresh + `cancel_per_fill`
- [x] Ledger fills + markout toxicity
- [x] Multi-trigger kill switch with book-unreliable exemptions
- [x] Inventory circuit breakers
- [x] Operator GUI + session analytics
- [x] Auto-profile switch (never auto `profit_mode`)

### 2.2 What blocks competitiveness today

```
┌────────────────────────────────────────────────────────────┐
│  GAP LAYER          │  Symptom              │  Fix tier    │
├─────────────────────┼───────────────────────┼──────────────┤
│  Profile economics  │  0 intents, off-book  │  Gate 2 ops  │
│  Edge gating        │  Quotes without edge  │  Tier 2.5 #5 │
│  Book feed          │  Inverted ask RPC     │  Tier 2.5 #6 │
│  PnL attribution    │  profit_xrp ≈ 0       │  Tier 2.5    │
│  Capital model      │  11k vs 250 XRP       │  Tier 2.5 #1 │
│  Latency (later)    │  Poll-only            │  Tier 3      │
│  A-S model (later)  │  Heuristic spreads    │  Tier 3      │
└────────────────────────────────────────────────────────────┘
```

### 2.3 Competitive positioning statement

**Short term (Gate 2):** Be the **best disciplined RLUSD/XRP quote bot** on XRPL at pilot size — touch when favorable, wide when hostile, never lie about PnL.

**Medium term (Tier 2.5–3):** Match **professional XRPL desk** behavior: stable queue at L1, honest metrics, automated edge tuning.

**Long term:** Institutional-grade — WebSocket, true A-S, external monitoring — when capital > ~few thousand XRP equiv. and ops are unattended.

---

## 3. Phased roadmap (integrated with your gates)

### Phase 0 — Repository truth (1–2 days) **parallel**

| Task | Owner | Done when |
|------|-------|-----------|
| Merge or fast-forward `main` from `tier-2-polish` | Dev | GitHub README matches v1.4.4 |
| Tag `v1.4.4` release | Dev | GitHub Releases page |
| Add CI: `pytest tests/` on push | Dev | Green badge |
| Document default branch = active pilot branch | Ops | README branch table |

*Why competitive:* External credibility + reproducible deploys for any second operator or auditor.

---

### Phase 1 — Gate 2 competitive pilot (2–4 weeks) **CURRENT**

**Profile:** `tight_spread`  
**Capital:** ~250 XRP, L1 10–15 XRP, L2/L3 off  
**Ops rules:** From `OPERATOR_MANUAL.md` + implementation plan

#### Week 1 — Setup

- [ ] Pull v1.4.4+, clear kill, restart engine (reset baselines)
- [ ] **Sync risk capital to live portfolio** in GUI
- [ ] Apply `tight_spread` preset; confirm `dynamic_min_edge_enabled`
- [ ] `toxic_fill_kill_enabled: false` (pause/off-book only)
- [ ] Session balance kill on (−0.35 XRP / 25 fills) unless consciously off
- [ ] Run `weekly_skim_report.py` baseline before changes

#### Weeks 2–4 — Run & measure

- [ ] Accumulate **≥100 fills** without profile thrashing
- [ ] Log every kill — classify false vs real
- [ ] Track weekly:

  - realized spread bps/fill  
  - toxic % (50-fill window)  
  - cancel/fill  
  - % cycles at_touch / near_touch (from decisions.jsonl)  
  - balance PnL  

#### Gate 2 pass criteria (from your plan)

- [ ] ≥100 fills `tight_spread`
- [ ] Toxic < 20% / 50 fills
- [ ] Realized spread bps reviewed weekly
- [ ] cancel/fill not rising vs Gate 1
- [ ] Inventory deviation > 12% rare

**If fail:** Step back to `safe`, fix feed/edge issues (Phase 2), do not widen into pickoff.

---

### Phase 2 — Tier 2.5 engineering (1–2 weeks dev, parallel with late Gate 2)

Priority order from your plan — **this is the competitive code sprint**:

| # | Deliverable | Acceptance test |
|---|-------------|-----------------|
| **6** | Fix `BookOffers` ask inversion in `xrpl_connector.py` | Fixture tests: no mid from ghost ask; spread-check pass rate up |
| **5b** | Hard gate: no `place_quote` when `market_edge_met` false | Unit test + decision log reason |
| **4** | `competitive_pilot` profile or GUI preset | Higher `min_touch_size_mult`, lower off-touch threshold vs `tight_spread` |
| **5** | Join-touch path when favorable + edge + toxic OK | `cancel_per_fill` down; visible L1 time up |
| **7** | Optional persist fill-quality across restart | Toxic gate not reset to 0 on every restart |
| **PnL** | Ledger price on all fills in CSV | `profit_xrp_equiv` non-zero on >80% of fills |

**Optional high-value:**

- Engine stop → prompt or auto `cancel_all_offers`
- Split `trading_engine` into cycle phases (enables faster iteration)

---

### Phase 3 — Gate 3 field skim (4+ weeks after Gate 2 pass)

**Only if Gate 2 metrics stable 2+ weeks.**

| Step | Action |
|------|--------|
| Size | L1 15 → 20 → 25 XRP in steps |
| Profile | `profit_mode` manual only on calm tight-book days |
| Capital | Do not scale toward 11k placeholder until metrics green |
| Ops | Weekly skim + bleed analysis mandatory |

**Gate 3 pass signal:** Growing **balance PnL** under `tight_spread` or `competitive_pilot` with toxic still < 20%.

---

### Phase 4 — Tier 3 institutional (when capital justifies)

| Item | Competitive benefit |
|------|---------------------|
| Real Avellaneda–Stoikov in `avellaneda_strategy.py` | Inventory-aware optimal spread |
| WebSocket book + tx subscription | Fresher touch, fewer stale-book cycles |
| Rolling 7-day edge tuner (capped, manual override) | Adapt without ML black box |
| Prometheus + alertmanager | Unattended degradation detection |
| Connector integration CI | Prevent RPC regression |

**Not required** to be “competitive” on 250 XRP if Gate 2 passes — required to **scale** and run **unattended**.

---

## 4. Competitive profile design (proposal)

Add **`competitive_pilot`** (code or preset) between `tight_spread` and `profit_mode`:

| Parameter | `safe` | `tight_spread` | `competitive_pilot` (proposed) |
|-----------|--------|----------------|--------------------------------|
| min_spread_floor_pct | 0.16 | ~0.10 | ~0.08 |
| toxic_no_touch_ratio | 0.20 | lower | 0.22 enter / 0.17 exit |
| min_touch_size_mult | 0.55 | 0.62 | **0.75** |
| max_touch_backoff_pct | 0.12 | 0.08 | **0.05** |
| off_touch default | early | moderate | **late** (only when hostile) |
| auto-switch target | never profit_mode | same | same |

**Rule:** `competitive_pilot` only selectable after Gate 2 pass or operator ack checkbox in GUI.

---

## 5. Competitive operating playbook (condensed)

1. **Scoreboard = wallet balance change**, not MTM alone.
2. **Never override spread-check FAIL** on mainnet.
3. **Restart engine after kill clear** — baselines matter.
4. **Stop engine ≠ flat book** — cancel offers explicitly if needed.
5. **Profile changes** — log in decisions; avoid mid-session thrash.
6. **Thin RLUSD nights** — expect toxic noise; don’t tune on 9 fills.
7. **Growing the bag** — weekly balance PnL ≥ 0 before size steps.

---

## 6. What NOT to do (common MM mistakes)

| Mistake | Why it fails on XRPL |
|---------|----------------------|
| Widen spreads after losses without toxic signal | Pays more pickoff |
| Max size on thin book | Adverse selection dominates |
| Chase inventory with aggressive touch | Bleeds on one-sided flow |
| Trust MTM when book crossed | False confidence (you fixed marks — stay disciplined) |
| Jump to `profit_mode` early | Designed for calm ideal books only |
| Scale capital before Gate 2 | Masks strategy bugs with size |

---

## 7. Success timeline (realistic)

| Milestone | ETA (indicative) | Dependency |
|-----------|------------------|------------|
| Gate 2 pass (`tight_spread`) | 2–4 weeks ops | Stable mainnet run |
| Tier 2.5 code shipped | 1–2 weeks dev | Parallel late Gate 2 |
| Gate 3 size steps | +4 weeks | Gate 2 stable 2 weeks |
| Tier 3 WebSocket + A-S | 2–3 months | Capital + ops bandwidth |
| “Competitive” vs other XRPL bots | Ongoing | Relative metrics, not absolute |

---

## 8. Summary: three things that make you competitive

1. **Time on touch when edge is real** — policy + join-touch + lower cancel/fill.  
2. **Honest economics** — ledger-priced fills, balance PnL, no bad-book phantom wins.  
3. **Disciplined gates** — toxic < 20%, inventory bounded, kills only for real reasons.

You already built **(3)** better than most hobby XRPL bots. **(1)** and **(2)** are Gate 2 + Tier 2.5. Tier 3 is how you **scale** competitiveness, not how you **prove** it.

---

## 9. Cross-references

| Doc | Location |
|-----|----------|
| Your implementation plan | `docs/IMPLEMENTATION_PLAN.md` |
| Policy conflict audit | `docs/AUDIT_REPORT.md` |
| Strategy / operator manuals | `docs/STRATEGY_MANUAL.md`, `docs/OPERATOR_MANUAL.md` |
| Grok full-stack audit | [01_FULL_STACK_CODE_AUDIT.md](01_FULL_STACK_CODE_AUDIT.md) |
| How it works + improvements | [02_HOW_IT_WORKS_AND_IMPROVEMENTS.md](02_HOW_IT_WORKS_AND_IMPROVEMENTS.md) |

---

*End of competitive MM roadmap.*