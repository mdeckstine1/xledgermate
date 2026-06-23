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

---

### `buy_limit_offset_pct` / `sell_limit_offset_pct`

How far below mid (buy) or above mid (sell) the bot places limits.

**Higher = patient sniper.** Deeper bids, better average entry, slower fills.  
**Lower = eager.** Near mid, faster fills, worse average price.

HUD range is roughly **0.05% – 1.0%** per side. This is *not* “5% below market” unless you type a large number in the number box — and the slider may cap you.

---

### `max_pending_buys` / `max_pending_sells`

How many open orders of each type at once.

- **1** = conservative, one shot at a time.  
- **3–5** = ladders multiple dips (more RLUSD deployed, more to manage).

### `stale_pending_buy_enabled` / `stale_pending_buy_max_drift_pct`

Each engine cycle, the bot can **auto-cancel resting buy bids** that no longer match where it would place a new entry (mid moved, or your `buy_limit_offset_pct` changed).

**How it decides “stale”**

1. Compute **target entry** = `mid × (1 − buy_limit_offset_pct / 100)`  
2. For each **pending buy** bracket, compute **drift** = `|entry − target| / mid × 100`  
3. If drift **>** `stale_pending_buy_max_drift_pct` (default **0.15%**, match `buy_limit_offset_pct`), cancel that bid and free a `max_pending_buys` slot.

Also cancels when:

- **`entry_above_mid`** — bid is above mid (off-policy; new bids are always below mid)
- **`mid_passed_entry`** — mid rallied more than `max_drift_pct` above the bid without a fill
- **`excess_pending_buy`** — more open pending buys than `max_pending_buys` (farthest from target pruned first)

**Example — clearly stale**

- Mid **1.10**, offset **0.05%** → target ≈ **1.099**  
- A bid still at **1.04** → drift ≈ **5.5%** → **cancelled**

**Example — still valid (why you may keep 5 pending)**

- Mid **1.102**, offset **0.5%** → target ≈ **1.097**  
- Pending bids at **1.097 – 1.100** → drift ≈ **0.2%** → **kept** (within 0.5%)  
- HOLD reason `max_pending_buys=5` is correct here — slots are full with *current* bids, not stuck legacy ones.

**Don’t confuse Brackets history with live pending**

`logs/alpha_brackets.json` lists old entries (e.g. **~1.04** from an earlier deep-offset session). Check the HUD **Brackets** tab **State** column: only rows marked **`pending buy`** count toward the cap. Filled or cancelled brackets (and active TP/SL legs) are separate.

**Tuning**

| Goal | Action |
|------|--------|
| Prune bids that drifted only slightly | Lower `stale_pending_buy_max_drift_pct` (e.g. **0.15%**) on Live → Risk & entry, then **Apply** |
| Turn off auto-prune | Uncheck `stale_pending_buy_enabled` |
| Force-cancel one bid | Brackets tab **✕** on that row |
| Nuclear option | **Cancel all** — also kills active TP/SL (you keep XRP) |

Optional `stale_pending_buy_max_age_seconds` in `config.yaml` (0 = off) cancels bids older than N seconds regardless of drift.

Watch **Activity** or engine logs for `stale_pending_buy_cancelled` after a cycle.

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
| Cancelled but orders still show | Active brackets ≠ pending | Check state column; active = exits on filled bags |
| What does **BE** / **BO** mean? | Trailing flags on active brackets | **BE** = breakeven passed, SL can trail · **BO** = breakout confirmed, TP can trail · needs `bracket_trailing_enabled` |
| No rows in tax CSV | Dry-run or no fills yet | Switch to LIVE; CSV updates on bracket buy/TP/SL fills and Config → Send |
| `ta_warming_up` | New session / thin history | Wait; needs mid samples |
| Preflight not OK | Trust line, balance, config | Fix alerts in status report |

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
