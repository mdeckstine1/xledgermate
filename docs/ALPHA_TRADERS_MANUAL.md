# xLedgerMate Alpha — Trader's Manual

**Organized by HUD tab and card.** Scenarios live in [Appendices](#appendices--scenario-playbook) at the end.

Written for operators who have watched too many green candles turn red.

For install, VPS, dry-run cutover, and credentials: [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) · [`ALPHA_LIVE_RUN_MANUAL.md`](ALPHA_LIVE_RUN_MANUAL.md).

---

## How to read this manual

1. **Part 0** — what the bot does, lifecycle, data speed (read once).
2. **Part 1** — walk the HUD left-to-right: each **tab**, each **card**, with **Bull / Neutral / Bear** stance.
3. **Part 2** — funding, coupling, troubleshooting, soak checklists, SKYNET tuning.
4. **Appendices** — lettered scenario recipes (A–Z) when Decision reason matches a pattern.

**Nav order:** Live · TA · Brackets · Open offers · Reports · Activity · **PRO** · SKYNET · Config

---

## Table of contents

- [Part 0 — Foundations](#part-0--foundations)
  - [Pro accumulator loop](#pro-accumulator-loop-read-once)
- [Part 1 — HUD guide](#part-1--hud-guide-by-tab-then-card)
  - [Always visible](#always-visible--header--sidebar)
  - [Live tab](#live-tab)
    - [Accumulation / opportunity](#accumulation--opportunity-watch-card)
    - [RLUSD reload](#rlusd-reload-card)
  - [TA tab](#ta-tab)
  - [Brackets tab](#brackets-tab)
  - [Open Offers tab](#open-offers-tab)
  - [Reports tab](#reports-tab)
  - [Activity tab](#activity-tab)
  - [PRO tab](#pro-tab)
  - [SKYNET tab](#skynet-tab)
  - [Config tab](#config-tab)
- [Part 2 — Operator playbook](#part-2--operator-playbook)
- [Appendices — Scenario playbook](#appendices--scenario-playbook)

---

## Part 0 — Foundations

## What this bot actually does

xLedgerMate Alpha is a **limit-order bag-growth bot** on XRPL (XRP / RLUSD).

- It **does not** market-buy or market-sell.
- It **does not** have a manual “Buy now” button.
- It places **limit bids** when inventory is RLUSD-heavy **or** when the **accumulation regime** arms on bull/breakout tape (even if inventory is only mildly RLUSD-heavy or balanced).
- It can **reload RLUSD** by selling a controlled slice of XRP in **post-run chop** when dry powder is below the deploy floor (see [RLUSD reload](#rlusd-reload-card) — not the same as classic strength sells).
- When a buy fills, it automatically places **take-profit + stop-loss** sells (a bracket).
- It can **trail** those exits as price moves in your favor.
- After a TP or SL exit, a **re-entry gate** can block impatient reloads.

**Core philosophy:** We are not here to “balance” for balance’s sake. We deploy RLUSD when the book is weak and we are under our XRP target. We take profit on strength. We try to end up with **more XRP** — not just more activity.

The bot has **eyes** (technical analysis) and **hands** (limit orders + brackets). **You** are the brain that decides how aggressive those hands should be — via the HUD at `:8765`.

For install, VPS, dry-run cutover, and the **Config** tab (credentials + withdraw), see [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md) and [`ALPHA_LIVE_RUN_MANUAL.md`](ALPHA_LIVE_RUN_MANUAL.md). This manual is about **how it feels to run it**.

### Recent engine capabilities (2026)

| Area | What changed |
|------|----------------|
| **Accumulation regime** | First-class **bull/breakout deploy** when tape arms — not only dip-only `weakness_deviation`. Tighter offset, chase stale drift, up to 3 pending buys, re-entry bypass on rips. HUD **Accumulation / opportunity** card + scorecard. |
| **Opportunity watch** | Header **ready** badge + Live card: `idle` → `watching` → `armed` → `executing` / `blocked`. SKYNET scenario **V**. |
| **RLUSD reload** | **Post-run chop** funding sells to refill deploy floor (~45 XRP-equiv RLUSD default). **Fund then bid** — accumulation blocked until floor met. HUD **RLUSD reload** card. SKYNET scenario **W** (reload). |
| **Tape participation** | Waives lagging **bearish TA** on closed 5m bars when live tape is up (inside buy path). |
| **Re-entry** | Scratch/breakeven SL tier, cluster guard, recovery early release, post-clear bid spacing — all tunable in **Live → Re-entry → SL mitigations**. |
| **PRO / defensive** | Alpha Replay, auto-defensive circuit (recent-window gate, manual release suppress), treasury placeholder. |
| **TA / OHLC** | Completed bars advance correctly on live ticks; warmup no longer stuck after rebuild. |
| **Elliott 5-wave** | Zigzag pivots on ~50 closed OHLC bars — wave label (`W3↑`, `W4↑`), trend (`bullish_impulse` / `bearish_impulse`), graded buy/sell contribution. **Does not arm accumulation alone.** |
| **Divergence detector** | Pivot-based **RSI / Stoch** (optional MACD) disagreement — boosts buy/sell scores; surfaced on TA tab, accumulation scorecard, SKYNET context. HUD toggle **`alpha_ta_divergence_enabled`**. |
| **Volume confirmation** | Last closed bar **tick_count** vs rolling avg — spike boosts move/breakout scores; low activity dampens chop. HUD **Volume** toggle. |
| **HTF bias filter** | **1h** SMA stack (default) on cached OHLC — light multiplier on aligned LTF scores, dampens counter-trend. HUD **HTF bias** toggle. |
| **SKYNET gate diagnostics** | Each Ask includes **authoritative PASS/FAIL** for dip gate, dev caps, TA breakout, structure arm, momentum, accumulation — SKYNET should not guess thresholds. |
| **Scale-phase dev caps** | Operator overrides `alpha_accumulation_max_deviation` / `alpha_bull_run_max_deviation` (e.g. **0.08**) let accumulation arm when mildly XRP-heavy; still blocked by `alpha_max_inventory_imbalance_pct` (default **0.10**). |
| **Reload fill tracking** | Funding sells record fills in `reload_session` — committed RLUSD and deploy floor math stay accurate. |
| **Market metrics** | Per-cycle ATR%, realized vol, spread, depth, regime in **Market Conditions** + `logs/alpha_market.db`. |
| **Tax CSV** | Strength sells log `cost_basis_rlusd_per_xrp` and `proceeds_usd` like bracket exits. |
| **Restart safety** | Same bracket TP/SL re-detected on restart no longer resets re-entry cooldown. |

### Pro accumulator loop (read once)

Classic Alpha only bought when **RLUSD-heavy** (`dev ≤ −weakness`). On a rip with **balanced** inventory, Decision said `balanced dev=…` and nothing happened.

**Today the engine runs two coordinated regimes:**

```text
1. ACCUMULATION (deploy RLUSD → XRP on tape)
   PRIMED / WATCHING → ARMED → EXECUTING
   Signals: breakout, tape participation, early ARM on slope, bull SKYNET regime
   Knobs bundle: tight buy offset (~0.06%), chase drift (~0.08%), max_pending 3, RLUSD spend budget (8h window)

2. RLUSD RELOAD (fund dry powder in chop — not into the rip)
   WATCHING (low RLUSD, still breaking out) → ARMED (post-run chop) → EXECUTING → FUNDED
   Sells small XRP slice at tight ask when structure neutral near highs after a proven run
   Policy 4: accumulation bids BLOCKED until deploy floor met (~45 XRP-equiv RLUSD)

Typical sequence on a multi-hour move:
  Rip → accumulation may ARM but starve if RLUSD thin → RELOAD WATCHING
  Stall/chop → RELOAD ARMED → funding ask fills → FUNDED
  Next leg or dip → accumulation unblocked → bids with real budget
```

**You are not the knob-twiddler for every cycle** — read the **Live cards** and **Decision reason**. SKYNET **Ask** on either card for context.

**Config keys (defaults on):** `alpha_accumulation_regime_enabled`, `alpha_reload_regime_enabled` in `config.yaml` — see [Appendix X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) · [Appendix Y](#appendix-y--rlusd-reload-post-run-chop-funding).

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
| **Ready badge** (header) | **Accumulation / reload phase** — `watching`, `armed`, `executing`, `blocked` (not the same as posture `patient`) |
| **Accumulation / opportunity** (Live) | Bull/breakout readiness, scorecard (bids/fills/chase/missed move), **Ask SKYNET** |
| **RLUSD reload** (Live) | Deploy floor, shortfall, chop timing, **accumulation blocked** when under-funded |
| **Quote age** | How fresh the L1 book patch is (sidebar). Stale >25s = waiting for next book sample |
| **Chart** | Candle history (lags) + **live** bid/ask/mid lines (1s HUD poll). Candles right-aligned |
| **Market Conditions** | Spread, **bid/ask depth ±1% of mid**, max buy size, best bid/ask, **regime / ATR% / realized vol** |
| **Decision** | Last action + **reason** — this is your best friend when confused |
| **Brackets tab** | Open positions: pending buys vs active brackets; size, RLUSD, TP/SL, **Trail** flags |
| **Open Offers** | Raw ledger orders (✕ cancel, ✎ reprice) |
| **Reports** | Cycle status text + path to monthly **tax CSV** (`logs/trades_YYYY-MM.csv`) |
| **PRO** | **Alpha Replay** (realized TP/SL, verdict), **auto-defensive circuit**, treasury placeholder |
| **SKYNET** | SKYNET advisor, Agent Smith, operator phase / market regime |
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

**Regime & volatility:** The same card shows **regime**, **ATR%**, and **realized vol** from the latest engine cycle. Values are also stored in `logs/alpha_market.db` for history. Use them to sanity-check whether offsets and cooldowns match current chop — advisory context, not a standalone trade signal.

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

## Part 1 — HUD guide (by tab, then card)

Nav order: **Live · TA · Brackets · Open offers · Reports · Activity · PRO · SKYNET · Config**

Every card below uses the same lens:

- **What it is** — what you are looking at on screen
- **How to use it** — when to glance, when to act
- **Bull / Neutral / Bear** — how tape regime should color your reading (SKYNET **market regime** mirrors this for advice)
- **Narrative** — one sentence of operator story
- **See also** — deep-dive **Appendices** at the end of this manual

---
### Always visible — header & sidebar

The ticker and left rail update every **~1 second**. They are your pulse when you are not on the Live tab.

#### Ticker & mode badges

**What it is:** Top bar: version, network, LIVE/dry-run, **posture** (`patient` / buying), **ready** badge (accumulation/reload phase), pause/kill badges, freshness.

**How to use it:** First glance on login. **Posture** is inventory skew; **ready** is opportunity (`watching` → `armed` → `executing` / `blocked`). **Kill** or **Pause** mean stop tuning knobs — fix state first.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | LIVE + ready `armed`/`executing` — accumulation may bid even when `dev` is balanced; check scorecard fills. |
| **Neutral** | Chop: frequent HOLD is normal if Decision explains; reload **watching** if RLUSD below deploy floor. |
| **Bear** | Kill lit, ready `blocked`, or defensive ACTIVE — no aggression until cleared. |

**Narrative:** You open the HUD at 7am; ticker says LIVE, ready `watching`, posture `patient` — tape building, not broken.

**See also:** [Accumulation / opportunity](#accumulation--opportunity-watch-card) · [RLUSD reload](#rlusd-reload-card) · [Appendix P](#appendix-p--kill-switch-drawdown-or-pause)
#### Portfolio, inventory & P&L

**What it is:** Sidebar: mid, XRP/RLUSD balances, XRP %, deviation label, drawdown, **bag growth** (since baseline, this week, trading edge 7d), session P&L, realized 24h.

**How to use it:** **Bag growth** = portfolio size (holdings + price). **Trading edge 7d** = tax-CSV TP/SL truth. **Session P&L** is mark-to-market (can lie after deposits or on mid rip). **Realized 24h** is the short-window bleed check.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Session and realized both positive — optional scale phase on SKYNET. |
| **Neutral** | Session green, realized flat — common in chop; trust realized for edge. |
| **Bear** | Realized bleeding while session flat — open **PRO** replay; expect defensive circuit. |

**Narrative:** Session says +200 XRP after you funded yesterday — ignore it; read Realized 24h instead.

**See also:** [Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro) · [Funding changes](#funding-changes-scaling-toward-11k-xrp)
#### Quote age

**What it is:** How stale the last L1 book patch is.

**How to use it:** Stale >25s — next full book sample is coming; don't panic on one old mid tick.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Fresh quotes + rising mid — fills may still be passive-limit slow. |
| **Neutral** | 15–25s age is normal between engine cycles. |
| **Bear** | Stale during volatility — wait for fresh book before repricing bids. |

**Narrative:** Mid flickers but quote age says 18s — the chart line is live, depth card lags one cycle.

**See also:** [Data speed](#data-speed--what-updates-how-fast)

### Live tab

The command center. Decision + Market Conditions + three control decks (**Risk & entry**, **Structure & trailing**, **Re-entry**).

#### Decision

**What it is:** Last engine action (`HOLD`, `PLACE_BID`, `PLACE_ASK`) and the **reason string**.

**How to use it:** **Always read the reason before touching knobs.** It maps 1:1 to an Appendix letter in the cheat table at the end of Part 2.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | `place_bid` with weakness dev or **`accumulation`** / **`bull_run`** in reason — deployment working. |
| **Neutral** | `hold` with `max_pending_buys`, re-entry gates, or **`reload_blocks_accumulation`** — patience, not broken. |
| **Bear** | `hold` with `ta_buy_blocked bearish` after SL streak — don't lower offset; see PRO/SKYNET bear. |

**Narrative:** Decision says `reentry_sl_await_bounce` — the bot is doing what you asked after a stop.

**See also:** [Why no buys?](#why-no-buys--decision-reason-cheat-sheet) · Appendices **K**, **J**, **D**
#### Book

**What it is:** Mid and spread from the latest book patch.

**How to use it:** Compare to Brackets **entry** and Market Conditions **best bid/ask** — mid alone doesn't fill limits.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Spread tight, mid rising — eager offsets still won't fill until ask trades down. |
| **Neutral** | Typical 8–15 bps spread on RLUSD/XRP mainnet. |
| **Bear** | Wide spread or gap — consider wider offsets and lower size. |

**Narrative:** Book mid 1.029 but your bid is 1.027 — you are intentionally below the touch.

**See also:** [Appendix N](#appendix-n--bid-on-book-mid-looks-good-still-no-fill)
#### Structure

**What it is:** Short HTF trend label + summary from recent mids.

**How to use it:** Context for trailing (**BE**/**BO**) and re-entry stabilization — not a buy button.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | `breakout_up` — trailing may arm on filled bags. |
| **Neutral** | `neutral` chop — pair with TA bias, not structure alone. |
| **Bear** | `breakout_down` — post-SL re-entry waits for stabilization. |

**Narrative:** Structure says neutral while TA says bearish — re-entry after SL stays blocked.

**See also:** [Appendix K](#appendix-k--post-sl-re-entry-bot-wont-reload)
#### Brackets summary

**What it is:** Counts: pending buys, active fixed, SL trail, breakout trail, orphan bids.

**How to use it:** If pending > `max_pending_buys`, expect stale cancels or HOLD — open **Brackets** tab for detail.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Active brackets with **BE** flags — winners trailing. |
| **Neutral** | One pending buy, zero active — normal deploy queue. |
| **Bear** | Many pending, none filling — ladder clutter; don't add heat. |

**Narrative:** Summary says 4 pending but cap is 1 — engine is pruning, not ignoring you.

**See also:** [Appendix C](#appendix-c--ladder-clutter-many-pending-buys-none-filling)
#### Preflight

**What it is:** Wallet/trust-line/config readiness summary.

**How to use it:** Must be green before live quoting. Red here beats every knob tweak.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Preflight OK — focus on Decision. |
| **Neutral** | — |
| **Bear** | Preflight fail — fix trust line, balance, or config before trading. |

**Narrative:** You cranked risk to 5% but preflight says trust line missing — nothing will place.

**See also:** [Appendix P](#appendix-p--kill-switch-drawdown-or-pause)
#### Execution

**What it is:** Last cycle execution result (bid placed, dry-run skip, etc.).

**How to use it:** Confirms whether the last Decision actually hit the ledger.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | `place_bid executed` — offer on book; check Brackets. |
| **Neutral** | Skipped due to pause — expected if you paused. |
| **Bear** | Repeated skips with risk allowed — read Decision reason, not Execution alone. |

**Narrative:** Decision said PLACE_BID but Execution dry_run — you are still in sim mode.

**See also:** [Config → dry_run](#config-tab)
#### Accumulation / opportunity watch card

**What it is:** Live card for the **accumulation regime** — phase (`idle` / `primed` / `watching` / `armed` / `executing` / `blocked`), why it is in that phase, **scorecard** (bids placed, fills, chase cancels, minutes in phase, **divergence** when TA fires), and **missed move** flag when tape ripped without fills.

**How to use it:** When the chart runs but Decision says `balanced dev=…`, check here first. **ARMED** means the engine will use accumulation knobs (tighter offset, chase drift, up to 3 pending, re-entry bypass) on the next qualifying `place_bid`. **BLOCKED** usually means reload policy (under deploy floor) or risk/pause.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | `armed`/`executing` — let chase work; don’t manually widen offset unless scorecard shows repeated chase cancels with zero fills. |
| **Neutral** | `watching`/`primed` — signals building; early ARM may fire on tape+slope without full breakout. |
| **Bear** | Usually `idle`/`blocked` — accumulation should not fight bear tape; trust defensive. |

**Narrative:** Card says **ARMED**, scorecard **0 fills**, missed move **yes** — you under-funded RLUSD; check **RLUSD reload** card.

**See also:** [Pro accumulator loop](#pro-accumulator-loop-read-once) · [Appendix X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) · SKYNET playbook **V** (not operator phase U)
#### RLUSD reload card

**What it is:** Live card for the **reload regime** — phase, RLUSD vs **deploy floor** (default ~45 XRP-equiv), shortfall, whether **accumulation is blocked**, and last funding sell in the 8h window.

**How to use it:** Reload is **not** classic strength sell (`dev ≥ 4%`). It fires in **post-run chop** — neutral/digesting structure near recent highs after a proven run, when slope/tape are not still ripping. **Policy 4** (`alpha_reload_block_accumulation_until_funded`): bids wait until floor is met.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | During the rip: **WATCHING** (“wait for chop”) — correct; do not expect funding sell into breakout. |
| **Neutral** | **ARMED** after stall — expect `place_ask` with `reload_funding` reason; then accumulation unblocks. |
| **Bear** | Reload rarely arms; if RLUSD is ample, ignore reload — focus on not adding heat. |

**Narrative:** RLUSD 28 XRP-equiv, floor 45, accumulation **blocked** — bot will fund in chop, not chase the rip with empty wallet.

**See also:** [Appendix Y](#appendix-y--rlusd-reload-post-run-chop-funding) · SKYNET playbook **W**
#### Mid price chart

**What it is:** Candle history (lagging) + live bid/ask/mid lines (1s poll). Timeframe buttons: 5m–2h.

**How to use it:** Candles lag samples; **live lines** are fresher. Use for context, not exact fill prediction.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Higher highs — don't chase with offset↓ unless scale phase earned. |
| **Neutral** | Sideways box — TA gate matters more than chart FOMO. |
| **Bear** | Lower highs — trust phase offsets; PRO/defensive may trip. |

**Narrative:** Candles look bullish but last three Decision lines say `ta_buy_blocked` — believe Decision.

**See also:** [TA tab](#ta-tab) · [Appendix A](#appendix-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind)
#### Market Conditions

**What it is:** Spread, depth ±1% of mid, max buy size, regime, ATR%, realized vol, DCA lines, cycle timing.

**How to use it:** **Max buy** is the binding clip right now. Depth refreshes each **engine cycle**, not each HUD poll.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Deep ask book, max buy at your risk cap — deploy when gates pass. |
| **Neutral** | Regime chop, ATR moderate — default offsets. |
| **Bear** | Thin depth, max buy tiny — don't raise risk%; fix book health first. |

**Narrative:** Max buy 17.5 XRP — that's 3% of book, not a bug.

**See also:** [Appendix H](#appendix-h--order-size-stuck-13-rlusd-or-smaller-than-expected) · [Appendix R](#appendix-r--insufficient_ask_depth)

#### Risk & entry (control deck)

**What it is:** The main tuning surface — target allocation, size, edge, bid placement, stale cancel, deferred SL, cycle speed. **Apply** after changes.

**How to use it:** Change **one knob** per soak window. After Apply, watch Decision 10–20 cycles. Cross-check **Market Conditions → Max buy**.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Modest offset (0.12–0.18), `max_pending_buys` 2–3 only after clean realized week; scale SKYNET phase. |
| **Neutral** | Default patient offsets (0.15–0.25), `max_pending_buys` 1–2, sticky drift > offset + spread. |
| **Bear** | Wide offset (0.18+), `max_pending_buys` 1, lower risk%, trust/defensive circuit; no offset chase. |

**Narrative:** You lower offset to catch a rip — fills improve, SLs cluster — PRO trips bear bundle overnight.

**See also:** [Knob coupling](#knob-coupling--change-x-change-y) · Appendices **A–I**, **V**

##### `target_xrp_pct` / `weakness_deviation` / `strength_deviation`

North star XRP share and how far below/above target before buys/sells fire. RLUSD-heavy = below target = buy side eligible.

| Regime | target / weakness |
|--------|-------------------|
| **Bull** | target 80–85%, weakness 0.03–0.04 |
| **Neutral** | target 75–80%, weakness 0.04–0.05 |
| **Bear** | target unchanged; raise weakness 0.06–0.08 (fewer knives) |

##### `risk_per_trade_pct`

Caps bracket size ≈ `% × portfolio` (also leg cap & depth). HUD **Max buy** confirms.

| Regime | Typical |
|--------|---------|
| **Bull** | 2.5–3.5% after trust earned |
| **Neutral** | 0.5–2.5% |
| **Bear** | ≤2.5%; defensive circuit may force min |

##### `min_edge_threshold_pct` ⚠️

Must be **≤ `buy_limit_offset_pct`** or HOLD forever (`edge_below_threshold`). Couple with offset changes.

##### `buy_limit_offset_pct` / `sell_limit_offset_pct`

Distance below mid (buy) or above mid (sell). Main fill vs entry-quality lever.

| Regime | buy offset |
|--------|------------|
| **Bull** | 0.08–0.15 (eager) only if realized P&L healthy |
| **Neutral** | 0.15–0.25 |
| **Bear** | 0.18–0.35 patient |

##### `max_pending_buys` / stale pending buy knobs

`stale_pending_buy_max_drift_pct` must be **> offset + spread** for sticky bids, or ≈ offset to chase. **`mid_passed_entry` trap** — see Appendix G.

##### `deferred_sl_enabled` / `deferred_sl_arm_buffer_pct` ⚠️

XRPL stops below bid cross instantly without deferral. **SL↯** on Brackets = off-ledger stop until arm.

| Regime | deferred SL |
|--------|-------------|
| **Bull** | On; buffer 0–0.1% |
| **Neutral** | On; default buffer 0% |
| **Bear** | On; avoid disabling; widen `initial_stop_loss_pct` instead |

##### `cycle_interval_seconds`

5–60s between engine cycles. Lower = faster stale cancel/replace, more RPC load.

---

#### Structure & trailing (control deck)

**What it is:** Stop/TP distances, trailing enable, breakout/structure lookback — protects filled bags.

**How to use it:** Prove deferred SL before enabling trailing. Watch Brackets **Trail** column (**BE**/**BO**).

| Regime | Stance |
|--------|--------|
| **Bull** | Trailing on, `trailing_step_pct` 1.5–2%, breakout 0.02 |
| **Neutral** | Trailing on after soak; fixed TP/SL first week |
| **Bear** | Trailing off if scratch SL churn; wider `initial_stop_loss_pct` |

**Narrative:** BE flags appear on a rally — then one wick scratches four brackets; scratch tier saves you from 71-cycle SL penalty.

**See also:** [Appendix E](#appendix-e--buying-too-often-in-a-downtrend) · SL mitigations below

Key knobs: `bracket_trailing_enabled`, `trailing_step_pct`, `breakout_pct`, `structure_lookback`, `initial_stop_loss_pct`, `take_profit_pct` / `take_profit_rr`.

---

#### Re-entry after exit (control deck)

**What it is:** Cooldowns and gates after TP/SL before the next buy — anti-churn discipline.

**How to use it:** Read Decision re-entry line. Cooldowns are **non-negotiable** first; then dip/stabilization/TA.

| Regime | Stance |
|--------|--------|
| **Bull** | Shorter TP cooldown/dip; keep SL cooldown meaningful |
| **Neutral** | Default TP 4 / SL 8–15 cycles |
| **Bear** | Long SL cooldown, high `sl_min_ta_score`, deep offsets after damage |

**Narrative:** TP at 1.10 — bot refuses to rebuy at 1.105 because you set `tp_dip_pct` — that's the feature.

**See also:** [Appendix K](#appendix-k--post-sl-re-entry-bot-wont-reload) · [Appendix L](#appendix-l--post-tp-re-entry-waiting-for-dip)

#### SL mitigations (sub-panel)

Scratch tier, cluster window, recovery release, post-clear spacing — tame breakeven SL storms without disabling re-entry.

| Knob | Bear tip |
|------|----------|
| `scratch_sl_max_loss_pct` | 0.10–0.15 — more exits count as scratch |
| `scratch_sl_cooldown_cycles` | 3–6 |
| `sl_cluster_window_sec` | 1800+ — cluster doesn't reset timer |
| `recovery_enabled` | on — end cooldown when price recovers |

---

#### Manual actions (control deck)

**What it is:** Pause, resume, cancel all, config reload, dry-run toggle, engine start.

**How to use it:** **Pause** stops new entries; brackets stay. **Cancel all** is nuclear — type `CANCEL_ALL`.

| Regime | Action |
|--------|--------|
| **Bull** | Rarely touch — let brackets work |
| **Neutral** | Pause for manual bracket surgery |
| **Bear** | Pause + review PRO; cancel pending ladder if cluttered |

**Narrative:** You cancel all during a bleed — you keep XRP bags without TP/SL until you fix posture.

**See also:** [Emergency controls](#emergency-controls)

---

### TA tab

Technical analysis gate and indicator detail. **TA tuning** sliders at top; indicator cards below.

#### TA tuning (`ta_enabled`, `ta_weight`, scores, candle interval)

**What it is:** Master switch, gate strength, min buy/sell scores, bar size.

**How to use it:** `ta_weight` 0 = advisory; 1 = hard gate. Changing candle interval affects warmup time.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | weight 0.6–0.8, min_buy 1.2–1.5 — participate in trend. |
| **Neutral** | weight 0.8, min_buy 1.5–2.0 — default chop filter. |
| **Bear** | weight 1.0, min_buy 2.0+, bearish bias blocks — expect HOLD. |

**Narrative:** You disable TA to force buys in bear tape — you catch the knife; turn it back on.

**See also:** [Appendix J](#appendix-j--ta-blocking-buys-in-chop) · [Appendix Q](#appendix-q--ta_warming_up--insufficient-history)
#### Status / Bias / Buy / Sell / Breakout scores

**What it is:** Composite scores and whether each gate passes.

**How to use it:** Mirror Decision `decTa` line on Live tab. Buy gate FAIL = no PLACE_BID when weight=1.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | buy > min, bias bullish/neutral — gate PASS. |
| **Neutral** | scores flicker 1.2–1.8 — normal chop. |
| **Bear** | bearish bias or sell > buy — gate BLOCK. |

**Narrative:** Buy score 1.51, min 1.50 — one tick from HOLD forever.

**See also:** [Appendix J](#appendix-j--ta-blocking-buys-in-chop)
#### RSI / Stochastic / Bollinger / Fibonacci / Signals

**What it is:** Indicator breakdown and recent signal list.

**How to use it:** Diagnostics when you disagree with composite score. Signals table = last fired rules.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Oversold RSI + bullish engulfing — supports buy score. |
| **Neutral** | Mixed signals — trust composite over one indicator. |
| **Bear** | Overbought + bearish bias — don't override with weakness alone. |

**Narrative:** RSI 28 but bias bearish — structure still down; re-entry waits.

**See also:** [Appendix J](#appendix-j--ta-blocking-buys-in-chop)
#### Elliott wave (5-wave pivots)

**What it is:** Under **Bias**, the muted **Elliott** line shows wave position from zigzag pivots on the TA lookback window (default **50** closed bars): labels like **`W3↑`**, **`W4↑`**, trend (`bullish_impulse` / `bearish_impulse` / `corrective`), and confidence.

**How to read it:**

| HUD label | Meaning |
|-----------|---------|
| **`W4↑`** | Wave 4 **up-leg** inside the detected pattern — **not** the same as legacy bias `impulse_up`. |
| **`impulse_up` / `impulse_down`** | Legacy bias field in the signals table — overall impulse direction. |
| **Corrective / low conf** | Dampens TA scores; accumulation still needs structure/tape gates. |

**Operator rule:** Elliott **grades** buy/sell scores; it does **not** replace breakout, bull_run drift, momentum, or dip-only weakness paths. A bullish TA card with **`bearish_impulse`** Elliott is possible — read both lines.

**See also:** [Appendix Z](#appendix-z--elliott-5-wave--divergence-detector)
#### Divergence detector (RSI / Stoch / MACD)

**What it is:** Under **Bias**, **Divergence: …** when price pivots and momentum disagree:

- **Bullish regular** — price lower low, RSI/Stoch higher low → **+buy score** (weakness reversal).
- **Bearish regular** — price higher high, indicator lower high → **+sell score** (strength exhaustion).
- **Hidden** variants — continuation setups at **~45%** of regular weight.

**HUD:** TA tab toggle **Divergence** (`alpha_ta_divergence_enabled`). Signals table row **`divergence`** with kind, indicator, strength. Accumulation scorecard copies the live read when fired.

**Config** (`config.yaml` → `alpha_technical_analysis.divergence`):

```text
lookback_bars: 50    min_swing_pct: 0.25    min_strength: 0.35
use_rsi: true        use_stochastic: true    use_macd: false
buy_weight: 0.7      sell_weight: 0.7        hidden_weight_mult: 0.45
```

**Narrative:** Bullish divergence + fib support + oversold RSI — higher-confidence dip bid; bearish divergence while XRP-heavy — consider deferring strength asks (`ta_sell_deferred`).

**See also:** [Appendix Z](#appendix-z--elliott-5-wave--divergence-detector) · [Appendix J](#appendix-j--ta-blocking-buys-in-chop)

#### Volume confirmation

**What it is:** Under **Bias**, **Volume: …** compares the last **closed** bar’s tick activity (`tick_count` in OHLC cache) to the rolling average.

| Read | Meaning |
|------|---------|
| **spike_up** + ratio ≥ 1.25 | Green bar with above-average activity — +buy / +breakout score |
| **spike_down** | Red bar with spike — +sell score |
| **low_vol_noise** | Ratio below 0.65 — dampens buy/sell/breakout (chop filter) |

**HUD:** TA tab **Volume** toggle (`alpha_ta_volume_enabled`). Not exchange tape volume — book-sample density proxy, live-friendly on XRPL.

#### HTF bias filter

**What it is:** **1h bias: bullish/bearish** (default **3600s** bars from SQLite cache). Fast/slow SMA stack on HTF closes multiplies LTF scores — **light filter**, not a hard block.

| HTF | LTF effect |
|-----|------------|
| **Bullish** | Buy/breakout scores × up to ~1.15; sell scores slightly damped |
| **Bearish** | Sell scores boosted; buy/breakout damped |
| **Neutral / warming** | Multipliers 1.0 |

Use **7200s** (2h) in config for a slower anchor. Auto-bumps above your TA candle window if needed.

**HUD:** **HTF bias** toggle (`alpha_ta_htf_enabled`).

**See also:** [Appendix Z](#appendix-z--elliott-5-wave--divergence-detector)

### Brackets tab

Full bracket table: state, mode, entry, size, TP/SL, trail flags, per-row cancel/edit.

**What it is:** Source of truth for **pending buy** vs **active** vs history rows.

**How to use it:** Only **`pending buy`** counts toward cap. **SL↯** = deferred stop. **BE**/**BO** = trailing milestones.

| Regime | Stance |
|--------|--------|
| **Bull** | Watch BE/BO; trail winners |
| **Neutral** | One pending, edit entry with ✎ if needed |
| **Bear** | Cancel excess pending; don't stack ladder |

**Narrative:** JSON file shows 1058 rows; HUD shows 1 pending — believe the HUD State column.

**See also:** [Appendix C](#appendix-c--ladder-clutter-many-pending-buys-none-filling) · [Appendix G](#appendix-g--entry-price-keeps-moving-cancelreplace-loop)

---

### Open Offers tab

Raw XRPL offers (sequence, side, price, size). ✕ cancel, ✎ reprice.

**What it is:** Ledger truth — one row per open offer including non-bracket asks.

**How to use it:** When Brackets and Offers disagree, Offers wins for "what's on chain."

| Regime | Stance |
|--------|--------|
| **Bull** | Expect bid + TP legs on active bags |
| **Neutral** | Single bid typical |
| **Bear** | Many stale bids — prune via Brackets or Cancel all |

**Narrative:** One offer, sequence 12345 — that's your only pending bid.

**See also:** [Appendix N](#appendix-n--bid-on-book-mid-looks-good-still-no-fill)

---

### Reports tab

Cycle report text, tax CSV path, download helpers, transfer index.

**What it is:** Human-readable cycle dump + pointer to `logs/trades_YYYY-MM.csv`.

**How to use it:** Archive monthly CSV for taxes. Cross-check realized P&L vs PRO replay.

| Regime | Stance |
|--------|--------|
| **Bull** | TP rows dominate CSV |
| **Neutral** | Mixed small P&L |
| **Bear** | SL rows cluster — sum `profit_xrp_equiv` |

**Narrative:** Session P&L +200, CSV sum −5 — you were measuring the wrong scoreboard.

**See also:** [Tax & transfer records](#tax--transfer-records) · [Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro)

---

### Activity tab

Reverse-chronological engine events (cycles, cancels, fills, defensive circuit).

**What it is:** Lightweight log tail — faster than SSH for "did stale cancel fire?"

**How to use it:** After Apply, look for `stale_pending_buy_cancelled`, `defensive_circuit`, `place_bid`.

| Regime | Stance |
|--------|--------|
| **Bull** | Regular `place_bid` / fills |
| **Neutral** | Mix HOLD + occasional bid |
| **Bear** | SL cluster in log; `defensive_circuit_activated` |

**Narrative:** Activity every 34s says hold — that's one engine cycle, not a freeze.

**See also:** [Appendix G](#appendix-g--entry-price-keeps-moving-cancelreplace-loop)

---

### PRO tab

**Alpha Replay**, **auto-defensive circuit**, **treasury placeholder**.

#### Alpha Replay

**What it is:** Rolling TP/SL, realized P&L, scratch SLs, verdict (`healthy`/`sl_heavy`/`bleeding`/`churn`).

**How to use it:** Pick window (14h default). Judge bleed here — not Session P&L.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | TP ≥ SL, verdict healthy — optional release defensive. |
| **Neutral** | Mixed — watch trend over 48h. |
| **Bear** | sl_heavy / bleeding — expect or confirm defensive ACTIVE. |

**Narrative:** 63 SL, 0 TP — verdict sl_heavy; you didn't need to wait for Session P&L to tell you.

**See also:** [Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro)
#### Auto-defensive circuit

**What it is:** Auto bear bundle via overrides when replay trips thresholds.

**How to use it:** Let it work in bear; **Release defensive** (type RELEASE) restores saved knobs.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Armed but inactive — normal. |
| **Neutral** | Hold defensive if churning chop. |
| **Bear** | DEFENSIVE ACTIVE — don't SKYNET-Apply aggressive offsets in parallel. |

**Narrative:** Circuit trips at 3am; you wake up to bear regime without touching SKYNET.

**See also:** [Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro) · [Appendix S](#appendix-s--trust-phase-skynet-bias)
#### Treasury (placeholder)

**What it is:** Future sideline Tangem tranche deploy — not wired.

**How to use it:** Fund manually: Config → RLUSD issuer + Xaman send to bot address.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | — |
| **Neutral** | — |
| **Bear** | — |

**Narrative:** 11k on Tangem stays manual until Phase 2 treasury ships.

**See also:** [Funding changes](#funding-changes-scaling-toward-11k-xrp)

### SKYNET tab

SKYNET advisor — operator phase, market regime, Agent Smith, Full SKYNET, manual Ask.

#### Operator phase (trust / scale / aggressive)

**What it is:** Strategy bias for SKYNET suggestions — does not change knobs until Apply.

**How to use it:** Match phase to tranche soak. Trust after deploy/SL streak; scale after clean realized week.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Scale → Aggressive only with guardrails. |
| **Neutral** | Trust or Scale. |
| **Bear** | Trust — anti-bleed prompts; max_pending before offset↓. |

**Narrative:** You set Aggressive on day one — SKYNET suggests 0.08% offset; you Apply; SLs follow.

**See also:** [Appendix S](#appendix-s--trust-phase-skynet-bias) · [Appendix T](#appendix-t--scale-phase-modest-accumulation) · [Appendix U](#appendix-u--aggressive-phase-bag-push)
#### Market regime (bull / neutral / bear)

**What it is:** Tape bias for SKYNET Ask + Agent Smith — mirrors PRO/defensive posture language.

**How to use it:** Set bear after SL-heavy night if circuit disabled. Apply suggestions manually.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Bull — accumulate dips in prompts. |
| **Neutral** | Neutral — anti-churn language. |
| **Bear** | Bear — defensive; aligns with auto circuit bundle. |

**Narrative:** Regime bear + phase trust — SKYNET refuses to recommend offset below 0.15.

**See also:** [Appendix W](#appendix-w--sl-heavy-night-defensive-circuit-pro)
#### Agent Smith (Phase 2)

**What it is:** Bounded auto-suggestions every 3–5 cycles within guardrails.

**How to use it:** Review purple knob highlights on Live; Apply safe changes manually.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Allow modest risk/pending bumps inside guardrails. |
| **Neutral** | Default guardrails. |
| **Bear** | Pause Agent Smith during defensive circuit. |

**Narrative:** Purple ◆ on max_pending — Agent Smith agrees you need cap before offset.

**See also:** [Tuning SKYNET](#tuning-skynet-ask-agent-smith-full-mode)
#### Full SKYNET (Phase 3) & Manual Ask

**What it is:** Autonomous apply (confirmed) vs conversational Ask → Apply.

**How to use it:** Full mode requires `ENABLE_FULL_SKYNET`. Kill/pause always override.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | Still cap with guardrails — not a license for 5% risk. |
| **Neutral** | Ask for stale bid ladder diagnosis. |
| **Bear** | Do not enable Full during bleed — use PRO + trust phase. |

**Narrative:** You Ask 'why no fills?' — SKYNET returns pending_buy_stale block with target entry math.

**Scenario quick buttons (2026):** SKYNET playbook letters **U** (bull run / missed move on balanced dev) · **V** (accumulation ARMED/EXECUTING knobs) · **W** (RLUSD reload / deploy floor). Live cards also expose **Ask SKYNET** with the same context pre-loaded. *(Playbook **U** is not the same as operator phase **Aggressive** — [Appendix U](#appendix-u--aggressive-phase-bag-push).)*

**See also:** [Tuning SKYNET](#tuning-skynet-ask-agent-smith-full-mode) · [Appendix X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) · [Appendix Y](#appendix-y--rlusd-reload-post-run-chop-funding)

### Config tab

Credentials, network, Telegram/HUD auth, **Send / withdraw**, transfer log.

#### Bot account & network

**What it is:** Address, RLUSD issuer (read-only resolved), secret, testnet, RPC.

**How to use it:** Copy **rlusd_issuer** when funding from Xaman/Tangem. Never commit secrets.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | — |
| **Neutral** | Verify mainnet + trust line before tranche. |
| **Bear** | — |

**Narrative:** You paste issuer into Xaman — RLUSD lands on bot with correct trust line.

**See also:** [Funding changes](#funding-changes-scaling-toward-11k-xrp)
#### Send / withdraw from bot

**What it is:** Signed XRPL payment to any `r…` address. Type SEND to confirm.

**How to use it:** Pause/stop engine before large withdrawals. Logged to transfers.csv + tax CSV.

| Regime | Operator stance |
|--------|-----------------|
| **Bull** | — |
| **Neutral** | Tranche profit skim — small test send first. |
| **Bear** | — |

**Narrative:** You SEND 50 XRP to cold wallet after pausing — tax row logs OUT.

**See also:** [`ALPHA_OPERATOR_GUIDE.md`](ALPHA_OPERATOR_GUIDE.md)

## Part 2 — Operator playbook

Cross-tab topics: tax logs, scaling capital, knob coupling, troubleshooting, soak discipline, SKYNET, emergencies.

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
| `cost_basis_rlusd_per_xrp` | Lot cost on **BUY** rows; entry basis on **SELL** rows (bracket entry or running average for strength sells) |
| `proceeds_usd` | **SELL** / **TRANSFER** (RLUSD): `rlusd_amount × alpha_tax_usd_per_rlusd` (default 1.0) |
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
| Strength sell fill | `SELL` | `Y` | Inventory ask (`PLACE_ASK`) fills; basis from running average of prior BUY rows |
| Config → Send withdrawal | `TRANSFER` | `Y` | Also mirrored in `logs/transfers.csv` |

**Not logged:** order cancels/replaces (`OFFER_REFRESH` is used elsewhere in xLedgerMate, not Alpha bracket cancels).

### Example rows (illustrative)

```csv
timestamp_utc,event_type,taxable,network,side,xrp_amount,rlusd_amount,price_rlusd_per_xrp,profit_xrp_equiv,cost_basis_rlusd_per_xrp,proceeds_usd,notes
2026-06-23T14:00:00+00:00,BUY,Y,mainnet,BUY,50.000000,55.000000,1.100000,0.000000,1.100000,,alpha bracket buy 441b8974
2026-06-23T16:30:00+00:00,SELL,Y,mainnet,SELL,50.000000,57.500000,1.150000,2.272727,1.100000,57.5000,alpha bracket take-profit 441b8974 entry=1.100000
2026-06-23T17:00:00+00:00,SELL,Y,mainnet,SELL,25.000000,28.750000,1.150000,1.136364,1.100000,28.7500,alpha strength sell seq=12345 basis=1.100000
2026-06-23T18:00:00+00:00,TRANSFER,Y,mainnet,OUT,100.000000,0.000000,0.000000,0.000000,,,Payment to rDest…
```

### Operator checklist

1. Confirm **LIVE** (not dry-run) before relying on the CSV for real tax records.  
2. After month-end, archive `logs/trades_YYYY-MM.csv` before the calendar rolls.  
3. Cross-check bracket fills on the **Brackets** / **Activity** tabs against new CSV rows.  
4. Withdrawals: verify both `trades_*.csv` and `transfers.csv` if you use **Config → Send**.

---

## Funding changes (scaling toward ~11k XRP)

Use this when you **add XRP or RLUSD** to the bot wallet on mainnet. The bot does not auto-detect narrative capital — you sync **`risk_capital_xrp`** and HUD knobs after each deposit.

**Rule:** Grow the book in **tranches**. Judge each tranche on **realized** bracket P&amp;L (`profit_xrp_equiv` in tax CSV), not **Session P&amp;L** (MTM). SKYNET **operator phase** should match the tranche ([Appendix S](#appendix-s--trust-phase-skynet-bias) · [T](#appendix-t--scale-phase-modest-accumulation) · [U](#appendix-u--aggressive-phase-bag-push)). To deploy RLUSD already on the book, see [Deploy RLUSD to XRP](#deploy-rlusd-to-xrp-get-xrp-heavy).

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

Inbound deposits appear in balances next cycle; they are **not** auto-detected. After each inbound transfer, open **Config → Operator deposits** and record the XRP/RLUSD amount so bag growth excludes your funding (stored in `logs/operator_deposits.json`).

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

**SKYNET:** **scale** first; **aggressive** only if you accept churn and realized P&amp;L is healthy ([Appendix U](#appendix-u--aggressive-phase-bag-push)).

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
| **Buys** | When `deviation ≤ −weakness_deviation` (classic) **or** **accumulation regime ARMED** on bull/breakout tape (even near-balanced `dev`). |
| **`sell_blocked`** | **On** while RLUSD-heavy — bot **won’t** classic strength-sell XRP away. **Reload** funding sells are separate ([Appendix Y](#appendix-y--rlusd-reload-post-run-chop-funding)). |
| **Fills** | **Passive** — ask must trade **down to your bid**. Mid dipping ≠ fill. |

You are usually already in the **right posture** (`heavy_rlusd`, buys allowed). RLUSD sits on the sidelines because **clips are small**, **`max_pending_buys = 1`**, **offset**, or **reload deploy floor** blocking accumulation when wallet RLUSD is thin.

**Two deploy paths (2026):**

1. **Classic** — RLUSD-heavy, weakness gate, your Live offset / pending / risk knobs.  
2. **Accumulation regime** — tape arms tighter bundle (see [Appendix X](#appendix-x--accumulation-regime-chart-rips-balanced-hold)); may need **reload** first if RLUSD &lt; deploy floor.

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

**Trust phase:** do not lower offset below **0.15** until realized TP/SL in tax CSV looks acceptable ([Appendix S](#appendix-s--trust-phase-skynet-bias)).

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

See also [Appendix F](#appendix-f--chop--mild-dips-want-more-action) (eager fills) and [Appendix V](#appendix-v--deploy-sideline-rlusd-faster-xrp-heavy).

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

### Why no buys? — Decision reason cheat sheet

You are RLUSD-heavy. TA looks fine. Bot still HOLD. **Read the Decision reason**, then open the matching appendix:

| Reason pattern | Appendix |
|----------------|----------|
| `edge_below_threshold` / edge < min | [D](#appendix-d--hold-forever-edge-in-the-reason) |
| `post_sl_` / `post_tp_` / `reentry_` / `reentry_reload_spacing` | [K](#appendix-k--post-sl-re-entry-bot-wont-reload) · [L](#appendix-l--post-tp-re-entry-waiting-for-dip) |
| `ta_buy_blocked` / `ta_warming_up` | [J](#appendix-j--ta-blocking-buys-in-chop) · [Q](#appendix-q--ta-warming-up-insufficient-history) |
| `balanced dev=` | [M](#appendix-m--balanced-inventory-nothing-to-do) · [X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) if accumulation card armed |
| `accumulation` / `bull_run` / `tape_participation` | [X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) |
| `reload_funding` / `reload_blocks_accumulation` | [Y](#appendix-y--rlusd-reload-post-run-chop-funding) |
| `max_pending_buys=` | [C](#appendix-c--ladder-clutter-many-pending-buys-none-filling) · [G](#appendix-g--entry-price-keeps-moving-cancelreplace-loop) |
| `insufficient_ask_depth` | [R](#appendix-r--insufficient_ask_depth) |
| `kill_switch` / `pause_bids` / preflight | [P](#appendix-p--kill-switch-drawdown-or-pause) |
| Pending buy exists, no fill | [N](#appendix-n--bid-on-book-mid-looks-good-still-no-fill) |
| `weakness dev=` but no bid | [I](#appendix-i--rlusd-heavy-sell-blocked-buys-only) · [V](#appendix-v--deploy-sideline-rlusd-faster-xrp-heavy) |

---

## Troubleshooting cheat sheet

| Problem | Likely cause | What to do |
|---------|--------------|------------|
| Stuck on HOLD, edge in reason | Offset < min edge | [Appendix D](#appendix-d--hold-forever-edge-in-the-reason) |
| RLUSD-heavy, only bids, no sells | Normal `sell_block` | [Appendix I](#appendix-i--rlusd-heavy-sell-blocked-buys-only) |
| `ta_buy_blocked` / bearish | TA gate in chop | [Appendix J](#appendix-j--ta-blocking-buys-in-chop) |
| Quiet after SL | Re-entry gate (check `sl_tier` scratch vs full) | [Appendix K](#appendix-k--post-sl-re-entry-bot-wont-reload) |
| Quiet after gate cleared | Buy spacing | `reentry_reload_spacing` in Decision |
| Quiet after TP | Await dip + cooldown | [Appendix L](#appendix-l--post-tp-re-entry-waiting-for-dip) |
| `balanced dev=…` | On target band — or accumulation waiting on tape | [Appendix M](#appendix-m--balanced-inventory-nothing-to-do) · [X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) |
| Chart ripping, 0 fills, RLUSD low | Reload blocks accumulation | [Appendix Y](#appendix-y--rlusd-reload-post-run-chop-funding) |
| `reload_funding` / funding ask | Post-run chop sell — not strength unload | [Appendix Y](#appendix-y--rlusd-reload-post-run-chop-funding) · [O](#appendix-o--xrp-heavy-want-strength-sells) |
| Bid resting, no fill | Passive limit | [Appendix N](#appendix-n--bid-on-book-mid-looks-good-still-no-fill) |
| XRP-heavy, no asks | Strength threshold | [Appendix O](#appendix-o--xrp-heavy-want-strength-sells) |
| `ta_sell_blocked` / `ta_sell_deferred` | XRP-heavy path evaluated **sells** first — not accumulation | [Appendix O](#appendix-o--xrp-heavy-want-strength-sells) · [Appendix J](#appendix-j--ta-blocking-buys-in-chop) |
| Chart bullish, accumulation `off`, dev +0.10 | Dev cap / buy imbalance — not “between cycles” | [Appendix X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) · SKYNET **gate_diagnostics** |
| `W4↑` on TA but no accumulation | Wave label ≠ `impulse_up`; need breakout/drift | [Appendix Z](#appendix-z--elliott-5-wave--divergence-detector) |
| Bullish **divergence** on scorecard | TA confluence only — still need ARMED + RLUSD budget | [Appendix Z](#appendix-z--elliott-5-wave--divergence-detector) · [Appendix X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) |
| Kill / pause / preflight | Risk state | [Appendix P](#appendix-p--kill-switch-drawdown-or-pause) |
| Entry keeps jumping | Stale `mid_passed_entry` | [Appendix G](#appendix-g--entry-price-keeps-moving-cancelreplace-loop) |
| Size ~13 RLUSD | `risk_per_trade_pct` cap | [Appendix H](#appendix-h--order-size-stuck-13-rlusd-or-smaller-than-expected) |
| No buys, RLUSD-heavy | Weakness too high | Lower `weakness_deviation` or [Appendix M](#appendix-m--balanced-inventory-nothing-to-do) |
| Buying too soon after sells | Cooldowns too short | [Appendix L/K](#appendix-l--post-tp-re-entry-waiting-for-dip) |
| Bids way below mid (~5%) | Offset set very high | [Appendix A](#appendix-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind) |
| Bids at ~1.04 when mid ~1.10 | Old bracket history or deep offset | Check Brackets **State** = `pending buy`; stale cancel only hits live pending rows |
| HOLD at max pending, bids ~1.097–1.10 | Bids match current offset (low drift) | [Appendix C](#appendix-c--ladder-clutter-many-pending-buys-none-filling) |
| Many pending bids, mid “passed”, no cancel | `max_drift` too loose (e.g. 0.5%) vs offset 0.15–0.35% | [Appendix C](#appendix-c--ladder-clutter-many-pending-buys-none-filling) |
| Bid feels left behind as price rises | Offset too high vs movement | [Appendix A](#appendix-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind) |
| Cancels very slow | One XRPL cancel per engine cycle | Normal — wait or lower pending count / use Cancel all |
| Cancelled but orders still show | Active brackets ≠ pending | Check state column; active = exits on filled bags |
| What does **BE** / **BO** mean? | Trailing flags on active brackets | **BE** = breakeven passed, SL can trail · **BO** = breakout confirmed, TP can trail · needs `bracket_trailing_enabled` |
| What does **SL↯** mean? | Deferred stop (Risk & entry) | SL target set but **not on ledger yet** — avoids instant XRPL exit; arms when mid reaches stop (+ buffer) |
| Bracket vanishes right after fill | Instant SL cross (legacy) or fast stop | Enable **`deferred_sl_enabled`**; check logs for `deferred_sl_hold` / `sl_filled` |
| No rows in tax CSV | Dry-run or no fills yet | Switch to LIVE; CSV updates on bracket buy/TP/SL fills and Config → Send |
| `ta_warming_up` | New session / thin history | [Appendix Q](#appendix-q--ta_warming_up--insufficient-history) |
| Max buy = 0 | Thin book | [Appendix R](#appendix-r--insufficient_ask_depth) |
| Preflight not OK | Trust line, balance, config | [Appendix P](#appendix-p--kill-switch-drawdown-or-pause) |

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
| **Accumulation ARMED** | **`buy_limit_offset_pct`** on Live | Engine uses **`alpha_accumulation_*`** bundle — manual offset↓ may not apply until disarmed |
| **RLUSD below deploy floor** | **`alpha_reload_min_rlusd_deploy_xrp_equiv`** | Lowering floor forces bids with thin wallet — prefer chop reload or deposit |
| **`alpha_reload_block_accumulation_until_funded`** off | Accumulation + empty RLUSD | Bids may place with no budget — churn risk |

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
4. **Decision reason** + **ready** badge — re-entry gates and `max_pending_buys` are **expected**; on rips check **Accumulation** / **RLUSD reload** cards before tweaking offset.
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
| Bull rip | SKYNET playbook **U** / **V** — bull run missed · accumulation knobs |
| Low RLUSD after run | SKYNET playbook **W** — reload / deploy floor |
| 48h | Paste sidebar numbers: ratio, realized 24h, TP/SL counts, last decision reason, **ready** badge |
| If bleeding | **Anti-bleed** / Appendix S knobs |

### Telegram / logs (optional)

- Hourly Telegram: alive + portfolio snapshot.
- Tax truth: `logs/trades_YYYY-MM.csv` on VPS — sum `profit_xrp_equiv` on SELL rows should match **Realized 24h** on HUD.

**Next full compare target:** ~**2026-06-26** (48h from baseline).

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

## Tuning SKYNET (Ask, Agent Smith, Full mode)

SKYNET is the **advisor layer** — it does not place trades. Set **operator phase** on the SKYNET tab so advice matches soak vs scale goals.

**Backend note:** Inference runs on xAI's API (Grok-family models). **Prompts, playbooks, guardrails, and Apply logic are ours** — you talk to SKYNET; you are not chatting with stock Grok.

**HUD names:** Phase 1 manual prompt = **Ask SKYNET**; Phase 2 bounded automation = **Agent Smith** (checkbox **Enable Agent Smith Mode**); Phase 3 = **Full SKYNET**.

### Operator phase (trust / scale / aggressive)

**SKYNET tab → Operator phase → Save phase.** Persisted as `alpha_operator_phase`. See [Appendix S](#appendix-s--trust-phase-skynet-bias), [T](#appendix-t--scale-phase-modest-accumulation), [U](#appendix-u--aggressive-phase-bag-push).

| Phase | Use when | SKYNET bias |
|-------|----------|-------------|
| **Trust** (default) | Soak, SL streak | `max_pending↑` before `offset↓` |
| **Scale** | Clean nights | offset 0.15–0.20, max_pending 2–3 |
| **Aggressive** | Bag push | offset 0.08–0.12; revert if SL streak |

Phase does **not** change knobs until you Apply.

### Runtime context (each Ask / Agent Smith cycle)

- **`alpha_operator_phase`** and playbook **S–U**
- **`pending_buy_stale`** — target entry, per pending bid `would_cancel` / `reason`, `over_cap_count`
- **`likely_scenarios`** — auto hints (A–Z) from decision reason + inventory (reference only)
- **`accumulation_regime`** / **`reload_regime`** — phase, blockers, scorecard (incl. **divergence**), deploy floor (mirrors Live cards)
- **`gate_diagnostics`** — pre-computed PASS/FAIL for dip gate, `accumulation_dev_cap`, `bull_run_dev_cap`, TA breakout/buy, structure arm, momentum, tape, last decision (authoritative — do not invent thresholds)
- **`structure`** — trend, swing high, breakout flags, confirmation candle
- **Appendix playbook (A–Z, S–U)** — condensed presets matching this manual
- **Operator knobs (effective)** — current HUD overrides

**Session P&L** is MTM — use **`realized_bracket_pnl`** in SKYNET context (`realized_profit_xrp_equiv`, `tp_exits` / `sl_exits` from tax CSV) for bleed in trust phase.

**Natural language → Apply**

On the SKYNET tab, set **operator phase**, type your goal in plain English, click **Send**, then **Apply suggested changes**:

```text
Trust phase: max pending 2 only — keep offset 0.20, weakness 0.05. Do not tighten drift.
```

SKYNET maps your goals to allowlisted keys. Quick buttons **Trust phase review**, **Scale phase knobs**, **Preset: sticky + 4% risk**, **My settings → Apply**.

If **Apply** stays disabled, name settings explicitly (percent values help) or check the hint for guardrail errors.

**Modes**

| Mode | Behavior |
|------|----------|
| **SKYNET tab — Ask** | You prompt; SKYNET suggests changes; you **Apply** manually |
| **Agent Smith** (Phase 2) | SKYNET runs every 3–5 cycles; **Apply safe** for guardrailed suggestions |
| **Full SKYNET** (Phase 3) | Auto-applies guardrailed changes (confirm with `ENABLE_FULL_SKYNET`; requires Agent Smith mode) |

SKYNET uses operator phase + appendix playbook + `pending_buy_stale`. **Agent Smith** proposals do **not** overwrite the Ask response box.

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

## Appendices — Scenario playbook

Lettered recipes — not gospel. Change **one knob**, watch Decision **10–20 cycles**.

### Appendix index

| | Appendix | When to use |
|---|----------|-------------|
| **A** | [Bid left behind in uptrend](#appendix-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind) | RLUSD-heavy, price rising, want nearer bids |
| **B** | [Patient dip sniper](#appendix-b--patient-dip-sniper-default-philosophy) | Deep offsets, can wait hours |
| **C** | [Ladder clutter](#appendix-c--ladder-clutter-many-pending-buys-none-filling) | Many pending buys, none filling |
| **D** | [HOLD, edge in reason](#appendix-d--hold-forever-edge-in-the-reason) | `edge_below_threshold` |
| **E** | [Buying too often in downtrend](#appendix-e--buying-too-often-in-a-downtrend) | SL streak, knife catching |
| **F** | [Chop, want more action](#appendix-f--chop-mild-dips-want-more-action) | Tight spread, rare fills |
| **G** | [Entry keeps moving](#appendix-g--entry-price-keeps-moving-cancel-replace-loop) | Cancel/replace every cycle |
| **H** | [Size stuck ~13 RLUSD](#appendix-h--order-size-stuck-13-rlusd-or-smaller-than-expected) | Clip smaller than expected |
| **I** | [RLUSD-heavy, sell blocked](#appendix-i--rlusd-heavy-sell-blocked-buys-only) | Heavy RLUSD, only bids fire |
| **J** | [TA blocking buys in chop](#appendix-j--ta-blocking-buys-in-chop) | `ta_buy_blocked` / bearish |
| **K** | [Post-SL re-entry](#appendix-k--post-sl-re-entry-bot-wont-reload) | After stop-loss, quiet bot |
| **L** | [Post-TP re-entry](#appendix-l--post-tp-re-entry-waiting-for-dip) | After take-profit, no reload |
| **M** | [Balanced HOLD](#appendix-m--balanced-inventory-nothing-to-do) | `balanced dev=…` |
| **N** | [Bid resting, no fill](#appendix-n--bid-on-book-mid-looks-good-still-no-fill) | Passive limit mechanics |
| **O** | [XRP-heavy, want sells](#appendix-o--xrp-heavy-want-strength-sells) | Strength asks / unload XRP |
| **P** | [Kill / drawdown / pause](#appendix-p--kill-switch-drawdown-or-pause) | Hard stops, no trading |
| **Q** | [TA warming up](#appendix-q--ta-warming-up-insufficient-history) | New session, thin history |
| **R** | [Thin book](#appendix-r--insufficient-ask-depth) | Depth gate blocks size |
| **S** | [Trust phase (SKYNET)](#appendix-s--trust-phase-skynet-bias) | Prove overnight, anti-bleed |
| **T** | [Scale phase (SKYNET)](#appendix-t--scale-phase-modest-accumulation) | After trust earned |
| **U** | [Aggressive phase (SKYNET)](#appendix-u--aggressive-phase-bag-push) | Bag-growth push |
| **V** | [Deploy sideline RLUSD faster](#appendix-v--deploy-sideline-rlusd-faster-xrp-heavy) | RLUSD on sidelines, want higher XRP % |
| **W** | [SL-heavy night / defensive circuit (PRO)](#appendix-w--sl-heavy-night-defensive-circuit-pro) | Auto bear posture after bleed |
| **X** | [Accumulation regime](#appendix-x--accumulation-regime-chart-rips-balanced-hold) | Chart rips, `balanced dev`, missed move |
| **Y** | [RLUSD reload](#appendix-y--rlusd-reload-post-run-chop-funding) | Fund dry powder in chop; blocks bids |

---

### Appendix A — RLUSD-heavy, price drifting up, bid feels “left behind”

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

**If fills still rare:** ask is still above your bid — try offset **0.08–0.10** only if you accept worse entries. If entries **keep moving**, drift is still too tight — see [Appendix G](#appendix-g--entry-price-keeps-moving-cancelreplace-loop).

---


---

### Appendix B — Patient dip sniper (default philosophy)

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


---

### Appendix C — Ladder clutter (many pending buys, none filling)

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


---

### Appendix D — HOLD forever, edge in the reason

**Symptoms:** `edge 0.050% < min 0.500%` or similar.

```text
Either: buy_limit_offset_pct  = 0.50   (bid deeper — more edge)
Or:     min_edge_threshold_pct = 0.08   (accept smaller edge)
```

Never leave **offset < min edge**.

---


---

### Appendix E — Buying too often in a downtrend

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


---

### Appendix F — Chop / mild dips, want more action

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


---

### Appendix G — Entry price keeps moving (cancel/replace loop)

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


---

### Appendix H — Order size stuck ~13 RLUSD (or smaller than expected)

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


---

### Appendix I — RLUSD-heavy, sell blocked, buys only

**Symptoms:** Sidebar shows **~20–30% XRP** vs **95% target**; inventory label **`heavy_rlusd`** or **`rlusd_heavy`**; Decision **`place_bid`** or **`weakness dev=…`**; **`sell_block=True`** in logs; no strength sells.

**What’s happening:** This is **normal bag-deploy posture**. You are far below target XRP allocation, so the engine **deploys RLUSD via limit bids**. **`sell_blocked_imbalance`** blocks unloading XRP until you are closer to target — you are not “missing” sells; the bot is correctly refusing to sell XRP while RLUSD-heavy.

| Signal | Meaning |
|--------|---------|
| `dev ≈ -0.70` @ target 95% | ~25% XRP actual — deep RLUSD bag |
| `sell_block=True` | Won’t place strength asks until less RLUSD-heavy |
| `buy_block=False` | Buys allowed when `dev ≤ -weakness_deviation` |

**If buys are too aggressive:** raise **`weakness_deviation`** (e.g. **0.05–0.08**) or lower **`risk_per_trade_pct`**.

**If you want faster XRP accumulation:** you are usually already past the weakness gate — use **`max_pending_buys`**, **`risk_per_trade_pct`**, and **`buy_limit_offset_pct`** in that order. Full presets: [Deploy RLUSD to XRP](#deploy-rlusd-to-xrp-get-xrp-heavy) · [Appendix V](#appendix-v--deploy-sideline-rlusd-faster-xrp-heavy). Don’t expect strength sells until **`dev`** recovers toward target.

**Config note:** **`inventory_target_xrp_ratio`** (HUD: target XRP %) sets the north star. At **75%** target with **46%** actual, large negative deviation is expected until many fills land. For **85–90%** target, raise **`inventory_target_xrp_ratio`** explicitly.

---


---

### Appendix V — Deploy sideline RLUSD faster (XRP-heavy)

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


---

### Appendix W — SL-heavy night / defensive circuit (PRO)

**Symptoms:** Overnight **`sl_exits` ≫ `tp_exits`** in tax CSV; realized **`profit_xrp_equiv`** negative; Session P&amp;L may still look fine (MTM); scratch SLs at entry; HUD **PRO** verdict **`sl_heavy`**, **`bleeding`**, or **`churn`**.

**What’s happening:** The engine runs **Alpha Replay** each cycle. When metrics cross thresholds, the **auto-defensive circuit** trips (if `alpha_defensive_circuit_enabled: true` and not dry-run): bear market regime + capped pending buys + wider buy offset + longer SL cooldown + trimmed risk — written to **`logs/alpha_overrides.json`**. State persists in **`logs/alpha_defensive_circuit.json`**.

**Operator checklist:**

1. Open HUD → **PRO** tab (nav: Activity · **PRO** · SKYNET · Config).
2. Confirm replay window (default **14h** matches `alpha_defensive_window_hours`).
3. If **DEFENSIVE ACTIVE** is expected after a bad night — let it work; do **not** fight with aggressive SKYNET Apply in parallel.
4. When realized P&amp;L recovers (TP &gt; SL, verdict **healthy**) or after **`alpha_defensive_auto_release_hours`**, circuit may auto-release — or click **Release defensive** (type `RELEASE`).
5. Align SKYNET **market regime** to **Bear** or **Neutral** manually if you disabled the circuit.

**Manual bear bundle (if circuit off):** SKYNET regime **Bear** → Apply, or Live:

```text
alpha_operator_market_regime         = bear
alpha_max_pending_buys               = 1
alpha_buy_limit_offset_pct           = 0.18+
alpha_reentry_sl_cooldown_cycles     = 20+
alpha_risk_per_trade_pct             = ≤ 2.5
```

**Treasury:** PRO tab shows **placeholder** only — sideline Tangem tranches still manual via Config → RLUSD issuer + Xaman.

**Coupling:** [Appendix K](#appendix-k--post-sl-re-entry-bot-wont-reload) (per-SL cooldown) · [Appendix S](#appendix-s--trust-phase-skynet-bias) (trust phase after bleed) · [Funding changes](#funding-changes-scaling-toward-11k-xrp) (don’t scale tranche while defensive).

---


---

### Appendix X — Accumulation regime (chart rips, balanced HOLD)

**Symptoms:** Price ripping on chart; Decision **`HOLD — balanced dev=…`** or only occasional small bids; Live **Accumulation** card **`watching`/`armed`**; scorecard **missed move**; header **ready** badge lit.

**What’s happening:** The **accumulation regime** deploys RLUSD on **tape** (breakout, bull structure, tape participation, optional **early ARM** on slope) — not only when `dev ≤ −weakness`. When **ARMED**, bids use a bundled profile:

```text
alpha_accumulation_buy_offset_pct           ≈ 0.06   (tighter than default buy offset)
alpha_accumulation_stale_drift_pct              ≈ 0.08   (chase-until-fill on mid_passed)
alpha_accumulation_max_pending_buys         = 3
alpha_accumulation_risk_boost               = 1.5×   (within global risk cap)
alpha_accumulation_rlusd_budget_pct         = spend cap per 8h window
alpha_accumulation_early_arm_enabled        = on     (tape + slope without full breakout)
```

**Chase-until-fill:** Stale cancel on **`mid_passed_entry`** re-places with slightly tighter offset; **chase count** on scorecard tracks reprices. Repeated chase with **zero fills** usually means **ask never traded to your bid** — passive limit mechanics ([Appendix N](#appendix-n--bid-on-book-mid-looks-good-still-no-fill)), not a broken engine.

**BLOCKED on card:** Often **`reload_blocks_accumulation`** — RLUSD below deploy floor ([Appendix Y](#appendix-y--rlusd-reload-post-run-chop-funding)). Fix funding before lowering offset.

**Operator checklist:**

1. Read **Accumulation** card phase + scorecard (bids / fills / chase cancels).
2. If **blocked** — open **RLUSD reload** card; do not crank `buy_limit_offset_pct` on Live unless scorecard shows chase loop with ample RLUSD.
3. SKYNET playbook **V** or card **Ask SKYNET** for diagnosis.
4. Session log: `logs/accumulation_session.json` on VPS.

**Do not:** disable accumulation to “fix” balanced dev during a rip — you will miss the move. **Do:** fund RLUSD via reload chop path or manual deposit, then let regime execute.

**Coupling:** [Appendix A](#appendix-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind) (offset math) · [Appendix V](#appendix-v--deploy-sideline-rlusd-faster-xrp-heavy) (classic RLUSD-heavy deploy) · [Pro accumulator loop](#pro-accumulator-loop-read-once)

---


---

### Appendix Y — RLUSD reload (post-run chop funding)

**Symptoms:** RLUSD wallet thin vs deploy ambition; **Accumulation** **blocked**; **RLUSD reload** card **`watching`** during rip → **`armed`** after stall; Decision **`reload_funding`** / **`place_ask`** with tight offset; or **`reload_blocks_accumulation`** on bids.

**What’s happening:** **Reload** refills **dry powder** after a proven run — **not** into active breakout. Arms when structure is **neutral/digesting** near **recent high**, run proven from **recent low**, slope/tape not still ripping. Sells a **capped** XRP slice (`reload_funding` mode) with TA bullish-defer **bypass** when armed.

**Policy 4 (default on):** `alpha_reload_block_accumulation_until_funded` — accumulation bids wait until RLUSD ≥ **deploy floor** (`alpha_reload_min_rlusd_deploy_xrp_equiv`, default **~45** XRP-equiv).

| Concept | Reload funding sell | Classic strength sell |
|---------|---------------------|------------------------|
| Trigger | Low RLUSD + chop after run | `dev ≥ strength_deviation` (~4%) |
| Timing | Post-run consolidation | XRP-heavy inventory |
| TA | Bypass when reload armed | May defer (`ta_sell_deferred`) |
| Goal | Fund bids for next leg | Trim XRP toward target ratio |

**Default knobs (config.yaml):**

```text
alpha_reload_regime_enabled                 = true
alpha_reload_min_rlusd_deploy_xrp_equiv     = 45
alpha_reload_block_accumulation_until_funded = true
alpha_reload_max_sells_per_window           = 1      (8h window)
alpha_reload_sell_offset_pct                = tight  (~0.06% above mid)
```

**Operator checklist:**

1. During rip with low RLUSD: **WATCHING** is correct — wait for chop.
2. After stall: expect at most **one** funding sell per 8h window; then **FUNDED** → accumulation unblocks.
3. SKYNET playbook **W** or reload card **Ask SKYNET**.
4. Session log: `logs/reload_session.json` on VPS.

**Do not:** confuse reload ask with panic unload — check Decision reason. **Do not** lower deploy floor to force bids mid-rip without accepting empty-wallet risk.

**Manual alternative:** Deposit RLUSD from Tangem → **Config → Reload** → accumulation unblocks when floor met.

**Coupling:** [Appendix X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) · [Deploy RLUSD to XRP](#deploy-rlusd-to-xrp-get-xrp-heavy) · [Appendix O](#appendix-o--xrp-heavy-want-strength-sells)

---


---

### Appendix J — TA blocking buys in chop

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
reentry_sl_min_ta_score = 2.0+     ← pairs with [Appendix K](#appendix-k--post-sl-re-entry-bot-wont-reload)
```

**Coupling:** Lower **`ta_min_buy_score`** + lower **`weakness_deviation`** together = very eager reload in sideways markets. Change one at a time.

**Verify:** Decision reason no longer contains `ta_buy_blocked`; TA panel shows buy score above your gate.

---


---

### Appendix K — Post-SL re-entry (bot won’t reload)

**Symptoms:** Stop-loss filled; bot goes quiet for cycles/minutes; Decision shows:

```text
post_sl_cooldown cycles=2/8 tier=scratch
reentry_reload_spacing cycles=3/5
reentry_sl_await_bounce mid=1.098 need>=1.101 (0.03% above recent_low)
reentry_sl_await_stabilization trend=bearish breakout_down=True
reentry_sl_ta_score=1.80<2.00
reentry_scratch_ta_score=1.20<1.50
reentry_sl_await_weakness dev=-0.45
```

**What’s happening:** After an **SL exit**, **`reentry_enabled`** runs a **mandatory cooldown** first — inventory and TA **cannot bypass** cooldown (except **recovery early release** when enabled and price has recovered). Then the gate requires **structure stabilization** (full SL only — skipped for **scratch** tier), optional **bounce above recent low**, **TA score**, and **weakness** again.

**Scratch vs full:** Breakeven/small-loss exits use **`scratch_sl_cooldown_cycles`** and lighter gates. Real stops use **`sl_cooldown_cycles`** and stabilization. See [SL mitigations](#sl-mitigations--scratch-stops-clusters-recovery-live--re-entry-panel).

**Default-ish live overrides:** `sl_cooldown_cycles` may be high on VPS (e.g. 71) — pair with scratch/cluster/recovery knobs rather than setting SL cooldown to 1.

**Patient reload after SL:**

```text
reentry_enabled              = on
sl_cooldown_cycles           = 8–15        ← full SL only; scratch uses scratch_sl_cooldown_cycles
scratch_sl_max_loss_pct      = 0.10–0.20
scratch_sl_cooldown_cycles   = 3–6
sl_cluster_window_sec        = 1800–3600
recovery_enabled             = on
post_clear_buy_spacing_cycles = 4–8
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

**Nuclear:** `reentry_enabled = off` — SL exits do not block the next buy (see [Appendix E](#appendix-e--buying-too-often-in-a-downtrend) trade-offs).

**Verify:** `logs/alpha_reentry.json` shows cooldown counting down; reason shifts from `post_sl_cooldown` → stabilization/TA → then **`place_bid`**.

---


---

### Appendix L — Post-TP re-entry (waiting for dip)

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


---

### Appendix M — Balanced inventory, nothing to do

**Symptoms:** Decision **`HOLD — balanced dev=+0.02`** (or similar small deviation); neither buy nor sell; inventory label **`balanced`**.

**What’s happening:** **`deviation`** is between **`−weakness_deviation`** and **`+strength_deviation`**. Classic path: no weakness buys, no strength sells.

**Accumulation override (2026):** On bull/breakout tape the **accumulation regime** can still **`place_bid`** when the Live card shows **`armed`/`executing`** — Decision reason may say **`accumulation`**, **`bull_run`**, or **`tape_participation`** instead of weakness dev. If card is **`idle`** and reason is purely **`balanced dev`**, you are truly on target for classic logic.

**To buy on classic path:** lower **`weakness_deviation`** so current **`dev`** qualifies (e.g. dev **−0.04** needs weakness **≥ 0.04**).

**To sell anyway:** raise **`strength_deviation`** in config (default **0.04**; HUD exposes weakness only today) or wait until XRP allocation rises — or see [Appendix Y](#appendix-y--rlusd-reload-post-run-chop-funding) for **reload** funding sells (different gate).

**Often confused with:** [Appendix X](#appendix-x--accumulation-regime-chart-rips-balanced-hold) (tape armed but starved) · [Appendix D](#appendix-d--hold-forever-edge-in-the-reason) (edge gate) · [Appendix J](#appendix-j--ta-blocking-buys-in-chop) (TA gate) — read the **exact reason string** and **both Live cards**.

---


---

### Appendix N — Bid on book, mid looks good, still no fill

**Symptoms:** Brackets show **pending buy**; mid at or below entry on HUD; **`place_bid`** already executed; offer rests for minutes; no fill.

**What’s happening:** **Limit bids are passive.** Fill requires **best ask ≤ your bid** (or a seller hitting your price). **Mid crossing entry does not fill you.** Large **ask depth** above your bid means liquidity exists **higher**, not at your level.

| Check | Action |
|-------|--------|
| **Best ask** vs your entry (Market Conditions) | Ask must drop to bid |
| Spread ~10+ bps | Need a trade through the spread |
| Entry below best bid | You’re behind the touch — lower offset or wait |

**Fix for more fills:** lower **`buy_limit_offset_pct`** (nearer ask) — see [Appendix A/F](#appendix-a--rlusd-heavy-price-drifting-up-bid-feels-left-behind). **Not a bug** if mid dips visually but ask never trades to your bid.

---


---

### Appendix O — XRP-heavy, want strength sells

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


---

### Appendix P — Kill switch, drawdown, or pause

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


---

### Appendix Q — `ta_warming_up` / insufficient history

**Symptoms:** Early session or after restart; Decision **`ta_warming_up — insufficient price history for buy gate`**; TA panel sparse.

**What’s happening:** TA needs **`min_candles`** in price history (`alpha_price_history.json` samples). Until warmed, **`ta_weight` = 1** blocks buys.

**Fix:** Wait **15–30 min** of engine cycles (depends on **`alpha_price_sample_interval_seconds`** and chart bucket). Or temporarily:

```text
ta_weight = 0          ← advisory only until warmed
ta_enabled = off       ← last resort while learning
```

**Not the fix:** Lowering offset or weakness — gate is history, not inventory.

---


---

### Appendix R — `insufficient_ask_depth`

**Symptoms:** HOLD **`insufficient_ask_depth depth=0.XX`**; Market Conditions **Max buy** = **0** or tiny.

**What’s happening:** Book depth within **±1% of mid** is below **`min_order_size_xrp`**. Rare on RLUSD/XRP mainnet; can happen during outages, bad book snapshot, or testnet.

**Fix:** Check **best bid/ask** sanity on HUD. Wait for next engine cycle book refresh. If persistent, verify RPC/book health (preflight). **Do not** raise **`risk_per_trade_pct`** — depth is the binder, not risk cap.

---


---

### Appendix S — Trust phase (SKYNET bias)

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
4. **Decision reason** + **ready** badge — re-entry gates and `max_pending_buys` are **expected**; on rips check **Accumulation** / **RLUSD reload** cards before tweaking offset.
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
| Bull rip | SKYNET playbook **U** / **V** — bull run missed · accumulation knobs |
| Low RLUSD after run | SKYNET playbook **W** — reload / deploy floor |
| 48h | Paste sidebar numbers: ratio, realized 24h, TP/SL counts, last decision reason, **ready** badge |
| If bleeding | **Anti-bleed** / Appendix S knobs |

### Telegram / logs (optional)

- Hourly Telegram: alive + portfolio snapshot.
- Tax truth: `logs/trades_YYYY-MM.csv` on VPS — sum `profit_xrp_equiv` on SELL rows should match **Realized 24h** on HUD.

**Next full compare target:** ~**2026-06-26** (48h from baseline).

---


---

### Appendix T — Scale phase (modest accumulation)

**When:** Clean nights, deferred SL arming, XRP ratio climbing toward target, TP:SL improving. You earned trust — want **one notch** more deploy.

**HUD:** Operator phase → **Scale** → Save.

```text
alpha_operator_phase            = scale
alpha_operator_market_regime    = bull          ← optional; accumulation signals
alpha_buy_limit_offset_pct      = 0.15–0.20
alpha_weakness_deviation        = 0.04
alpha_accumulation_max_deviation = 0.06–0.08   ← mild XRP-heavy still arms on tape
alpha_bull_run_max_deviation    = match accum cap
alpha_max_pending_buys          = 2–3
alpha_risk_per_trade_pct        = 2–3%
```

**Dev caps vs imbalance:** `accumulation_max_deviation` allows accumulation logic when **mildly** above target XRP; **`alpha_max_inventory_imbalance_pct`** (default **0.10**) still hard-blocks new bids when too XRP-heavy. Raise caps together only with intent.

**Rule:** Change **one knob at a time**. Prefer **`max_pending_buys`** before **`buy_limit_offset_pct↓`**.

**Quick prompt:** **Scale phase knobs**.

---


---

### Appendix U — Aggressive phase (bag push)

**When:** Multi-day realized P&amp;L healthy, TP:SL acceptable, you accept churn. Often paired with **bull** SKYNET **market regime** so accumulation can arm on rips.

**HUD:** Operator phase → **Aggressive** → Save. Set **market regime** → **Bull** if you want tape-aligned deploy (not required for every night).

```text
alpha_operator_phase              = aggressive
alpha_operator_market_regime      = bull          ← advisory; helps accumulation prompts
alpha_buy_limit_offset_pct        = 0.08–0.12
alpha_weakness_deviation          = 0.03–0.04
alpha_max_pending_buys            = 3
alpha_risk_per_trade_pct          = 3–4%          ← only on larger book you can afford to bleed
```

**With accumulation regime on (default):** engine may use **tighter** accumulation offset (~0.06%) when **ARMED** — you do not need to manually set 0.08% unless scorecard shows zero fills and no reload block.

**Revert triggers:** SL streak, PRO **sl_heavy**, missed-move + zero fills with RLUSD starved → back to **trust**, check [Appendix Y](#appendix-y--rlusd-reload-post-run-chop-funding) before cranking offset.

**Quick prompt:** **Aggressive phase knobs** · SKYNET playbook **U**/**V** if chart rips on balanced dev.

---

### Appendix Z — Elliott 5-wave + divergence detector

**When to use:** TA tab looks bullish but accumulation stays **off** / Decision shows **`ta_sell_blocked`** while XRP-heavy; or you want reversal confluence before lowering `weakness_deviation`.

#### Elliott (structure context, not arming)

- Scans **zigzag pivots** on **`elliott_wave.lookback`** closed bars (default **50**).
- **Wave label** (`W1↑` … `W5↑`, `W4↑`, `ABC?`) describes position in the best-fit 5-wave count.
- **↑ / ↓** on the label = direction of **that wave leg**, not the strategy mode name.
- **`elliott_trend`**: `bullish_impulse` | `bearish_impulse` | `corrective` | `neutral`.
- **Scoring:** W3 strongest buy/sell contribution; W5 half; W2/W4 dip-friendly (`dip_wave_weight_mult`).

**Does not arm accumulation.** Arming still requires signals such as `breakout_up`, bull_run drift, `momentum_entry`, tape + slope, or classic `dev ≤ −weakness`.

**Common misread:** **`W4↑`** with **`bearish_impulse`** — counter-trend bounce inside a down-impulse count; TA bias can still be **bullish** from RSI/Stoch.

#### Divergence (reversal confluence)

| Type | Price | Indicator | TA effect |
|------|-------|-----------|-----------|
| Bullish regular | Lower low | Higher low (RSI/Stoch) | +buy score |
| Bearish regular | Higher high | Lower high | +sell score |
| Hidden | Continuation pivot | Opposite indicator move | Milder weight |

- Pivot scan shares the same family as Elliott (`min_swing_pct` on `divergence` config).
- Fires appear in: TA **Signals** row `divergence`, **Bias** sub-line, **accumulation scorecard**, SKYNET `technical_analysis` payload.
- **`alpha_ta_divergence_enabled`** on TA tab — master HUD toggle.

**Strategy fit:**

- **Weakness buys** — bullish divergence + fib + oversold RSI → stronger dip bids (brackets unchanged).
- **Strength sells** — bearish divergence → favor `ta_sell_deferred` / tighter RLUSD brackets on rips.
- **Accumulation** — `divergence:bullish_regular@rsi` signal when fired; still blocked by dev cap, reload floor, inventory.

**SKYNET:** Ask with Live context — read **`gate_diagnostics`** block before advising “wait for next cycle.” Compare `accumulation_dev_cap` and `bull_run_dev_cap` to live `dev`.

**Config path:** `alpha_technical_analysis.elliott_wave` · `divergence` · `volume_confirmation` · `htf_bias` in `config.yaml`.

**Roadmap (not yet):** vol-adjusted BB/RSI bands, daily anchor, XRPL on-chain flow tie-in.

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


*Grow the bag. Respect the spread. Read the reason string.*
