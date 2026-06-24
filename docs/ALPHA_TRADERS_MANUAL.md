# xLedgerMate Alpha — Trader’s Manual

**The no-bullshit guide for people who want to grow their bag.**

Written for operators who have watched too many green candles turn red.

This bot is not your grandma’s savings account. It is a weapon. You point it, you tune it, and you live with the results.

---

## What this bot actually does

xLedgerMate Alpha is a **limit-order bag-growth bot** on XRPL (XRP / RLUSD).

- It **does not** market-buy or market-sell.
- It **does not** have a manual “Buy now” button.
- It places **limit bids** when inventory is RLUSD-heavy and gates pass.
- When a buy fills, it automatically places **take-profit + stop-loss** sells (a bracket).
- It can **trail** those exits as price moves in your favor.
- After a TP or SL exit, a **re-entry gate** can block impatient reloads.

**Core philosophy:** We are not here to “balance” for balance’s sake. We deploy RLUSD when the book is weak and we are under our XRP target. We take profit on strength. We try to end up with **more XRP** — not just more activity.

The bot has **eyes** (technical analysis) and **hands** (limit orders + brackets). **You** are the brain that decides how aggressive those hands should be — via the HUD at `:8765`.

For install, VPS, dry-run cutover, and the **Config** tab (credentials + withdraw), see [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) and [`ALPHA_LIVE_RUN_MANUAL.md`](ALPHA_LIVE_RUN_MANUAL.md). This manual is about **how it feels to run it**.

---

## The order lifecycle (read this once)

```
1. Engine cycle runs (every N seconds)
2. Decision: HOLD | PLACE_BID | PLACE_ASK
3. If PLACE_BID → limit buy below mid → "pending buy" bracket
4. Buy fills → bot places TP on book; SL on book **or deferred** (SL↯) until price nears stop → "active bracket"
5. TP fills → profit (RLUSD back) → re-entry gate may block new buys
6. SL fills → loss capped → longer re-entry wait + stronger TA required
```

**Pending buy** = RLUSD committed, waiting for fill.  
**Active bracket** = you already own the XRP; TP is on the book; SL is on the book or **deferred off-ledger** (see **SL↯**).  
Cancelling a pending buy pulls the bid. Cancelling an active bracket cancels TP/SL only — **you keep the XRP**.

---

## Your dashboard — what to watch

| Where | What it tells you |
|--------|-------------------|
| **Ticker / sidebar** | Mode (LIVE/dry), mid, portfolio, inventory %, drawdown, session P&L |
| **Quote age** | How fresh the L1 book patch is (sidebar). Stale >25s = waiting for next book sample |
| **Chart** | Candle history (lags) + **live** bid/ask/mid lines (1s HUD poll). Candles right-aligned |
| **Market Conditions** | Spread, **bid/ask depth ±1% of mid**, max buy size, best bid/ask |
| **Decision** | Last action + **reason** — this is your best friend when confused |
| **Brackets tab** | Open positions: pending buys vs active brackets; size, RLUSD, TP/SL, **Trail** flags |
| **Open Offers** | Raw ledger orders (✕ cancel, ✎ reprice) |
| **Reports** | Cycle status text + path to monthly **tax CSV** (`logs/trades_YYYY-MM.csv`) |
| **Config** | Credentials, network, **Send / withdraw**, transfer history |

If the bot is “doing nothing,” the **Decision reason** almost always explains why.

### Data speed — what updates how fast

| Layer | Typical interval (your box) | What it drives |
|-------|----------------------------|----------------|
| **HUD poll** | **1s** | Ticker mid, live chart lines, sidebar |
| **Book sample** (`alpha_price_sample_interval_seconds`, default 15s) | ~**15s** between full engine cycles | Mid/quote age, chart candle history |
| **Engine cycle** (`alpha_cycle_interval_seconds`, e.g. 34s) | **34s** | Decision, liquidity depth, TA, place/cancel orders |
| **Chart candle** | `bucket_samples × sample_seconds` (e.g. 5×15s = **75s**) | Each candle body on the chart |

The **chart candles lag** the live mid line on purpose — candles are built from saved samples, while the cyan **mid** / green **bid** / red **ask** lines use the latest book patch every second.

**Liquidity on the ledger:** Market Conditions shows **ask depth** and **bid depth** within **±1% of mid** (XRP available to trade through that band), plus **recommended max buy** sized from that depth. This is DEX book liquidity, not “will someone sell into my bid.” Depth refreshes on each **engine cycle**, not every HUD poll.

### Why we place bids but nobody sells (no fill)

Limit buys are **passive**. You join the bid side of the book and wait for a **seller** (or ask liquidity) to trade down to your price.

| You see | Meaning |
|---------|---------|
| Mid **above** your entry | Normal — you bid below mid |
| Best **ask above** your entry | **No fill yet** — sellers are still asking higher |
| Large **ask depth** (e.g. 85k XRP) | Liquidity exists **above** you, not at your bid |
| Mid crosses your entry | **Still no fill** — mid ≠ trade price; need **ask ≤ your bid** |

**To fill more often:** lower `buy_limit_offset_pct` (bid closer to ask), or wait for a dip that trades through your level. The spread gap in bps on best bid vs best ask is the minimum move needed for interaction.

---

## Risk & Entry — your main weapons

All knobs live on the **Live** tab. Hit **Apply** after changes — they take effect on the next engine cycle (no restart).

### `target_xrp_pct`

How much of your portfolio the bot *wants* in XRP.

| Range | Vibe |
|-------|------|
| **40–55%** | Defensive. Lots of RLUSD on the sidelines. Safer in crashes, slower bag growth. |
| **60–70%** | Balanced aggression. Solid starting point while learning. |
| **75–90%+** | Full send. Hungry for XRP. Where real bag growth lives — and where drawdowns bite harder. |

**Default in code:** 75%. You are RLUSD-heavy when **actual XRP % is below target**.

---

### `weakness_deviation`

How far **below** target XRP the bot must be before it even *considers* buying.

| Range | Vibe |
|-------|------|
| **0.02–0.03** | Jumpy. Buys on small dips. Good in chop; dangerous in downtrends. |
| **0.04–0.05** | Reasonable middle ground. |
| **0.08+** | Patient. Waits for real blood before deploying RLUSD. |

Example: target 80%, weakness 0.05 → bot wants to buy when you are at ~75% XRP or lower.

---

### `risk_per_trade_pct`

Max size of **one bracket** as a % of portfolio (also capped by book depth and risk capital).

| Range | Vibe |
|-------|------|
| **0.2–0.3%** | Training wheels. |
| **0.5%** | Normal (config.yaml default). |
| **2–3%** | Active bag deploy on a ~500+ XRP book. |
| **4–5%** | Large clips — watch drawdown and leg cap. |

**How size is computed (each PLACE_BID):**

```text
desired   = alpha_base_order_size_xrp × (1 + |inventory deviation| × 2)
risk_cap  = portfolio_xrp_equiv × (risk_per_trade_pct / 100)
leg_cap   = risk_capital_xrp × max_leg_size_pct_of_capital   ← config.yaml only
size      = min(desired, risk_cap, leg_cap, ask_depth, inventory cap)
```

The HUD shows **RLUSD notional** on offers as roughly `size_xrp × entry_price`. Engine logs show `size=` in **XRP**.

Check **Market Conditions → Max buy** after **Apply** — that number is the **binding cap right now** (same formula the decision engine uses).

**Example @ portfolio ≈ 584 XRP, mid ≈ 1.103** (your live box, 2026-06-23):

| `risk_per_trade_pct` | Size (XRP) | ≈ RLUSD @ 1.103 |
|----------------------|------------|-----------------|
| **2.0%** | ~11.7 | **~12.9** ← what you saw before raising risk |
| **3.0%** (current HUD) | ~17.5 | **~19.3** |
| **4.0%** | ~23.3 | **~25.7** |
| **5.0%** | ~29.2 | **~32.2** |
| **Leg cap** (`251 XRP × 12%`) | ~30.1 | ~33.2 ← ceiling from `config.yaml` |

To go bigger: raise **`risk_per_trade_pct`** on Live → Apply. **`alpha_base_order_size_xrp`** (config, default 50) only matters once risk cap exceeds desired — at your portfolio it is **not** the limiter until risk ≈ 5%+.

---

### `min_edge_threshold_pct` ⚠️

Minimum **edge** (spread capture vs mid) required before placing a bid or ask.

| Range | Vibe |
|-------|------|
| **Low (0.05–0.08)** | Takes smaller edges. Fills more often. |
| **Middle (0.10–0.15)** | Balanced sniper. |
| **High (0.3+)** | Picky. Sits on hands until prices are juicy. |

**Critical rule:** Your edge on a buy is roughly equal to `buy_limit_offset_pct`.  
If **offset < min edge**, the bot will **never buy**. You will see:

```text
HOLD — edge 0.050% < min 0.500%
```

That is not a bug. You told it to bid too close to mid while demanding too much edge. **Fix one or the other.**

| offset | min edge | Result |
|--------|----------|--------|
| 0.15 | 0.08 | ✅ Works (default-ish) |
| 0.50 | 0.50 | ✅ Works |
| 0.05 | 0.50 | ❌ Stuck on HOLD forever |

**Coupling:** Lowering `buy_limit_offset_pct` to chase price → lower `min_edge_threshold_pct` to match. Set `stale_pending_buy_max_drift_pct` ≈ offset. See [Knob coupling](#knob-coupling--change-x-change-y).

---

### `buy_limit_offset_pct` / `sell_limit_offset_pct`

How far below mid (buy) or above mid (sell) the bot places limits.

**Higher = patient sniper.** Deeper bids, better average entry, slower fills.  
**Lower = eager.** Near mid, faster fills, worse average price.

HUD range is roughly **0.05% – 1.0%** per side. This is *not* “5% below market” unless you type a large number in the number box — and the slider may cap you.

**Formula:** `target bid ≈ mid × (1 − buy_limit_offset_pct / 100)` — this is where **new** bids land after a stale cancel, not where old resting bids move to.

---

### `max_pending_buys` / `max_pending_sells`

How many open orders of each type at once.

- **1** = conservative, one shot at a time.  
- **3–5** = ladders multiple dips (more RLUSD deployed, more to manage).

### `stale_pending_buy_enabled` / `stale_pending_buy_max_drift_pct`

Each engine cycle, the bot can **auto-cancel resting buy bids** that no longer match where it would place a new entry (mid moved, or your `buy_limit_offset_pct` changed).

**Important — limit bids vs mid**

Pending buys are **passive limit orders**. They fill when the **best ask** trades down to your bid price — **not** when mid crosses your entry. Seeing mid below your entry on the HUD does not mean a fill should have happened.

**How it decides “stale”**

1. Compute **target entry** = `mid × (1 − buy_limit_offset_pct / 100)`  
2. For each **pending buy** bracket, evaluate (any match → cancel on next cycle):

| Rule | Meaning |
|------|---------|
| **`entry_drift`** | `|entry − target| / mid × 100` **>** `stale_pending_buy_max_drift_pct` |
| **`mid_passed_entry`** | Mid rallied above bid without fill by more than max drift |
| **`entry_above_mid`** | Bid is above mid (off-policy — new bids are always below mid) |
| **`excess_pending_buy`** | More pending buys than `max_pending_buys` — farthest from target pruned first |
| **`age`** | Optional: `alpha_stale_pending_buy_max_age_seconds` in `config.yaml` or via operator overrides (e.g. **1800** = 30 min max rest) |

Default **`stale_pending_buy_max_drift_pct` = 0.15%** in code — but see **`mid_passed_entry` trap** below before matching drift to offset.

**`mid_passed_entry` trap (why entries “switch” every cycle)**

A new bid is placed **`buy_limit_offset_pct` below mid** — so at rest, mid is already **~offset% above your entry**. The **`mid_passed_entry`** rule cancels when `(mid − entry) / mid × 100` **>** `stale_pending_buy_max_drift_pct`.

If **drift ≈ offset** (e.g. both **0.12%**), the bid is **stale almost immediately** — any spread tick or mid uptick triggers cancel → replace on the next cycle (~20–34s). Engine logs look like:

```text
stale_pending_buy_cancelled | … | mid_passed_entry=0.130%>0.12%
```

**To make entries stick:** set **`stale_pending_buy_max_drift_pct` wider than offset + typical spread**, e.g. offset **0.12%** + spread **~0.10%** → drift **0.35%** (not 0.12–0.20%). See [Scenario G](#scenario-g--entry-price-keeps-moving-cancelreplace-loop).

**Cancel speed**

Each cancel is one **XRPL ledger transaction**. The engine typically processes **one stale cancel per cycle** (`cycle_interval_seconds`). Clearing 20 bids can take **several minutes**, not seconds. Watch engine logs for `stale_pending_buy_cancelled` or `excess_pending_buy_cancelled`.

**Example — clearly stale**

- Mid **1.10**, offset **0.05%** → target ≈ **1.099**  
- A bid still at **1.04** → drift ≈ **5.5%** → **cancelled**

**Example — ladder stuck (common)**

- Mid **1.103**, offset **0.35%** → target ≈ **1.099**  
- 20 bids at **1.098–1.100**, **`max_drift` = 0.5%** → drift **0.15–0.25%** → **kept** (under 0.5%)  
- **`max_pending_buys` = 20** → engine HOLDs with slots full  
- **Fix:** set **`stale_pending_buy_max_drift_pct` → 0.15** (or match offset), lower **`max_pending_buys`**, then **Apply**

**Don’t confuse Brackets history with live pending**

`logs/alpha_brackets.json` lists old entries from prior sessions. Check the HUD **Brackets** tab **State** column: only rows marked **`pending buy`** count toward the cap.

**Tuning**

| Goal | Action |
|------|--------|
| **Stick longer** (fewer cancel/replace) | Raise `stale_pending_buy_max_drift_pct` to **offset + spread + ~0.10%** (e.g. offset 0.12 → drift **0.35**) |
| Chase market (repricing) | Keep drift **≈ offset** — expect frequent `mid_passed_entry` cancels |
| Prune bids that drifted far | Lower `stale_pending_buy_max_drift_pct` (e.g. **0.15%**) |
| Limit ladder size | Lower `max_pending_buys` to **1** (5 slots + fast cycles = churn) |
| Time-out old bids | Set `alpha_stale_pending_buy_max_age_seconds` to **0** (off) or **3600+** in overrides/config |
| Turn off auto-prune | Uncheck `stale_pending_buy_enabled` |
| Force-cancel one bid | Brackets tab **✕** on that row |
| Nuclear option | **Cancel all** — also kills active TP/SL (you keep XRP) |

Watch **Activity** or engine logs for `stale_pending_buy_cancelled` after a cycle.

**SKYNET / Grok** (manual Ask, **Agent Smith**, or Full SKYNET) receives a **`pending_buy_stale`** block in context: target entry, per-bid `would_cancel` / `reason`, `over_cap_count`, and tuning notes. Use the SKYNET quick prompt **“Stale bid ladder”** or ask why bids are not canceling.

**Coupling:** See [Knob coupling](#knob-coupling--change-x-change-y) — when you change offset, also align `min_edge`, `stale_max_drift`, and often `max_pending_buys`.

---

### `deferred_sl_enabled` / `deferred_sl_arm_buffer_pct` ⚠️ (XRPL stop-loss)

**Where:** Live → **Risk & entry** (not Structure & trailing).

After a buy fills, the bot places **take-profit** above market (safe — rests on the book) and a **stop-loss** below entry. On XRPL, a **limit sell below the current best bid crosses the book and fills immediately** — it is not a resting stop. Without deferral, brackets can “stop out” within seconds at ~breakeven even though price never dipped to your stop target.

| Knob | Default | What it does |
|------|---------|--------------|
| **`deferred_sl_enabled`** | **On** | Keep SL **off the ledger** while best bid is above the stop price. Monitor mid each cycle; place SL only when price approaches the stop. |
| **`deferred_sl_arm_buffer_pct`** | **0%** | How early to place SL on-ledger. **0** = arm when mid **≤ stop target** (or bid has dropped enough to rest safely). **> 0** = arm when mid is still slightly **above** stop, within this % buffer. |

**While deferred:** Brackets tab shows **`SL↯`** in State — stop is tracked in software, not as an open ledger offer. **TP** is still on the book.

**Engine logs:**

```text
deferred_sl_hold  | sl=1.091000 | reason=best_bid_above_stop   ← after buy fill
deferred_sl_arm   | sl=1.091000 | mid=1.091200 | arm_at=1.091000  ← SL placed on book
bracket_place_sl  | reason=deferred_sl_arm | immediate=False
```

**`deferred_sl_arm_buffer_pct` — what different values do**

Stop target = `entry × (1 − initial_stop_loss_pct)`. Example: entry **1.108**, SL **1.5%** → stop **1.091**, mid **1.111** after fill.

| Buffer | Arm when mid ≤ | Effect |
|--------|----------------|--------|
| **0%** (default) | **1.091** exactly | SL hits the ledger only when price has actually reached the stop zone. Most faithful to your stop distance. |
| **0.10%** | **~1.092** | Places SL one tick early — slightly faster exit if price is falling through the stop; tiny extra gap vs buffer 0. |
| **0.25%** | **~1.094** | Arms while price is still **~1.5% above** the raw stop — more protection in fast drops (SL on book before the wick), but you give up a bit more room on normal noise. |
| **0.50%+** | **~1.096+** | Aggressive early arm — bracket behaves closer to a tight trailing stop; use only if you accept exiting sooner on pullbacks. |

Formula: `arm_at = stop_price × (1 + buffer_pct / 100)`.

**Also arms** when best bid has already dropped to the stop (safe to rest on book) even if mid has not crossed yet.

**Turn off deferral:** Uncheck **`deferred_sl_enabled`** → legacy behavior (SL placed immediately after fill). Only do this if you understand instant XRPL exits when SL < bid.

**Coupling:** **`initial_stop_loss_pct`** (Structure & trailing) sets **how far** the stop is; deferred SL sets **when** it goes on-ledger. Widen **`initial_stop_loss_pct`** for a wider stop target; adjust **`deferred_sl_arm_buffer_pct`** for how eagerly the bot posts that stop before price gets there.

**Related:** Trailing SL **updates** (`sl_trail`) always attempt a ledger place; only the **first** deferred SL below market uses the bid-above-stop hold.

---

### `cycle_interval_seconds`

How often the engine wakes up (5–60s).

- **Lower** = faster reactions, more RPC load.  
- **Higher** = calmer, cheaper, slower to react.

---

## Technical Analysis panel

TA produces **buy** and **sell** scores from RSI, Stochastic, Bollinger, engulfing patterns, etc.

| Knob | What it does |
|------|----------------|
| **`ta_enabled`** | Master switch. Off = scores display but do not block trades. |
| **`ta_weight`** | 0 = advisory only. 1 = full gate at `min_buy_score` / `min_sell_score`. |
| **`min_buy_score`** | Minimum buy score to allow PLACE_BID (scaled by weight). |
| **`min_sell_score`** | Minimum sell score for strength sells. |

**Warm-up:** Early on you may see `ta_warming_up` — not enough price history yet. Normal. → [Scenario Q](#scenario-q--ta_warming_up--insufficient-history)

**Blocked in chop:** `ta_buy_blocked` / bearish bias with RLUSD-heavy inventory → [Scenario J](#scenario-j--ta-blocking-buys-in-chop)

---

## Structure & Trailing — protect the bag you just bought

### `bracket_trailing_enabled`

After a buy fills, the bot can **ratchet TP and SL higher** as price moves in your favor.

**On:** Buy at 1.00, SL 0.985, TP 1.03. Price hits 1.05 → SL trails up toward 1.01, TP can move too. Locks in progress.  
**Off:** Fixed TP/SL. Simpler. Gives back more on reversals.

#### When to enable trailing (after deferred SL is trusted)

Use **off** during initial soak when you are proving **entry + stop** behavior (instant SL bleed, deferred SL not arming). Turn **on** once:

| Gate | Why |
|------|-----|
| **`deferred_sl_enabled` on** and **`deferred_sl_arm`** in logs | Stops are not crossing the book on entry |
| **No mass instant `sl_filled` at breakeven** right after buys | Exit path is sane |
| **Rally / consolidation break** with bags **at or above entry** | Trailing only helps when `mid ≥ entry` (**BE**) |
| You accept **breakeven stops** on pullbacks in chop | Tighter `trailing_step_pct` → more whipsaw |

**Does not help underwater bags** — entries above current mid stay on fixed SL until price recovers past entry.

**Works with deferred SL:** initial SL stays **SL↯** until arm; once price passes **BE**, trailing **places** the ratcheted stop on-ledger (resting or immediate fill) so a reversal **executes** — trailing updates are not blocked by the bid-above-stop deferral used for first placement below market.

**Rising market / post-consolidation preset (Structure & trailing → Apply):**

```text
bracket_trailing_enabled   = on
trailing_step_pct          = 1.5     # 2.0 if BE stops feel too twitchy in chop
alpha_breakout_pct         = 0.02
alpha_structure_lookback   = 20
initial_stop_loss_pct      = 0.02    # keep — pairs with deferred SL
```

Keep **`deferred_sl_enabled` on** (Risk & entry). Watch Brackets **Trail** column for **BE** (SL trail armed) and **BO** (TP trail armed after breakout).

**Turn off again if:** `sl_filled` clusters right after `trailing_sl_update`, or you re-enter trust phase after an SL streak.

### `trailing_step_pct`

How much favorable move before the trail steps again.

| Range | Vibe |
|-------|------|
| **0.5–1.0%** | Tight. Great trends; easy whipsaw. |
| **1.5%** | Balanced default territory. |
| **3%+** | Loose. Room to breathe; give back more on pullbacks. |

### `breakout_pct`

How far past recent structure high/low counts as a breakout (feeds trailing logic and the **BO** flag on active brackets — see [Brackets tab: BE and BO](#brackets-tab-be-and-bo-trail-column)).

### `structure_lookback`

How many recent mid samples define “structure” (trend / swing levels).

| Range | Vibe |
|-------|------|
| **~10** | Short-term, twitchy. |
| **~20** | Balanced. |
| **50+** | Big picture, ignores noise. |

### `initial_stop_loss_pct`

Stop distance below entry — sets the **target** stop price (`entry × (1 − pct)`).

| Range | Vibe |
|-------|------|
| **0.8–1.0%** | Tight. Small losses if the stop actually triggers at that price. |
| **1.5%** | Reasonable. |
| **3%+** | Wide. Survives noise; bigger loss if wrong. |

**XRPL note:** A stop **below** the current bid is a marketable sell if placed on-ledger immediately. With **`deferred_sl_enabled`** on (Risk & entry), the bot holds SL off-book until price nears this target — so **`initial_stop_loss_pct`** defines distance, not instant exit. See [deferred SL](#deferred_sl_enabled--deferred_sl_arm_buffer_pct--xrpl-stop-loss).

### `take_profit_pct` / `take_profit_rr`

- **`take_profit_pct`** — fixed TP % above entry when RR is off.  
- **`take_profit_rr`** — TP distance = SL distance × RR (preferred when > 0).

| RR | Vibe |
|----|------|
| **1.5** | Conservative. |
| **2.0–3.0** | Standard. |
| **4.0+** | Aggressive — needs real trends to pay off. |

### Brackets tab: **BE** and **BO** (Trail column)

On **active** brackets only (after the buy has filled), the HUD shows short tags in **State** and spelled-out labels in **Trail**:

| Tag | Full name (Trail column) | Meaning |
|-----|--------------------------|---------|
| **BE** | **Breakeven** | Price moved favorably enough that **stop-loss trailing is armed** — the SL can ratchet up as price rises, locking in progress. |
| **BO** | **Breakout** | Structure confirmed a **breakout** — **take-profit trailing is armed** — the TP can ratchet up in a strong trend. |

**Important:**

- **BE** and **BO** are **trailing milestones**, not separate orders. They tell you which exit leg is allowed to trail.
- They only matter when **`bracket_trailing_enabled`** is on (Live → Structure & trailing).
- **Pending buys** never show BE/BO — nothing has filled yet.
- Hover the Trail column labels in the HUD for the same tooltips.

**Example:** Buy fills at 1.00. Price reaches ~1.015 → **BE** appears → SL may move up from 0.985 toward breakeven. Price breaks structure → **BO** appears → TP may trail above the original 1.03 target.

---

## Re-entry after exit — the “don’t be stupid” panel

After you **sell** (TP or SL), the bot can forbid immediate re-buys. This protects the spread: *sell high → wait → buy lower*.

### `reentry_enabled`

On = respect all cooldown / dip / stabilization rules.  
Off = can reload immediately (more aggressive, more knife-catching risk).

### After take-profit (TP)

| Knob | Purpose |
|------|---------|
| **`tp_cooldown_cycles`** | Hard wait (engine cycles) after TP. **Cannot be overridden** by inventory or TA. |
| **`tp_cooldown_minutes`** | Optional time gate (0 = cycles only). |
| **`tp_dip_pct`** | After cooldown, mid must dip X% below exit price before buy. |
| **`tp_min_ta_score`** | TA buy score required for reload. |

**Example:** Sold at 1.10, `tp_dip_pct` 0.08 → need mid **≤ ~1.0991** (0.08% below exit) before re-entry is considered. See [Scenario L](#scenario-l--post-tp-re-entry-waiting-for-dip).

### After stop-loss (SL)

| Knob | Purpose |
|------|---------|
| **`sl_cooldown_cycles`** | Usually **longer** than TP cooldown. |
| **`sl_cooldown_minutes`** | Optional time gate. |
| **`sl_stabilization_pct`** | Price must bounce X% off recent low. |
| **`sl_min_ta_score`** | **Higher** bar than TP — demand real reversal confirmation. |

**Real save:** SL hits at 1.00. Bot waits. Price dumps to 0.85. You are *not* auto-buying at 0.95 because TA and stabilization said no. That is the feature working. See [Scenario K](#scenario-k--post-sl-re-entry-bot-wont-reload).

---

## Brackets & offers — managing live orders

### Brackets tab

| State | Meaning |
|-------|---------|
| **pending buy** | Limit bid resting; RLUSD committed |
| **active · bracket** | Filled; TP on book; SL on book **or** deferred (**SL↯**) |
| **active · bracket · SL↯** | Filled; TP on book; SL held off-ledger until price nears stop |
| **active · bracket · BE** | Filled; SL trailing armed (breakeven passed) |
| **active · bracket · BE · BO** | Filled; SL and TP trailing both armed |
| **BE** (in State) | Shorthand for **Breakeven passed** — see [BE and BO](#brackets-tab-be-and-bo-trail-column) |
| **BO** (in State) | Shorthand for **Breakout confirmed** — TP trailing armed |

**Trail column** spells these out as **Breakeven** / **Breakout** (hover for detail). They are trailing milestones, not separate orders.

- **✕** — Cancel that bracket’s open orders (pending bid or TP/SL legs).  
- **✎** — Edit pending buy entry price. Active brackets: edit TP/SL with **Set**.

### Open Offers tab

Every raw ledger order. Same ✕ / ✎ controls.

### Cancel all orders

Live tab — nuclear option. Type `CANCEL_ALL`. Use when you want a clean slate.

---

## Tax & transfer records

Alpha keeps a **running CSV ledger** of taxable activity for tax prep. It uses the same monthly format as the main xLedgerMate engine.

### Where the files live

| File | Purpose |
|------|---------|
| **`logs/trades_YYYY-MM.csv`** | **Primary tax log** — buys, sells, transfers (`taxable=Y` rows) |
| **`logs/transfers.csv`** | Simple outbound payment log from **Config → Send** (destination, tx hash) |

The HUD **Reports** tab shows the current month’s `trades_*.csv` path. Copy the file from the VPS (or your local `logs/` folder) for your accountant or tax software.

### CSV columns (`trades_YYYY-MM.csv`)

| Column | Meaning |
|--------|---------|
| `timestamp_utc` | When the event was recorded (ISO UTC) |
| `event_type` | `BUY`, `SELL`, `TRANSFER`, `MAJOR`, `OFFER_REFRESH` |
| `taxable` | **`Y`** = taxable / include in tax prep · **`N`** = operational only |
| `network` | `mainnet` or `testnet` |
| `side` | `BUY`, `SELL`, or `OUT` (transfer) |
| `xrp_amount` | XRP size of the leg |
| `rlusd_amount` | RLUSD notional (`xrp × price` on trades) |
| `price_rlusd_per_xrp` | Fill or payment price |
| `profit_xrp_equiv` | Estimated P&amp;L on **sells** (TP/SL exit vs bracket entry), in XRP terms |
| `tx_hash` | On-chain hash when available |
| `cycle` | Engine cycle number (if applicable) |
| `notes` | Human context, e.g. `alpha bracket buy abc12345`, `alpha bracket take-profit …` |
| `balance_xrp_after` / `balance_rlusd_after` | Wallet snapshot after event (when available) |

### What Alpha logs automatically

**Live mode only** — **dry-run does not append rows** (no fake tax history).

| Event | `event_type` | `taxable` | When |
|-------|--------------|-----------|------|
| Bracket buy fill | `BUY` | `Y` | Pending buy fills; you acquire XRP |
| Take-profit fill | `SELL` | `Y` | TP leg fills; `profit_xrp_equiv` vs entry |
| Stop-loss fill | `SELL` | `Y` | SL leg fills; `profit_xrp_equiv` vs entry |
| Config → Send withdrawal | `TRANSFER` | `Y` | Also mirrored in `logs/transfers.csv` |

**Not logged yet:** inventory **strength sells** (non-bracket asks) and order cancels/replaces (`OFFER_REFRESH` is used elsewhere in xLedgerMate, not Alpha bracket cancels).

### Example rows (illustrative)

```csv
timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,price_rlusd_per_xrp,profit_xrp_equiv,notes
2026-06-23T14:00:00+00:00,BUY,Y,mainnet,BUY,50.000000,55.000000,1.100000,0.000000,alpha bracket buy 441b8974
2026-06-23T16:30:00+00:00,SELL,Y,mainnet,SELL,50.000000,57.500000,1.150000,2.272727,alpha bracket take-profit 441b8974 entry=1.100000
2026-06-23T18:00:00+00:00,TRANSFER,Y,mainnet,OUT,100.000000,0.000000,0.000000,0.000000,Payment to rDest…
```

### Operator checklist

1. Confirm **LIVE** (not dry-run) before relying on the CSV for real tax records.  
2. After month-end, archive `logs/trades_YYYY-MM.csv` before the calendar rolls.  
3. Cross-check bracket fills on the **Brackets** / **Activity** tabs against new CSV rows.  
4. Withdrawals: verify both `trades_*.csv` and `transfers.csv` if you use **Config → Send**.

---

## Funding changes (scaling toward ~11k XRP)

Use this when you **add XRP or RLUSD** to the bot wallet on mainnet. The bot does not auto-detect narrative capital — you sync **`risk_capital_xrp`** and HUD knobs after each deposit.

**Rule:** Grow the book in **tranches**. Judge each tranche on **realized** bracket P&amp;L (`profit_xrp_equiv` in tax CSV), not **Session P&amp;L** (MTM). SKYNET **operator phase** should match the tranche ([Scenario S](#scenario-s--trust-phase-skynet-bias) · [T](#scenario-t--scale-phase-modest-accumulation) · [U](#scenario-u--aggressive-phase-bag-push)). To deploy RLUSD already on the book, see [Deploy RLUSD to XRP](#deploy-rlusd-to-xrp-get-xrp-heavy).

### Before you send anything

| Step | Action |
|------|--------|
| 1 | Bot account has **RLUSD trust line** (`python main.py --mode setup-trust` if new wallet). |
| 2 | **`dry_run: false`** only when you intend live tax rows. |
| 3 | Note **portfolio XRP-equiv** on HUD Live tab (or `python -m alpha status`). |
| 4 | Edit **`config/config.yaml`** on the VPS — set **`risk_capital_xrp`** ≈ **post-deposit portfolio XRP-equiv** (see table below). |
| 5 | HUD → **Config → Send** is for **outbound** only; **inbound** = normal XRPL payment **to** `bot_account_address`. |
| 6 | After deposit confirms, **Config → Reload** (or restart engine) so sizing sees new balances. |

**Why `risk_capital_xrp` matters**

```text
risk_cap  = portfolio_xrp_equiv × (risk_per_trade_pct / 100)   ← usual binding cap
leg_cap   = risk_capital_xrp × max_leg_size_pct_of_capital     ← config.yaml (default 12%)
size      = min(desired, risk_cap, leg_cap, depth, inventory)
```

If wallet is **~11k XRP-equiv** but `risk_capital_xrp` is still **~250**, you get a HUD alert (*wallet exceeds risk capital*) and **`leg_cap`** can clip size incorrectly. **Always bump `risk_capital_xrp` when you fund.**

| Post-deposit book (XRP-equiv) | Set `risk_capital_xrp` |
|-------------------------------|-------------------------|
| ~600 (current soak) | `600` |
| ~2,000 | `2000` |
| ~4,000 | `4000` |
| ~8,000 | `8000` |
| ~11,000 (full bag) | `11000` |

`max_leg_size_pct_of_capital` default **0.12** → leg cap at 11k ≈ **1,320 XRP** per leg (rarely binding at 2–3% risk).

### What you send: XRP vs RLUSD

| You send | Bot posture after deposit | Tranche knobs bias |
|----------|---------------------------|-------------------|
| **RLUSD** | Stays or becomes **RLUSD-heavy** → **limit bids** deploy on weakness | Trust/Scale: patient bids, `max_pending` before offset↓ |
| **XRP** | **XRP-heavy** vs 75% target → fewer buys until deviation; **strength sells** possible later | Wider `weakness_deviation` or wait for RLUSD from TPs; don’t crank buys until ratio drops |
| **Mix** | Match tranche preset to **dominant** side after transfer | Re-check **Inventory** label on HUD |

Inbound deposits appear in balances next cycle; they are **not** a separate HUD “deposit” button.

### Tranche map (recommended)

| Tranche | Target book | Operator phase | When to advance |
|---------|-------------|----------------|-----------------|
| **0** | ~500–800 (soak) | **trust** | Already running — deferred SL on, bleed under control |
| **1** | ~1,500–2,500 | **trust** | +1–2k sent; 48–72h stable; no kill/preflight issues |
| **2** | ~3,500–5,000 | **trust** → **scale** | Realized P&amp;L ≥ 0 over 7d **or** TP:SL improving; ratio climbing |
| **3** | ~7,000–9,000 | **scale** | Clean week at tranche 2 knobs; depth still healthy |
| **4** | ~11,000 | **scale** → **aggressive** (optional) | Operator OK with churn; SL streak contained |

**Do not** enable **Full SKYNET** or **Aggressive** phase on tranche 1 day one.

---

### Tranche 0 — current soak (~600 XRP-equiv)

*Baseline if you are already live on the VPS.*

**`config/config.yaml`**

```yaml
risk_capital_xrp: 600
```

**SKYNET tab:** `alpha_operator_phase` = **trust** → Save.

**Live → Risk & entry → Apply**

```text
inventory_target_xrp_ratio     = 0.75    # 75% XRP target
alpha_risk_per_trade_pct       = 2.0
alpha_buy_limit_offset_pct     = 0.20
alpha_min_edge_threshold_pct   = 0.08
alpha_weakness_deviation       = 0.05
alpha_max_pending_buys         = 1       # or 2 if cap blocks deploy only
alpha_stale_pending_buy_enabled = on
alpha_stale_pending_buy_max_drift_pct = 0.35
alpha_deferred_sl_enabled      = on
alpha_deferred_sl_arm_buffer_pct = 0.0
alpha_cycle_interval_seconds   = 20
initial_stop_loss_pct          = 0.02    # 2% — Structure tab
```

**Expected size @ ~600 book, mid ~1.08:** **Max buy** ≈ **12 XRP** (~**13 RLUSD**) at 2% risk.

**Graduate to tranche 1 when:** engine stable 48h+, deferred SL arming in logs, you are comfortable with bracket flow.

---

### Tranche 1 — first scale-in (+1–2k → ~2k book)

*After first meaningful deposit.*

**`config/config.yaml`**

```yaml
risk_capital_xrp: 2000
```

**SKYNET:** **trust** → Save. Quick prompt: **Trust phase review**.

**Live → Risk & entry → Apply**

```text
inventory_target_xrp_ratio     = 0.75
alpha_risk_per_trade_pct       = 2.0       # do NOT jump to 4% yet
alpha_buy_limit_offset_pct     = 0.20
alpha_min_edge_threshold_pct   = 0.08
alpha_weakness_deviation       = 0.05
alpha_max_pending_buys         = 2         # allow 2 bids if RLUSD-heavy + bullish
alpha_stale_pending_buy_max_drift_pct = 0.35
alpha_deferred_sl_enabled      = on
alpha_cycle_interval_seconds   = 20
```

**Structure & trailing → Apply** (unchanged from trust soak)

```text
initial_stop_loss_pct          = 0.02
take_profit_pct                = 0.03      # or take_profit_rr = 2.0
bracket_trailing_enabled       = on        # after deferred SL trusted; see [When to enable trailing](#when-to-enable-trailing-after-deferred-sl-is-trusted)
trailing_step_pct              = 1.5
```

**Expected size @ ~2,000 book:** **Max buy** ≈ **40 XRP** (~**43 RLUSD**) at 2%.

**Wait 48–72h.** Check tax CSV: `sum profit_xrp_equiv` on SELLs and `tp_exits` vs `sl_exits` (SKYNET context shows **Realized bracket P&amp;L**).

**Graduate to tranche 2 when:** realized bleed not worsening; at least some TPs or flat realized week; no new instant-SL pattern.

---

### Tranche 2 — mid bag (~4k book)

*Second deposit band — optional move to **Scale** phase after trust metrics OK.*

**`config/config.yaml`**

```yaml
risk_capital_xrp: 4000
```

**SKYNET:** **scale** → Save (only after tranche 1 metrics OK). Quick prompt: **Scale phase knobs**.

**Live → Risk & entry → Apply** — change **one knob at a time** if nervous; full bundle:

```text
inventory_target_xrp_ratio     = 0.75
alpha_risk_per_trade_pct       = 2.0       # optional 2.5 after clean week
alpha_buy_limit_offset_pct     = 0.18
alpha_min_edge_threshold_pct   = 0.08
alpha_weakness_deviation       = 0.04
alpha_max_pending_buys         = 2
alpha_stale_pending_buy_max_drift_pct = 0.35
alpha_deferred_sl_enabled      = on
alpha_cycle_interval_seconds   = 20
```

**Re-entry → Apply** (slightly patient reload at larger size)

```text
alpha_reentry_enabled          = on
alpha_reentry_sl_cooldown_cycles = 10
alpha_reentry_sl_stabilization_pct = 0.12
alpha_reentry_sl_min_ta_score  = 2.5
```

**Expected size @ ~4,000 book:** **Max buy** ≈ **80 XRP** (~**86 RLUSD**) at 2%; ≈ **100 XRP** at 2.5%.

**Graduate to tranche 3 when:** 7+ days at this band, realized P&amp;L flat/positive, XRP ratio trending toward target.

---

### Tranche 3 — large bag (~8k book)

**`config/config.yaml`**

```yaml
risk_capital_xrp: 8000
```

**SKYNET:** **scale** → Save.

**Live → Risk & entry → Apply**

```text
inventory_target_xrp_ratio     = 0.75
alpha_risk_per_trade_pct       = 2.5
alpha_buy_limit_offset_pct     = 0.15
alpha_min_edge_threshold_pct   = 0.08
alpha_weakness_deviation       = 0.04
alpha_max_pending_buys         = 2
alpha_stale_pending_buy_max_drift_pct = 0.35
alpha_deferred_sl_enabled      = on
alpha_cycle_interval_seconds   = 20
```

**Expected size @ ~8,000 book:** **Max buy** ≈ **200 XRP** (~**216 RLUSD**) at 2.5%.

**Structure & trailing:** [enable trailing](#when-to-enable-trailing-after-deferred-sl-is-trusted) once deferred SL is trusted.

---

### Tranche 4 — full ~11k bag

*Only after tranche 3 proof window. This is the narrative capital target — not day-one settings.*

**`config/config.yaml`**

```yaml
risk_capital_xrp: 11000
```

**SKYNET:** **scale** first; **aggressive** only if you accept churn and realized P&amp;L is healthy ([Scenario U](#scenario-u--aggressive-phase-bag-push)).

**Live → Risk & entry → Apply** (scale-safe full bag)

```text
inventory_target_xrp_ratio     = 0.75
alpha_risk_per_trade_pct       = 2.5       # max 3.0 after 2+ clean weeks — not 4% on day one
alpha_buy_limit_offset_pct     = 0.15
alpha_min_edge_threshold_pct   = 0.08
alpha_weakness_deviation       = 0.04
alpha_max_pending_buys         = 2
alpha_stale_pending_buy_max_drift_pct = 0.35
alpha_deferred_sl_enabled      = on
alpha_cycle_interval_seconds   = 20
```

**Optional aggressive bundle** (operator explicitly OK — SKYNET phase **aggressive**)

```text
alpha_risk_per_trade_pct       = 3.0
alpha_buy_limit_offset_pct     = 0.12
alpha_weakness_deviation       = 0.03
alpha_max_pending_buys         = 3
```

**Expected size @ ~11,000 book:**

| `risk_per_trade_pct` | ≈ Max buy (XRP) | ≈ RLUSD @ 1.08 |
|----------------------|-----------------|----------------|
| **2.0%** | ~220 | ~238 |
| **2.5%** | ~275 | ~297 |
| **3.0%** | ~330 | ~356 |

Confirm on **Market Conditions → Max buy** after Apply + one engine cycle.

---

### If you fund mostly XRP (11k XRP, little RLUSD)

The bot targets **75% XRP** — you start **above** target → **`sell_blocked`** / few buys until ratio falls.

| Goal | Action |
|------|--------|
| Let bot rebalance over time | Keep tranche knobs; wait for TPs + optional **strength sells** |
| Deploy RLUSD from profits | Normal bracket flow — no extra knob crank |
| Force faster RLUSD deploy | **Not recommended** at tranche 1 — lowers `inventory_target_xrp_ratio` only if you change strategy |

**Strength-sell knobs** (only when XRP-heavy on purpose) — config or SKYNET; not Live sliders today:

```text
alpha_strength_deviation       = 0.04
alpha_sell_limit_offset_pct    = 0.12
alpha_ta_min_sell_score        = 1.0
```

Prefer **RLUSD tranche deposits** if you want the bot buying immediately without fighting inventory.

---

### Deploy RLUSD to XRP (get XRP-heavy)

Use this when you are **RLUSD-heavy** and want sideline RLUSD **into XRP** — not a one-shot market buy. The bot deploys via **limit bids → bracket fills → repeat**. Default target is **75% XRP**, not 100%; raise target if you want a heavier end state.

#### How the bot decides (read once)

| Concept | Meaning |
|---------|---------|
| **`inventory_target_xrp_ratio`** | North star (HUD: **target XRP %**). Default **75%** — design keeps ~25% RLUSD dry powder. |
| **`deviation`** | `actual_xrp_ratio − target`. **Negative** = RLUSD-heavy (e.g. **−0.29** @ 46% XRP vs 75% target). |
| **Buys** | When `deviation ≤ −weakness_deviation` (e.g. **−0.05**) and gates pass. Deep RLUSD already qualifies. |
| **`sell_blocked`** | **On** while RLUSD-heavy — bot **won’t** strength-sell XRP away. Correct for accumulation. |
| **Fills** | **Passive** — ask must trade **down to your bid**. Mid dipping ≠ fill. |

You are usually already in the **right posture** (`heavy_rlusd`, buys allowed). RLUSD sits on the sidelines because **clips are small**, **`max_pending_buys = 1`**, and **offset** places bids below live price.

#### Why deployment feels slow

1. **`risk_per_trade_pct`** caps each bracket (~**2%** of book → ~**12 XRP** on a ~600 book).  
2. **`max_pending_buys = 1`** → **HOLD** while one bid rests (`max_pending_buys=1`).  
3. **`buy_limit_offset_pct`** (~**0.20%**) → patient entry, slower fills.  
4. RLUSD is split: **wallet** + **pending buy** + **open brackets** (XRP with TP/SL). TP returns RLUSD → cycle repeats.  
5. **Target 75%** — “done” still leaves meaningful RLUSD by design.

**Ballpark fills to move sideline RLUSD** (each successful buy deploys one clip):

| Clip (XRP) | ~RLUSD @ 1.08 | Fills to deploy ~318 XRP (~344 RLUSD) |
|------------|---------------|----------------------------------------|
| ~12 (2% @ 600 book) | ~13 | **~25+** |
| ~40 (2% @ 2k book) | ~43 | **~8** |
| ~220 (2% @ 11k book) | ~238 | **~1–2** per wave |

Raise **`risk_per_trade_pct`** and sync **`risk_capital_xrp`** as the book grows ([tranche table](#tranche-map-recommended)).

#### Knob ladder (apply in order)

Change **one step at a time**; watch **Decision reason** and **Market Conditions → Max buy** after **Apply**.

| Step | Goal | Knobs |
|------|------|--------|
| **1** | More shots while RLUSD-heavy | `alpha_max_pending_buys` **1 → 2** |
| **2** | Bigger RLUSD per fill | `alpha_risk_per_trade_pct` **2.0 → 2.5** (after `risk_capital_xrp` synced) |
| **3** | Faster fills (more aggression) | `alpha_buy_limit_offset_pct` **0.20 → 0.18 → 0.15**; keep `min_edge ≤ offset`; `stale_max_drift` **0.35** |
| **4** | Heavier end state | `inventory_target_xrp_ratio` **0.75 → 0.80–0.90** |
| **5** | SKYNET alignment | Phase **scale** when trust metrics OK; prompt: *deploy RLUSD, max_pending + risk before offset↓* |

**Trust phase:** do not lower offset below **0.15** until realized TP/SL in tax CSV looks acceptable ([Scenario S](#scenario-s--trust-phase-skynet-bias)).

#### Preset — deploy RLUSD now (trust-safe)

**Live → Risk & entry → Apply** (Structure: keep **`deferred_sl_enabled` on**, SL **2%**).

```text
inventory_target_xrp_ratio           = 0.80    # 0.85–0.90 if you want heavier bag
alpha_risk_per_trade_pct           = 2.5
alpha_max_pending_buys             = 2
alpha_buy_limit_offset_pct         = 0.18
alpha_min_edge_threshold_pct       = 0.08
alpha_weakness_deviation           = 0.05    # already passed when dev ≈ -0.29
alpha_stale_pending_buy_enabled    = on
alpha_stale_pending_buy_max_drift_pct = 0.35
alpha_deferred_sl_enabled          = on
alpha_cycle_interval_seconds       = 20
```

**Expected @ ~600 book, mid ~1.08:** **Max buy** ≈ **15 XRP** (~**16 RLUSD**) at 2.5% risk.

#### Preset — deploy faster (scale phase only)

After a clean week on the trust-safe preset:

```text
inventory_target_xrp_ratio           = 0.85
alpha_risk_per_trade_pct           = 2.5       # 3.0 on ~4k+ book if realized P&L OK
alpha_max_pending_buys             = 2
alpha_buy_limit_offset_pct         = 0.15
alpha_min_edge_threshold_pct       = 0.08
alpha_stale_pending_buy_max_drift_pct = 0.35
alpha_weakness_deviation           = 0.04
```

See also [Scenario F](#scenario-f--chop--mild-dips-want-more-action) (eager fills) and [Scenario V](#scenario-v--deploy-sideline-rlusd-faster-xrp-heavy).

#### What not to do

- **`weakness_deviation` → 0.02** when already **dev ≤ −0.20** — does not speed deployment (gate already open).  
- **`reentry_enabled = off`** — more buys after SL, more knife-catching.  
- **`risk 4%` + `offset 0.08`** on first tranche — size without exit trust.  
- Expect **100% XRP** — use **85–90% target** max; keep reserve RLUSD for ops/fees.  
- **Manual DEX swap** RLUSD→XRP is fastest but bypasses limit discipline; bot then rebalances around new ratio.

#### Almost all XRP (operator choice)

1. Set **target 90%** (`inventory_target_xrp_ratio = 0.90`).  
2. Scale **risk** with funding tranches.  
3. Let **TP → RLUSD → rebuy** cycle run.  
4. Optional: one manual swap, then let bot maintain ratio.

#### Verify it’s working

| Check | Good sign |
|-------|-----------|
| **Inventory** | XRP % climbing toward target; `sell_blocked=True` while RLUSD-heavy |
| **Decision** | `place_bid` / `weakness dev=…` — not stuck on `max_pending` forever |
| **Brackets** | Pending buys filling; **SL↯** on new bags (deferred SL) |
| **Tax CSV** | BUY rows + eventual TP/SL; track **`profit_xrp_equiv`** on SELLs |
| **SKYNET Ask** | **Realized bracket P&amp;L** block — not Session P&amp;L alone |

---

### If you fund mostly RLUSD

Matches **heavy_rlusd** posture — use [Deploy RLUSD to XRP](#deploy-rlusd-to-xrp-get-xrp-heavy) presets above; **`max_pending_buys = 2`** before lowering offset.

---

### Post-funding checklist (every tranche)

1. **`risk_capital_xrp`** updated in `config.yaml` → **Config → Reload** on HUD.  
2. **Live → Market Conditions** — **Max buy** matches table above.  
3. **SKYNET → operator phase** saved for tranche.  
4. **Brackets** — no mass instant `sl_filled` at entry; deferred SL shows **SL↯** until armed.  
5. **Reports / tax CSV** — new rows after fills; track **`profit_xrp_equiv`** on SELLs.  
6. **Session P&amp;L** may jump on mid move — ignore for bleed; use realized block in SKYNET Ask.  
7. **Pause** or **kill** if something looks wrong — you can always send the next tranche later.

### What not to do on funding day

- **Do not** set `risk_per_trade_pct` to **4–5%** on first 11k deposit.  
- **Do not** lower `buy_limit_offset_pct` below **0.15** on tranche 1–2.  
- **Do not** enable **Full SKYNET** auto-apply.  
- **Do not** skip **`risk_capital_xrp`** sync — sizes will lie.  
- **Do not** judge success by Session P&amp;L alone after a large XRP deposit (MTM step change).

---

## Real-talk scenarios

### Bull market — ride it

```text
target_xrp_pct = 80
weakness_deviation = 0.03
ta_weight = 0.7
buy_limit_offset_pct ≥ min_edge_threshold_pct
tp_cooldown_cycles = 3–4
```

Bot buys dips, reloads after profit with discipline, trails winners.

### Stop-loss hit — survive it

Price dumps → SL fills → bot goes quiet.  
`sl_cooldown_cycles` ticks down. Stabilization + `sl_min_ta_score` must pass.  
You do **not** catch the falling knife because you were greedy on cooldown.

### Too aggressive — degenerate mode

```text
target_xrp_pct = 90
weakness_deviation = 0.02
risk_per_trade_pct = 2+
max_pending_buys = 5
reentry_enabled = off
ta_weight = 0.2
```

The bot becomes a gambler with limit orders. You either print or get rekt. **Kill switch exists for a reason.**

### “Why no buys?” — today’s classic

You are RLUSD-heavy. TA is fine. Bot still HOLD.

**Check Decision reason** — then jump to the scenario:

| Reason pattern | Scenario |
|----------------|----------|
| `edge_below_threshold` / edge < min | [D](#scenario-d--hold-forever-edge-in-the-reason) |
| `post_sl_` / `post_tp_` / `reentry_` | [K](#scenario-k--post-sl-re-entry-bot-wont-reload) · [L](#scenario-l--post-tp-re-entry-waiting-for-dip) |
| `ta_buy_blocked` / `ta_warming_up` | [J](#scenario-j--ta-blocking-buys-in-chop) · [Q](#scenario-q--ta_warming_up--insufficient-history) |
| `balanced dev=` | [M](#scenario-m--balanced-inventory-nothing-to-do) |
| `max_pending_buys=` | [C](#scenario-c--ladder-clutter-many-pending-buys-none-filling) · [G](#scenario-g--entry-price-keeps-moving-cancelreplace-loop) |
| `insufficient_ask_depth` | [R](#scenario-r--insufficient_ask_depth) |
| `kill_switch` / `pause_bids` / preflight | [P](#scenario-p--kill-switch-drawdown-or-pause) |
| Pending buy exists, no fill | [N](#scenario-n--bid-on-book-mid-looks-good-still-no-fill) |
| `weakness dev=` but no bid | [I](#scenario-i--rlusd-heavy-sell-blocked-buys-only) · [V](#scenario-v--deploy-sideline-rlusd-faster-xrp-heavy) |

---

## Troubleshooting cheat sheet

| Problem | Likely cause | What to do |
|---------|--------------|------------|
| Stuck on HOLD, edge in reason | Offset < min edge | [Scenario D](#scenario-d--hold-forever-edge-in-the-reason) |
| RLUSD-heavy, only bids, no sells | Normal `sell_block` | [Scenario I](#scenario-i--rlusd-heavy-sell-blocked-buys-only) |
| `ta_buy_blocked` / bearish | TA gate in chop | [Scenario J](#scenario-j--ta-blocking-buys-in-chop) |
| Quiet after SL | Re-entry gate | [Scenario K](#scenario-k--post-sl-re-entry-bot-wont-reload) |
| Quiet after TP | Await dip + cooldown | [Scenario L](#scenario-l--post-tp-re-entry-waiting-for-dip) |
| `balanced dev=…` | On target band | [Scenario M](#scenario-m--balanced-inventory-nothing-to-do) |
| Bid resting, no fill | Passive limit | [Scenario N](#scenario-n--bid-on-book-mid-looks-good-still-no-fill) |
| XRP-heavy, no asks | Strength threshold | [Scenario O](#scenario-o--xrp-heavy-want-strength-sells) |
| Kill / pause / preflight | Risk state | [Scenario P](#scenario-p--kill-switch-drawdown-or-pause) |
| Entry keeps jumping | Stale `mid_passed_entry` | [Scenario G](#scenario-g--entry-price-keeps-moving-cancelreplace-loop) |
| Size ~13 RLUSD | `risk_per_trade_pct` cap | [Scenario H](#scenario-h--order-size-stuck-13-rlusd-or-smaller-than-expected) |
| No buys, RLUSD-heavy | Weakness too high | Lower `weakness_deviation` or [Scenario M](#scenario-m--balanced-inventory-nothing-to-do) |
| Buying too soon after sells | Cooldowns too short | [Scenario L/K](#scenario-l--post-tp-re-entry-waiting-for-dip) |
| Bids way below mid (~5%) | Offset set very high | [Scenario A](#scenario-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind) |
| Bids at ~1.04 when mid ~1.10 | Old bracket history or deep offset | Check Brackets **State** = `pending buy`; stale cancel only hits live pending rows |
| HOLD at max pending, bids ~1.097–1.10 | Bids match current offset (low drift) | [Scenario C](#scenario-c--ladder-clutter-many-pending-buys-none-filling) |
| Many pending bids, mid “passed”, no cancel | `max_drift` too loose (e.g. 0.5%) vs offset 0.15–0.35% | [Scenario C](#scenario-c--ladder-clutter-many-pending-buys-none-filling) |
| Bid feels left behind as price rises | Offset too high vs movement | [Scenario A](#scenario-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind) |
| Cancels very slow | One XRPL cancel per engine cycle | Normal — wait or lower pending count / use Cancel all |
| Cancelled but orders still show | Active brackets ≠ pending | Check state column; active = exits on filled bags |
| What does **BE** / **BO** mean? | Trailing flags on active brackets | **BE** = breakeven passed, SL can trail · **BO** = breakout confirmed, TP can trail · needs `bracket_trailing_enabled` |
| What does **SL↯** mean? | Deferred stop (Risk & entry) | SL target set but **not on ledger yet** — avoids instant XRPL exit; arms when mid reaches stop (+ buffer) |
| Bracket vanishes right after fill | Instant SL cross (legacy) or fast stop | Enable **`deferred_sl_enabled`**; check logs for `deferred_sl_hold` / `sl_filled` |
| No rows in tax CSV | Dry-run or no fills yet | Switch to LIVE; CSV updates on bracket buy/TP/SL fills and Config → Send |
| `ta_warming_up` | New session / thin history | [Scenario Q](#scenario-q--ta_warming_up--insufficient-history) |
| Max buy = 0 | Thin book | [Scenario R](#scenario-r--insufficient_ask_depth) |
| Preflight not OK | Trust line, balance, config | [Scenario P](#scenario-p--kill-switch-drawdown-or-pause) |

---

## Knob coupling — change X, change Y

Alpha is not “set and forget.” Several knobs **must move together** or you get confusing behavior (bids that never fill, HOLD forever, or ladders that never cancel).

### The bid placement chain

```text
mid (live book)
  → target bid = mid × (1 − buy_limit_offset_pct / 100)
  → edge on buy ≈ buy_limit_offset_pct
  → must pass min_edge_threshold_pct
  → resting bid kept until stale rules fire OR fill OR max_age
```

| If you change… | Also check / change… | Why |
|----------------|----------------------|-----|
| **`buy_limit_offset_pct`** ↓ (closer to mid) | **`min_edge_threshold_pct`** ≤ new offset | Edge gate uses offset; too-high min edge → HOLD forever |
| **`buy_limit_offset_pct`** ↓ + want **sticky** bid | **`stale_pending_buy_max_drift_pct`** **>** offset + spread (e.g. 0.12 → **0.35**) | Drift ≈ offset → **`mid_passed_entry`** cancels every cycle |
| **`buy_limit_offset_pct`** + want **chase** | **`stale_pending_buy_max_drift_pct`** ≈ offset | Tight drift reprices bid with mid (cancel/replace loop) |
| **`buy_limit_offset_pct`** ↓ | Expect **worse average entry** but **more fills** | You are paying spread to be eager |
| **`max_pending_buys`** ↑ | **`stale_pending_buy_max_drift_pct`** tight + **`cycle_interval_seconds`** | More slots = more ladder clutter; cancels are one per cycle |
| **`stale_pending_buy_max_drift_pct`** ↓ | **`max_pending_buys`** maybe ↓ to 1–3 | Aggressive prune + one slot = simplest behavior |
| **`risk_per_trade_pct`** ↑ | **Market Conditions → Max buy** | Confirms new clip size before live orders |
| **`weakness_deviation`** ↓ | **`risk_per_trade_pct`** — don’t crank both at once | More buy attempts + bigger size = fast RLUSD deploy |
| **`ta_min_buy_score`** ↑ | **`ta_weight`** = 1.0 | High gate + low weight = confusing partial blocks |
| **`cycle_interval_seconds`** ↓ | RPC load / cancel latency | Faster cycles = faster stale cancel + new bids, more ledger traffic |
| **`initial_stop_loss_pct`** ↑ / ↓ | **`deferred_sl_enabled`** (keep on for XRPL) | Wider stop = lower stop price; deferral prevents instant cross on placement |
| **`deferred_sl_arm_buffer_pct`** ↑ | Faster SL on-ledger on pullbacks | Higher buffer = arm before raw stop; 0% = arm at stop only |
| **`reentry_*` cooldowns** ↓ | **`ta_min_buy_score`** on re-entry | Shorter wait + weak TA = reload into chop |

### Rules of thumb

1. **`buy_limit_offset_pct` ≥ `min_edge_threshold_pct`** — always.  
2. **Sticky bids:** **`stale_pending_buy_max_drift_pct` > `buy_limit_offset_pct` + spread** (e.g. offset 0.12%, drift 0.35%). **Chasing bids:** drift ≈ offset (expect frequent cancels).  
3. **`max_pending_buys` = 1** until you understand stale + fill behavior; then ladder to 3–5 only with wider drift.  
4. The bot **does not chase** resting bids — it **cancels stale** and **places new** at the current target. To “move” a bid, either wait for stale cancel or cancel manually on Brackets tab.  
5. **Limit fills need the ask** — mid crossing your entry does not fill you. Closer offset = closer to ask = higher fill odds on mild dips.

### Timing reference (typical)

| Event | Rough delay |
|-------|-------------|
| HUD **Apply** → engine sees new knobs | Next cycle (`cycle_interval_seconds`, e.g. 15–34s) |
| Stale cancel of one pending bid | One cycle + one XRPL tx (~cycle_interval each) |
| New bid after cancel | Next `PLACE_BID` cycle when gates pass |
| Age-based stale cancel | `alpha_stale_pending_buy_max_age_seconds` (config or operator overrides; **0** = off) |

---

## Live box snapshot (VPS mainnet · 2026-06-23)

Pulled from `logs/alpha_runtime_state.json`, `logs/alpha_overrides.json`, and engine logs on your Hetzner box. Use as a baseline when tuning.

### Effective knobs (HUD overrides win over `config.yaml`)

| Knob | **Live (effective)** | `config.yaml` on disk |
|------|----------------------|------------------------|
| `risk_per_trade_pct` | **3.0%** | 0.5% |
| `buy_limit_offset_pct` | **0.12%** | 0.15% |
| `stale_pending_buy_max_drift_pct` | **0.20%** | 0.50% |
| `deferred_sl_enabled` | **true** | true |
| `deferred_sl_arm_buffer_pct` | **0.0%** | 0.0% |
| `max_pending_buys` | **5** | 1 |
| `cycle_interval_seconds` | **20s** | 60s |
| `min_edge_threshold_pct` | **0.08%** | 0.08% |
| `weakness_deviation` | **0.035** | 0.05 |
| `stale_pending_buy_max_age_seconds` | **1800** (30 min) | 0 (off) |
| `alpha_base_order_size_xrp` | 50 (config) | 50 |
| `max_leg_size_pct_of_capital` | 12% | 12% |
| `risk_capital_xrp` | 251 | 251 |

### Market & size right now

| Field | Value |
|-------|--------|
| Portfolio | **~584 XRP** equiv |
| Mid | **~1.1029** RLUSD/XRP |
| Spread | **~0.10%** (~11 bps) |
| Ask depth (1% band) | **~84k XRP** (not limiting size) |
| **Max buy** (HUD) | **~17.5 XRP** ≈ **~19.3 RLUSD** ← `3% × portfolio` |
| Leg cap ceiling | **~30.1 XRP** ≈ **~33 RLUSD** |

Recent engine sizes: **11.7 XRP** (~12.9 RLUSD) at **2%** risk → **17.5 XRP** (~19.3 RLUSD) after raising to **3%**.

### Why entries were switching every ~20–50s

Logs show repeated **`mid_passed_entry`** cancels while offset was **0.12%** and drift was **0.12–0.20%**:

```text
stale_pending_buy_cancelled | entry=1.102025 | mid=1.103459 | mid_passed_entry=0.130%>0.12%
```

With **`max_pending_buys = 5`**, each cancel frees a slot → **`PLACE_BID` every cycle** → entry price jumps even though you only “see” one offer on the book at a time.

### Recommended adjust for your goals (Live → Apply)

**Stickier entry + cleaner behavior + modestly bigger clip:**

```text
buy_limit_offset_pct            = 0.12      ← keep (eager placement)
stale_pending_buy_max_drift_pct = 0.35      ← wider than offset + spread
max_pending_buys                = 1         ← one bid, less churn
alpha_stale_pending_buy_max_age_seconds = 0  ← off (config or SKYNET); was 1800
risk_per_trade_pct              = 4.0       ← ~23 XRP / ~26 RLUSD per bracket
cycle_interval_seconds          = 20        ← keep
min_edge_threshold_pct          = 0.08      ← keep
```

**If you only want bigger size** (keep current repricing): raise **`risk_per_trade_pct`** to **4.0** and confirm **Max buy** on Market Conditions.

**If you only want stickier price:** raise **`stale_pending_buy_max_drift_pct`** to **0.35** and set **`max_pending_buys` = 1** — leave risk where it is.

After **Apply**, wait 1–2 cycles and confirm logs show fewer `stale_pending_buy_cancelled` lines and **Max buy** matches your target RLUSD.

---

## Scenarios & suggested presets

Use these as **recipes**, not gospel. Apply on **Live → Risk & entry**, watch **Decision reason** for 10–20 cycles, adjust one knob at a time.

### Scenario index

| | Scenario | When to use |
|---|----------|-------------|
| **A** | [Bid left behind in uptrend](#scenario-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind) | RLUSD-heavy, price rising, want nearer bids |
| **B** | [Patient dip sniper](#scenario-b--patient-dip-sniper-default-philosophy) | Deep offsets, can wait hours |
| **C** | [Ladder clutter](#scenario-c--ladder-clutter-many-pending-buys-none-filling) | Many pending buys, none filling |
| **D** | [HOLD, edge in reason](#scenario-d--hold-forever-edge-in-the-reason) | `edge_below_threshold` |
| **E** | [Buying too often in downtrend](#scenario-e--buying-too-often-in-a-downtrend) | SL streak, knife catching |
| **F** | [Chop, want more action](#scenario-f--chop--mild-dips-want-more-action) | Tight spread, rare fills |
| **G** | [Entry keeps moving](#scenario-g--entry-price-keeps-moving-cancelreplace-loop) | Cancel/replace every cycle |
| **H** | [Size stuck ~13 RLUSD](#scenario-h--order-size-stuck-13-rlusd-or-smaller-than-expected) | Clip smaller than expected |
| **I** | [RLUSD-heavy, sell blocked](#scenario-i--rlusd-heavy-sell-blocked-buys-only) | Heavy RLUSD, only bids fire |
| **J** | [TA blocking buys in chop](#scenario-j--ta-blocking-buys-in-chop) | `ta_buy_blocked` / bearish |
| **K** | [Post-SL re-entry](#scenario-k--post-sl-re-entry-bot-wont-reload) | After stop-loss, quiet bot |
| **L** | [Post-TP re-entry](#scenario-l--post-tp-re-entry-waiting-for-dip) | After take-profit, no reload |
| **M** | [Balanced HOLD](#scenario-m--balanced-inventory-nothing-to-do) | `balanced dev=…` |
| **N** | [Bid resting, no fill](#scenario-n--bid-on-book-mid-looks-good-still-no-fill) | Passive limit mechanics |
| **O** | [XRP-heavy, want sells](#scenario-o--xrp-heavy-want-strength-sells) | Strength asks / unload XRP |
| **P** | [Kill / drawdown / pause](#scenario-p--kill-switch-drawdown-or-pause) | Hard stops, no trading |
| **Q** | [TA warming up](#scenario-q--ta_warming_up--insufficient-history) | New session, thin history |
| **R** | [Thin book](#scenario-r--insufficient_ask_depth) | Depth gate blocks size |
| **S** | [Trust phase (SKYNET)](#scenario-s--trust-phase-skynet-bias) | Prove overnight, anti-bleed |
| **T** | [Scale phase (SKYNET)](#scenario-t--scale-phase-modest-accumulation) | After trust earned |
| **U** | [Aggressive phase (SKYNET)](#scenario-u--aggressive-phase-bag-push) | Bag-growth push |
| **V** | [Deploy sideline RLUSD faster](#scenario-v--deploy-sideline-rlusd-faster-xrp-heavy) | RLUSD on sidelines, want higher XRP % |

---

### Scenario A — RLUSD-heavy, price drifting up, bid feels “left behind”

**Symptoms:** One (or few) pending buys ~0.3%+ below mid; market moving up; you want to participate without waiting for a deep dip.

**What’s happening:** `buy_limit_offset_pct` = 0.35% places target ~36 bps below mid. `mid_passed_entry` stale cancel will pull the old bid (~34s per cycle), but the **replacement** bid is still 0.35% below **new** mid unless you lower offset.

**Suggested adjust (eager bag deploy):**

```text
buy_limit_offset_pct           = 0.12    ← was 0.35; nearer live (~13 bps below mid)
min_edge_threshold_pct         = 0.08    ← must stay ≤ offset
stale_pending_buy_max_drift_pct = 0.35   ← wider than offset (avoid mid_passed_entry loop)
max_pending_buys               = 1
cycle_interval_seconds         = 20     ← optional; faster cancel/replace
```

**If fills still rare:** ask is still above your bid — try offset **0.08–0.10** only if you accept worse entries. If entries **keep moving**, drift is still too tight — see [Scenario G](#scenario-g--entry-price-keeps-moving-cancelreplace-loop).

---

### Scenario B — Patient dip sniper (default philosophy)

**Symptoms:** You want better entries, can wait; RLUSD-heavy is fine for hours.

```text
buy_limit_offset_pct           = 0.25–0.35
min_edge_threshold_pct         = 0.08
stale_pending_buy_max_drift_pct = 0.25   ← match offset so ladder doesn’t over-prune
max_pending_buys               = 1–2
weakness_deviation             = 0.05–0.08
```

**Coupling:** Do **not** set `stale_max_drift` to 0.15% while offset is 0.35% — bids within the placement band look “valid” and sit through rallies.

---

### Scenario C — Ladder clutter (many pending buys, none filling)

**Symptoms:** 10–20+ pending buys; HOLD `max_pending_buys=N`; mid moved; orders “just sit there.”

```text
stale_pending_buy_max_drift_pct = 0.15   ← tighten (align to offset, not 0.5%)
buy_limit_offset_pct           = 0.15    ← if you want nearer market too
max_pending_buys               = 1–3
stale_pending_buy_enabled      = on
```

Optional in `config.yaml`: `alpha_stale_pending_buy_max_age_seconds: 1800` (30 min max rest).

**Manual:** Brackets **Cancel all** clears ledger bids (kills active TP/SL too — use only if you mean it).

---

### Scenario D — HOLD forever, edge in the reason

**Symptoms:** `edge 0.050% < min 0.500%` or similar.

```text
Either: buy_limit_offset_pct  = 0.50   (bid deeper — more edge)
Or:     min_edge_threshold_pct = 0.08   (accept smaller edge)
```

Never leave **offset < min edge**.

---

### Scenario E — Buying too often in a downtrend

**Symptoms:** Repeated fills, SL hits, bag not growing.

```text
weakness_deviation             = 0.06–0.08   ↑ patience
ta_min_buy_score               = 2.0–2.5     ↑
reentry_sl_cooldown_cycles     = 10–15       ↑
risk_per_trade_pct             = 0.3–0.5     ↓
buy_limit_offset_pct           = 0.20+       ↑ (deeper bids only)
```

**Coupling:** Tightening entries (higher TA) + deeper offset + longer SL re-entry — move together.

---

### Scenario F — Chop / mild dips, want more action

**Symptoms:** RLUSD-heavy, TA OK, bot buys but fills are rare; spread is tight.

```text
buy_limit_offset_pct           = 0.08–0.12
min_edge_threshold_pct         = 0.05–0.08
weakness_deviation             = 0.03–0.04
max_pending_buys               = 1
cycle_interval_seconds         = 15–20
```

**Trade-off:** More fills, worse average entry, more bracket management.

---

### Scenario G — Entry price keeps moving (cancel/replace loop)

**Symptoms:** Pending buy entry changes every **20–60s**; Activity shows **`place_bid`** almost every cycle; logs show **`mid_passed_entry`** or **`entry_drift`**.

**What’s happening:** **`stale_pending_buy_max_drift_pct` is too close to `buy_limit_offset_pct`**. The bid starts below mid by ~offset%; **`mid_passed_entry`** fires when mid is above entry by more than max drift — often on the **first cycle** after placement. With **`max_pending_buys` > 1**, each cancel opens a slot for another **`PLACE_BID`**.

**Fix (sticky bid):**

```text
stale_pending_buy_max_drift_pct = 0.35–0.50   ← main lever (offset 0.12 → drift 0.35+)
max_pending_buys                = 1
alpha_stale_pending_buy_max_age_seconds = 0     ← disable 30-min age churn if set
buy_limit_offset_pct            = 0.12          ← keep unless you want deeper bids
```

**Nuclear stick:** uncheck **`stale_pending_buy_enabled`** — bid rests until fill or manual cancel (won’t chase a rising market).

**Verify:** fewer `stale_pending_buy_cancelled` in logs; Brackets entry stable for several minutes while mid drifts.

---

### Scenario H — Order size stuck ~13 RLUSD (or smaller than expected)

**Symptoms:** HUD / Open Offers show **~12–13 RLUSD** per buy; **Max buy** on Market Conditions matches that number.

**What’s happening:** Size is capped by **`risk_per_trade_pct × portfolio`**, not book depth. At **~584 XRP** portfolio:

| `risk_per_trade_pct` | ≈ RLUSD @ 1.103 |
|----------------------|-----------------|
| 2.0% | **~13** ← common “why so small?” |
| 3.0% | **~19** |
| 4.0% | **~26** |
| 5.0% | **~32** (near **leg cap** ~33 RLUSD) |

**Fix:** Live → **`risk_per_trade_pct`** → **Apply** → confirm **Market Conditions → Max buy** moved.

**Not the fix (usually):** `buy_limit_offset_pct`, `max_pending_buys`, or stale drift — those change **price**, not **size**. **`alpha_base_order_size_xrp`** in config only binds when risk cap exceeds desired (unlikely below ~5% risk on your book).

---

### Scenario I — RLUSD-heavy, sell blocked, buys only

**Symptoms:** Sidebar shows **~20–30% XRP** vs **95% target**; inventory label **`heavy_rlusd`** or **`rlusd_heavy`**; Decision **`place_bid`** or **`weakness dev=…`**; **`sell_block=True`** in logs; no strength sells.

**What’s happening:** This is **normal bag-deploy posture**. You are far below target XRP allocation, so the engine **deploys RLUSD via limit bids**. **`sell_blocked_imbalance`** blocks unloading XRP until you are closer to target — you are not “missing” sells; the bot is correctly refusing to sell XRP while RLUSD-heavy.

| Signal | Meaning |
|--------|---------|
| `dev ≈ -0.70` @ target 95% | ~25% XRP actual — deep RLUSD bag |
| `sell_block=True` | Won’t place strength asks until less RLUSD-heavy |
| `buy_block=False` | Buys allowed when `dev ≤ -weakness_deviation` |

**If buys are too aggressive:** raise **`weakness_deviation`** (e.g. **0.05–0.08**) or lower **`risk_per_trade_pct`**.

**If you want faster XRP accumulation:** you are usually already past the weakness gate — use **`max_pending_buys`**, **`risk_per_trade_pct`**, and **`buy_limit_offset_pct`** in that order. Full presets: [Deploy RLUSD to XRP](#deploy-rlusd-to-xrp-get-xrp-heavy) · [Scenario V](#scenario-v--deploy-sideline-rlusd-faster-xrp-heavy). Don’t expect strength sells until **`dev`** recovers toward target.

**Config note:** **`inventory_target_xrp_ratio`** (HUD: target XRP %) sets the north star. At **75%** target with **46%** actual, large negative deviation is expected until many fills land. For **85–90%** target, raise **`inventory_target_xrp_ratio`** explicitly.

---

### Scenario V — Deploy sideline RLUSD faster (XRP-heavy)

**Symptoms:** **`heavy_rlusd`** / **`rlusd_heavy`**; **`sell_block=True`**; lots of RLUSD in wallet; XRP ratio stuck or climbing slowly; Decision often **`max_pending_buys=1`** or small **`place_bid`** clips.

**What’s happening:** Normal accumulation — bot is **buying**, not broken. Deployment is limited by **passive limits**, **per-trade risk %**, and **one pending bid**. See [Deploy RLUSD to XRP](#deploy-rlusd-to-xrp-get-xrp-heavy) for mechanics.

**Trust-safe preset (Live → Apply):**

```text
inventory_target_xrp_ratio           = 0.80
alpha_risk_per_trade_pct           = 2.5
alpha_max_pending_buys             = 2
alpha_buy_limit_offset_pct         = 0.18
alpha_min_edge_threshold_pct       = 0.08
alpha_weakness_deviation           = 0.05
alpha_stale_pending_buy_max_drift_pct = 0.35
alpha_deferred_sl_enabled          = on
```

**Scale phase (after clean realized P&amp;L week):** target **0.85**, offset **0.15**, optional risk **3.0** on larger book.

**Not the fix:** lowering **`weakness_deviation`** when **`dev` already ≤ −0.15** — gate is already open.

---

### Scenario J — TA blocking buys in chop

**Symptoms:** RLUSD-heavy, inventory OK, but HOLD with reasons like:

```text
ta_buy_blocked score=1.20<2.00 weight=1.00 sell=0.80 bias=neutral
ta_buy_blocked bearish bias=bearish buy=1.50 sell=3.20
ta_warming_up — insufficient price history for buy gate
```

**What’s happening:** With **`ta_enabled`** and **`ta_weight` = 1**, buys need **`buy_score ≥ min_buy_score`** and **non-bearish bias**. In chop, scores flicker; bearish bias blocks even when you “feel” RLUSD-heavy enough to buy.

**Loosen (more buys in chop):**

```text
ta_min_buy_score     = 1.0–1.5     ← was 2.0+
ta_weight            = 0.5–0.7     ← partial gate; 0 = advisory only
ta_enabled           = on
```

**Tighten (fewer knife catches):**

```text
ta_min_buy_score     = 2.0–2.5
ta_weight            = 1.0
reentry_sl_min_ta_score = 2.0+     ← pairs with [Scenario K](#scenario-k--post-sl-re-entry-bot-wont-reload)
```

**Coupling:** Lower **`ta_min_buy_score`** + lower **`weakness_deviation`** together = very eager reload in sideways markets. Change one at a time.

**Verify:** Decision reason no longer contains `ta_buy_blocked`; TA panel shows buy score above your gate.

---

### Scenario K — Post-SL re-entry (bot won’t reload)

**Symptoms:** Stop-loss filled; bot goes quiet for cycles/minutes; Decision shows:

```text
post_sl_cooldown cycles=2/8
reentry_sl_await_bounce mid=1.098 need>=1.101 (0.03% above recent_low)
reentry_sl_await_stabilization trend=bearish breakout_down=True
reentry_sl_ta_score=1.80<2.00
reentry_sl_await_weakness dev=-0.45
```

**What’s happening:** After an **SL exit**, **`reentry_enabled`** runs a **mandatory cooldown** first — inventory and TA **cannot bypass** cooldown. Then the gate requires **structure stabilization** (no bearish breakout), optional **bounce above recent low**, **TA score**, and **weakness** again.

**Default-ish live overrides:** `sl_cooldown_cycles = 1` (short) — raise if reloading too fast after SL.

**Patient reload after SL:**

```text
reentry_enabled              = on
sl_cooldown_cycles           = 8–15
sl_stabilization_pct         = 0.03–0.05
sl_min_ta_score              = 2.0–2.5
weakness_deviation           = 0.05–0.08
buy_limit_offset_pct         = 0.20+        ← deeper bids after damage
```

**Eager reload (riskier):**

```text
sl_cooldown_cycles           = 1–3
sl_min_ta_score              = 1.0–1.5
sl_stabilization_pct         = 0.02
```

**Nuclear:** `reentry_enabled = off` — SL exits do not block the next buy (see [Scenario E](#scenario-e--buying-too-often-in-a-downtrend) trade-offs).

**Verify:** `logs/alpha_reentry.json` shows cooldown counting down; reason shifts from `post_sl_cooldown` → stabilization/TA → then **`place_bid`**.

---

### Scenario L — Post-TP re-entry (waiting for dip)

**Symptoms:** Take-profit filled; bot won’t immediately rebuy; Decision shows:

```text
post_tp_cooldown cycles=1/4
reentry_tp_await_dip mid=1.105 need<=1.102 (0.08% below tp_exit=1.103)
reentry_tp_await_weakness dev=-0.40
reentry_tp_ta_score=1.20<1.50
```

**What’s happening:** After **TP**, the gate enforces cooldown, then waits for mid to dip **`reentry_tp_dip_pct`** below the **TP exit price**, plus weakness + TA. Prevents instantly rebuying the top after a winner.

**Default live:** `tp_cooldown_cycles = 4`, `tp_dip_pct = 0.08`, `tp_min_ta_score = 1.5`.

**Reload sooner after winners:**

```text
tp_cooldown_cycles     = 2–3
tp_dip_pct             = 0.03–0.05
tp_min_ta_score        = 1.0
weakness_deviation     = 0.03
```

**More discipline (don’t chase green candles):**

```text
tp_cooldown_cycles     = 6–10
tp_dip_pct             = 0.10–0.15
tp_min_ta_score        = 2.0
```

**Verify:** After cooldown, mid must trade **below** `tp_exit × (1 − dip_pct/100)` before a new bid — check reason clears `reentry_tp_await_dip`.

---

### Scenario M — Balanced inventory, nothing to do

**Symptoms:** Decision **`HOLD — balanced dev=+0.02`** (or similar small deviation); neither buy nor sell; inventory label **`balanced`**.

**What’s happening:** **`deviation`** is between **`−weakness_deviation`** and **`+strength_deviation`**. The bot considers the book **on target enough** — no weakness buys, no strength sells.

**To buy anyway:** lower **`weakness_deviation`** so current **`dev`** qualifies (e.g. dev **−0.04** needs weakness **≥ 0.04**).

**To sell anyway:** raise **`strength_deviation`** in config (default **0.04**; HUD exposes weakness only today) or wait until XRP allocation rises.

**Often confused with:** [Scenario D](#scenario-d--hold-forever-edge-in-the-reason) (edge gate) or [Scenario J](#scenario-j--ta-blocking-buys-in-chop) (TA gate) — read the **exact reason string**.

---

### Scenario N — Bid on book, mid looks good, still no fill

**Symptoms:** Brackets show **pending buy**; mid at or below entry on HUD; **`place_bid`** already executed; offer rests for minutes; no fill.

**What’s happening:** **Limit bids are passive.** Fill requires **best ask ≤ your bid** (or a seller hitting your price). **Mid crossing entry does not fill you.** Large **ask depth** above your bid means liquidity exists **higher**, not at your level.

| Check | Action |
|-------|--------|
| **Best ask** vs your entry (Market Conditions) | Ask must drop to bid |
| Spread ~10+ bps | Need a trade through the spread |
| Entry below best bid | You’re behind the touch — lower offset or wait |

**Fix for more fills:** lower **`buy_limit_offset_pct`** (nearer ask) — see [Scenario A/F](#scenario-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind). **Not a bug** if mid dips visually but ask never trades to your bid.

---

### Scenario O — XRP-heavy, want strength sells

**Symptoms:** **70%+ XRP**, target lower or at cap; HOLD **`sell_blocked_imbalance`** when too RLUSD-heavy *or* **`place_ask` / strength** when **`dev ≥ strength_deviation`**; TA may show **`ta_sell_deferred bullish`**.

**What’s happening:** Strength sells deploy when **`deviation ≥ alpha_strength_deviation`** (default **0.04** — config/SKYNET, not a Live slider today). **`sell_limit_offset_pct`** sets ask above mid. **`ta_sell_deferred`** holds XRP when bias is bullish and buy score is strong.

**Unload XRP into RLUSD faster:**

```text
strength_deviation       = 0.03        ← config / SKYNET
sell_limit_offset_pct    = 0.10–0.15   ← nearer mid = more sell fills
ta_min_sell_score        = 1.0–1.5
inventory_target_xrp_ratio = lower target if you want less XRP ambition
```

**Hold winners longer:**

```text
ta_min_sell_score        = 2.5+
sell_limit_offset_pct    = 0.30+
ta_sell_deferred         ← respect bullish deferral in reason
```

**Verify:** Decision **`place_ask`** or **`strength dev=…`**; Open Offers shows RLUSD bid side (you sell XRP).

---

### Scenario P — Kill switch, drawdown, or pause

**Symptoms:** Sidebar **Kill** or **Pause**; Decision **`kill_switch: …`**, **`risk_trading_not_allowed`**, **`preflight_not_ready`**, **`pause_bids`**, or **`buy_blocked_imbalance`** when XRP **too high** (opposite of RLUSD-heavy).

**What’s happening:**

| Reason | Meaning |
|--------|---------|
| **`kill_switch`** | Hard stop — daily drawdown or manual kill file |
| **`preflight_not_ready`** | Trust line, balance, or config issue |
| **`pause_bids`** | Inventory circuit breaker — too XRP-heavy vs target |
| **`buy_blocked_imbalance`** | Beyond **`alpha_max_inventory_imbalance_pct`** on buy side |

**Fix:** Resolve alerts in **Reports / status** first. **Kill** requires clearing kill state and fixing drawdown cause. **Pause** on HUD stops new entries but keeps brackets.

**Do not** crank aggression knobs while kill/preflight active — fix risk state first.

---

### Scenario Q — `ta_warming_up` / insufficient history

**Symptoms:** Early session or after restart; Decision **`ta_warming_up — insufficient price history for buy gate`**; TA panel sparse.

**What’s happening:** TA needs **`min_candles`** in price history (`alpha_price_history.json` samples). Until warmed, **`ta_weight` = 1** blocks buys.

**Fix:** Wait **15–30 min** of engine cycles (depends on **`alpha_price_sample_interval_seconds`** and chart bucket). Or temporarily:

```text
ta_weight = 0          ← advisory only until warmed
ta_enabled = off       ← last resort while learning
```

**Not the fix:** Lowering offset or weakness — gate is history, not inventory.

---

### Scenario R — `insufficient_ask_depth`

**Symptoms:** HOLD **`insufficient_ask_depth depth=0.XX`**; Market Conditions **Max buy** = **0** or tiny.

**What’s happening:** Book depth within **±1% of mid** is below **`min_order_size_xrp`**. Rare on RLUSD/XRP mainnet; can happen during outages, bad book snapshot, or testnet.

**Fix:** Check **best bid/ask** sanity on HUD. Wait for next engine cycle book refresh. If persistent, verify RPC/book health (preflight). **Do not** raise **`risk_per_trade_pct`** — depth is the binder, not risk cap.

---

### Scenario S — Trust phase (SKYNET bias)

**When:** New deploy, post-fix soak, SL streak, or underwater open brackets. You want the bot to **prove** behavior overnight without bleeding on instant SL churn.

**HUD:** SKYNET tab → **Operator phase** → **Trust** → **Save phase**.

**What SKYNET should recommend (not always what it did before phase existed):**

```text
alpha_operator_phase            = trust   ← SKYNET tab (not a trading knob)
alpha_buy_limit_offset_pct      = 0.20+   ← patient; do not chase
alpha_weakness_deviation        = 0.05
alpha_max_pending_buys          = 1–2     ← raise cap before lowering offset
alpha_risk_per_trade_pct        = ~2%
alpha_deferred_sl_enabled       = on
alpha_stale_pending_buy_max_drift_pct = 0.35  ← sticky if offset ~0.20
```

**SKYNET rules in trust phase:**

- RLUSD-heavy + bullish TA + HOLD `max_pending_buys` → **`max_pending_buys↑`**, not scenario C drift tighten.
- Do **not** lower **`buy_limit_offset_pct`** below effective unless you explicitly ask or mid dumps 2%+.
- Judge success by **realized bracket exits** (`profit_xrp_equiv` in tax CSV), **not** **Session P&L** (MTM).

**Quick prompt:** SKYNET tab → **Trust phase review**.

---

## 48-hour watch checklist (hands-off soak)

Use this when the stack is deployed, deferred SL is on, and you want to **let the bot cook** instead of tuning every HOLD. Check the HUD **2–3× per day**; do a full compare **~48 hours** after the baseline timestamp.

### Baseline — 2026-06-24 (post deploy `8308ecc`, trailing on)

Recorded from live VPS `alpha_runtime_state.json` + activity log.

| Metric | Where on HUD | Baseline (now) | 48h later | Δ | OK? |
|--------|----------------|----------------|-----------|---|-----|
| Portfolio (XRP equiv) | Sidebar **Portfolio** | **588.7** | | | |
| XRP ratio (target 75%) | Sidebar **Inventory** | **51.7%** | | | ↑ or flat |
| Session P&L (MTM) | Sidebar **Session P&L** | **+214.1 XRP** | | | informational only |
| Realized 24h (TP/SL) | Sidebar **Realized 24h** | **−7.16 XRP** | | | not worse by >3 XRP |
| TP exits (24h window) | Realized 24h meta line | **0** | | | any TP is a win |
| SL exits (24h window) | Realized 24h meta line | **53** | | | not accelerating |
| Daily drawdown | Sidebar **Drawdown** | **0.0%** / 10% | | | stay &lt; 3% |
| Kill switch | Sidebar / Risk | **off** | | | must stay off |
| Operator phase | SKYNET tab | **scale** | | | trust OK; scale if earned |
| Pending buys | Brackets summary | **1** | | | 0–2 normal |
| Active fixed TP/SL | Brackets summary | **7** | | | |
| Active SL trail | Brackets summary | **1** | | | BE in Trail col |
| Deferred SL | Risk & entry | **on** | | | stay on |
| Bracket trailing | Overrides / Risk | **on** | | | off if trail→SL churn |
| Typical HOLD reasons | Decision card | `max_pending_buys`, `reentry_sl_await_bounce`, `ta_buy_blocked` | | | patience, not stuck |

**Copy row values from the sidebar at check-in.** MTM can diverge wildly from realized — judge bleed on **Realized 24h**, not Session P&L.

### Daily glance (2 minutes)

1. **Kill switch** off, **drawdown** under 3%.
2. **Realized 24h** — trending flat or up? SL count not spiking?
3. **XRP ratio** — drifting toward 75% or at least not falling?
4. **Decision reason** — re-entry gates and `max_pending_buys` are **expected**; only worry if cycles stop entirely.
5. **Brackets** — pending buys filling, trails arming (BE), no burst of `sl_filled` right after `trailing_sl_update` in Activity.

### 48-hour decision tree

```text
After 48h, compare to baseline table:

GOOD (keep cooking, no knob changes)
  • Realized 24h improved or flat (not −3 XRP worse than baseline)
  • XRP ratio ≥ baseline (51.7%) or clearly climbing
  • Drawdown < 3%, kill off
  • Some TP exits OR SL rate slowed vs baseline window

WATCH (check daily, still no knobs unless bleed worsens)
  • Realized still negative but SL count stable; ratio flat
  • MTM green, realized red — normal; do not chase with offset↓

ACT (one change only, then another 24–48h soak)
  • Realized 24h worse by >3 XRP AND SL >> TP → SKYNET phase **trust**, review offset (do not go below 0.15)
  • Trailing SL churn (fills right after trail update) → run disable trailing script; stay trust
  • Drawdown > 5% → pause, review; kill if > 8%

SCALE (only if GOOD + ratio climbing + TP:SL improving)
  • Already on scale phase — do not add heat until realized turns positive over multi-day window
  • Next step: max_pending_buys before buy_limit_offset_pct↓
```

### SKYNET quick prompts at check-in

| When | Prompt |
|------|--------|
| Daily | **Trust phase review** (even on scale — asks about bleed) |
| 48h | Paste sidebar numbers: ratio, realized 24h, TP/SL counts, last decision reason |
| If bleeding | **Anti-bleed** / Scenario S knobs |

### Telegram / logs (optional)

- Hourly Telegram: alive + portfolio snapshot.
- Tax truth: `logs/trades_YYYY-MM.csv` on VPS — sum `profit_xrp_equiv` on SELL rows should match **Realized 24h** on HUD.

**Next full compare target:** ~**2026-06-26** (48h from baseline).

---

### Scenario T — Scale phase (modest accumulation)

**When:** Clean nights, deferred SL arming, XRP ratio climbing toward target, TP:SL improving. You earned trust — want **one notch** more deploy.

**HUD:** Operator phase → **Scale** → Save.

```text
alpha_operator_phase            = scale
alpha_buy_limit_offset_pct      = 0.15–0.20
alpha_weakness_deviation        = 0.04
alpha_max_pending_buys          = 2–3
alpha_risk_per_trade_pct        = 2–3%
```

**Rule:** Change **one knob at a time**. Prefer **`max_pending_buys`** before **`buy_limit_offset_pct↓`**.

**Quick prompt:** **Scale phase knobs**.

---

### Scenario U — Aggressive phase (bag push)

**When:** You accept churn; book healthy; TA supportive; bleed under control; scaling toward a large XRP bag.

**HUD:** Operator phase → **Aggressive** → Save. **Agent Smith** guardrails still cap risk — Full SKYNET cannot exceed bounds.

```text
alpha_operator_phase            = aggressive
alpha_buy_limit_offset_pct      = 0.08–0.12
alpha_stale_pending_buy_max_drift_pct = 0.35   ← sticky
alpha_max_pending_buys          = 2–3
alpha_risk_per_trade_pct        = toward guardrail max (e.g. 4%)
```

**Stop rule:** If SL streak returns or realized P&L turns negative → drop back to **trust** phase knobs, not more heat.

---

### Quick reference — your “closer to live price” checklist

When you say *“price is leaving my bid behind”*:

| Step | Action |
|------|--------|
| 1 | Lower **`buy_limit_offset_pct`** (main lever) |
| 2 | Set **`min_edge_threshold_pct`** ≤ new offset |
| 3 | For **chase**: set **`stale_pending_buy_max_drift_pct`** ≈ offset · For **stick**: drift **>** offset + spread |
| 4 | Keep **`max_pending_buys` = 1** while tuning |
| 5 | **Apply** → wait 1–2 cycles for stale cancel + new bid |
| 6 | Confirm on Brackets: new **pending buy** entry ≈ `mid × (1 − offset%)` |
| 7 | SKYNET **Stale bid ladder** — verify `would_cancel` / `target_entry` |

**Example @ mid 1.1037:**

| offset | Approx target bid | Gap below mid |
|--------|-------------------|---------------|
| 0.35% (old) | 1.0999 | ~38 bps |
| 0.15% | 1.1021 | ~17 bps |
| 0.12% (suggested eager) | 1.1024 | ~12 bps |
| 0.08% | 1.1028 | ~9 bps |

---

## Suggested starter settings (first week)

Conservative learner preset:

```text
target_xrp_pct          = 65–70
weakness_deviation      = 0.04
risk_per_trade_pct      = 0.4
min_edge_threshold_pct  = 0.08
buy_limit_offset_pct    = 0.15    ← must be ≥ min edge
sell_limit_offset_pct   = 0.15
max_pending_buys        = 1
stale_pending_buy_max_drift_pct = 0.15   ← match buy_limit_offset
ta_weight               = 0.8
ta_min_buy_score        = 1.5
reentry_enabled         = on
tp_cooldown_cycles      = 4
sl_cooldown_cycles      = 8
bracket_trailing_enabled = on
trailing_step_pct       = 1.5
```

**Rules while learning:**

1. Change **one knob** at a time.  
2. Watch **Decision reason** for 10–20 cycles after each change.  
3. Read **Market Conditions** before cranking aggression.  
4. Use **dry_run** until you trust the behavior.  
5. **Kill** without hesitation if something looks wrong.

When you understand how each knob *feels*, then turn up the aggression.

---

## Tuning SKYNET (Grok Ask, Agent Smith, Full mode)

SKYNET is the **advisor layer** — it does not place trades. Set **operator phase** on the SKYNET tab so Grok matches soak vs scale goals.

**HUD names:** Phase 1 manual prompt = **Send to Grok**; Phase 2 bounded automation = **Agent Smith** (checkbox **Enable Agent Smith Mode**); Phase 3 = **Full SKYNET**.

### Operator phase (trust / scale / aggressive)

**SKYNET tab → Operator phase → Save phase.** Persisted as `alpha_operator_phase`. See [Scenario S](#scenario-s--trust-phase-skynet-bias), [T](#scenario-t--scale-phase-modest-accumulation), [U](#scenario-u--aggressive-phase-bag-push).

| Phase | Use when | SKYNET bias |
|-------|----------|-------------|
| **Trust** (default) | Soak, SL streak | `max_pending↑` before `offset↓` |
| **Scale** | Clean nights | offset 0.15–0.20, max_pending 2–3 |
| **Aggressive** | Bag push | offset 0.08–0.12; revert if SL streak |

Phase does **not** change knobs until you Apply.

### Runtime context (each Ask / Agent Smith cycle)

- **`alpha_operator_phase`** and playbook **S–U**
- **`pending_buy_stale`** — target entry, per pending bid `would_cancel` / `reason`, `over_cap_count`
- **`likely_scenarios`** — auto hints (A–R) from decision reason + inventory (reference only)
- **Scenario playbook (A–R, S–U)** — condensed presets matching this manual
- **Operator knobs (effective)** — current HUD overrides

**Session P&L** is MTM — use **`realized_bracket_pnl`** in SKYNET context (`realized_profit_xrp_equiv`, `tp_exits` / `sl_exits` from tax CSV) for bleed in trust phase.

**Natural language → Apply**

On the SKYNET tab, set **operator phase**, type your goal in plain English, click **Send**, then **Apply suggested changes**:

```text
Trust phase: max pending 2 only — keep offset 0.20, weakness 0.05. Do not tighten drift.
```

Grok maps your goals to allowlisted keys. Quick buttons **Trust phase review**, **Scale phase knobs**, **Preset: sticky + 4% risk**, **My settings → Apply**.

If **Apply** stays disabled, name settings explicitly (percent values help) or check the hint for guardrail errors.

**Modes**

| Mode | Behavior |
|------|----------|
| **SKYNET tab — Ask** | You prompt; Grok suggests changes; you **Apply** manually |
| **Agent Smith** (Phase 2) | Grok runs every 3–5 cycles; **Apply safe** for guardrailed suggestions |
| **Full SKYNET** (Phase 3) | Auto-applies guardrailed changes (confirm with `ENABLE_FULL_SKYNET`; requires Agent Smith mode) |

Grok uses operator phase + scenario playbook + `pending_buy_stale`. **Agent Smith** proposals do **not** overwrite the Ask response box.

**Purple knob labels (Live / TA tabs):** When **Agent Smith** proposes safe changes (or SKYNET Ask returns applicable changes), matching knob labels turn **purple ◆** with the suggested value in the tooltip. Legend appears under Risk & entry. Highlights clear after Apply or when values already match effective config.

---

## Emergency controls

| Control | Effect |
|---------|--------|
| **Pause** | Stops new entries; existing brackets remain |
| **Kill switch** | Hard stop — no new risk |
| **Cancel all** | Pulls open ledger offers |
| **Config → Send** | Withdraw XRP or RLUSD to any `r…` address (type `SEND` to confirm) |
| **Reports tab** | Cycle report + path to `logs/trades_YYYY-MM.csv` tax log |
| **Dry run toggle** | Simulates without submitting (when enabled); **no tax CSV rows** |

The bot is live. The market is live. You are live.

**Trade accordingly.**

— xLedgerMate Alpha · Aggressive Bag Growth
