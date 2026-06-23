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
4. Buy fills → bot places TP + SL limit sells → "active bracket"
5. TP fills → profit (RLUSD back) → re-entry gate may block new buys
6. SL fills → loss capped → longer re-entry wait + stronger TA required
```

**Pending buy** = RLUSD committed, waiting for fill.  
**Active bracket** = you already own the XRP; TP/SL are exit orders.  
Cancelling a pending buy pulls the bid. Cancelling an active bracket cancels TP/SL only — **you keep the XRP**.

---

## Your dashboard — what to watch

| Where | What it tells you |
|--------|-------------------|
| **Ticker / sidebar** | Mode (LIVE/dry), mid, portfolio, inventory %, drawdown, session P&L |
| **Decision** | Last action + **reason** — this is your best friend when confused |
| **Market Conditions** | Mid, spread, depth, max buy/sell size, TA summary |
| **Brackets tab** | Open positions: pending buys vs active brackets; size, RLUSD, TP/SL, **Trail** flags |
| **Open Offers** | Raw ledger orders (✕ cancel, ✎ reprice) |
| **Reports** | Cycle status text + path to monthly **tax CSV** (`logs/trades_YYYY-MM.csv`) |
| **Config** | Credentials, network, **Send / withdraw**, transfer history |

If the bot is “doing nothing,” the **Decision reason** almost always explains why.

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
| **0.5%** | Normal. |
| **1%+** | Titanium balls. One bad streak hurts. |

Check **Market Conditions → max buy** to see what the book and caps allow *right now*.

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
| **`age`** | Optional: `stale_pending_buy_max_age_seconds` in `config.yaml` (HUD does not expose this yet) |

Default **`stale_pending_buy_max_drift_pct` = 0.15%** — align with **`buy_limit_offset_pct`**. If drift is much looser (e.g. **0.5%** while offset is **0.15–0.35%**), you can accumulate **many** resting bids that look “passed” but are still considered valid.

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
| Prune bids that drifted only slightly | Lower `stale_pending_buy_max_drift_pct` (e.g. **0.15%**) on Live → Risk & entry, then **Apply** |
| Match drift to placement band | Set `stale_pending_buy_max_drift_pct` ≈ `buy_limit_offset_pct` |
| Limit ladder size | Lower `max_pending_buys` (1–3 conservative) |
| Time-out old bids | Set `stale_pending_buy_max_age_seconds` in `config.yaml` (e.g. **1800**) |
| Turn off auto-prune | Uncheck `stale_pending_buy_enabled` |
| Force-cancel one bid | Brackets tab **✕** on that row |
| Nuclear option | **Cancel all** — also kills active TP/SL (you keep XRP) |

Watch **Activity** or engine logs for `stale_pending_buy_cancelled` after a cycle.

**SKYNET / Grok** (manual ask, Agent mode, or Full SKYNET) receives a **`pending_buy_stale`** block in context: target entry, per-bid `would_cancel` / `reason`, `over_cap_count`, and tuning notes. Use the SKYNET quick prompt **“Stale bid ladder”** or ask why bids are not canceling.

**Coupling:** See [Knob coupling](#knob-coupling--change-x-change-y) — when you change offset, also align `min_edge`, `stale_max_drift`, and often `max_pending_buys`.

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

**Warm-up:** Early on you may see `ta_warming_up` — not enough price history yet. Normal.

---

## Structure & Trailing — protect the bag you just bought

### `bracket_trailing_enabled`

After a buy fills, the bot can **ratchet TP and SL higher** as price moves in your favor.

**On:** Buy at 1.00, SL 0.985, TP 1.03. Price hits 1.05 → SL trails up toward 1.01, TP can move too. Locks in progress.  
**Off:** Fixed TP/SL. Simpler. Gives back more on reversals.

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

Stop distance below entry.

| Range | Vibe |
|-------|------|
| **0.8–1.0%** | Tight. Small losses; stopped out often. |
| **1.5%** | Reasonable. |
| **3%+** | Wide. Survives noise; bigger loss if wrong. |

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

**Example:** Sold at 1.10, `tp_dip_pct` 0.08 → need ~1.012 or lower before re-entry is even considered.

### After stop-loss (SL)

| Knob | Purpose |
|------|---------|
| **`sl_cooldown_cycles`** | Usually **longer** than TP cooldown. |
| **`sl_cooldown_minutes`** | Optional time gate. |
| **`sl_stabilization_pct`** | Price must bounce X% off recent low. |
| **`sl_min_ta_score`** | **Higher** bar than TP — demand real reversal confirmation. |

**Real save:** SL hits at 1.00. Bot waits. Price dumps to 0.85. You are *not* auto-buying at 0.95 because TA and stabilization said no. That is the feature working.

---

## Brackets & offers — managing live orders

### Brackets tab

| State | Meaning |
|-------|---------|
| **pending buy** | Limit bid resting; RLUSD committed |
| **active · bracket** | Filled; TP/SL on book |
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

**Check Decision reason:**

1. **Edge mismatch** — `buy_limit_offset_pct` < `min_edge_threshold_pct` → fix the table above.  
2. **Re-entry cooldown** — `post_tp_cooldown` / `post_sl_cooldown` in reason.  
3. **TA block** — score below gate; raise weight/score or wait.  
4. **Depth** — `insufficient_ask_depth` in Market Conditions.  
5. **Pause / kill** — sidebar badges.  
6. **Max pending** — already at `max_pending_buys`. If stale auto-cancel is on, check whether pending entries are still within `stale_pending_buy_max_drift_pct` of target (they may be valid, not stuck).

---

## Troubleshooting cheat sheet

| Problem | Likely cause | What to do |
|---------|--------------|------------|
| Stuck on HOLD, edge in reason | Offset < min edge | Raise offset or lower min edge |
| No buys, RLUSD-heavy | Weakness too high | Lower `weakness_deviation` or raise target |
| Buying too soon after sells | Cooldowns too short | Raise `tp_cooldown_cycles` / `tp_min_ta_score` |
| Bids way below mid (~5%) | Offset set very high | Lower `buy_limit_offset_pct` if you want nearer fills |
| Bids at ~1.04 when mid ~1.10 | Old bracket history or deep offset | Check Brackets **State** = `pending buy`; stale cancel only hits live pending rows |
| HOLD at max pending, bids ~1.097–1.10 | Bids match current offset (low drift) | Lower `stale_pending_buy_max_drift_pct` to prune tighter, or cancel manually |
| Many pending bids, mid “passed”, no cancel | `max_drift` too loose (e.g. 0.5%) vs offset 0.15–0.35% | Align drift to offset; check SKYNET `pending_buy_stale.would_cancel_count` |
| Bid feels left behind as price rises | `buy_limit_offset_pct` too high vs movement | [Scenario A](#scenario-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind) — lower offset + align stale drift |
| Cancels very slow | One XRPL cancel per engine cycle | Normal — wait or lower pending count / use Cancel all |
| Cancelled but orders still show | Active brackets ≠ pending | Check state column; active = exits on filled bags |
| What does **BE** / **BO** mean? | Trailing flags on active brackets | **BE** = breakeven passed, SL can trail · **BO** = breakout confirmed, TP can trail · needs `bracket_trailing_enabled` |
| No rows in tax CSV | Dry-run or no fills yet | Switch to LIVE; CSV updates on bracket buy/TP/SL fills and Config → Send |
| `ta_warming_up` | New session / thin history | Wait; needs mid samples |
| Preflight not OK | Trust line, balance, config | Fix alerts in status report |

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
| **`buy_limit_offset_pct`** | **`stale_pending_buy_max_drift_pct`** ≈ same value | Loose drift (e.g. 0.5%) + tight offset (0.15%) → old bids never “stale” |
| **`buy_limit_offset_pct`** ↓ | Expect **worse average entry** but **more fills** | You are paying spread to be eager |
| **`max_pending_buys`** ↑ | **`stale_pending_buy_max_drift_pct`** tight + **`cycle_interval_seconds`** | More slots = more ladder clutter; cancels are one per cycle |
| **`stale_pending_buy_max_drift_pct`** ↓ | **`max_pending_buys`** maybe ↓ to 1–3 | Aggressive prune + one slot = simplest behavior |
| **`weakness_deviation`** ↓ | **`risk_per_trade_pct`** — don’t crank both at once | More buy attempts + bigger size = fast RLUSD deploy |
| **`ta_min_buy_score`** ↑ | **`ta_weight`** = 1.0 | High gate + low weight = confusing partial blocks |
| **`cycle_interval_seconds`** ↓ | RPC load / cancel latency | Faster cycles = faster stale cancel + new bids, more ledger traffic |
| **`reentry_*` cooldowns** ↓ | **`ta_min_buy_score`** on re-entry | Shorter wait + weak TA = reload into chop |

### Rules of thumb

1. **`buy_limit_offset_pct` ≥ `min_edge_threshold_pct`** — always.  
2. **`stale_pending_buy_max_drift_pct` ≈ `buy_limit_offset_pct`** — keep them aligned (e.g. both 0.15%).  
3. **`max_pending_buys` = 1** until you understand stale + fill behavior; then ladder to 3–5.  
4. The bot **does not chase** resting bids — it **cancels stale** and **places new** at the current target. To “move” a bid, either wait for stale cancel or cancel manually on Brackets tab.  
5. **Limit fills need the ask** — mid crossing your entry does not fill you. Closer offset = closer to ask = higher fill odds on mild dips.

### Timing reference (typical)

| Event | Rough delay |
|-------|-------------|
| HUD **Apply** → engine sees new knobs | Next cycle (`cycle_interval_seconds`, e.g. 15–34s) |
| Stale cancel of one pending bid | One cycle + one XRPL tx (~cycle_interval each) |
| New bid after cancel | Next `PLACE_BID` cycle when gates pass |
| Age-based stale cancel | `stale_pending_buy_max_age_seconds` (config only; e.g. 1800s) |

---

## Scenarios & suggested presets

Use these as **recipes**, not gospel. Apply on **Live → Risk & entry**, watch **Decision reason** for 10–20 cycles, adjust one knob at a time.

### Scenario A — RLUSD-heavy, price drifting up, bid feels “left behind”

**Symptoms:** One (or few) pending buys ~0.3%+ below mid; market moving up; you want to participate without waiting for a deep dip.

**What’s happening:** `buy_limit_offset_pct` = 0.35% places target ~36 bps below mid. `mid_passed_entry` stale cancel will pull the old bid (~34s per cycle), but the **replacement** bid is still 0.35% below **new** mid unless you lower offset.

**Suggested adjust (eager bag deploy):**

```text
buy_limit_offset_pct           = 0.12    ← was 0.35; nearer live (~13 bps below mid)
min_edge_threshold_pct         = 0.08    ← must stay ≤ offset
stale_pending_buy_max_drift_pct = 0.12   ← match offset
max_pending_buys               = 1
cycle_interval_seconds         = 20     ← optional; faster cancel/replace
```

**If fills still rare:** ask is still above your bid — try offset **0.08–0.10** only if you accept worse entries. Use SKYNET **“Stale bid ladder”** to read `pending_buy_stale` vs live mid.

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

### Quick reference — your “closer to live price” checklist

When you say *“price is leaving my bid behind”*:

| Step | Action |
|------|--------|
| 1 | Lower **`buy_limit_offset_pct`** (main lever) |
| 2 | Set **`min_edge_threshold_pct`** ≤ new offset |
| 3 | Set **`stale_pending_buy_max_drift_pct`** ≈ new offset |
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

## SKYNET (Grok advisor, Agent, Full mode)

SKYNET sends Grok a **runtime context** each ask/agent cycle. Besides inventory, decision, TA, and brackets, it includes:

- **`pending_buy_stale`** — target entry, per pending bid `would_cancel` / `reason`, `over_cap_count`, and policy notes (same rules as `stale_pending_buy_*` above)
- **Operator knobs (effective)** — including `alpha_stale_pending_buy_*`, `alpha_max_pending_buys`, `alpha_buy_limit_offset_pct`

**Modes**

| Mode | Behavior |
|------|----------|
| **SKYNET tab — Ask** | You prompt; Grok suggests changes; you **Apply** manually |
| **Agent mode** | Grok runs every 3–5 cycles; **Apply safe** for guardrailed suggestions |
| **Full SKYNET** | Auto-applies guardrailed changes (confirm with `ENABLE_FULL_SKYNET`) |

Grok is instructed to use `pending_buy_stale` when diagnosing unfilled bid ladders. Quick prompt: **Stale bid ladder** on the SKYNET tab.

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
