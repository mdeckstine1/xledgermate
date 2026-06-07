# WS Book Feed Handoff for AI / Future Sessions (Data-Driven Development)

**Date:** 2026-06-06 (approx, based on current long run)
**Branch:** grok-ws-feed (parallel to main Gate 2 work on grok-tier-2-collab)
**Purpose:** Develop and integrate WebSocket order book feed (Tier 3) as improvement over HTTP poll. Use the *current main engine run data* (long Gate 2 tests with hard gate deployed) as the primary testing ground and driver for WS improvements. Do not touch main engine code on the collab branch.

**Key Principle:** The current setup (HTTP poll + hard `market_edge_met` gate on main branch) is our live testing ground. All WS development, testing, replay, and validation happens here in experimental/ws_feed/ on this branch. Main work (hard gate, Gate 2 data collection, 150+ fills runs) stays safe and untouched.

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
- Update this handoff + PROBE_RESULTS.md when new data from main run or WS improvements land.
- When switching back to main work: checkout grok-tier-2-collab (stash/pop handoff edits as needed). WS branch stays for ongoing dev.

**Next for this session (per latest direction):** 
- Continue WS book feed completion on this branch (BookFeed ABC now in place; HttpPoll + WsBookFeed implement it; basic drift/recon guard + trust check hooks added. Use the 150-fill run's hard-gate "0 quotes on thin book" cycles as validation via replay).
- Start 3rd-party market analysis module (new experimental/market_analysis/external_data.py with pluggable ExternalMarketDataProvider + stub). Concrete example: AnodosFinanceProvider for secondary book snapshots / mids / liquidity (exactly the "services like Anodos providing secondary data" for when direct WS/HTTP is thin or snapshot-weak, as seen in the current 150-fill run's hundreds of hard-gate "thin book / L1 too tight / 0 offers" cycles). Hooked into WsBookFeed via seed_from_secondary for snapshots and reconciliation. Use replay + current run data + 30-min probe to test if Anodos secondary mid would have prevented some hard-gate blocks or improved presence.
- **AI analysis placeholder added (experimental/ai_analysis/)**: AIAnalyzer ABC + StubAIAnalyzer + LocalLLMAnalyzer / APIAIAnalyzer placeholders (with copy-paste-ready tiny prompts for Ollama etc.). replay_ai_orchestrator.py runs directly against the current testing-ground decisions (984 zero-gen-quote cycles in the local snapshot of the long run) and quantifies "with WS-fresh book (age ~1.2s) + Anodos secondary confirmation on ~40% of cases, the AI micro-signal would have marked X% as skimmable or suggested min_edge relax for better rake."
  - Living discussion document: `experimental/ai_analysis/THE_AI_DISCUSSION.md` (started per user request). Covers the data-as-training-corpus view, Grok API vs local tradeoffs for "quicker" progress on good rake + competitive dominance, first numbers, the training export, and open questions. This is the place to keep the conversation and results.
  - First run (stub heuristic stand-in for fast local): 984 cases, 859 (87.3%) ai_marked_truly_skimmable, 100% got suggested relax, 859 recommended non-off posture. (Stub is optimistic on secondary; real local model will be tuned on the same labeled corpus.)
  - Explicitly **not about trending**. Pure micro-structure: "given this thin on-chain L1 + WS freshness + secondary liquidity, is there real edge for spread capture (good rake) right now?" Goal = competitive dominance via higher safe presence (Tier C) on marginal books without increasing adverse selection.
  - Speed: Local (small model, Ollama/llama.cpp) for sub-100ms in-loop or replay triage. API for offline batch explanation of the full 150-fill hard-gate corpus or training-label generation. Hybrid is the practical path.
  - The orchestrator is the driver: `python -m experimental.ai_analysis.replay_ai_orchestrator --analyzer stub|local|api-stub`. Swapping the implementation inside LocalLLMAnalyzer is the only change needed to go from heuristic to real model.
- Keep everything sandboxed here. Main engine run (current long run with 150 fills, hard gate protecting) remains the live testing ground and data source (decisions.jsonl, runtime snapshots with edge_met=false + book spreads, trades with capture). Do not merge or deploy WS/3rd-party/AI to main branch until post-Gate 2.
- Document expansion path for competitive MM (see TODOs in external_data.py, ai_analysis/base.py + replay_ai_orchestrator.py): train small distilled model on long-run "false edge thin" vs "good capture" labels + WS features + Anodos liq; async advisory signal into future engine loop; A-S inputs, multi-venue, dynamic regime skimming. Build minimal now; design for growth and dominance via better presence + rake.
- Run/enhance replay (and the new AI orchestrator) against the current run's data + 30-min WS probe + Anodos-injected mids to quantify: "in the 0-edge / low-presence periods of this 150-fill run, would WS fresher book + Anodos secondary + fast local AI micro-signal have allowed more safe quotes / better rake?"

Update this handoff + PROBE_RESULTS.md after each increment. The current main run is generating the exact "thin book, edge thin, hard gate blocks, but some fills still happen with capture" cases that will let us make WS + 3rd-party + AI meaningfully better than pure poll for skimming/presence and competitive dominance.

Contact / context: See main FOR_AI_AND_FUTURE_SESSIONS.md for overall project. The long run with hard gate is generating the exact data we need to make WS better than poll for presence on marginal books.