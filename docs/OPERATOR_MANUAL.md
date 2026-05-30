# XLedgerMate — Plain-English Operator Manual

*Version 1.4.0 · For humans who remember when “save” meant a floppy disk*

This guide assumes you are **not** a programmer. You have a **Bot Account** (a separate XRPL wallet just for the bot), some test XRP, and the patience to read one page at a time.

---

## What is this thing?

**XLedgerMate** is a robot that watches the XRP / RLUSD market on the XRP Ledger and posts **buy and sell offers** for you — like a shopkeeper who keeps adjusting prices on the shelf.

- It uses **only** your **Bot Account** (not your main “Mangie” wallet).
- On **testnet**, the money is play money. Prices can look weird. That is normal.
- By default it runs in **dry-run** mode: it *pretends* to trade so you can watch without risk.

---

## How to start it (the easy way)

1. Open the project folder (`xledgermate`).
2. **Double-click `run.bat`.**
3. Wait. Two things should happen:
   - A black window (the **engine** — the worker).
   - Your web browser opens to **http://localhost:8501** (the **control panel**).

If the browser does not open, type that address in Chrome or Edge yourself.

**To stop:** Close the browser tab if you like, but also close the black engine window — or use **Stop Bot** in the Dashboard (see below).

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
Portfolio can rise when **mid moves** even if you did not trade (common when you are XRP-heavy and RLUSD/XRP mid dips). **Session MTM P&L** includes that. **Balance Δ P&L** stays near zero until a fill or fee changes XRP/RLUSD balances. Both reset when you restart the engine.

Turn **Live refresh (5s)** on in the left sidebar if you want numbers to update automatically.

### Controls (the knobs)

- **Three sliders** — How big each order “shelf” is (Level 1, 2, 3). Start small on testnet.
- **Base spread & refresh time** — How wide the prices are and how often the bot rearranges offers.
- **Dry run** — Leave **ON** until you deliberately want real testnet orders.
- **Trading enabled** — Master switch; off means the bot thinks but does not trade.

**Defensive quoting** (same tab):

- **Edge strictness** — Scales your profile’s built-in minimum edge (Low / Normal / Strict). Each profile owns its own target (e.g. `tight_spread` ≈ 0.08%).
- **Dynamic min edge** — Optional: adapts required edge to live book spread (never above profile cap).
- **Max daily drawdown %** — Kill switch if portfolio drops this much in a day (default **10%**; range 2–25% in GUI).
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

- Testnet vs mainnet, RPC URLs, Telegram alerts, **Emergency stop**, cancel all offers.
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
| “Preflight failed” | Read the red/yellow messages; usually trust line, zero sizes, or no mid price. |
| `amendmentBlocked` / “need upgrade” | Your **mainnet RPC** hit an outdated node (common on `xrplcluster.com`). In **Advanced**, set Mainnet RPC to `https://s1.ripple.com:51234`, **Save Config**, retry. |
| Spread check red on mainnet | Planned quotes are too far from **live** best bid/ask. Stay in **dry-run**; adjust **Live spread guard** on Controls or profile until Dashboard shows **Spread check OK**. Live orders are blocked until it passes. If the engine log says `spread_check=OK` but the panel shows FAIL, **Stop Bot → Start Bot** after an update (v1.3.3+ shows the engine’s last-cycle result). |

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

- Current version: **1.4.0** (see `VERSION` file).
- What changed release-by-release: **`CHANGELOG.md`** in the project folder.
- Roadmap to “great” MM (checklist): **[`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)**.

---

## One sentence summary

**Double-click `run.bat`, use the Dashboard, keep dry-run on until you trust the vitals, save config after changes, and never put your main life savings wallet secret in this app — only the Bot Account.**

*Questions? Read the yellow/red messages in the GUI first; they are usually telling the truth.*
