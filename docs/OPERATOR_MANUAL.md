# XLedgerMate — Plain-English Operator Manual

*Version 1.4.2 · For humans who remember when “save” meant a floppy disk*

> **Production (VPS / live MM, v2.1+):** Market making runs as **`ws-engine`** with the operator **HUD at port 8765** (`http://YOUR_VPS:8765`). Runtime state lives in `logs/runtime_state.json`. **WS HUD** is the live operator surface (Live, Inventory, Intelligence, Metrics, Book, Reports). The Streamlit panel at **:8501** below is the **legacy lab** UI — still useful for replay analysis, not the live soak path. See [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md) and [`WS_ONLY_MIGRATION.md`](WS_ONLY_MIGRATION.md).

This guide assumes you are **not** a programmer. You have a **Bot Account** (a separate XRPL wallet just for the bot), some test XRP, and the patience to read one page at a time.

---

## What is this thing?

**XLedgerMate** is a robot that watches the XRP / RLUSD market on the XRP Ledger and posts **buy and sell offers** for you — like a shopkeeper who keeps adjusting prices on the shelf.

- It uses **only** your **Bot Account** (not your main “Mangie” wallet).
- On **testnet**, the money is play money. Prices can look weird. That is normal.
- By default it runs in **dry-run** mode: it *pretends* to trade so you can watch without risk.

---

## How to start it (the easy way)

**Production (recommended):** Double-click `run.bat` or run `.\run.ps1`. This starts **ws-engine** and the **WS HUD** at **http://localhost:8765**.

**Legacy lab (Streamlit):** `python main.py --mode gui` → **http://localhost:8501** (sections below describe this UI).

1. Open the project folder (`xledgermate`).
2. **Double-click `run.bat`.**
3. Wait. Two things should happen:
   - A black window (**ws-engine** — the live market maker).
   - A second window serving the **WS HUD** at **http://localhost:8765**.

For the legacy Streamlit lab only, use `python main.py --mode gui` and open **http://localhost:8501**.

**To stop:** Close the engine/HUD windows — or use **Stop Bot** in Streamlit Dashboard if you are on the lab UI (see below).

---

## WS HUD (production — port 8765)

Use this surface on VPS or when running `live_pure_as_tester --serve-hud`. Hard refresh after HUD updates (**Ctrl+Shift+R**).

| Tab | What you see |
|-----|----------------|
| **Live** | Book, reservation, would-quote, G2/G7, quote ladder, session fills, soak strip |
| **Inventory** | Balances, **Wallet Δ** (all portfolio change — includes deposits) |
| **Intelligence** | Competitors, peer lane, Grok analyze |
| **Metrics** | §7 grades + **G6 activation** (tier, hold/FAIL, attention list) |
| **Book** | Depth chart, our L1–L3 ladder (L2/L3 planned until ledger sync) |
| **Reports** | Read-only soak reports from `logs/` |

**Left sidebar — wealth (RLUSD-stable):** Session Δ, skim / spot / rebal split, XRP @ mid. **Skim Δ** on the soak strip is **trading spread capture only** (engine counter) — not the same as Wallet Δ or a deposit.

**G6 `hold`:** On Metrics, red tier means spread capture needs attention (often high win rate but low bps/fill). Gate FAIL — stay conservative; no automatic size-up. See [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md).

**Deploy during soak:** HUD-only changes restart **`xledgermate-ws-hud`** only — leave **`xledgermate`** (ws-engine) running unless planned.

---

When the engine is running, a **marquee** under the logo shows the latest status in plain English:

- **Policy line first** — e.g. `Policy: near-touch 0.085% | relevant ≤0.10% from touch` (how close quotes sit vs the live book).
- **Pause flags** — “bids paused” / “asks paused” when inventory or toxicity rules stop a side.
- **Fill quality** — mixed / poor when recent fills look adverse.
- Long **decision text** is split into short segments so you can scan without opening the log.

If the engine is stopped, the ticker says so and shows the **last saved cycle** from `logs/runtime_state.json`.

---

## Banner at the top (read this first)

When the engine is running, a colored banner tells you the mode:

| Banner | Meaning |
|--------|---------|
| **Blue — DRY-RUN** | Rehearsal only. No orders hit the ledger. **Recommended default.** |
| **Yellow — LIVE on TESTNET** | Real testnet orders (play money). |
| **Red — MAINNET LIVE TRADING** | Real funds. Only use when you mean it. |

---

## Market conditions (top of the page)

To the right of the logo you will see **Market conditions** — how the bot reads the book *right now*:

- **Profile** — Which risk posture is active (`Safe`, `Thin liq`, etc.).
- **Market** — Favorable, Neutral, Defensive, or Hostile (color-coded).
- **Vol / Liq / Spread** — Volatility level, liquidity score, and how wide the book is.
- **Health score** — 0–100 summary in the caption below (higher = nicer for quoting).
- **Suggested profile** — e.g. **Tight spread** when volatility is low, liquidity is high, and the book is tight; **Safe** or defensive profiles when conditions worsen. **Profit mode** is never suggested automatically — select it manually on Controls if you want maximum aggression. Green check if suggestion matches your active profile; otherwise use **Apply** (no separate Save Config needed).

The Dashboard also shows **Why these quotes?** when the engine explains its spread/size choices (e.g. “defensive market → wider + smaller”).

**Session insights** (below market suggestion) summarizes **fills since the last engine start** from `logs/trades_YYYY-MM.csv`:

- **Spread capture** — sum of `profit_xrp_equiv` on BUY/SELL rows (economics of fills, not MTM).
- **Per fill** — average capture per trade.
- **Inventory** — XRP share vs your target (e.g. 55%).
- **Buy / sell volume** — net XRP bought vs sold in the session window.

Defensive/cautious headlines also scroll in the **top status marquee** (above the quote feed). The dashboard section shows metrics and suggestions only (no duplicate alert boxes). Bullet suggestions call out dynamic edge, cancel/fill churn, and inventory skew when relevant.

**Top marquees (all pages):**

1. **Status** — mainnet/dry-run, no offers, spread check, profile sync, session defensive/cautious.
2. **Quote feed** — policy label, pauses, fill quality, quote decision summary.

### Engine (sidebar + Controls → Engine)

| Button | Action |
|--------|--------|
| **Start** | Launch `main.py --mode engine` in a new console window |
| **Stop** | Request graceful stop, then terminate engine process(es) |
| **Restart engine** | Stop + **clear kill switch** + start — also resets in-memory toxic refresh pause; config unchanged |
| **Clear kill switch** | Required if kill is ON — kill is stored in `logs/kill_switch.json` and **survives** engine restart until cleared |

**Toxic-fill kill (mainnet pilot):** Default is **off** (`toxic_fill_kill_enabled: false`). Bad markouts still trigger **refresh pause** and **off-book** policy on the **safe** profile — you are protected without a full halt. Turn toxic kill **on** only after you want a hard stop at e.g. **75% over 12+ fills**. Configure under **Advanced → Safety & emergency**.
| **Run one cycle** | Single `once` cycle without leaving the engine running |

**Refresh paused** (toxic ratio ≥ profile limit with ≥3 recent fills) blocks cancel/replace but keeps existing ledger offers. If you have **no offers** and are stuck, use **Restart engine**, or wait for the bot to **probe refresh** after ~3 full cycles (~3 min on safe) with an empty storefront, then **reset the fill window** after ~6 empty cycles.

---

## The control panel — five tabs

Think of it like five drawers in a desk.

### Dashboard (where you live)

- **Start Bot** — Turns the worker on (if it was off).
- **Stop Bot** — Stops the engine (on Windows, kills both the launcher and worker process). If cycles keep logging, click Stop again or close the **XLedgerMate Engine** PowerShell window.
- **Run One Cycle** — One heartbeat: check balances, prices, maybe refresh quotes. Good for testing.

You will see:

- **Green “RUNNING”** or stopped status.
- **Balances** — XRP on top, RLUSD underneath in smaller text.
- **Prices** — Bid / mid / ask (how much RLUSD per 1 XRP).
- **Session MTM P&L** — Change in total portfolio value (XRP + RLUSD at mid) since this engine run. **Matches the portfolio number in the cycle log.**
- **Balance Δ P&L** — Change from wallet balances only (fills, fees), ignoring mid price moves on RLUSD you already hold.
- **Quote ladder** — The three levels the bot *wants* to post.

**Session P&L — why two numbers?**  
Portfolio can rise when **mid moves** even if you did not trade (common when you are XRP-heavy and RLUSD/XRP mid dips). **Session MTM P&L** includes that. **Balance Δ P&L** stays near zero until a fill or fee changes XRP/RLUSD balances — **use Balance Δ** (not MTM alone) for whether holdings are really growing through Gate 2 and beyond. Both reset when you restart the engine.

If the book is **inverted** (bid much higher than ask), v1.4.3+ keeps the **last valid mid** for portfolio display and skips bogus drawdown marks. If you ever see **400+ XRP** on a **~247** wallet, stop and **Restart engine** after pulling latest code; do not trust that readout.

Turn **Live refresh (5s)** on in the left sidebar if you want numbers to update automatically.

### Controls (the knobs)

- **Three sliders** — How big each order “shelf” is (Level 1, 2, 3). Start small on testnet.
- **Base spread & refresh time** — How wide the prices are and how often the bot rearranges offers.
- **Dry run** — Leave **ON** until you deliberately want real testnet orders.
- **Trading enabled** — Master switch; off means the bot thinks but does not trade.

**Defensive quoting** (same tab):

- **Edge strictness** — Scales your profile’s built-in minimum edge (Low / Normal / Strict). Each profile owns its own target (e.g. `tight_spread` ≈ 0.08%).
- **Dynamic min edge** — Optional: adapts required edge to live book spread (never above profile cap). **Safe** preset leaves this **off** until you turn it on; **tight_spread** / **profit_mode** presets turn it **on**.
- **Pause side at skew (±)** — One slider for both modes: when XRP share is this far from target (default **12%**), the bot pauses the vulnerable side (inventory bailout).
- **Max daily drawdown %** — Kill switch if portfolio drops this much in a day (default **10%**; range 2–25% in GUI). Measured on **full portfolio** (XRP + RLUSD at mid). If the book feed is stale or crossed for one cycle, the engine **skips** that drawdown check instead of counting RLUSD as zero (avoids false kills like “39% drawdown” while session P&amp;L is flat).
- **Auto profile switching** — Off by default. When on, after you have been idle for the configured minutes, the engine switches only when the **Suggested profile** stays the same for **several cycles** and the **cooldown** since the last auto-switch has passed. Stops rapid flipping when the book jitters at tier boundaries.
- **Auto-switch after idle (min)** — How long you must leave it alone before auto-switch can fire (default 120 min).

After changing anything important: click **Save Config** in the sidebar.

### Bot Account (wallet stuff)

- Paste your bot **address** and **secret** (the secret is like a password — never email it, never commit it to GitHub).
- **Fund** — Send **test XRP** to the address shown.
- **Trust line** — Lets the account hold RLUSD. Click the button once, or use tryrlusd.com with the **same** address.
- **Disable RLUSD rippling** — Turns off rippling (sets **No Ripple**) on the RLUSD trust line. Recommended for the bot wallet so other payments cannot route through your RLUSD balance. Same as fixing the warning in Xaman.
- **Send out** — Move coins to another address (e.g. back to Mangie). Stop the bot first.

### Advanced (for later)

- Testnet vs mainnet, RPC URLs, Telegram alerts, **Safety & emergency** / **Kill settings**, **Emergency stop**, cancel all offers.
- **Kill settings** (save with **Save kill settings**):
  - **Spread-check fail cycles → kill** — consecutive spread validation failures (default 8; `0` = off).
  - **Session balance loss → kill (XRP)** — halts if **Balance Δ P&L** since engine start is below **−this** (default **0.35**; `0` = off).
  - **Session balance kill min fills** — only after this many session fills (default **25**).
  - **Toxic-fill kill** — optional hard stop on toxic ratio (default **off** on pilot; use off-book instead).
- Log file locations are listed at the bottom.

### History (charts and diary)

- **Session statistics (live)** — Same portfolio, P&L, drawdown, vol, and liquidity as the engine; refreshes every **5s** with **Live refresh** on (same as Dashboard). Includes a **portfolio value** chart from `logs/portfolio_snapshots.csv`.
- Price chart over time (one point per engine cycle, ~60s apart).
- Recent **decisions** — what the bot was thinking.

If numbers look frozen, confirm **Live refresh (5s)** is on and check **Engine state updated** under the metrics. After an engine restart, **Session MTM P&L** starts at **0** until mid or balances move.

---

## Words we refuse to spell out in acronym soup

| Term | Plain English |
|------|----------------|
| **Dry run** | Rehearsal. No real orders on the ledger. |
| **Live** | Real orders. Real offers. Still testnet if testnet is on. |
| **Bid** | An offer to **buy** XRP (you spend RLUSD). |
| **Ask** | An offer to **sell** XRP (you receive RLUSD). |
| **Mid** | Middle of the market price. |
| **Preflight** | Bot’s checklist before it quotes: enough money? trust line? sane price? |
| **Kill switch** | Bot hit the panic wire (often drawdown). Stops trading until you clear it. |
| **Trust line** | Permission slip to hold RLUSD in that wallet. |
| **Market condition** | Bot’s read of the book: Favorable → Hostile. Defensive = widen and shrink. |
| **Profile** | Named risk posture (`safe`, `thin_liquidity`, etc.). Drives spreads and size. |
| **Toxic ratio** | Share of recent fills classified adverse (markout). Drives defensive sizing and pauses. |
| **Toxic @30s** | Same idea using only fills with a completed 30-second markout — can read **100%** with only one bad fill; use **Toxic ratio** for the fuller picture. |
| **Quoting policy** | Short line in the ticker: at-touch, near-touch, spread-mid, or off-book when toxicity is high. |

### Dashboard metrics (Tier 2)

| Metric | Plain English |
|--------|----------------|
| **Toxic ratio** | Adverse fills ÷ recent fills. Above your profile’s refresh limit (~22% on **safe**), the bot may **pause order refresh** until quality improves. |
| **Toxic @30s** | Stricter short-horizon view; noisy with few fills. |
| **Cancel / fill** | How many cancels per fill this session — lower is better (queue preservation). |
| **Refresh cadence** | Poll interval vs full refresh (from active profile). |

---

## Safe order of operations (testnet)

1. Set bot address + secret → **Save credentials** on Bot Account tab.
2. Fund with **test XRP** (faucet or transfer).
3. Leave **Dry run ON** → **Start Bot** → watch Dashboard for a while.
4. **Setup RLUSD trust line** when ready.
5. Get test RLUSD from [tryrlusd.com](https://tryrlusd.com) (same bot address).
6. Turn off **Fund with XRP only** in Controls if you want buys and sells.
7. Only then consider **Dry run OFF** and **tiny** order sizes for a live testnet trial.

---

## Mainnet go-live gate (`mainnet-prep` complete → `mainnet-pilot`)

Use this checklist **before** you turn off dry-run on mainnet. Every item should be green.

| Step | What to verify |
|------|----------------|
| 1 | **Advanced** → testnet **OFF**, Mainnet RPC = `https://s1.ripple.com:51234` → **Save Config** |
| 2 | Bot credentials saved (`sn...` or family seed); **Spread check** does not say “credentials mismatch” |
| 3 | **RLUSD trust line** on ledger (Bot Account tab) |
| 4 | **Stop Bot** → **Start Bot** after any code update (loads latest spread logic) |
| 5 | **10+ dry-run cycles** with Dashboard **Spread check OK** (table shows asks near best ask) |
| 6 | **Controls** → tiny **order_sizes** (e.g. one level at 5–10 XRP); **Live spread guard** left on |
| 7 | **Emergency stop** tested once in dry-run (you know where it is) |
| 8 | Only then: **Dry run OFF** for a **small live pilot** — watch `logs/trades_*.csv` and open offers |

Stay on **dry-run** until step 5 passes consistently. The engine **blocks live orders** if spread check fails.

---

## When something looks wrong

| Symptom | What to try |
|---------|-------------|
| White or empty screen | Restart `run.bat`; hard-refresh browser (Ctrl+Shift+R). Turn off Live refresh temporarily. |
| Bot says STOPPED | Click **Start Bot**. Check address/secret saved. |
| Stop Bot but log still updates | Restart Streamlit after an update; use **Stop Bot** again or close the Engine window. |
| RLUSD is 0 | Normal until faucet pays you after trust line exists. |
| Price looks insane (millions) | Stop Bot → Start Bot again (kills stale engines). |
| Kill switch active | Advanced tab → **Clear kill switch** after you understand why it fired. Page refreshes; drawdown baseline resets on next cycle. |
| Kill: “Session balance PnL … limit” | **Advanced → Kill settings**: session lost more than **Session balance loss → kill** (default **0.35 XRP**) after **min fills** (default **25**). Uses balance PnL at honest mids — set **0** to disable. Clear kill → restart if you want a fresh session baseline. |
| Kill: “Spread check failed 8 consecutive cycles” | Quotes were too far from the live book — **or** (pre-v1.4.4) bad/inverted book ticks stacked failures. v1.4.4+ pauses on bad feed **without** kill streak. Clear kill → **Restart engine** when bid/ask look normal (~1.17). |
| Kill: “Daily portfolio drawdown 40%” but wallet looks fine | Often a **stale book** tick (v1.4.2+ skips that). Clear kill → **Restart engine**; check log for `crossed or stale` / `ask=0`. |
| “Preflight failed” | Read the red/yellow messages; usually trust line, zero sizes, or no mid price. |
| `amendmentBlocked` / “need upgrade” | Your **mainnet RPC** hit an outdated node (common on `xrplcluster.com`). In **Advanced**, set Mainnet RPC to `https://s1.ripple.com:51234`, **Save Config**, retry. |
| Spread check red on mainnet | Planned quotes are too far from **live** best bid/ask. Stay in **dry-run**; adjust **Live spread guard** on Controls or profile until Dashboard shows **Spread check OK**. Live orders are blocked until it passes. If the engine log says `spread_check=OK` but the panel shows FAIL, **Stop Bot → Start Bot** after an update (v1.3.3+ shows the engine’s last-cycle result). |
| **Toxic @30s** stuck at 100% | Often **one or two fills** and a bad 30s markout — not “every fill ever.” Check **Toxic ratio**, ticker **Policy**, and whether **bids paused** after buying into a falling market. |
| Quotes far from touch but “OK” | On thin books the bot may use **near-touch** (small backoff) or **spread-mid** with a **visibility cap** (~8–14% from touch by profile) — read the **Policy** line in the ticker. |

**Emergency stop** (Advanced) — Disables trading, stops engine, sets kill switch, cancels offers (if not dry-run). Use when you want everything off *now*.

---

## Files the bot writes (for your records)

All in the `logs` folder (created automatically):

| File | What it is |
|------|------------|
| `trades_2026-05.csv` (month changes) | **Tax-ish ledger** — buys, sells, transfers, major events. Give this to your accountant, not to Facebook. |
| `portfolio_snapshots.csv` | Balance snapshot every cycle. |
| `transfers.csv` | When you used **Send out**. |
| `decisions.jsonl` | Bot diary (technical). |
| `runtime_state.json` | Current snapshot for the GUI. |
| `operator_activity.json` | Last time you saved config or applied a profile (for auto-switch idle timer). |

Dry-run does **not** log fake buys/sells to the tax CSV. Live testnet does.

---

## Telegram (optional)

If you want a ping on your phone:

1. Create a bot with **@BotFather** on Telegram.
2. Put the **token** and your **chat ID** in Advanced.
3. **Save Config** → **Send Telegram test**.

Leave “notify each cycle” off unless you enjoy constant buzzing.

---

## Version & history

- Current version: **1.4.2** (see `VERSION` file). WS HUD operator detail: [`WS_AS_MANUAL.md`](WS_AS_MANUAL.md).
- Code audit notes (quoting conflicts resolved): **[`AUDIT_REPORT.md`](AUDIT_REPORT.md)**.
- What changed release-by-release: **`CHANGELOG.md`** in the project folder.
- Roadmap to “great” MM (checklist): **[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)**.

---

## One sentence summary

**Double-click `run.bat`, use the Dashboard, keep dry-run on until you trust the vitals, save config after changes, and never put your main life savings wallet secret in this app — only the Bot Account.**

*Questions? Read the yellow/red messages in the GUI first; they are usually telling the truth.*
