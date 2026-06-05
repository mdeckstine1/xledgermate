# Master roadmap — realistic metrics → competitive XRPL market maker

**Date:** 2026-06-05  
**Replaces as primary path:** informal targets in docs 03–04 that were optimistic or mis-measured  
**End goal:** A **competitive** XRP/RLUSD MM on XRPL — earns spread at the book, bounds adverse selection, runs with minimal operator rescue, scales capital only when metrics prove edge.

**Working capital reference:** ~250 XRP bot wallet, mainnet RLUSD book, v1.4.4+ on `tier-2-polish`.

---

## 1. What “competitive” means here (realistic, not CeFi fantasy)

| Myth | Reality on your stack |
|------|------------------------|
| “HFT microsecond quotes” | Ledger ~3–4s; your loop **12–20s** — competitive = **right price, stable queue, few cancels** |
| “Toxic < 10%” | Thin RLUSD + 30s markout → **20–30% toxic can coexist with profitable balance PnL** if capture bps > pickoff cost |
| “70% time on touch” on `safe` | That profile is **designed** to leave touch — not a failure, wrong profile |
| “100 fills in one weekend” | Thin book → **2–6 fills/hour** typical → 100 fills = **~20–50 engine-hours** cumulative |
| “MTM session PnL green” | Use **wallet balance Δ** when book is sane; MTM is secondary |
| “Avellaneda in the name” | Heuristic spreads until Tier 3 — judge **economics**, not model label |

### Competitive MM definition (operational)

You have a **competitive pilot** when, over a **rolling 2-week window** with stable `tight_spread` (or `data_pilot`):

1. **Wallet balance PnL (XRP equiv.) ≥ 0** after fees, with no unexplained bleed scripts flagging drift.  
2. **Spread economics positive:** capture bps **> 0** on **≥ 70% ledger-priced fills**.  
3. **Presence:** at least one open offer **≥ 45%** of cycles in **favorable/neutral** market assessment (not globally 70% on all hours).  
4. **Adverse selection managed:** toxic ratio **not worsening** week-over-week while (1) holds; absolute cap **≤ 32%** over 50 fills (not 20% as hard fail on RLUSD).  
5. **Execution discipline:** `cancel_per_fill` **flat or down** vs prior week; spread-check kills rare.  
6. **Inventory:** outside ±12% of target **< 10%** of cycles; no manual panic swaps required.

**Scale to field MM (Gate 4):** Above holds **4 consecutive weeks**, then L1 size steps and optional Tier 3 (WebSocket, A-S).

---

## 2. Metric audit — what to measure, what to ignore

### 2.1 Tier A — Primary scoreboard (decide go / no-go)

These directly answer: *Is the bot making money without blowing up?*

| Metric | How measured today | Validity | Realistic target (pilot) | Why it matters |
|--------|-------------------|----------|--------------------------|----------------|
| **Weekly balance PnL (XRP)** | Wallet before/after week + `portfolio_bleed_analysis.py` | ✅ High | **≥ 0 XRP** (stretch: ≥ +0.15/week on 250 XRP) | Ground truth; kills and MTM can lie |
| **Session balance PnL** | `session_pnl_balance_delta_xrp` in engine | ✅ High if book OK | Per session: **> −0.5 XRP** during learning; kill at **−0.85** after 45 fills | Stops bleed without ending 12-fill science runs |
| **Spread capture sum (XRP)** | `profit_xrp_equiv` in trades CSV | ⚠️ Medium | Positive week when fills ≥ 30 | Understates on balance-delta rows |
| **Capture bps vs volume** | `weekly_skim_report.py` | ⚠️ Medium until ledger fills dominate | **> 0 bps** week; stretch **≥ 3–8 bps** on RLUSD pilot | Comparable across size changes |
| **Negative capture fill %** | CSV count `profit_xrp_equiv < 0` | ✅ Medium | **< 15%** of fills (Gate 2); was ~6% on best 80-fill session | Pickoff frequency |

**Rule:** If Tier A is green and Tier B toxic is “high,” **tune policy**, don’t declare failure.

### 2.2 Tier B — Adverse selection (manage, don’t worship)

| Metric | Validity | Old target | **Revised realistic target** | Notes |
|--------|----------|------------|-------------------------------|-------|
| **Toxic ratio (cycle markout)** | ⚠️ Noisy until n≥25 | < 20% / 50 fills | **≤ 32%** over 50 fills **while Tier A green**; trend ↓ week-over-week | Your own Gate 1 doc: toxic bar misaligned on thin RLUSD |
| **Toxic @30s (GUI)** | ⚠️ Very noisy n<12 | < 20% | **Advisory only** until 12 fills; then compare to profile `toxic_refresh_pause_ratio` | Hides until 3 fills — don’t panic early |
| **Mean markout 30s %** | ✅ Useful | Negative mean bad | **> −0.05%** mean over 50 fills | Better than ratio for tuning threshold |
| **Toxic while at_touch** | ❌ Not split today | — | **Engineering:** log policy at fill time; target toxic_at_touch **< 40%** | Distinguishes bad quotes vs bad luck |

**Do not** enable `toxic_fill_kill_enabled` for Gate 2 — policy off-book is enough; kill on toxic causes the data-run death spiral.

### 2.3 Tier C — Market-making presence (competitive shape)

| Metric | Validity | Old target | **Revised target** | Notes |
|--------|----------|------------|---------------------|-------|
| **% cycles with ≥1 open offer** | ⚠️ Snapshot proxy in skim report | > 70% all hours | **≥ 45%** overall; **≥ 60%** when `market_condition ∈ {favorable, neutral}` | 70% global unrealistic on `safe` / hostile hours |
| **% cycles at_touch \| near_touch** | ❌ Not auto-aggregated | > 50% | **≥ 35%** favorable/neutral hours; parse `decisions.jsonl` | Competitive = touch when book pays |
| **Quote intents > 0** | ✅ In decision log | — | **≥ 50%** cycles when book trustworthy | “Barely MM” fix = profile + edge, not this % alone |
| **Fills per engine hour** | ✅ Derivable | — | **≥ 1.5/hour** cumulative (stretch 3/hour) | Depends on size; 12 XRP L1 on thin book |

### 2.4 Tier D — Execution quality

| Metric | Validity | Old target | **Revised target** | Notes |
|--------|----------|------------|---------------------|-------|
| **cancel_per_fill** | ✅ runtime_state | “lower is better” | **≤ 2.0** pilot; **week-over-week not increasing**; stretch **≤ 1.3** | Baseline ~1.66 on 80-fill session — beat that, not zero |
| **Spread validation pass rate** | ✅ decisions | ~100% | **≥ 85%** when book trustworthy; failures mostly `book_unreliable` | Fail kills only when book valid + 12 streak |
| **Invisible offer cancels** | ✅ | — | Stable or falling | Cleanup, not churn |
| **Cycle latency** | ✅ | Faster | `tight_spread` poll **15s**; `data_pilot` **12s** (future) | “Faster decisions” = poll + less off-book time |

### 2.5 Tier E — Safety (keep strict — non-negotiable)

| Metric | Realistic setting |
|--------|-------------------|
| Daily drawdown kill | **3.5%** on valid mid only — keep |
| False drawdown on bad book | **Must stay 0** post v1.4.4 |
| Session kill | **−0.85 XRP after 45 fills** (data); **−0.35 after 25** (guard only on `safe`) |
| Spread-fail kill | **12+ cycles**, never on `book_unreliable` |
| Secrets / main wallet | Bot account only — process, not metric |

### 2.6 Metrics to deprioritize until fixed

| Metric | Problem |
|--------|---------|
| **profit_xrp_equiv on balance-delta fills** | Often **0** → distorts bps and Gate scripts |
| **MTM session PnL hero** | Misleading when book crossed |
| **Gate pass on toxic < 20% with n=9** | Statistically meaningless |
| **Risk capital 11k vs 250 XRP** | Makes size metrics nonsense until synced |

**Engineering gate for trusting bps:** ≥ **70%** of session fills have `fill_source=ledger` or non-zero capture before using bps as **pass/fail**.

---

## 3. Revised deployment gates (realistic)

Progress only when **Tier A** criteria met; Tier B/C are tuning guides, not single-session religion.

```
Gate 0 ──► Gate 1 ──► Gate 2 ──► Gate 3 ──► Gate 4 (field)
(plumbing)  (survive)   (compete)   (skim)     (scale)
```

### Gate 0 — Plumbing ✅ (done)

- Engine, GUI, offers, fills, kills, v1.4.2–1.4.4 book guards.

### Gate 1 — Survive & measure truth ✅ (signed off, criteria relaxed)

**Purpose:** Prove the bot does not lie or suicide on bad data.

| Criterion | Old | **Revised pass** |
|-----------|-----|------------------|
| Uninterrupted fills | ≥40 one session | **≥40 cumulative** OR **≥25** in one session without false kill |
| Spread capture | > 0 | **≥ +0.2 XRP** cumulative on best-effort sessions |
| Toxic | < 25% | **Advisory** if balance PnL ≥ 0; log ratio, don’t fail Gate 1 on toxic alone |
| False drawdown kill | 0 | **0** — mandatory |
| Balance PnL | ≥ 0 one session | **Weekly bleed ≤ 0.5 XRP** across restarts (script) |

### Gate 2 — Competitive pilot (current, 3–6 weeks)

**Profile:** `tight_spread` (later `data_pilot`) · **inventory_mode:** `market_make` · **L1:** 10–15 XRP  

**Minimum data before judging:** **60 fills** same config, **≥ 20 engine-hours**, book trustworthy **≥ 80%** of cycles.

| # | Criterion | Pass (all required) | Stretch |
|---|-----------|---------------------|---------|
| 2A | Cumulative fills | **≥ 60** | ≥ 100 |
| 2B | Weekly balance PnL | **≥ 0 XRP** for the week | ≥ +0.15 XRP |
| 2C | Capture bps (ledger-weighted) | **> 0** | ≥ 5 bps avg |
| 2D | Negative capture fills | **≤ 18%** | ≤ 12% |
| 2E | Toxic ratio (50-fill window) | **≤ 32%** OR falling vs prior 50 | ≤ 25% |
| 2F | cancel_per_fill | **Not rising** vs Gate 1 baseline; **≤ 2.0** | ≤ 1.4 |
| 2G | Presence (favorable/neutral) | Offers **≥ 45%** cycles | ≥ 55% |
| 2H | Inventory | **> 12%** deviation **< 15%** of cycles | < 8% |
| 2I | Kill events | Only **balance/drawdown/real spread** — document each | ≤ 1 unexplained/week |

**Fail Gate 2 if:** 2B negative two weeks running **or** 2A not met in 6 weeks **or** kills dominated by false spread streak (book bug).

**Do not fail Gate 2 solely for:** toxic 22–30% with positive 2B; low fill rate on hostile days; 0 intents during crossed book (defense correct).

### Gate 3 — Skim & size (after Gate 2, +4 weeks)

| Criterion | Pass |
|-----------|------|
| Gate 2 pass held **2 consecutive weeks** | Required |
| L1 stepped **12 → 15 → 18 XRP** one step per 2 weeks | No hero size |
| Weekly balance PnL | **≥ 0** all 4 weeks |
| Cumulative fills | **≥ 250** under Gate 2 config |
| `profit_mode` | **Manual only**, ≤ 2 sessions total, logged |

### Gate 4 — Field competitive (scale capital)

| Criterion | Pass |
|-----------|------|
| Gate 3 **4 weeks** | Required |
| Risk capital synced to wallet | Always |
| Tier 2.5 code shipped | BookOffers fix, edge gate, ledger PnL |
| Optional Tier 3 | WebSocket + A-S when capital **> ~1,000 XRP** equiv. |

**Then:** Scale risk capital in steps (250 → 500 → …), never jump to 11k placeholder without Gate 4 history.

---

## 4. Profile strategy mapped to metrics (faster + competitive)

Profiles are the **control surface**. Each maps to metric tiers:

| Profile | Use when | Optimizes | Hurts if used for |
|---------|----------|-----------|-------------------|
| **`safe`** | Hostile book, inventory crisis, overnight guard | Tier E safety | Gate 2 data, competitive presence |
| **`tight_spread`** | Gate 2 pilot, calm/neutral hours | Tier A capture, Tier C presence | Extreme vol without switch |
| **`thin_liquidity`** | Wide book, low depth | Tier B toxic (fewer fills) | Touch competition |
| **`high_volatility`** | Vol spike | Tier E | Fill count |
| **`data_pilot`** *(proposed)* | Long metric runs | Tier A sample size, Tier D stability | Max skim |
| **`profit_mode`** | Manual calm day only | Max Tier C | Learning / thin toxic periods |

### Gate 2 config bundle (realistic)

```yaml
active_profile: tight_spread
inventory_mode: market_make
dynamic_min_edge_enabled: true
order_levels: 1
order_sizes: [12.0, 0.0, 0.0]

# Kills: safety without aborting at fill #25
session_balance_loss_kill_xrp: 0.85
session_balance_loss_kill_min_fills: 45
spread_failure_kill_cycles: 12
toxic_fill_kill_enabled: false
max_daily_drawdown_percent: 3.5
```

GUI: **Apply profile** → **Sync risk capital** → **Restart engine**.

### Policy success = metric movement

| If ticker shows… | Expect metric… | Action |
|----------------|----------------|--------|
| `off-book (toxic)` most cycles | Low presence, toxic high | Widen toxic enter (profile) or reduce size — **don’t** enable toxic kill |
| `at_touch` in favorable | Fills/hour up, capture up | Stay course |
| `spread check FAILED` | Spread-fail streak risk | Fix book or widen base_spread 1 tick |
| `market edge not met` | Low fills, OK toxic | Tier 2.5 edge gate (code) — don’t force touch |

---

## 5. Phased roadmap (12 weeks to competitive pilot pass)

### Phase 1 — Measurement honesty (Week 1)

**Goal:** Trust Tier A before tuning toxicity.

- [ ] Run `tight_spread` only; kills per §4 bundle  
- [ ] After each session: `weekly_skim_report.py`, `analyze_session.py`, `portfolio_bleed_analysis.py`  
- [ ] Log: % fills with `fill_source=ledger` in CSV  
- [ ] **Pass Phase 1:** ≥ 25 fills, balance session PnL **> −0.5**, zero false drawdown kills  

**Do not:** Change profile mid-session; judge toxic before 12 fills.

### Phase 2 — Presence & MM shape (Weeks 2–3)

**Goal:** Tier C — actually on the book when market pays.

- [ ] Parse `decisions.jsonl` for `at_touch|near_touch` % on favorable/neutral  
- [ ] Target: **≥ 35%** touch/near on those hours  
- [ ] If < 25%: confirm `market_make`, dynamic edge on, not stuck in rebalance  
- [ ] **Pass Phase 2:** ≥ 45% cycles with offers in favorable/neutral window  

### Phase 3 — Economics (Weeks 4–6) = Gate 2

**Goal:** Tier A green over a week with ≥ 60 fills.

- [ ] Cumulative **60+ fills**, same config  
- [ ] Weekly balance PnL **≥ 0**  
- [ ] Capture bps **> 0** (if ledger % low, fix T5 before failing)  
- [ ] Toxic **≤ 32%** on last 50 OR down vs first 50 of phase  
- [ ] cancel_per_fill **≤ 2.0** and not up vs ~1.66 baseline  

**Pass Phase 3 = Gate 2 pass.**

### Phase 4 — Engineering enablers (parallel Weeks 2–6)

| Priority | Deliverable | Unlocks metric |
|----------|-------------|----------------|
| P0 | `data_pilot` profile | Longer runs → valid Tier B |
| P0 | Ledger-first fill logging | Valid capture bps |
| P1 | `market_edge_met` live block | Fewer toxic-negative capture fills |
| P1 | BookOffers ask fix | Spread pass rate, trustworthy mid |
| P2 | Policy-at-fill in CSV | toxic_at_touch vs off_book |
| P3 | WebSocket book | Tier D latency (Gate 4) |

### Phase 5 — Gate 3 & field (Weeks 7–12)

- Size steps, 4-week green weekly balance PnL, 250+ fills.  
- Only then: `profit_mode` experiments, capital scale, A-S / WebSocket.

---

## 6. Weekly review template (copy to `logs/review_YYYY-MM-DD.md`)

```markdown
## Week of YYYY-MM-DD
Profile: tight_spread | Engine hours: __ | Fills: __

### Tier A (decide)
- Wallet balance Δ (XRP): __
- Spread capture sum: __
- Capture bps (ledger fills only): __
- Negative capture %: __

### Tier B (tune)
- Toxic 50-fill window: __% (prior week: __%)
- Mean markout 30s: __%

### Tier C (compete)
- % offers visible (favorable/neutral): __%
- at_touch|near_touch % (parsed): __%
- Fills/hour: __

### Tier D (execute)
- cancel_per_fill: __ (prior: __)
- Spread fail kills: __

### Tier E (safety)
- Kill reasons: __
- False book kills: __

### Decision
- [ ] Continue Gate 2  [ ] Tune profile  [ ] Step down safe  [ ] Engineering ticket: __
```

---

## 7. How this fixes your specific pain

| Your symptom | Wrong conclusion | **Realistic read** | Roadmap action |
|--------------|------------------|--------------------|----------------|
| Barely MM | “Bot broken” | **`safe`/rebalance/off-book`** by design | `tight_spread` + market_make; judge Tier C on favorable hours only |
| Toxic dominates | “Strategy failed” | Toxic **drives defense**, kills data runs | Toxic ≤32% with positive balance; don’t toxic-kill; tune enter/exit |
| Kill stops runs | “Remove kills” | **Session −0.35 @ 25 fills** too tight | §4 kill bundle; weekly balance as pass, not every session |
| Can’t get 100 fills | “Not trying” | **100 fills ≈ 20–50 hours** on thin book | Gate 2 pass at **60**; 100 = stretch |
| Want faster decisions | “Need HFT” | Need **less off-book**, shorter poll | `data_pilot` 12s + edge gate + join-touch when favorable |

---

## 8. Success statement (end state)

You have a **competitive MM bot** when:

> Over four weeks at ~250 XRP, `tight_spread` (or successor) keeps **weekly wallet PnL ≥ 0**, **positive ledger-weighted capture bps**, **stable or improving cancel/fill**, **material presence on favorable books**, and **toxicity stable or falling without** turning off the book — and you can **step size or capital** without changing code.

That is achievable on XRPL RLUSD with what you have **after Gate 2 config + Tier 2.5 fixes**. It is not achievable by demanding CeFi toxic ratios on `safe` or 70% global touch time.

---

## 9. Document map

| File | Role |
|------|------|
| **This file (05)** | **Canonical** metrics + gates + 12-week plan |
| [04_ROADMAP_FASTER_DECISIONS_AND_CLEAN_DATA_RUNS.md](04_ROADMAP_FASTER_DECISIONS_AND_CLEAN_DATA_RUNS.md) | Kill/profile tuning detail (aligned to 05) |
| [03_COMPETITIVE_MARKET_MAKER_ROADMAP.md](03_COMPETITIVE_MARKET_MAKER_ROADMAP.md) | Original competitive framing (see 05 for revised numbers) |
| [01_FULL_STACK_CODE_AUDIT.md](01_FULL_STACK_CODE_AUDIT.md) | Code risks |
| `docs/IMPLEMENTATION_PLAN.md` | Update Gate 2 thresholds to match 05 when you merge |
| [../vps/06_TWO_WEEK_DEDICATED_HOST_SETUP.md](../vps/06_TWO_WEEK_DEDICATED_HOST_SETUP.md) | Dedicated PC / VPS for 2-week runs |

---

*Suggested next code change: update `scripts/weekly_skim_report.py` Gate lines to match §3 Gate 2 table (60 fills, toxic 32%, balance week).*