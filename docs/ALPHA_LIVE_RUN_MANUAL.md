# Alpha — Live Run & Order Manual

**For:** Operators going from dry-run to **real mainnet orders**  
**HUD:** `http://YOUR_VPS:8765` (login required on public VPS)  
**Strategy:** Directional value accumulation — the bot places **limit orders for you** when rules pass. There is **no “Buy now” button**.

---

## The most important idea

**You do not create orders by hand in the HUD.**

Alpha runs a loop (~every 60 seconds on VPS):

1. Read balances, book, inventory, risk, TA (if enabled)
2. **Decide:** `HOLD`, `PLACE_BID` (buy XRP with RLUSD), or `PLACE_ASK` (sell XRP)
3. **Execute** (if not paused, not dry-run, and risk allows)
4. **Manage brackets** — after a buy fills, TP and SL limit sells are placed automatically

Your job is to **configure**, **enable live mode**, **watch the Decision card**, and **use Pause / Kill** when needed.

---

## What an “order” means in Alpha

| Stage | What happens | Where you see it |
|--------|----------------|------------------|
| **1. Entry signal** | Engine decides `PLACE_BID` with size + limit price | **Live** tab → **Decision** card |
| **2. Entry order** | Limit **buy** on XRPL (XRP size @ RLUSD/XRP price below mid) | **Open offers** tab |
| **3. Buy fills** | Ledger offer disappears; bracket activates | **Brackets** tab → state changes |
| **4. Bracket legs** | Bot places **take-profit** and **stop-loss** limit **sells** | **Brackets** tab (TP / SL columns) |
| **5. Exit** | TP or SL fills; other leg cancelled (OCO-style) | **Brackets** + **Activity** tab |

**Typical long trade:** RLUSD-heavy inventory → limit buy below market → on fill, sell limits above (TP) and below (SL).

---

## HUD layout (what each area does)

### Header bar

| Badge | Meaning |
|--------|---------|
| `dry-run` | Paper mode — **no real ledger orders** |
| `LIVE` | Real money mode (`dry_run: false`) |
| `paused` | Operator pause — engine runs but **does not execute** |
| `kill` | Kill switch — trading blocked until cleared |
| `patient` / `buying` / `in_position` | Posture (waiting / entry working / brackets open) |

### Sidebar (left)

| Item | Meaning |
|--------|---------|
| **Start** | Starts `xledgermate-alpha` systemd service (VPS only) |
| **Pause** | Stops **execution** (decisions still logged) |
| **Restart** | Restarts the Alpha engine service |
| **Enable LIVE trading…** | Type `ENABLE_LIVE` to set live mode via HUD override |
| **trading_enabled** | Master yaml switch — must be **on** + **Apply trading** |

Portfolio shows **RLUSD equivalent**; mid is RLUSD per XRP.

### Live tab

| Block | Use it to… |
|--------|------------|
| **Status strip** (6 cards) | **Decision** = will it try to trade? **Preflight** = safe to quote? **Execution** = what happened last cycle |
| **Chart** | Price history (mid series); structure lines on the right |
| **Risk & entry** | Size, edge, buy offset — click **Apply risk & entry** |
| **Structure & trailing** | SL/TP %, breakout, trailing — **Apply structure & trailing** |
| **Manual actions** | Pause, Kill, Cancel all, Config reload |

### Other tabs

| Tab | Purpose |
|-----|---------|
| **TA** | Toggle technical analysis; scores gates for entries |
| **Brackets** | Open trades — adjust TP/SL with price + **Set** |
| **Open offers** | Raw XRPL offers (pending buy before fill) |
| **Reports** | Text cycle report |
| **Activity** | JSON event feed |

---

## Before your first live order (checklist)

Do these **in order**. Do not skip dry-run soak.

### A. Server & services (VPS)

```bash
systemctl is-active xledgermate-alpha      # should be: active
systemctl is-active xledgermate-alpha-hud  # should be: active
```

In HUD sidebar: click **Start** if the engine was stopped. **Restart** after config changes on disk.

### B. Config files (`config/config.yaml` + `credentials.local.yaml`)

| Setting | Soak value | Live value |
|---------|------------|------------|
| `testnet` | `false` | `false` |
| `dry_run` | `true` | `false` when ready |
| `trading_enabled` | `true` | `true` |
| `bot_account_address` | Your Bot Account | Same |
| Secret in `credentials.local.yaml` | Present | Present |

Conservative live starting points:

```yaml
alpha_risk_per_trade_pct: 0.5
alpha_max_pending_buys: 1
alpha_min_edge_threshold_pct: 0.08
alpha_buy_limit_offset_pct: 0.15
alpha_weakness_deviation: 0.05
initial_stop_loss_pct: 0.015
take_profit_rr: 2.0
max_daily_drawdown_percent: 10.0
```

### C. Soak in dry-run (mainnet, no real orders)

1. Confirm HUD badge says **dry-run**
2. Let engine run **50+ cycles** (≈50 minutes at 60s interval)
3. Open **Activity** — look for `cycle` events without errors
4. When conditions align, **Decision** may show `PLACE_BID` and **Execution** shows `dry_run:...` (simulated, not on ledger)
5. Run: `python scripts/alpha_validate.py`

### D. Go live (real orders)

1. **Kill switch clear** — no `kill` badge; or Manual actions → **Clear kill**
2. **Not paused** — no `paused` badge; **Resume** if needed
3. **trading_enabled** checked → **Apply trading**
4. Sidebar → **Enable LIVE trading…** → type exactly: `ENABLE_LIVE`  
   - Or edit `config.yaml`: `dry_run: false` and `systemctl restart xledgermate-alpha`
5. Confirm badge flips to **LIVE** (red)
6. Watch **first 3 cycles** — Decision, Execution, Open offers

**Rollback:** Enable dry-run again (`ENABLE_DRY_RUN` or yaml `dry_run: true`) + restart engine.

---

## How Alpha decides to place a buy (PLACE_BID)

All must pass in the **same cycle**:

### Inventory (most common blocker)

- Portfolio must be **RLUSD-heavy** vs target (default target **55% XRP**)
- Deviation ≤ **−`alpha_weakness_deviation`** (default **−0.05** = 5% below target)
- Example: **58% XRP / 42% RLUSD** → deviation ≈ **+0.03** → label **balanced** → **HOLD**, no buy

**You need more RLUSD (or less XRP) relative to target** for the bot to want to buy.

Check sidebar **Inventory** line and **Live → Decision** reason (`balanced dev=...`).

### Risk & preflight

- **Preflight** card: `Preflight OK — ready to quote`
- No **kill** switch
- Drawdown below daily limit
- `trading_enabled: true`

### Book & edge

- Valid mid from order book
- Limit buy price = mid minus **`alpha_buy_limit_offset_pct`** (default 0.15% below mid)
- **Edge** (mid vs limit) ≥ **`alpha_min_edge_threshold_pct`**
- Enough ask-side depth for size cap

### Position limits

- Pending buys < **`alpha_max_pending_buys`** (default **1**)
- Size after caps ≥ **`min_order_size_xrp`**

### Technical analysis (if enabled on TA tab)

- TA toggle **on** → must pass buy score gates
- If blocked: Decision reason contains `ta_buy_blocked`
- Turn TA off to test inventory-only behavior, or wait for bullish scores

### Operator state

- **Not paused**
- **`dry_run: false`** for real submission (dry-run still *decides* but does not submit)

When everything passes, **Decision** shows **`PLACE_BID`** and reason like:

`weakness dev=-0.06 edge=0.150% ...`

---

## How Alpha decides to place a sell (PLACE_ASK)

Symmetric to buys — used when inventory is **XRP-heavy** (above target allocation):

### Inventory

- Deviation ≥ **`alpha_strength_deviation`** (default **+0.05**)
- Example: **70% XRP / 30% RLUSD** with 55% target → **PLACE_ASK** candidate

### Book & edge

- Limit sell price = mid plus **`alpha_sell_limit_offset_pct`** (default 0.15% above mid)
- **Edge** (limit vs mid) ≥ **`alpha_min_edge_threshold_pct`**
- Enough **bid-side** depth (`insufficient_bid_depth` if book too thin)

### Position limits

- Strength sells < **`alpha_max_pending_sells`** (default **1**)
- **`max_pending_buys` does not block sells** — you can unload XRP while a buy is working

### TA (if enabled)

- Decision reason may include `ta_sell_blocked` when sell scores are too low

When everything passes, **Decision** shows **`PLACE_ASK`**:

`strength dev=+0.15 edge=0.150% depth_cap=...`

Strength sells are **naked limit unloads** (no TP/SL bracket — brackets apply only to buy entries).

---

## Step-by-step: “I want my first live buy”

This is the practical sequence many operators follow.

### 1. Start the engine

- VPS: `systemctl start xledgermate-alpha` or HUD **Start**
- Wait for header **Updated** timestamp to refresh (~1 min)

### 2. Confirm you are in LIVE mode

- Header badge: **LIVE** (not dry-run)
- If still dry-run: sidebar **Enable LIVE trading…** → `ENABLE_LIVE`

### 3. Confirm trading is allowed

| Check | OK looks like |
|--------|----------------|
| Preflight | `Preflight OK` |
| Pause | No `paused` badge |
| Kill | No `kill` badge |
| trading_enabled | Checkbox on + applied |

### 4. Get inventory into “buy zone”

Alpha buys when **RLUSD-heavy** (below target XRP %).

- If inventory shows **balanced** or **xrp_heavy**, the bot will **HOLD**
- Options:
  - **Wait** for market / P&L to shift allocation
  - **Manually** swap on XRPL (outside bot) to increase RLUSD share
  - **Lower** `alpha_weakness_deviation` in config (more aggressive — understand risk first)

Watch **Decision** each cycle until reason is not `balanced dev=...`.

### 5. Optional: tune entry aggression (Live tab)

| Slider | Effect |
|--------|--------|
| `buy_limit_offset_pct` ↑ | Buy further below mid (more edge, less likely to fill) |
| `min_edge_threshold_pct` ↓ | Easier to pass edge gate |
| `risk_per_trade_pct` | Bigger size when order fires |

Click **Apply risk & entry** after changes.

### 6. Wait for PLACE_BID

- **Decision** card: action **PLACE_BID**
- **Execution** card: message without `dry_run` (live) and `executed` true when submitted

### 7. Verify on ledger

- **Open offers** tab: one **buy** row (side buy, price, size)
- XRPL explorer / wallet: offer on your Bot Account

### 8. After the buy fills

- **Open offers**: buy disappears
- **Brackets** tab: new row — **pending** → **active** with **TP** and **SL** prices
- Bot placed two limit **sells** (take profit above entry, stop below)

### 9. Manage the bracket (optional)

On **Brackets** tab:

1. Type new price in TP or SL input
2. Click **Set**
3. Change queues for next engine cycle (cancel-replace on ledger when live)

Enable **bracket_trailing_enabled** on Live tab for trailing SL after breakeven/breakout (advanced).

---

## Why is Decision stuck on HOLD?

| Decision reason (examples) | What it means | What to do |
|----------------------------|---------------|------------|
| `balanced dev=+0.03` | Not RLUSD-heavy enough | Wait or rebalance portfolio |
| `max_pending_buys=1` | Already one pending buy | Wait for fill/cancel; **sells still allowed** |
| `max_pending_sells=1` | Already one strength sell open | Wait for fill/cancel on Open offers |
| `insufficient_bid_depth` | Bid book too thin for sell size | Smaller size or wait |
| `edge_below_threshold` | Limit too close to mid | Lower `min_edge_threshold` or raise offset |
| `ta_buy_blocked` | TA scores too low | TA tab: wait, tune thresholds, or disable TA |
| `kill_switch: ...` | Kill active | **Clear kill** |
| `preflight_not_ready` | Book/trust/RPC issue | Check logs; fix trust line / connectivity |
| `risk_trading_not_allowed` | Drawdown or `trading_enabled: false` | Check drawdown; enable trading |
| `insufficient_ask_depth` | Book too thin | Smaller size or wait |
| `operator_pause` (in logs) | Paused | **Resume** |

Full reason text is always on **Live → Decision** and in `logs/alpha_activity.jsonl`.

---

## Manual controls (when to use what)

| Button | When to use |
|--------|-------------|
| **Pause** | Stop new executions; keep monitoring (macro news, unsure, debugging) |
| **Resume** | Allow execution again |
| **Emergency kill** | Halt trading via kill switch (drawdown/manual panic) |
| **Clear kill** | After fixing issue — only when you understand why it fired |
| **Cancel all orders** | Type `CANCEL_ALL` — removes open offers (does not undo fills) |
| **Config reload** | After editing `config.yaml` on disk — reload next cycle |
| **Enable LIVE / dry-run** | Mode switch with typed confirmation |

**Pause ≠ Stop engine.** Paused engine still polls; it skips `execute()`. **Stop** (systemd) halts the loop entirely.

---

## TA tab (optional gate)

1. Open **TA** tab
2. Toggle **Technical analysis** on
3. Wait ~1 cycle for scores
4. When active: buy entries need **`entry_buy_allowed`** (buy score ≥ threshold)

Use TA when you want entries filtered by indicators. Disable for pure inventory+edge logic.

---

## Logs to watch

```bash
tail -f logs/alpha_activity.jsonl
```

| Event | Meaning |
|--------|---------|
| `"event":"cycle"` | Normal heartbeat + decision |
| `"decision":"place_bid"` | Wanted to buy |
| `"event":"execution"` | Submit result |
| `"event":"cycle_skipped"` | Paused or risk block |

Telegram (if configured): startup, kill, cycle summaries.

---

## Live run day-one timeline (example)

| Time | Action |
|------|--------|
| T−0 | Soak complete; validate script passed |
| T+0 | `ENABLE_LIVE`; confirm LIVE badge |
| T+1 min | Cycle 1 — note Decision + Preflight |
| T+5 min | Inventory still balanced? Normal — no order yet |
| T+30 min | RLUSD-heavy? Watch for PLACE_BID |
| Order placed | Check Open offers |
| Fill | Check Brackets for TP/SL |
| Session end | Consider **Pause** or dry-run if leaving unattended |

---

## Safety rules (non-negotiable)

1. **One bot** on the Bot Account — do not run legacy market-maker live at the same time
2. **Start small** — `alpha_risk_per_trade_pct: 0.5`, `alpha_max_pending_buys: 1`
3. **Never commit** secrets
4. **Kill + dry-run** is your emergency combo
5. Alpha places **limits only** — no market orders; fills are not guaranteed

---

## Quick reference — VPS

```bash
# Deploy
bash scripts/vps_deploy_alpha.sh

# Services
systemctl restart xledgermate-alpha
systemctl restart xledgermate-alpha-hud

# Status
python -m alpha status
python scripts/alpha_validate.py
```

HUD: `http://188.245.50.229:8765` (your VPS IP)

---

## Related docs

- [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) — config reference & API
- [`ALPHA_MAINNET_CUTOVER.md`](ALPHA_MAINNET_CUTOVER.md) — migration from legacy MM
- [`ALPHA_FINAL_REPORT.md`](ALPHA_FINAL_REPORT.md) — architecture summary
