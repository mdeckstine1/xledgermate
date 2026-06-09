# WS Book Feed Handoff for AI / Future Sessions (Data-Driven Development)

**WE ARE COMMITTED.**  
**WS + pure A-S (Avellaneda-Stoikov) is the future of xledgermate.**  
**No more alternate setups.**

The production architecture is:
- WebSocket book feed (WsBookFeed + BookState — live incremental data is the primary source)
- Replicated provable wiring from the long-run sacred operation (assess_inventory, build_quote_adjustments + full dynamic policy, toxicity, momentum, inventory, etc.)
- Pure A-S as the quoting engine: reservation price (gamma) for inventory risk + optimal spread (kappa + vol) for adverse selection. Built-in protections only.
- No hard `market_edge_met` gate. No legacy heuristic layers (edge thin, toxicity off-book, etc.) in the production path.

External/secondary sources (e.g. Anodos-style) are not part of the core near-term path. We will evaluate only if live pure A-S runs show clear, measurable gaps that secondary data fixes without adding complexity or risk.

When long-run / Gate 2 testing is complete, the code running on the remote server is replaced **wholesale** with the WS + pure A-S version. The long-run data remains the validation corpus because the decision provenance and logging shape are preserved.

**Date:** 2026-06-06 (approx, based on current long run)
**Branch:** grok-ws-feed (parallel to main Gate 2 work on grok-tier-2-collab)
**Purpose:** Mature the committed WS + pure A-S path using the *current main engine run data* (long Gate 2 tests with hard gate) as the sole testing ground and labeled data source. Do not touch main engine code on the collab branch.

**Key Principle:** The current setup (HTTP poll + hard gate) is sacred testing ground / data generator only. All development, replay, calibration, and validation of the future WS + pure A-S engine happens here in experimental/ws_feed/. Main long-run work stays untouched.

## Current Main Run Data (as of latest update: 150 fills post clear-kill)
- **Run context:** New long run after clean restart (clear-kill + cancel-offers + systemctl start). Kill switch clear ("Operator cleared via CLI").
- **Fills:** ~150 (user report; accumulating under tight_spread, market_make, with hard gate active).
- **Hard gate in action (from decisions.jsonl patterns in available logs):**
  - Many cycles with "market_edge_met=false — insufficient edge vs book/fees (hard gate; no live quotes)".
  - "Book L1 spread ~0.15-0.19% (bid/ask close)", "our L1 too tight (e.g. 0.059% < need 0.088%)", "thin book", "edge guard: widened spread...", "Generated 0 quotes (two-sided)".
  - Policy often "off-book (toxic ~26%) | max 6.42% from touch".
  - Low open_offers_count (e.g. 1 in snapshots).
  - Last execution often "Live: no offers placed this cycle."
- **Other metrics (from runtime snapshot in logs, proxy for run behavior):**
  - cycle_count ~138+ (in snapshot; full run higher with 150 fills).
  - session_pnl_balance_xrp: slightly negative (e.g. -0.25 in proxy snapshot; monitor vs -0.85/45 guard).
  - session_pnl_mtm_xrp: slightly positive in some views.
  - book_spread_pct: ~0.05 (in one snapshot; varies 0.15+ in decisions).
  - market_edge_met: False in many cases.
  - active_profile: tight_spread.
- **Trades / Capture (proxy from recent trades in log):**
  - Recent fills show positive capture on both sides (e.g. BUY ~0.32-0.39 XRP, SELL ~0.22-0.35 XRP in proxies).
  - Consistent with prior long run (~12 bps, low negative %).
- **Presence / 0 quotes:** High number of 0-offer cycles (e.g. 45-59 in recent 100-200 cycle proxies; 985 in full log history). This is the key signal the WS feed aims to improve.
- **Overall:** The hard gate + BookOffers fixes are making the run "safer" and more defensive (blocks bad quotes on thin edge). This provides *clean, real test cases* for WS: cycles where poll data led to edge_met=false / 0 quotes / off-book. A fresher WS book (lower latency, incremental updates, better snapshots) could flip more of these to positive edge_met or better presence without increasing toxic risk.

**How this run drives WS development (testing ground):**
- Use decisions.jsonl + runtime_state snapshots from this run (and prior long runs) in replay tools to backtest WS improvements.
- Example: In the 985+ "0 quotes due to edge thin / hard gate" cases, simulate WS-updated book state (using high-res data from 30-min probes). Measure % of cases where edge_met would flip true, potential presence gain, impact on fills/capture.
- The 30-min WS probe (just completed) provides high-frequency "ground truth" deltas/mids from similar market conditions to make simulations realistic.
- Current WS code changes (separate bid/ask subscribes for reliable snapshots, prefer WS snapshots for seed/reconciliation instead of always HTTP) can be validated against this data.
- Goal: Improve WS to deliver better "presence when edge should be there" (Tier C metric) on exactly the thin-book / marginal-edge conditions this run is exposing.

## WS Current Status (on grok-ws-feed)
- **Sandbox only:** experimental/ws_feed/. Not wired to engine. Default on VPS/main remains HTTP poll until post-Gate 2 sign-off.
- **Recent probes (including 30-min just run):**
  - High frame rate (~3/s), high apply rate (95%+ in summaries), low book age (often <5s, sometimes 0.1-1s), small drift vs HTTP (<5-7 bps typically, with periodic refresh).
  - 30-min probe (post hard gate deploy on main): Consistent performance, good volume of OfferCreate/Cancel, response:success counts showing subscribes working.
  - Prior short probes validated after parser fixes (tx_json/tx).
- **Recent code changes (data-driven from main run gaps):**
  - Separate Subscribe per side (ask + bid) for distinct initial snapshot responses.
  - Added seed_from_ws_snapshot() + switched initial seed and periodic refresh to prefer native WS snapshots (addresses "rely on HTTP seed", improves reconciliation).
  - These directly target gaps exposed by long runs: better snapshots + fresher state should help edge detection in thin book cases like the current 150-fill run.
- **Replay harness (new, to drive with current run data):**
  - experimental/ws_feed/replay_long_run.py : Loads historical book snapshots + original decisions ("Book L1 spread", edge_met, "Generated 0 quotes", reasons) from long run logs.
  - Replays through WS BookState + same edge/policy logic.
  - Simulates WS freshness (using probe stats) and measures "what % of 0-edge cases from the actual run would flip with WS book?"
  - This is the primary tool for using the current testing ground data to iterate on WS (e.g. test snapshot changes, measure presence/edge improvement on real 150-fill + prior run conditions).
- **Gaps / Next (from PROBE_RESULTS.md, prioritized by main run data):**
  1. Subscribe snapshots (in progress with separate subscribes + WS seed).
  2. Book reconciliation / drift cap (in progress with WS snapshots; use replay + 30-min data to tune).
  3. Incremental depth + trust checks (reuse is_trustworthy_rlusd_mid from main code).
  4. Engine adapter (BookFeed protocol + flag in trading_engine; default poll).
  - Use replay on current run data to validate each step (e.g. does snapshot fix reduce simulated "edge false" in the 985 0-quote cases?).

## How to Use Current Run Data for WS Dev (on this branch)
- **Primary logs (from main run, post hard gate changes):** logs/decisions.jsonl (per-cycle "Book L1 spread", hard gate messages, 0 quotes, edge calcs), logs/runtime_state.json (snapshots with spreads, edge_met, offers, policy), logs/trades_2026-06.csv (fills/capture on the 150), logs/portfolio_snapshots.csv (PnL/balance drift).
- **Workflow:**
  1. Run main engine long run (current setup = testing ground).
  2. After clear or at milestones, copy relevant decisions/runtime excerpts or use full logs.
  3. Run `python -m experimental.ws_feed.replay_long_run --decisions logs/decisions.jsonl` (or point to full long run log) to quantify WS value on *this exact data*.
  4. Run fresh WS probes (30+ min) during quiet periods on main run for high-res data.
  5. Improve WS code (snapshots, recon, etc.).
  6. Re-run replay/probes — measure improvement against the run's 0-edge / low-presence cases.
- The 150-fill run (and prior) provides real "edge thin on thin book" test cases where hard gate correctly blocked — WS should aim to provide *better* edge detection/presence here without increasing risk.
- Do **not** change main config/profile mid-run. Use data offline for WS.

## Milestones / Next Expected (WS specific, driven by main run)
- [x] 30+ min probe completed (high-res data from current run conditions).
- [x] Snapshot + reconciliation improvements started (separate subscribes, WS seed; tested in short probe post-change).
- [ ] Replay harness run on full 150-fill + prior long run data; produce "WS would flip X% of 0-edge cases" baseline.
- [ ] Integrate 30-min probe deltas into replay for accurate simulation.
- [ ] Update/improve snapshot parsing (test with replay on current run data).
- [ ] Add drift guard / reconciliation cap; validate with replay (target <5 bps in simulated thin book cases from run).
- [ ] Start BookFeed adapter interface in experimental (for future engine wiring, default poll).
- [ ] Longer soaks / more runs on main to accumulate data for WS regression.
- After Gate 2 judgment on main: Merge improvements, operator opt-in for WS on VPS.

## Rules for This Branch / AI Sessions
- All WS changes, tests, replays, probes here only.
- Current main run data (this 150-fill run + history) is sacred testing ground — use it to measure everything.
- No deployment to VPS/engine until explicit post-Gate 2 sign-off.

## Real-time HUD / New Operator Surface (experimental/ws_feed/hud/)
**Purpose:** Provide a lightweight, high-frequency "new GUI" surface for watching the committed WS + pure A-S path live (book state, A-S reservation/optimal spread, would-quote decision, suggested levels, rich policy notes, recent decisions). This is additive to the main Streamlit (which can still load `logs/ws_as_demo_runtime.json` for the full analytical view + legacy strings).

**Key recent work (Cursor-friendly iteration):**
- Fully extracted from giant inline string in `real_time_as_hud.py` → standalone `hud/index.html` (single source of truth for the UI; easy for Cursor / web tooling).
- Python side is now a minimal FastAPI loader (`_HUD_DIR / "index.html"`, reads at startup, serves with CSP header).
- **Live tester integration** (`live_pure_as_tester.py --serve-hud`): feeds the same state dict (balances, inventory, as_*, ws_*, would_quote, quote_intents, recent_decisions, etc.) every cycle. Starts HUD on 8765 in background thread.
- **Sidebar**: Compact always-visible view (Balances XRP/RLUSD from bot wallet, Inventory label, Profile selector, Status, Engine Controls demo buttons). Added real project logo (`Xledermate.jpg` base64-embedded for self-contained serving) above Balances; sized up for prominence.
- **Nav tabs**:
  - Live: Book + Pure A-S Decision (reservation with bid/ask margins, optimal spread, γ/κ, would_quote status, suggested levels). Cleaned out legacy "BASE HARD GATE" simulation noise.
  - Config: Focused on operational + wallet-tied data — Bot Wallet (address + live XRP/RLUSD balances from tester state), L1–L3 inventory commitments, Inventory Target + current label, basic quoting params (profile selector + explanatory text moved here from old sidebar).
  - Inventory (new): Primary funding surface. Bot address (copy + real QR via /qr endpoint), live balances, "Bring in XRP from wallet" (QR + copy + simulate deposit buttons that update HUD balances for testing), "Send from the bot" form (demo withdraw to external r-address, mutates displayed bals + tx log). All demo-only for UI/inventory skew experimentation in the HUD. Real moves use XRPL Payment txs from the engine.
  - Credentials: Dedicated tab for secrets (XRPL address/seed, Telegram token/chat, other keys). Removed credential duplicates that were previously cluttering the old Config tab.
- **Sidebar cleanup**: Removed redundant "Credentials (demo)" section (address + secret inputs + note) — now lives only in the Credentials nav tab.
- **Collapsible sections**: "Last Decision Note" and "Recent Decisions" are now minimizable (click header, chevron rotates, state persisted in localStorage). Helps keep the Live view from being overwhelmed by verbose output while still having the rich policy strings available.
- **Other ergonomics**: Explicit CSP (script-src with unsafe-eval for inline + demo needs; connect-src), defensive JS (if(el) guards), live poll status, force-poll button, showPage state push on tab switch, etc.
- **Important for Cursor / future edits**: After any change to `hud/index.html` you **must** restart the tester process (the HTML/JS is read once at server start). Use hard refresh (Ctrl+Shift+R) in browser. The tester can be run with `--profile`, `--gamma`, `--kappa`, `--xrp-bal`, `--rlusd-bal` etc. to simulate different wallet/inventory conditions.

**Status**: The HUD is now a practical, low-friction surface for real-time observation of pure A-S decisions on live WS book data. It complements the sacred long-run / Gate 2 data generator (HTTP poll + hard gate remains untouched on the main branch for validation). Further HUD work (more live engine controls, deeper L1-L3 ladder from actual risk policy, better error states, etc.) can now be done efficiently in the external HTML file.

**How to run**:
```powershell
cd xledgermate
.\.venv\Scripts\Activate.ps1
python -m experimental.ws_feed.live_pure_as_tester --serve-hud --seconds 600 --verbose --profile tight_spread
```
Open http://127.0.0.1:8765 (hard refresh after edits). F12 console for poll/debug.

This surface is part of the "new GUI" story for the committed WS + pure A-S future. When we eventually wholesale-replace the remote server code, a polished version of this (or evolved from it) can become the primary operator view.
- Update this handoff + PROBE_RESULTS.md when new data from main run or WS improvements land.
- When switching back to main work: checkout grok-tier-2-collab (stash/pop handoff edits as needed). WS branch stays for ongoing dev.

**Current focus (committed direction only):** 
Mature the WS + pure A-S production path (this is what will replace the remote server code wholesale):
1. WS feed quality: snapshots, per-side subs, reconciliation, drift guards, trust checks. (No secondary/Anodos dependency in the core path for now.)
2. A-S realism + calibration: fix quote level math so "would quote" prices are competitive and realistic around the live book; derive good gamma/kappa from the sacred long-run fill/toxicity/inventory data (see grokster calibration output and replay).
3. Hardening for swap: keep the replicated long-run wiring (assess_inventory + build_quote_adjustments etc.) + pure A-S as the decision core. Make live tester / replay production-grade enough to become the engine path.
4. Measurement: default everything to pure; use replay + live tester + grokster on the full corpus to prove better Tier C presence while preserving the 7.5% neg / capture economics the long run validated.
5. Competitor intelligence + advisory Grok/xAI (new): on-chain scraper for active makers (observed spreads, pressure, profiles + domain); Config tab drives real Grok tokens (provider=grok, xai-... key, grok-beta); `/analyze_competitor` endpoint + Intelligence tab "Analyze with AI" button for competitor ledger address trending/strategy (advisory only — never mutates A-S reservation math). Llama3 stub deprecated for intel path. More token details later. The layer improves A-S *inputs* (pressure as vol/liquidity proxy) so we can skim harder when competitors are defensive.

See new `docs/WS_AS_MANUAL.md` (how to run tester + HUD, Intelligence tab, Grok config) and the updated `docs/STRATEGY_MANUAL.md` + `docs/IMPLEMENTATION_PLAN.md` (Tier 3 section + progress log).
Keep it simple and focused. Pure WS book + A-S built-in math + proven context wiring = the future.

The long-run hard-gate engine stays as the sacred data generator only.

### GUI Compatibility & Demo Plan (Base vs WS + pure A-S)
**Base long-run GUI** (streamlit_gui + ticker + formatters) depends on:
- runtime with market_edge_met (OK/THIN), quote_decision_summary (the rich wiring string), quoting_policy_label, inventory_label, recent_decisions events, quote_intents (ladder), toxic_*, cancel_per_fill, pauses, book L1/mid, PnL, profile, health_score, etc.
- Ticker shows policy, edge thin warnings, decision segments.
- "Recent activity" + "Why these quotes?" expander with sub-metrics.
- These displays have proven value for operator understanding of blocks/safety during the long run.

**WS + pure A-S current outputs** (live tester, replay, grokster):
- Reuse the exact same build_quote_adjustments → decision_summary (inventory skew, momentum, dynamic policy, "operating mode", edge notes) — **keep this richness for continuity**.
- Append "PURE A-S: reservation=... spread=... (gamma=..., kappa=...)" .
- In pure: "market_edge_met" is set from A-S (reservation inside book) for compatibility.
- Live WS adds: ws_book_age_s, ws_message_count (freshness proof).
- No hard-gate strings; presence is higher (A-S math decides).

**What to KEEP (no breakage on swap):**
- All decision_summary construction and recent_decisions events (base GUI will render them).
- Inventory, policy, toxic proxies, pause flags, quote ladder (synthesize simple intents from A-S bid/ask/size in pure).
- "Why these quotes?" layout + most sub-metrics.
- Ticker logic for policy/decision segments.

**What to ADD for demo / new value:**
- A-S specific runtime fields (already added to RuntimeState): as_mode, as_reservation, as_optimal_spread_pct, as_gamma, as_kappa, ws_book_age_s, as_protected, as_presence_pct.
- In "Why these quotes?": new row/columns for "A-S Reservation vs book", "A-S Optimal Spread", "Protected by math (not hard gate)".
- Ticker: "PURE A-S active", show reservation as key number, "WS age: Xs (fresher than base poll)".
- New demo views: 
  - "Presence lift" metric or chart (vs historical base gate blocks on same book data via replay).
  - Side-by-side: "Base gate decision" vs "A-S pure decision" on identical book snapshot.
  - WS freshness badge (age + msgs) next to book L1.
  - When A-S goes to 0 on thin book: explain via reservation (e.g. "inventory risk pushed reservation outside book").
- In live tester: now builds full gui_runtime dict on every sample (standard fields + A-S). Verbose mode prints compact snapshot. At end you have in-memory data you can json.dump and load into the Streamlit GUI for a live "what the future GUI would show" demo.
- Update clean_decisions_table / _segments_from_summary to nicely highlight "PURE A-S" segments (color or badge).

**Demo script for swap readiness:**
- Run live tester (or replay on sacred data) with verbose.
- Take the final/last gui_runtime, save as "ws_as_demo_runtime.json".
- Load it in streamlit_gui (or a small shim) — most panels will light up with familiar strings + new A-S numbers.
- Show operator: "Same rich policy/inventory language you trust from the long run, plus explicit A-S math and WS freshness. Higher quote rate on the exact thin books where base gate blocked."

This keeps the proven monitoring while surfacing the competitive advantage (presence without sacrificing the safety the long run proved). No big GUI refactor needed for initial swap; the data contract is mostly compatible by design (we kept the wiring). 

Update this section after any GUI shim or formatters changes.

The long-run hard-gate engine on the other branch + VPS continues solely as the generator of high-quality labeled data (0-quote cycles, fills with capture, toxicity, inventory states). We do not port changes back to it.

Update this handoff, PROBE_RESULTS.md, and logs/review_pure_as_ws.md after every meaningful increment on the WS + pure A-S path.

Contact / context: See groks input/FOR_AI_AND_FUTURE_SESSIONS.md. The sacred long-run data is the only thing that will let us prove (before the server swap) that WS + pure A-S delivers better competitive presence while keeping the safety the long run already validated.

Contact / context: See main FOR_AI_AND_FUTURE_SESSIONS.md for overall project. The long run with hard gate is generating the exact data we need to make WS better than poll for presence on marginal books.

---

**GUI Evaluation (Base long-run vs WS + pure A-S) + Demo Plan**

**Base GUI strengths (keep these displays and data shapes):**
- Recent decisions table (events with "Generated X quotes", policy notes, inventory/momentum strings).
- "Why these quotes?" expander + sub-metrics (Market edge OK/THIN, Fill quality, Toxic ratio, Cancel/fill, Pauses, decision_summary).
- Ticker (quoting_policy_label, edge thin warnings, decision segments).
- Quote ladder from intents.
- Overall: balances, PnL, book L1/mid/spread, profile, health, inventory_label.
These are battle-tested from the long run and give operators confidence in safety/rationale.

**WS + pure A-S current state (what the live tester/replay now produce):**
- Re-uses 100% of the wiring → identical rich decision_summary strings (continuity — the GUI will render them unchanged).
- Appends "PURE A-S: reservation=... (gamma=..., kappa=...)" for the math visibility.
- Sets market_edge_met from A-S met (reservation inside book) for compatibility.
- Adds WS freshness (age, message count) and A-S specifics.
- Synthesizes quote_intents from A-S bid/ask/size for the ladder.
- No "hard gate" strings; higher "Generated 2" rate on the same thin books.

**Gaps identified & addressed in this session:**
- No explicit A-S numbers in runtime → added as_* fields to RuntimeState + populated in tester.
- No easy way to load WS A-S output into existing GUI for demo → live tester now builds full gui_runtime dict on every sample + saves logs/ws_as_demo_runtime.json at end (standard fields + A-S + WS age + recent_decisions in base format + quote_intents).
- Quote levels were unrealistic → fixed in AvellanedaStrategy (now near-touch, anchored to live bests, reservation provides skew).

**What to DEMO (when showing the swap or to stakeholders):**
- Load a base runtime snapshot (from long run) side-by-side with a ws_as_demo_runtime.json in the Streamlit.
- Show: "Same decision table and 'Why these quotes?' you know from the long run (kept the wiring)".
- Highlight new: "PURE A-S" policy label, reservation value next to book, "WS age 1.2s vs base poll", "A-S quoted 2 (reservation inside book) where base gate blocked".
- Presence lift: "On the exact thin-book cycles from the sacred run, base had ~11% quotes; pure A-S + WS has 90%+ while A-S math kept the protection (no increase in modeled toxicity)".
- Safety continuity: the full inventory/momentum/policy strings are still there; A-S just replaced the binary gate.
- Freshness win: explicit WS age + high message count next to book L1.

**Keep / Add / Ditch summary for the GUI layer on swap:**
- **Keep**: decision_summary construction, recent_decisions events, inventory/policy/toxic/pause metrics, quote ladder, ticker logic, "Why these quotes?" layout, all PnL/book/profile displays. (Zero breakage for operators.)
- **Add** (minimal): A-S fields to runtime (done), A-S section or columns in the expander (reservation, optimal spread, "protected by math"), WS age badge, pure-mode indicator in policy/ticker, optional "A-S presence this session" metric, ability to load demo runtime json.
- **Ditch** (in pure mode): reliance on hard "market_edge_met=false — hard gate" messages for blocking rationale (replaced by A-S reservation explanation); any assumption that edge_met is always the old heuristic.

The live tester is now the best "GUI demo harness" for the committed path. Run it, grab the json, drop into the base GUI — you will immediately see the continuity + the new competitive advantage.

**Status update — "same provable wiring" for WS promotion (user request verbatim):**
"i just want the ws version to have the same provable wiring we have in long run, but with the ws archetecture. whe we make the switch we should have to replace what is running on the remote server with the ws version."

- Implemented in experimental/ws_feed/replay_long_run.py (the executable prototype / test harness for the future main WS engine).
- The replay now does the full call chain from the long-run sacred code:
  - profile = get_profile("tight_spread")
  - inv = assess_inventory(...)  [exact function + skew parsed from reasons the long run emits]
  - adj = build_quote_adjustments(profile, assessment, inventory, momentum, book_spread from WS state, min_edge, toxicity proxy, ...)
    (this pulls in the entire dynamic policy, momentum guard, book pressure, fill-quality, self-bailout, assess_market_edge, resolve_dynamic_quoting_policy etc.)
  - Then for pure: A-S compute_avellaneda_quote supplies the presence decision + levels (built-in reservation + spread protections); the adj.decision_summary (with all the "good" inventory / momentum / policy strings) is still emitted for log parity.
- Output per-cycle now contains strings of the form the long run produces: "Generated 2 quotes (two-sided) from mid=... | inventory=slight_xrp_heavy | tight_spread: favorable → ...; inventory ... → steer quotes; operating mode: market make; momentum ... → pause bids ...; dynamic policy (...); book too tight ... | PURE A-S (built-in protection): reservation=... gamma=... "
- This means the WS version carries the battle-tested decision provenance. When the long run finishes Gate 2, the VPS/remote server code is simply replaced wholesale with the WS package (BookFeed/WS + this wiring + pure A-S as the core instead of hard gate + heuristic layers).
- Latest runs on the hard-gate training corpus (latest 4008 snapshots / 620 zero-due-to-edge from decisions.jsonl + vps data):
  - grokster (recent 2000 window): 93.8% presence under pure A-S vs 10.7% baseline (+83.1pp lift), 0 high-tox risk.
  - replay_long_run --as-mode pure: 90.7% presence, 93.5% flip rate on the thin/0-edge cases.
- These numbers use the *exact* replicated long-run wiring + pure A-S (reservation inside book) with WS-freshness simulation from real probes.
- grokster.py and replay_long_run.py are the calibration + proof harnesses.
- Sacred long-run main (hard gate, tight_spread, vps) untouched and continues generating data.

Next increments (pure A-S + WS only, experimental/ only — do not touch sacred long-run branch):
- Production hardening of WsBookFeed (reconnect, is_fresh / trust_score guards, long-running run_forever mode) — started.
- Deeper gamma/kappa calibration from full current sacred data + live pure A-S runs (grokster already prints rough suggestions).
- Realistic near-touch quote levels in AvellanedaStrategy when book is very tight.
- Full "swap readiness" report output from replay (added to replay_long_run.py).
- Engine adapter prototype (new engine_adapter_example.py shows the clean surface the main engine will eventually use).
- 30+ min production-style probes exercising the hardened WsBookFeed.
- Update main docs (IMPLEMENTATION_PLAN.md Tier 3 section + OPERATOR_MANUAL) with current evidence (93%+ presence, 0 modeled tox increase, full wiring parity).
- Optional: small HUD enhancements for swap monitoring (presence lift badge, etc.).

The pure A-S + WS path (replicated wiring + A-S math + WS book) is the only thing that will replace the remote server. Hybrid and old logic are validation-only.