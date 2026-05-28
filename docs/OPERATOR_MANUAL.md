# XLedgerMate — Plain-English Operator Manual

*Version 1.1.0 · For humans who remember when “save” meant a floppy disk*

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

## The control panel — five tabs

Think of it like five drawers in a desk.

### Dashboard (where you live)

- **Start Bot** — Turns the worker on (if it was off).
- **Stop Bot** — Tells the worker to quit politely.
- **Run One Cycle** — One heartbeat: check balances, prices, maybe refresh quotes. Good for testing.

You will see:

- **Green “RUNNING”** or stopped status.
- **Balances** — XRP on top, RLUSD underneath in smaller text.
- **Prices** — Bid / mid / ask (how much RLUSD per 1 XRP).
- **Quote ladder** — The three levels the bot *wants* to post.

Turn **Live refresh (5s)** on in the left sidebar if you want numbers to update automatically.

### Controls (the knobs)

- **Three sliders** — How big each order “shelf” is (Level 1, 2, 3). Start small on testnet.
- **Base spread & refresh time** — How wide the prices are and how often the bot rearranges offers.
- **Dry run** — Leave **ON** until you deliberately want real testnet orders.
- **Trading enabled** — Master switch; off means the bot thinks but does not trade.

After changing anything important: click **Save Config** in the sidebar.

### Bot Account (wallet stuff)

- Paste your bot **address** and **secret** (the secret is like a password — never email it, never commit it to GitHub).
- **Fund** — Send **test XRP** to the address shown.
- **Trust line** — Lets the account hold RLUSD. Click the button once, or use tryrlusd.com with the **same** address.
- **Send out** — Move coins to another address (e.g. back to Mangie). Stop the bot first.

### Advanced (for later)

- Testnet vs mainnet, RPC URLs, Telegram alerts, **Emergency stop**, cancel all offers.
- Log file locations are listed at the bottom.

### History (charts and diary)

- Price chart over time (needs a few cycles running).
- Recent **decisions** — what the bot was thinking.

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

---

## Safe order of operations (testnet)

1. Set bot address + secret → **Save Config**.
2. Fund with **test XRP** (faucet or transfer).
3. Leave **Dry run ON** → **Start Bot** → watch Dashboard for a while.
4. **Setup RLUSD trust line** when ready.
5. Get test RLUSD from [tryrlusd.com](https://tryrlusd.com) (same bot address).
6. Turn off **Fund with XRP only** in Controls if you want buys and sells.
7. Only then consider **Dry run OFF** and **tiny** order sizes for a live testnet trial.

---

## When something looks wrong

| Symptom | What to try |
|---------|-------------|
| White or empty screen | Restart `run.bat`; hard-refresh browser (Ctrl+Shift+R). Turn off Live refresh temporarily. |
| Bot says STOPPED | Click **Start Bot**. Check address/secret saved. |
| RLUSD is 0 | Normal until faucet pays you after trust line exists. |
| Price looks insane (millions) | Stop Bot → Start Bot again (kills stale engines). |
| Kill switch active | Advanced tab → **Clear kill switch** after you understand why it fired. |
| “Preflight failed” | Read the red/yellow messages; usually trust line, zero sizes, or no mid price. |

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

- Current version: **1.1.0** (see `VERSION` file).
- What changed release-by-release: **`CHANGELOG.md`** in the project folder.

---

## One sentence summary

**Double-click `run.bat`, use the Dashboard, keep dry-run on until you trust the vitals, save config after changes, and never put your main life savings wallet secret in this app — only the Bot Account.**

*Questions? Read the yellow/red messages in the GUI first; they are usually telling the truth.*
