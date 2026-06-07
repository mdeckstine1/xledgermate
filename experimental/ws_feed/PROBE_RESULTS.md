# WebSocket book probe — captured results (2026-06-05)

**Branch:** `grok-ws-feed` · **Node:** `wss://s1.ripple.com:51233` / `https://s1.ripple.com:51234` · **Pair:** XRP/RLUSD mainnet  
**Status:** Sandbox validated locally — **not** deployed to VPS. Gate 2 stays HTTP poll.

Handoff summary: [groks input/FOR_AI_AND_FUTURE_SESSIONS.md](../../groks%20input/FOR_AI_AND_FUTURE_SESSIONS.md) §3b.

---

## Commits (reference)

| Commit | What |
|--------|------|
| `5934a9d` | Initial `experimental/ws_feed/` sandbox |
| `74e89fd` | RLUSD hex + `SubscribeBook.taker` |
| `0f918ad` | `--verbose`, parse `tx_json`/`tx` (not `transaction` only) |

---

## Run A — 10 min verbose (parser broken)

**Command:** `run_probe --seconds 600 --verbose`  
**Log:** `logs/ws_probe_10min_verbose.log`

| Metric | Result |
|--------|--------|
| Duration | ~603 s |
| WS frames | 2,003 (~3.3/s) |
| `book_apply` | **0** |
| Frame labels | `transaction:?` × 2002 (body in `tx`/`tx_json`, not read) |
| Final WS mid | 1.100789 (+3.6 bps vs HTTP) |
| WS book age | **13.3 s stale** (HTTP refresh only) |

**Lesson:** High frame volume ≠ useful book; wrong tx key made WS a no-op.

---

## Run B — 3 min verbose (parser fixed) ✅

**Command:** `run_probe --seconds 180 --verbose --summary-interval 30`  
**Date:** 2026-06-05 ~14:02–14:05 UTC (local)

| Metric | Result |
|--------|--------|
| Duration | ~183 s |
| WS frames | 543 (~3.0/s) |
| `book_apply` | **519** |
| Offers extracted | **868** |
| Tx mix | OfferCreate 456, OfferCancel 63, Payment 23, subscribe ack 1 |
| Final WS mid | 1.089863 |
| Final HTTP mid | 1.089420 |
| Drift | **+4.1 bps** |
| WS book age | **2.7 s** |

**Early behavior:** Mid moved on WS within seconds of subscribe (e.g. 1.096072 → 1.094183 on OfferCreate burst) without waiting for HTTP poll.

---

## Run C — 3 min summaries only (parser fixed) ✅

**Command:** `run_probe --seconds 180 --summary-interval 30` (no `--verbose`)

| Time | Frames | book_apply | WS mid | HTTP mid | Drift |
|------|--------|------------|--------|----------|-------|
| 33s | 91 | 87 | 1.087500 | 1.087740 | −2.2 bps |
| 63s | 175 | 168 | 1.086305 | 1.086560 | −2.3 bps |
| 94s | 286 | 273 | 1.086488 | 1.085810 | +6.2 bps |
| 124s | 451 | 437 | 1.088260 | 1.089775 | −13.9 bps |
| 155s | 548 | 532 | 1.091336 | 1.091185 | +1.4 bps |
| **Final** | **660** | **631** | **1.092051** | **1.092147** | **−0.9 bps** |

| Metric | Result |
|--------|--------|
| Tx mix (final) | OfferCreate 575, OfferCancel 56, Payment 28 |
| WS book age (final) | **0.4 s** |
| HTTP polls | 12 (~15 s interval) |

**Lesson:** Incremental offer patches can drift ±10 bps mid-run; end-state aligns within ~1 bps. HTTP seed every 45s still useful as reconciliation.

---

## 6. AI analysis placeholder (initial stage, speed for good rake + competitive dominance) — added

At the exact point you asked ("since we are at the initial stage of ws development, how hard would it be to add a placeholder for ai analysis? we need speed... ultimatly mm is not about trending, but about making good rake, competitive dominance is my goal"), we added the full lightweight placeholder on grok-ws-feed in experimental/ai_analysis/.

**How hard:** Very easy / low cost. The replay_long_run harness + the 984+ labeled "Generated 0 quotes + Book L1 spread X% (often thin 0.02-0.09%)" cycles from the current long-run testing ground (the same data that produced the 150 fills under hard gate) already existed. We only needed:
- AIAnalyzer ABC + AIAnalysis dataclass (base.py)
- Stub + LocalLLM + API placeholders (stub_llm.py) with ready prompts for real Ollama ("phi3:mini" etc.) or remote calls
- replay_ai_orchestrator.py (the driver that re-uses the corpus, injects simulated WS freshness + Anodos secondary, calls the analyzer at every 0-quote decision point, and emits flip stats)

No changes to main engine, hard gate, Gate 2 profile, or VPS.

**First run on your exact data (984 zero-gen-quote cycles):**
- Stub (fast local-style heuristic stand-in): 87.3% marked truly_skimmable, 100% suggested min_edge relax (-0.01), 87.3% non-off posture.
- API-stub (remote-style, more conservative): 13.8% skimmable, 51.4% relax, 13.8% non-off.
- Example (cycle 3, 0.068% L1): edge_q~0.32, skimmable=True, posture=spread_mid, "Secondary data supports skimming."
- Many sub-0.05% cases still get the relax signal when we "let" secondary confirm liquidity (the exact situation the 150-fill thin-book hard-gate cycles are hitting).

**Local vs API for your goal (speed + good rake + competitive dominance):**
- **Local (Ollama / llama.cpp small model)**: the right default for rapid analysis in the decision loop or replay. Tiny context (L1 spread, age, secondary liq, inventory skew, toxicity). Target <100 ms. This gives you the speed in decision making you asked for, so the bot can stay on book (better presence) on marginal but real rake opportunities that pure poll + hard gate would have skipped.
- **API (Grok, Claude, etc.)**: for offline/batch work on the full corpus ("explain every hard-gate cycle in the 150-fill run", generate high-quality labels for a future tiny distilled model that runs locally). Higher quality reasoning, but latency + cost make it unsuitable for the hot per-cycle path.
- Hybrid is ideal: local for fast triage, API for periodic deep analysis + label gen.

**Key constraints respected:**
- Not about trending or "the market is going up". Pure micro-structure: "right now, on this thin on-chain book, with WS freshness and secondary confirmation, is there real edge to skim for spread capture (good rake)?"
- The main hard gate ("market_edge_met=false — insufficient edge vs book/fees (hard gate; no live quotes)") and dynamic policy stay untouched and are the safety. AI is advisory only — it can suggest "relax 1-2 bp" or "quote near" for the cases where secondary says the thinness is likely a poll/WS snapshot artifact.
- Everything driven by the current main run as the sacred testing ground. Future VPS snapshots (after more fills under the same hard-gate regime) will be dropped into the same orchestrator to measure real improvement.

**Files:**
- experimental/ai_analysis/base.py, stub_llm.py, replay_ai_orchestrator.py, __init__.py
- Updated WS_HANDOFF.md (full rationale + "Next" section) and this file.

**Next immediate step (your choice):** Tell me "use local" or "use api" (or both). I'll wire a real small-model call (or API client) into LocalLLMAnalyzer, keep the same orchestrator interface, re-run on the 984 cases + any fresh data you give me from the live 150-fill run, and we iterate the conservatism until the % flips feel right for "more good rake without more toxic."

This is exactly the fast, data-driven, low-risk path that lets us turn the current long run's hard-gate / low-presence moments into a competitive advantage (better safe presence + rake) once WS book + Anodos secondary are solid post-Gate 2.

---

## Comparison: poll vs WS (Gate 2 context)

| | HTTP poll (production) | WS subscribe (sandbox) |
|--|------------------------|-------------------------|
| Typical interval | ~15 s book / ~45 s full refresh | ~3 frames/s on active RLUSD book |
| Latency (one-shot BookOffers) | ~1.0–1.3 s | ~0.6–0.9 s |
| Engine wired | Yes (VPS) | No |
| Book model | Full `BookOffers` depth | Per-tx offer deltas + partial state |

---

## Known gaps (next phase) — updated 2026-06-06 (WS book + 3rd-party market analysis direction; using current main run 150-fill data as driver)

1. **Subscribe snapshots** — ~~Initial `response:book_snapshot` rarely seen; rely on HTTP seed + deltas. Parse both subscribe responses (bid + ask books).~~ **In progress**: Separate per-side subscribes + WS snapshot seed now in ws_book_feed.py. Validated in post-change short probe (explicit "[WS] seeded full snapshot" logs + response:success counts).
2. **Book reconciliation** — ~~Periodic full HTTP refresh or snapshot merge; cap drift vs HTTP (target < 5 bps before quoting).~~ **In progress**: WS snapshots used for refresh; simple drift guard stub + max_drift_bps. 30-min probe data (just completed) + current main run (150 fills, many hard-gate 0-offer cycles on thin ~0.15% books) will be used to tune (via replay_long_run.py).
3. **Incremental depth + trust checks** — Current state is price-keyed patches, not full L2; competitive touch needs best bid/ask trust checks (reuse `is_trustworthy_rlusd_mid`). **Started**: BookFeed ABC created (book_feed.py); both feeds now implement it (common fetch/best/age/trustworthy/current_order_book). is_trustworthy hook added (reuses main connector logic). Future: use in edge calc so WS freshness + external signals flip trustworthy true more often on the marginal books the current long run is hitting.
4. **Engine adapter** — `book_feed_mode` flag in `trading_engine`; default `poll` on VPS until operator sign-off post–Gate 2. **Started**: BookFeed interface is the contract. Next: thin adapter + flag (keep experimental; do not touch main engine on collab branch yet). Current run data (hard gate correctly blocking on edge thin / thin book, low presence) is the perfect testbed for "does WS source improve edge_met / presence without more toxic?"
5. **Noise** — Payment txs on book stream ignored (`offers_applied=0`); OK.
6. **New (3rd-party market analysis for competitive growth)**: Start looking at external data (vol, liquidity, cross-venue signals) to augment on-chain book for better skimming on exactly the conditions the current 150-fill + prior runs expose (edge thin on thin books, 0-offer periods). See new experimental/market_analysis/external_data.py (pluggable ExternalMarketDataProvider + stub + expansion TODOs for full competitive MM: A-S inputs, ML, multi-venue, regime detection). Use replay + current run decisions (985+ 0-quote / hard-gate cycles) + 30-min WS probe as driver. Leave full integration/expansion for after Gate 2 + WS book solid.
7. **AI analysis placeholder (for speed in decision making / rapid analysis)**: At initial WS stage, add lightweight pluggable AIAnalyzer (experimental/ai_analysis/base.py + stubs for local LLM and API). Focus on *rapid micro-structure analysis* of WS book state + Anodos secondary + run context (inventory, toxicity, recent fills) to answer: "Is this thin book / edge thin / hard gate trigger real or data artifact? Suggested posture for better rake?" Not for trending — for edge quality, toxicity risk, optimal quoting posture to maximize spread capture (good rake) while protecting competitive dominance. 
   - Speed: Local AI (Ollama/llama.cpp small models like phi3/gemma2) for sub-100ms analysis in loop or replay. API (Grok/Claude/etc.) for heavier batch analysis of full 150-fill run's 200+ hard-gate cycles, or richer rationales.
   - Hybrid: Local for fast triage, API for offline. The placeholder augments (does not replace) the fast rules engine (hard gate + dynamic policy stay deterministic).
   - Driven by current run data: Feed the exact "Book L1 spread 0.166%, edge false, hard gate, ask-heavy -54%" cycles. Ask AI: "Given Anodos secondary mid + liquidity, is on-chain thinness real? Suggest posture." Measure in replay: "Would AI analysis have flipped X% of 0-edge cases to positive presence without more toxic?"
   - See experimental/ai_analysis/stub_llm.py (copy-paste-ready prompts for local models) and integration notes in WS_HANDOFF.md.
   - Expansion: Train small model on long-run "false edge thin" labels + WS + Anodos features; async in future engine loop for competitive MM dominance via faster/better "is this real rake opportunity?" decisions.
7. **AI analysis placeholder (for speed in decision making / rapid analysis)**: At initial WS stage, add lightweight pluggable AIAnalyzer (experimental/ai_analysis/base.py + stubs for local LLM and API). Focus on *rapid micro-structure analysis* of WS book state + Anodos secondary + run context (inventory, toxicity, recent fills) to answer: "Is this thin book / edge thin / hard gate trigger real or data artifact? Suggested posture for better rake?" Not for trending — for edge quality, toxicity risk, optimal quoting posture to maximize spread capture (good rake) while protecting competitive dominance. 
   - Speed: Local AI (Ollama/llama.cpp small models like phi3/gemma2) for sub-100ms analysis in loop or replay. API (Grok/Claude/etc.) for heavier batch analysis of full 150-fill run's 200+ hard-gate cycles, or richer rationales.
   - Hybrid: Local for fast triage, API for offline. The placeholder augments (does not replace) the fast rules engine (hard gate + dynamic policy stay deterministic).
   - Driven by current run data: Feed the exact "Book L1 spread 0.166%, edge false, hard gate, ask-heavy -54%" cycles. Ask AI: "Given Anodos secondary mid + liquidity, is on-chain thinness real? Suggest posture." Measure in replay: "Would AI analysis have flipped X% of 0-edge cases to positive presence without more toxic?"
   - See experimental/ai_analysis/stub_llm.py (copy-paste-ready prompts for local models) and integration notes in WS_HANDOFF.md.
   - Expansion: Train small model on long-run "false edge thin" labels + WS + Anodos features; async in future engine loop for competitive MM dominance via faster/better "is this real rake opportunity?" decisions.
7. **AI analysis placeholder (for speed in decision making / rapid analysis)**: At initial WS stage, add lightweight pluggable AIAnalyzer (experimental/ai_analysis/base.py + stubs for local LLM and API). Focus on *rapid micro-structure analysis* of WS book state + Anodos secondary + run context (inventory, toxicity, recent fills) to answer: "Is this thin book / edge thin / hard gate trigger real or data artifact? Suggested posture for better rake?" Not for trending — for edge quality, toxicity risk, optimal quoting posture to maximize spread capture (good rake) while protecting competitive dominance. 
   - Speed: Local AI (Ollama/llama.cpp small models like phi3/gemma2) for sub-100ms analysis in loop or replay. API (Grok/Claude/etc.) for heavier batch analysis of full 150-fill run's 200+ hard-gate cycles, or richer rationales.
   - Hybrid: Local for fast triage, API for offline. The placeholder augments (does not replace) the fast rules engine (hard gate + dynamic policy stay deterministic).
   - Driven by current run data: Feed the exact "Book L1 spread 0.166%, edge false, hard gate, ask-heavy -54%" cycles. Ask AI: "Given Anodos secondary mid + liquidity, is on-chain thinness real? Suggest posture." Measure in replay: "Would AI analysis have flipped X% of 0-edge cases to positive presence without more toxic?"
   - See experimental/ai_analysis/stub_llm.py (copy-paste-ready prompts for local models) and integration notes in WS_HANDOFF.md.
   - Expansion: Train small model on long-run "false edge thin" labels + WS + Anodos features; async in future engine loop for competitive MM dominance via faster/better "is this real rake opportunity?" decisions.
7. **AI analysis placeholder (for speed in decision making / rapid analysis)**: At initial WS stage, add lightweight pluggable AIAnalyzer (experimental/ai_analysis/base.py + stubs for local LLM and API). Focus on *rapid micro-structure analysis* of WS book state + Anodos secondary + run context (inventory, toxicity, recent fills) to answer: "Is this thin book / edge thin / hard gate trigger real or data artifact? Suggested posture for better rake?" Not for trending — for edge quality, toxicity risk, optimal quoting posture to maximize spread capture (good rake) while protecting competitive dominance. 
   - Speed: Local AI (Ollama/llama.cpp small models like phi3/gemma2) for sub-100ms analysis in loop or replay. API (Grok/Claude/etc.) for heavier batch analysis of full 150-fill run's 200+ hard-gate cycles, or richer rationales.
   - Hybrid: Local for fast triage, API for offline. The placeholder augments (does not replace) the fast rules engine (hard gate + dynamic policy stay deterministic).
   - Driven by current run data: Feed the exact "Book L1 spread 0.166%, edge false, hard gate, ask-heavy -54%" cycles. Ask AI: "Given Anodos secondary mid + liquidity, is on-chain thinness real? Suggest posture." Measure in replay: "Would AI analysis have flipped X% of 0-edge cases to positive presence without more toxic?"
   - See experimental/ai_analysis/stub_llm.py (copy-paste-ready prompts for local models) and integration notes in WS_HANDOFF.md.
   - Expansion: Train small model on long-run "false edge thin" labels + WS + Anodos features; async in future engine loop for competitive MM dominance via faster/better "is this real rake opportunity?" decisions.
7. **AI analysis placeholder (for speed in decision making / rapid analysis)**: At initial WS stage, add lightweight pluggable AIAnalyzer (experimental/ai_analysis/base.py + stubs for local LLM and API). Focus on *rapid micro-structure analysis* of WS book state + Anodos secondary + run context (inventory, toxicity, recent fills) to answer: "Is this thin book / edge thin / hard gate trigger real or data artifact? Suggested posture for better rake / competitive presence?" Not for trending — for edge quality, toxicity risk, optimal quoting posture to maximize spread capture (good rake) while protecting dominance. 
   - Speed: Local AI (Ollama/llama.cpp small models like phi3/gemma2) for sub-100ms analysis in loop or replay. API (Grok/Claude/etc.) for heavier batch analysis of full 150-fill run's 200+ hard-gate cycles, or richer rationales.
   - Hybrid: Local for fast triage, API for offline. The placeholder augments (does not replace) the fast rules engine (hard gate + dynamic policy stay deterministic).
   - Driven by current run data: Feed the exact "Book L1 spread 0.166%, edge false, hard gate, ask-heavy -54%" cycles. Ask AI: "Given Anodos secondary mid + liquidity, is on-chain thinness real? Suggest posture." Measure in replay: "Would AI analysis have flipped X% of 0-edge cases to positive presence without more toxic?"
   - See experimental/ai_analysis/stub_llm.py (copy-paste-ready prompts for local models) and integration notes in WS_HANDOFF.md.
   - Expansion: Train small model on long-run "false edge thin" labels + WS + Anodos features; async in future engine loop for competitive MM dominance via faster/better "is this real rake opportunity?" decisions.

1. **Subscribe snapshots** — Initial `response:book_snapshot` rarely seen; rely on HTTP seed + deltas. Parse both subscribe responses (bid + ask books).
2. **Book reconciliation** — Periodic full HTTP refresh or snapshot merge; cap drift vs HTTP (target &lt; 5 bps before quoting).
3. **Incremental depth** — Current state is price-keyed patches, not full L2; competitive touch needs best bid/ask trust checks (reuse `is_trustworthy_rlusd_mid`).
4. **Engine adapter** — `book_feed_mode` flag in `trading_engine`; default `poll` on VPS until operator sign-off post–Gate 2.
5. **Noise** — Payment txs on book stream ignored (`offers_applied=0`); OK.

---

## Probe commands (repeat)

```powershell
cd C:\Users\micha\xledgermate
git checkout grok-ws-feed
.\.venv\Scripts\python.exe -m experimental.ws_feed.run_probe --seconds 180 --summary-interval 30
.\.venv\Scripts\python.exe -m experimental.ws_feed.run_probe --seconds 180 --verbose --summary-interval 30
```

---

## Tier 3 integration checklist (after Gate 2)

- [ ] Implement `BookFeed` protocol + `WsBookFeed` behind config flag
- [ ] Unit tests for `tx_json` / snapshot responses
- [ ] 30+ min probe: max drift, reconnect, stale-book guard
- [ ] Operator opt-in; merge `grok-ws-feed` → collab branch
- [ ] VPS deploy only with explicit Tier 3 schedule (not during Gate 2 pilot)