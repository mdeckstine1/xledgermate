# XLedgerMate — Strategy Manual

*Version 1.4.2 · What the bot is trying to do with your money, in plain language*

This document is about **strategy and risk**, not which buttons to press. For setup, tabs, and wallet steps, see [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md).  
For the engineering roadmap and **pilot → field deployment gates** (validation, competitive pilot, scale), see [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

---

## The idea in one paragraph

XLedgerMate is a **market maker** on XRP/RLUSD. It posts **buy and sell offers** near the current market price and tries to earn the **spread** when both sides fill over time. It is built to be **defensive**: when the market is fast, thin, or unprofitable, it **quotes wider, trades smaller, or steps aside** rather than fighting for every fill. It also **nudges your wallet** toward a target mix (by default about **55% XRP / 45% RLUSD** in value terms) by skewing quotes — it does **not** swap coins for you on-chain.

### Example — a good hour (what success looks like)

Mid price is stable around **1.34 RLUSD per XRP**. The bot posts a bid slightly below mid and an ask slightly above. A buyer lifts your ask (you sell a little XRP); later a seller hits your bid (you buy a little XRP). You keep the **spread** between those two prices, minus fees. Your wallet drifts a bit but stays near **55% XRP**. Session P&L ticks up slowly — not because price mooned, but because **both sides paid you to provide liquidity**.

### Example — a bad hour (what defense is for)

News hits and mid drops **0.6% in five minutes**. Everyone hits the bids. If you had left **large buy orders** tight to the market, you would buy XRP all the way down. The bot instead **widens bids, shrinks size, or pauses buying** while the move is violent. You miss some spread, but you avoid being the **exit liquidity** for the whole move.

---

## What you are and are not running

**You are running:** A quoting bot that competes for spread while trying not to get picked off when price moves.

**You are not running:** A rebalancer, a trend follower, or a “guaranteed profit” machine. If you are **80% XRP** and want **55%**, you still need **fills on the right side** or a **manual swap** on Xaman or a DEX. The bot will help over time; it will not teleport inventory there in one click.

### Narrative — “I’m 80% XRP and I turned the bot on”

You funded the bot with mostly XRP. The target is **55% XRP**. The bot will **favor ask quotes** (selling XRP for RLUSD): somewhat **tighter / larger sells** and **wider / smaller buys**. Over many cycles you should see **RLUSD build up** and XRP % fall — but only if the market actually trades with you. If price rips upward, you might sell XRP too early and still look “too XRP heavy” on paper. That is normal inventory risk, not a broken bot. If you are **15%+ away** from target and need to sleep, a **manual swap** plus **safe** mode is often saner than cranking aggression.

---

## How the bot thinks every cycle (about once a minute)

Each refresh, it looks at the live order book and your balances, then decides **how wide** to quote, **how large** each order should be, and **whether to lean** toward buying XRP or selling XRP. Roughly, these ideas stack on top of each other:

| Priority (highest first) | Plain English |
|--------------------------|---------------|
| **Safety checks** | “Are my planned prices sane vs the real best bid and ask?” If not, live orders may be blocked. |
| **Market stress** | Fast moves, thin book, or ugly conditions → widen, shrink, or pause a side. |
| **Minimum edge** | “Is there enough room to cover fees and a little profit?” If not → usually **smaller size**, not hero quotes. |
| **Inventory** | Too much XRP → favor sells (asks); too much RLUSD → favor buys (bids). |
| **Profile mode** | Your chosen risk posture (`safe`, `tight_spread`, etc.) sets the baseline. |
| **Dynamic quoting policy** | Each cycle picks **at-touch**, **near-touch**, **spread-mid**, or **off-book** from profile bounds + health + toxicity (one resolver — no conflicting “posture” paths). |
| **Your saved settings** | Base spread %, order sizes, risk capital — the starting point you confirmed in the GUI. |

When two goals conflict, **protection usually wins**. Example: you are heavy XRP and want to sell, but price is falling hard — the bot may still **protect the bid side** or pause rather than blindly chase inventory.

### Scenario A — calm book, balanced wallet

**Market:** Favorable, tight spread, low vol.  
**You:** ~54% XRP, **safe** profile applied (0.10% base on disk).  
**Bot behavior:** Quotes near the market but not crossing; modest size; small skew. You might get one fill per side per few cycles. Decisions show **market edge OK**, **spread check OK**.  
**What you should expect:** Slow, boring P&L — that is fine.

### Scenario B — price falling fast (protect asks / pause)

**Market:** Mid down **0.35%** over the last few samples; momentum tier **strong** or **extreme**.  
**You:** **safe** or **high_volatility**.  
**Bot behavior:** **Wider asks, smaller ask size**; may **pause asks** on extreme moves so you are not dumping into a falling market. Bids may also widen so you do not catch knives.  
**What you should expect:** Fewer fills, less adverse selection. Do not switch to **profit_mode** because you are bored.

### Scenario C — price ripping up (protect bids)

**Market:** Mid up quickly; buyers stack in the book.  
**Bot behavior:** **Wider bids, smaller bid size**; may pause bids on extreme up moves. Asks may be more competitive if you are XRP-heavy (inventory wants sells).  
**What you should expect:** You might sell XRP on the way up — good for inventory, easy to regret if you fear missing the rip.

### Scenario D — thin book, wide spread

**Market:** Health score weak; liquidity **low**; book spread **wide** or **very wide**.  
**You:** Dashboard suggests **thin_liquidity** or **safe**.  
**Bot behavior:** **Smaller clips**; quotes farther from mid; strong reaction if depth is one-sided. Edge guard may shrink size further.  
**What you should expect:** Low fill rate until the book thickens — again, that is intentional.

### Scenario E — spread guard blocks live orders

**Market:** Vol moved; your **planned** ask is now far above the real best ask (or bid too far below).  
**Bot behavior:** Cycle completes with **spread check FAILED**; **no new live orders** until quotes are sane. Old offers may still sit until refresh/cancel.  
**What you should do:** Stay in dry-run or fix profile/spreads; do not assume the bot is “broken.”

---

## How to read your P&L in the GUI

| What you see | What it means |
|--------------|---------------|
| **Portfolio (XRP equivalent)** | Everything valued in XRP using the current mid: XRP plus RLUSD converted at that price. |
| **Session P&L** | How that total changed since you **started the engine this session**. Restarting the engine resets this baseline. |
| **Balance change P&L** | Change in raw XRP and RLUSD balances, marked at today’s mid — closer to “coins in/out,” less sensitive to mid moving while you hold. |

A red session P&L after a volatile hour does not always mean “bad trading”; it can be **inventory marked at a new price**. Use session P&L together with **how full you are on each side** and whether you are near your **55% XRP** target.

### Example — “Session is red but I didn’t trade badly”

You start at **234 XRP** equivalent, mostly XRP. Mid is **1.34**. Over an hour mid drifts to **1.32** without many fills. You are still ~80% XRP. **Session MTM P&L** goes negative because the RLUSD you hold and the XRP you hold are worth less at the new mid — **mark-to-market**, not necessarily bad quotes. **Balance change P&L** might be nearly flat if few fills happened. Read both numbers before changing profile.

### Example — “Lots of fills, session still red”

You traded actively in **profit_mode** during a choppy book. You bought XRP on small dips and sold on small rips, but **fees and adverse selection** ate the spread. Session and balance P&L can both be red. That is a signal to step back to **safe**, widen, shrink size — not to tighten more.

---

## Four ways people use the bot

1. **Defensive market making (default)** — Accept slow inventory drift; swap manually when deviation hurts.
2. **Inventory first** — Get near 55% XRP with a manual trade, then use **safe** mode to hold the mix.
3. **Spread first** — Use **tight_spread** when the book is friendly; accept that inventory may sit lopsided.
4. **Hybrid** — Manual swap when you are more than ~15% off target; let the bot work between swaps.

### Vignette — defensive MM

Maria runs **safe**, L1 size **15 XRP**, only when conditions are neutral or better. She manually swapped once from 78% → 58% XRP, then let the bot **nudge** her around 55%. She measures success in **weeks**, not hours.

### Vignette — inventory first

James funds with XRP only. He uses **fund with XRP only** until he has RLUSD, then turns bids on. He applies **safe** only after he can quote both sides. His first goal is **operational**, not max spread.

### Vignette — spread first

The book has been **favorable** for a day. He applies **tight_spread**, accepts 62% XRP for now, and watches **edge** and **spread check** every cycle. If inventory pain exceeds spread income, he swaps or returns to **safe**.

### Vignette — hybrid

Every time he drifts past **70% or 40% XRP**, he swaps in Xaman, then runs **safe** between events. The bot is maintenance, not the primary rebalance tool.

---

## Profiles: what they are

A **profile** is a **risk mode**, not a magic profitability switch. Think of it as answering: *“How hungry should we be for fills right now?”*

There are **five** built-in profiles:

- **safe** — Protect capital; wide quotes; small size; strong inventory steering.
- **high_volatility** — Market is jumping; widen more, trade less, protect early.
- **thin_liquidity** — Book is shallow; careful size, react strongly to one-sided depth.
- **tight_spread** — Conditions are decent; compete more for spread; still guarded on mainnet.
- **profit_mode** — Calm, tight, liquid book only; tightest quotes and largest appetite — **highest risk of getting run over**.

The Dashboard may **suggest** a profile when vol, liquidity, and spread look like a known pattern. That suggestion is advice until you **apply** it (see below).

### Example — suggestion vs action

The market panel says **“Suggested: tight_spread — stable vol and decent liquidity.”** You are still on **safe** with **0.10%** base on disk. Until you click **Apply profile now**, the bot keeps quoting like **safe** even if you changed the dropdown. The suggestion is a **weather forecast**; Apply is **dressing for the weather**.

---

## Profiles: two things actually change (this matters)

Many operators assume changing the profile dropdown is enough. It is not. A profile changes behavior in **two separate ways**, and both need to line up.

### 1. What you save in the GUI (“Apply profile now”)

When you click **Apply profile now**, the bot writes a **preset package** to your saved settings, including:

- Which profile name is active  
- **Base spread %** (how far from mid you start before adjustments)  
- **Level step %** (how much wider level 2 and 3 are vs level 1)  
- **Edge strictness** (Low / Normal / Strict — how picky about minimum profit)  
- **Book pressure sensitivity** — preset saves **1.0** on disk; the **profile** owns the real multiplier (e.g. safe **1.25×**) so Apply does not double-stack pressure.  
- **Dynamic min edge** (on/off — whether required profit can relax slightly when the book itself is very tight)

You should see a line on Controls like **“Saved on disk: profile … base spread …”**. If the base spread shown there does not match the profile you think you are on (e.g. **safe** but still **0.03%**), your quotes are still using the old spread — click **Apply profile now** again.

**Apply profile does not change:** order sizes (XRP per level), risk capital, daily drawdown limit, dry run, or the mainnet “stay near the touch” safety limits. You set those yourself and **Save Config**.

### 2. How the bot behaves every cycle (built into the mode)

Even with the same base spread saved, **safe** and **profit_mode** behave very differently. Each mode carries built-in behavior:

- **How wide quotes end up** after the bot reacts to volatility and thin liquidity  
- **Smallest spread** the bot will allow in a quiet market  
- **Order size** relative to normal (e.g. safe uses smaller clips)  
- **How hard it pushes** inventory back toward 55% XRP  
- **Minimum edge** (profit cushion) before it is willing to quote normal size  

So: **saved numbers** are the starting line; **the profile** is the personality that runs on that line every minute.

**Important:** If you only change the dropdown and hit **Save Config** without **Apply profile now**, you may save the new profile **name** but leave old spreads — the bot will say “safe” while still quoting like “tight.” That is the most common reason performance “does not change.”

**Auto profile switching** (if you turn it on) can change the **active mode name** by itself after you have been idle; it does **not** automatically rewrite your base spread and edge settings. After an auto-switch, click **Apply profile now** if you want the sliders and “Saved on disk” to match the new mode.

### Story — the “I picked safe but nothing changed” mistake

Monday: You run **tight_spread** with **0.06%** base; it feels too aggressive after a loss.  
Tuesday: You select **safe** in the dropdown and hit **Save Config**. Disk still shows **0.06%** base (only the name changed to safe).  
Wednesday: You wonder why the bot still trades like tight.  

**Fix:** **Apply profile now** → disk shows **safe** and **0.10%** base → then **Save Config** if you changed order sizes.

---

## Edge guard vs spread guard (trader language)

| | Edge guard | Spread guard |
|---|------------|--------------|
| **Question it asks** | “Is there enough spread here to bother?” | “Are my prices absurd vs the real best bid and ask?” |
| **If it fails** | Usually **smaller orders**; may still plan quotes | On mainnet live, can **block** sending new orders until fixed |
| **Tied to profile?** | Yes — stricter modes demand more edge | No — your safety limits on Controls |
| **Analogy** | “Is the juice worth the squeeze?” | “Am I about to post a quote miles from the market?” |

Tighter profiles (**tight_spread**, **profit_mode**) accept thinner edge; they do **not** turn off spread guard on mainnet.

---

## Dynamic quoting policy (v1.4.1)

Each cycle the engine runs **one** policy resolver. It chooses how close quotes sit to the live best bid/ask:

| Mode | When | What you see |
|------|------|----------------|
| **At-touch** | Book pays required edge; tight/normal spread | Small L1 backoff; two-sided when inventory allows |
| **Near-touch** | Book thinner than edge but market favorable/neutral | Joins L1 with backoff sized to edge gap — **visible** without blind pickoff |
| **Spread-mid** | Hostile, wide book, or edge not met | Quotes from spread model; capped **≤8–14%** from touch (profile) |
| **Off-book** | Toxicity ≥ profile no-touch limit (~18–25%) | No L1 join; may pause refresh; unload side only |

**Toxicity ladder (profile-owned, not one magic number):**

1. **Markout** — single fill adverse if price moves ~4+ bps against you within 30s.  
2. **Pause side** (~18%) — stop bidding (or asking) when skew + adverse fills align.  
3. **No touch** (~20% safe) — policy steps off L1 entirely.  
4. **Pause refresh** (~22% safe) — skip cancel/replace until quality improves.  
5. **Kill** (optional, off by default on pilot) — hard halt if `toxic_fill_kill_enabled` and ratio exceeds threshold over many fills. **Safe pilot:** use refresh pause + off-book only; enable kill later if you want a nuclear stop.

**Toxic @30s at 100%** with only one or two fills means “every fill that has a 30s score so far was bad” — not necessarily a broken bot. Check **Toxic ratio**, inventory skew, and whether you **bought XRP into a falling tape** while already XRP-heavy.

### Example — edge guard

The visible book spread is **0.08%**. Your profile wants **~0.12%** edge after fees. The bot still places quotes but at **~half normal size**. Decisions mention **edge guard**. You earn less per fill but bleed slower when the book is too tight.

### Example — spread guard

Best ask on the book is **1.3420**. Because of skew and stale settings, your planned ask is **1.3510** — too far above the touch. **Spread check FAILED**; live placement blocked. You fix spreads or Apply the right profile; next cycle **spread check OK**.

---

## Market conditions — what the bot should do

The Dashboard labels the environment **Favorable**, **Neutral**, **Defensive**, or **Hostile** (plus vol, liquidity, and book spread). Below is what that means in practice and what you should expect.

### Favorable — “the book is cooperating”

**Typical signs:** Health score high; vol not elevated; liquidity not thin; book spread tight or normal.

**What the bot should do:** Quote **more competitively** than in stress (within your profile). On **safe**, that still means wider than **tight_spread** — do not confuse favorable with profit_mode automatically.

**Suggested profile:** Often **tight_spread**; **profit_mode** only when vol is low, liquidity high, and spread truly tight for several cycles.

**Narrative:**  
For two hours, mid wiggles between 1.338 and 1.342. Liquidity score is strong. You apply **tight_spread**. Fills pick up on both sides. Inventory hovers 52–58% XRP. Session P&L creeps positive. This is the window to earn spread — still watch for sudden vol.

**Operator mistake:** Jumping to **profit_mode** on the first green “Favorable” reading without stable session P&L.

---

### Neutral — “ordinary day”

**Typical signs:** Health in the middle band; nothing extreme.

**What the bot should do:** Run your profile’s **baseline** personality — no extra tighten from favorable overlay, no full defensive widen.

**Suggested profile:** Often **safe** if mixed signals.

**Narrative:**  
Vol is moderate; book is neither gift nor disaster. You stay on **safe** with 0.10% base applied. A few fills per hour; inventory drifts slowly. You do not optimize — you **collect data** and watch drawdown vs your kill switch.

---

### Defensive — “stress building”

**Typical signs:** Health slipping; or vol high; or liquidity low (but not necessarily both worst-case).

**What the bot should do:** **Widen spreads** and **cut size** vs baseline (overlay on top of your profile). Inventory skew still applies but protection ramps up.

**Suggested profile:** **safe**, **high_volatility** (if vol is the problem), or **thin_liquidity** (if depth is the problem).

**Narrative:**  
Spread on the book widens from 0.2% to 0.5%. Vol ticks up. The bot’s decision summary says **defensive → wider + smaller**. Fill rate drops. Session P&L may wobble from marks more than from trading. You **do not** tighten to catch fills; you consider **high_volatility** + Apply, or pause and watch.

---

### Hostile — “capital preservation”

**Typical signs:** Very poor health; or **high vol and low liquidity together**.

**What the bot should do:** **Much wider**, **much smaller** size; momentum may **pause** a vulnerable side; hostile + extreme momentum is especially cautious.

**Suggested profile:** **safe** (always the recommendation here).

**Narrative:**  
A sudden sell wave: wide spread, thin depth, mid falling. Condition flips **Hostile**. On **safe**, quotes are far from touch, sizes small. You might go minutes without a fill. That is correct: your job is **not to die**. When condition improves to defensive then neutral, you re-evaluate — you do not leave **profit_mode** on from yesterday.

---

## Profile guide — what each mode is for

Each profile below includes **when to use it** and a **short story** of correct operation.

### safe (start here on real money)

**Goal:** Stay in the game; lose slowly if you must lose; steer inventory firmly.

**After Apply profile, typical saved settings:** about **0.10%** base spread, normal edge strictness, dynamic edge **off**.

**How it feels live:** Wider quotes than tight modes; **smaller** order sizes; strong push toward your target XRP/RLUSD mix; comfortable in choppy or defensive markets.

**Use when:** Learning the bot, recovering from drawdown, inventory messy, or you do not trust the book.

**Avoid when:** You are trying to maximize fills in a dead-calm, tight market — you will look too far from the touch.

**Story:**  
You run **234 XRP** risk capital, L1 **15 XRP**, **safe** applied. Hostile morning → few fills, small loss from marks. Afternoon turns neutral → occasional two-sided fills. You never see **profit_mode** in the suggestion. After a week, session P&L is slightly positive and inventory near 55%. You consider **tight_spread** only then.

---

### high_volatility

**Goal:** Survive spikes; do not get run over when price jumps.

**After Apply:** about **0.12%** base, **strict** edge, dynamic edge off.

**How it feels live:** Extra-wide quotes; **smallest** typical sizes; quick to defend when momentum picks up.

**Use when:** Volatility is elevated, conditions look hostile or nervous, or fills feel like toxic flow.

**Story:**  
Every headline moves XRP 0.3% in minutes. You Apply **high_volatility**. The bot pauses or shrinks the side price is running through. You complain about “no fills.” Compare that to the alternative — being fully filled on the wrong side of a spike. When vol calms, switch back toward **safe** or **tight_spread** with Apply.

---

### thin_liquidity

**Goal:** Thin book — do not post large clips into a hole.

**After Apply:** about **0.11%** base; highest **book pressure** sensitivity.

**How it feels live:** Smaller size; quotes react strongly when depth is one-sided; favors survival over volume.

**Use when:** Liquidity score is poor, spread is gappy, or you keep getting filled on one side only.

**Story:**  
The book shows **wide** spread and low depth. You keep getting hit on asks only — inventory piles into XRP. You Apply **thin_liquidity**. Sizes shrink; when bid depth is huge, the bot protects bids (does not blindly join the bid stack). You wait for depth to return before expecting income.

---

### tight_spread

**Goal:** Compete when the market is cooperating; still defensive on mainnet.

**After Apply:** about **0.06%** base; **low** edge strictness; dynamic edge **on**.

**How it feels live:** Noticeably tighter quotes and **larger** clips than safe; lighter inventory push.

**Use when:** Dashboard shows **favorable** conditions, book spread is tight, inventory is not extreme, and **safe** has been stable for a while.

**Story:**  
Three days of **safe** with positive session P&L. Today: favorable, tight book, low vol. You Apply **tight_spread**. Fills double; spread income visible. One bad hour: momentum **strong** down — bot widens anyway. You do not revert to **profit_mode** during that hour.

---

### profit_mode (expert / ideal book only)

**Goal:** Extract maximum spread in the best possible conditions.

**After Apply:** about **0.04%** base; low edge strictness; dynamic edge on.

**How it feels live:** Tightest quotes, **largest** sizes, most aggressive — also the easiest mode to **lose to adverse selection** if the book turns.

**Use when:** Suggested profile stays on profit_mode for many cycles, vol is low, liquidity is good, inventory is acceptable, and you accept more risk.

**Avoid when:** Piloting mainnet, inventory is wrong, or you have not proven positive session results on **safe** or **tight_spread** first.

**Story:**  
Perfect afternoon: tight book, low vol, 56% XRP. You Apply **profit_mode**. Spread income is best all week. Next morning: vol spikes while you are still on profit_mode without re-applying **safe** — you take several bad fills before you notice. Lesson: **profit_mode is a weather window**, not a default home.

---

## Quick comparison table

| Profile | Quote width | Typical size | Inventory push | Min profit cushion | Market you want |
|---------|-------------|--------------|------------------|--------------------|-----------------|
| **safe** | Wide | Small | Strong | Higher (~0.12%) | Anything stressful |
| **high_volatility** | Widest | Smallest | Strong | Highest (~0.13%) | Vol spikes |
| **thin_liquidity** | Wide | Small | Strong | Medium (~0.11%) | Shallow book |
| **tight_spread** | Tighter | Larger | Light | Lower (~0.08%) | Favorable |
| **profit_mode** | Tightest | Largest | Moderate | Lowest (~0.05%) | Calm + tight |

---

## Suggested workflow (profiles)

1. Read the **market panel** — condition, vol, suggested profile.  
2. Pick the mode that matches **today’s book**, not the P&L you wish you had.  
3. Click **Apply profile now** — confirm **Saved on disk** (profile name + base spread make sense).  
4. Set **order sizes** and risk capital if needed; **Save Config**.  
5. Watch a few cycles: spread check OK, edge messages, inventory steering.  
6. Only move **safe → tight_spread → profit_mode** when results and conditions support it.

**Run one cycle** does not apply profile presets. **Save Config** alone does not apply them either — use **Apply profile now**.

### Walkthrough — one full day

| Time | Market | You do | Bot should |
|------|--------|--------|------------|
| 08:00 | Neutral after overnight | Apply **safe**, L1 15 XRP | Wide-ish quotes; slow fills |
| 11:00 | Turns favorable | Apply **tight_spread** if session P&L OK | Tighter; more fills |
| 14:00 | Vol spike, defensive | Apply **high_volatility** | Wide, small; protect sides |
| 16:00 | Back to neutral | Apply **safe** | Back to capital-first |
| Never | Hostile + you want action | **Do not** Apply profit_mode | Preserve capital |

---

## Settings profiles do not touch

You still control these separately:

- **Order sizes** (how many XRP per level)  
- **Risk capital** (how much of the book you are willing to use)  
- **Target inventory** (default 55% XRP)  
- **Dry run vs live**  
- **Daily drawdown kill switch**  
- **Spread guard limits** (how close to the touch live orders must be)

### Example

You Apply **safe** (spread preset) but leave L1 size at **50 XRP** with only **234 XRP** risk capital. The bot will still try to quote **50 XRP** clips (subject to caps). Profile changes **how** you quote, not **how large** you chose unless you set sizes yourself.

---

## Further reading

- [`OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md) — Buttons, Apply profile, spread guard, kill switch.  
- [`MAINNET_PILOT.md`](MAINNET_PILOT.md) — Pilot scope and checklist.
