# Phase E (Intel): Dynamic Competitor Intelligence & Relative Peer Sizing

**Status:** Draft — operator principles locked (2026-06-13)  
**Branch:** `xledger-ws-as` / `grok-ws-feed` (experimental)  
**Related:** WS + pure A-S path, Intelligence tab / HUD, `dynamic_sizing.py`, `competitor_intel.py`  
**Checklist:** [`docs/PURE_AS_CRITICAL_PATH.md`](../docs/PURE_AS_CRITICAL_PATH.md) **Phase G** (VPS swap stays Phase E there — naming collision avoided in checklist)  
**Date:** 2026-06-13  

## 0. Operator principle — stay in your lane

**We cannot compete with top-10 whale accounts.** Intelligence must compare us to **similar-sized peers** — the whole reason the bot scales.

**Peer lane ruler (locked): posted touch size, not portfolio.**

- **`our_lane_xrp`** each cycle = our **posted touch** on the book (L1 bid/ask size from `dynamic_sizing` / `quote_intents` level 1). Optional extension: L1+L2+L3 ladder total for “depth lane.”
- **`peer_lane`** = makers whose **posted touch** at best bid/ask falls in a band around `our_lane_xrp` (e.g. 0.4×–2.5×, tunable).
- The lane **moves with inventory** because posted size moves with inventory (`min(configured_l1, k × balance)`). Growth from **fills or deposits** both widen the lane — that is intentional (bigger bag → bigger weight class).
- **Top-N by activity** (current scraper) remains **context only** in the HUD. **Pressure, observed spread, and structural signals** for quoting inputs come from **`peer_lane` only**.
- **Empty peer band:** widen once, then **neutral** (do not inherit whale behavior).

**Success ruler (separate from peer matching): portfolio XRP-equivalent.**

- Primary bag metric: **portfolio value in XRP-equiv** (`XRP + RLUSD/mid`) growth from **MM activity (fills)**, not deposits.
- Mix of XRP and RLUSD is fine — we are not grading “XRP balance must always rise.”
- Secondary: inventory deviation vs target (~55% XRP); A-S reservation + rebalance bias steer mix.

**Safety (unchanged):** Intelligence modulates `size_mult`, side bias, skim posture — **never** reservation price or `would_quote`.

**MM economics (operator-locked):** We are **market making**, not directional trading.

- **P&L comes from spread / rake** (capture per fill, round trips), not from betting on inventory moves.
- A bad fill or a lost “setup” is a **spread-quality** problem (toxic pickoff, negative capture) — not a signal to **kill**, halt, or abandon core two-sided MM.
- **No chasing big wins:** the scaler must not ramp aggression after a hot streak or treat one good hour as permission to leave lane discipline.
- **No full-stop on a losing stretch:** tighten slightly (size_mult down, wider effective spread via vol), keep quoting when A-S allows — do not flip into trader mode or sit out the book unless A-S / toxicity math already says so.
- **No panic-cancel after a mistake:** getting picked off hurts; **yanking quotes in shame** is a common MM weakness (seen in other makers). We refresh on **math** (A-S, spread check, toxicity dimmer), not on emotional exit. Staying on book with slightly softer posture beats leaving touch empty for the lane.
- Portfolio XRP-equiv and inventory target are **health / steering** metrics, not the primary scoreboard for whether MM is working.

---

## 1. Overview & Goals

Phase E (Intel) evolves competitor intelligence from static/top-10 analysis to a **dynamic, posted-touch-scaled peer system**.

The goal is disciplined market making in our weight class while **portfolio XRP-equiv** grows over time.

### Primary Objectives
- **Peer lane** from posted touch (L1; optional L1–L3), scaled as inventory/deposits move posted size.
- Objective **structural signals** on peers only (cancel behavior, one-sided pressure, defense, book velocity).
- Modest edges on favorable peer-local setups; A-S reservation protected.
- Natural scaling: small bag → small peers; larger bag → larger peers.

### Success Criteria
- Peer signals match our posted size (§7.6).
- Spread capture and portfolio XRP-equiv up from fills (§7.1, §7.2).
- Clear visibility into lane, peers, and why we biased size/side.
- No quoting logic driven by whale accounts we cannot compete with.

## 2. Core Design Philosophy

This is a **market making system** focused on collecting the spread and growing **portfolio XRP-equiv** in our lane.

Key principles:
- **Posted touch** defines who we compare to; **portfolio XRP-equiv** defines whether we are winning.
- Avoid momentum chasing and tilt based on recent P&L.
- Intelligence modulates how A-S is applied (size, bias, aggression) — not reservation.
- Deposits and fill-driven growth both move the lane; the bot does not treat deposits as “out of band.”
- Accept controlled risk on favorable **peer-local** structures only.

## 3. Proposed Architecture

### 3.1 Dynamic relative peer band (E.1 — posted touch)

**Per cycle:**

1. Compute **`our_lane_xrp`** from live `quote_intents` / `compute_pure_l1_sizes`:
   - Default: `max(bid_size_xrp, ask_size_xrp)` at level 1 (touch).
   - Optional: sum of active L1–L3 sizes on each side for ladder-aware lane.
2. Scrape book; for each account compute **`peer_touch_xrp`** = size at best bid + best ask for that account (or max of the two sides at touch).
3. **`peer_lane`** = accounts where `peer_touch_xrp ∈ [our_lane × peer_low_mult, our_lane × peer_high_mult]`.
   - Starting defaults: `peer_low_mult = 0.4`, `peer_high_mult = 2.5` (tune in replay).
4. Aggregate **observed spread**, **pressure**, depth on **`peer_lane` only** → feed `competitor_pressure` / HUD.
5. If `len(peer_lane) < min_peers` (e.g. 1): widen band once (e.g. ×1.5 each bound); if still empty → `pressure_score = 0.5` (neutral), log `peer_lane_empty`.

**Not in peer band:** Total wallet balance (unobservable on-chain). Whales with small touch stay in lane; whales with huge touch stay out.

**Code touchpoints:** `experimental/market_analysis/competitor_intel.py` (today: `avg_size_xrp` + sort by activity → change to touch-size band filter); `experimental/competitor_pressure.py` (inputs from peer-lane aggregates).

### 3.2 Structural signals (incl. panic-cancel weakness)

Objective, observable signals on **`peer_lane` only**:

- **Cancel-after-adverse / panic refresh** — peer pulls quotes too fast after a fill or tick against them → **defensive error**, often leaves touch thin; *opportunity* for in-lane presence, not behavior to copy.
- Sustained one-sided pressure, defense strength, book velocity vs spread.

**Our discipline vs theirs:** Other MMs often cancel too fast because they know they erred — it hurts, but it is a **weakness**. We do not mirror that. Bad capture → G2 dimmer + A-S wider; **keep core two-sided MM** when reservation allows. Structural intel may flag “peer fled touch” as low pressure / skim window — never as “we should flee too.”

Used to identify modest in-lane edges; never to override reservation.

### 3.3 Spread-quality scaler (G2 / E.2 — not a “performance chase”)

**Touchy component — strict rules:**

- **Primary input:** rolling **spread capture** (positive capture %, avg bps per fill, toxic/neg-fill rate) — **not** session P&L, not inventory MTM, not “big win” detection.
- **Brake only by default:** worsening capture/toxicity → small `size_mult` reduction or slightly higher effective vol — **keep core MM operations** (refresh, two-sided when A-S allows).
- **No kill-switch coupling:** a losing half-day of MM does **not** trigger wholesale stop; sacred kill stack handles true catastrophes — G2 scaler is a **dimmer**, not an off switch.
- **No win-chasing:** after strong capture streak, **do not** auto size-up or abandon peer-lane discipline; size-up (if ever enabled) requires peer-local structural signals + capture grade, capped and rare.
- **One lost setup ≠ change strategy:** log it, maybe one notch softer next cycles, stay in lane.

### 3.4 Advisory Intelligence Layer
- All intelligence outputs are advisory.
- Modulates size_mult, side bias, and skim_harder through gated signals.
- Core A-S reservation price remains protected.

## 4. Key Mechanisms

### 4.1 Spread-quality scaler (G2)

- Tune on **capture bps and neg-fill %**, not portfolio delta or “hot hand.”
- Default: **brake-only** dimmer on `size_mult` / vol inputs.
- Optional future: **tiny** size-up only when peer structural + capture grades are both good — never after a single big win.
- Explicitly **excluded:** momentum tilt, session P&L chase, kill-switch triggers, one-sided “go for it” mode.

### 4.2 Structural Bias
- Light to moderate bias allowed on clearly favorable structural setups.
- Focus on competitor behavior and book structure rather than momentum.

### 4.3 Inventory & spread (division of labor)

- **A-S reservation** steers inventory toward target — operational, not the profit model.
- **Profit model** = spread capture on fills; intelligence must not confuse “bag moved” with “MM won.”
- Intelligence supports consistent in-lane MM; it does not turn the bot into an inventory bet.

## 5. Scaling with inventory growth

Posted touch scales with bag (and deposits); peer lane scales with it automatically:

| Posted touch (our lane) | Peer band targets | Gating |
|-------------------------|-------------------|--------|
| Small (~10 XRP L1) | Other small touch makers | Conservative bias; widen band if sparse |
| Mid (50–100 XRP L1) | Mid-tier two-sided MMs | Standard mults |
| Large (post-deposit / 11k thesis) | Larger touch peers, still not global top-10 unless touch matches | Stronger structural signals when peer coverage good |

Advanced contrarian logic remains a future module.

## 6. Live Market Making Considerations

- Strong emphasis on observability and logging.
- Intelligence can start in advisory/monitoring mode.
- Gradual activation with clear rollback options.
- Focus on consistent, lower-drama bag building.

## 7. Performance Grading & Evaluation Criteria

To evaluate live MM and guide **modest** intel tweaks (not strategy overhauls):

### 7.1 Spread capture / rake (primary scoreboard)

- % of fills with **positive capture** (spread earned)
- Average **bps per fill**
- This is the main definition of “winning” for this bot.

**Good**: >70% positive capture, average >8–10 bps  
**Needs Attention**: <60% positive capture, average <5 bps

### 7.2 Portfolio / inventory health (secondary — steering, not P&L)

- Portfolio XRP-equiv drift from fills (capital retention while MM runs)
- Deviation vs ~55% XRP target — A-S + rebalance bias, not the rake itself
- RLUSD-heavy phases OK when **capture** (§7.1) is good

**Good**: Capture strong; deviation mostly within ±8–10%  
**Needs Attention**: Capture weak **or** unmanaged deviation swings (inventory stress)

### 7.3 Risk / Toxicity
- % of fills with negative capture
- Toxicity events or defensive actions

**Good**: Low negative capture rate, rare toxicity issues  
**Needs Attention**: Rising negative capture, frequent defensive actions

### 7.4 Structural Signal Effectiveness
- How often signals trigger
- Results when signals are applied (win rate / impact)

**Good**: Signals fire on clear setups with positive results  
**Needs Attention**: Signals fire too often/rarely or produce poor results

### 7.5 Consistency & Drawdown
- Max drawdown
- Day-to-day / week-to-week stability

**Good**: Controlled drawdowns, relatively smooth results  
**Needs Attention**: Large or frequent drawdowns, high volatility

### 7.6 Peer band relevance

- % of cycles with ≥1 peer in lane (posted touch band)
- `our_lane_xrp` vs median `peer_touch_xrp` in lane
- Top-10 activity list still shown but **not** used for pressure when peer lane populated

**Good**: Regular peer coverage; signals feel size-appropriate  
**Needs Attention**: Persistent empty lane after widen, or peers still whale-sized vs our touch

### 7.7 How to Use These Criteria
- Track over rolling periods (last 100 fills, last 7 days, last 30 days).
- Review regularly during live market making.
- Use results to guide tweaks (e.g., gating strictness, signal strength, performance scaler permissiveness).

## 8. Logging Requirements

All performance and intelligence-related data must be logged for future analysis and refinement.

### 8.1 What to Log
- Per-fill: capture result (positive/negative), bps, portfolio XRP-equiv after fill, XRP share %, deviation from target
- Per-cycle: `our_lane_xrp`, peer band bounds, peer count, peer account ids (truncated), active structural signals, gating decisions, advisory values (`size_mult`, bias)
- Periodic aggregates: rolling positive capture %, net XRP-equiv from fills, toxicity, max drawdown
- Peer band state: `peer_low_mult`, `peer_high_mult`, widen/neutral events
- Intelligence decisions: signal applied or rejected and why

### 8.2 Logging Format
- Structured logging (JSON Lines preferred) for easy parsing and analysis.
- Include timestamps, cycle/fill IDs, and relevant context for correlation.
- Maintain both detailed per-event logs and aggregated periodic summaries.

### 8.3 Purpose
- Enable post-analysis and performance reviews.
- Support data-driven tweaks to signals, gating, and parameters.
- Provide historical data for future improvements and when adding more advanced structural logic.

## 9. Phased Rollout

**E.1 — Posted-touch peer band** — `our_lane_xrp` from L1 intents; filter scrape by touch band; peer-only pressure/spread; HUD shows lane + peers vs top-10 context.  
**E.2 — Spread-quality scaler (brake-first)** — dimmer on capture/toxic deterioration only; no win-chase, no kill coupling.  
**E.3 — Async wiring, HUD** — Performance Metrics tab; JSONL intel log (`logs/intel_decisions.jsonl` or extend runtime export).  
**E.4 — Integration into quoting** — peer-lane pressure → `size_mult` / side bias in `PureQuotePath` (advisory only).  
**E.5 — Replay validation** — sacred corpus + WS samples: peer coverage %, neutral-fallback rate.  
**E.6 — Gradual live activation** — after engine parity + WS-path fills; grade with §7.

*Blocked until engine parity (checklist Phase E VPS / E4): E.4 live size effects, E.6 production activation. E.1–E.3 can run advisory-only in the lab.*

## 10. Open Questions & Next Steps

- Exact `peer_low_mult` / `peer_high_mult` and `min_peers` (replay tune on sacred book snapshots).
- Structural signal v1 set (peer-local only) after E.1 ships.
- Performance Metrics tab: HUD-only vs Streamlit vs both.

**Immediate next action (Cursor):** Implement **E.1** in `competitor_intel.py` — touch-size peer band + runtime fields `our_lane_xrp`, `peer_lane_count`, `peer_pressure_score`.

---

*Lives in `experimental/` on `xledger-ws-as`. VPS wholesale swap remains checklist Phase E (E1–E4); this doc is Phase G (intel) in `PURE_AS_CRITICAL_PATH.md`.*