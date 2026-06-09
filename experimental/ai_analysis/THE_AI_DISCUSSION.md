# The AI Discussion — Micro-Structure Rake & Competitive Dominance

**Branch:** `grok-ws-feed` (parallel experimental work only)  
**Date started:** 2026-06-06 (initial placeholder + this doc)  
**Context:** All AI-related exploration lives here in `experimental/ai_analysis/`. The live long-running engine (hard `market_edge_met` gate + current tight_spread profile on VPS) is the **sacred testing ground**. We do not touch main engine code, the hard gate, Gate 2 config, or deploy anything until explicit post-Gate 2 sign-off. Development is driven 100% by real data from that run.

## Core Principle
Market making here is **not about trending**.  
It is about **making good rake** (consistent spread capture when edge is real) and achieving **competitive dominance** through better safe presence (more Tier C time on the book) on marginal/thin books — without increasing adverse selection or toxic fills.

The current hard gate ("market_edge_met=false — insufficient edge vs book/fees (hard gate; no live quotes)") + dynamic policy + inventory/momentum guards are doing exactly the right job for safety on thin L1 books (often 0.02–0.09% spreads with "Generated 0 quotes", "L1 too tight", "edge thin", etc.). The AI's job is **advisory micro-structure analysis only**: "Given WS-fresh book state + secondary (Anodos-style) confirmation + run context, is this thin book actually paying real edge for rake right now? Suggested posture or min_edge adjustment?"

## The Data Asset (Why This Is Trainable)
The long Gate 2 runs (150+ fills post clear-kill, plus prior history) are generating exactly the labeled corpus we need:

- `logs/decisions.jsonl`: Per-cycle events with "Book L1 spread X%", best bid/ask, full policy strings ("Generated 0 quotes (two-sided) ... inventory=rlusd_heavy ... momentum +0.0X% → pause bids (MM adverse-selection guard) ... edge thin (L1 0.0XX% < need 0.0XX%)"), hard-gate phrasing, mid, etc.
- `logs/trades_2026-06.csv` (and earlier): Actual fills with cycle linkage, "spread capture ~+0.00xx XRP", side, price, profit_xrp_equiv, notes ("Fill via balance delta").
- `logs/runtime_state.json` (snapshots): inventory, open offers, profile, etc.

**Key counts from current snapshot (one long-run log):**
- ~4000+ decision cycles exported.
- ~984 cycles with "Generated 0 quotes".
- ~656–789 hard-gate / edge-thin blocked cases (very thin L1 + explicit edge false signals).
- Real positive (and some small negative) capture outcomes tied to specific cycles.

This gives supervised signals:
- Strong negatives: hard gate fired + 0 quotes placed.
- Outcome labels: did a fill with positive spread capture occur on/near that cycle?
- Contrast: cycles on similar L1 spreads where quotes *were* generated and fills happened.
- Context features: inventory skew, toxicity proxies, momentum, profile min_edge, etc.

The 0-offer / hard-gate periods on thin books are the exact "ambiguous marginal opportunities" where a well-trained micro AI can learn when the current conservative rules are correctly blocking vs. when secondary + freshness would have supported a safer quote for extra rake and presence.

## Current AI Placeholder (Initial Stage)
We added a lightweight, pluggable foundation **without touching production**:

- `base.py`: `AIAnalysis` dataclass + `AIAnalyzer` ABC + `StubAIAnalyzer` (fast heuristic stand-in).
- `stub_llm.py`: `LocalLLMAnalyzer` (Ollama/llama.cpp-ready with copy-paste tiny prompt for small models like phi3/gemma2 + current heuristic) and `APIAIAnalyzer` (for heavier offline work).
- `replay_ai_orchestrator.py`: The driver. Replays the exact 0-quote cycles from decisions, injects simulated WS freshness (low age from probe data) + Anodos-style secondary (liquidity_score), calls the analyzer, and reports flips.

**First results on the 984 zero-gen-quote cycles (WS age ~1.2s + 40% secondary support):**
- Stub (local-style heuristic): 87.3% `ai_marked_truly_skimmable`, 100% suggested min_edge relax, 87.3% non-off posture.
- API-stub (more conservative remote-style): 13.8% skimmable, 51.4% relax, 13.8% non-off.
- Examples surface the pattern: on 0.018–0.089% L1 books the stub often says "Secondary data supports skimming" when we simulate good Anodos liquidity.

The high stub % is optimistic (heuristic). The contrast run shows how a "real" model behaves more cautiously. This is the measurement loop: re-run the orchestrator on the *same* corpus (or fresh snapshots from the live 150-fill run) after any change.

**Training export:** Running with `--export-training` produces `logs/ai_training_examples.jsonl` (4000+ rows) with structured `features`, `original` decision (hard_gate_fired, policy_snippet), and `outcome` (positive_capture_seen, any_fill_on_this_cycle from trades joined by cycle). This is the starting labeled set for real training or Grok API labeling.

All of this is in `experimental/ai_analysis/` on this branch only.

## Grok API vs Local AI — Would It Be Quicker?

**Yes for development velocity and insight speed.** The current rule-based hard gate + policy is safe and deterministic but conservative on exactly the thin-book conditions the run is exposing. Hand-augmenting more heuristics takes time and risks over-fitting or missing subtle interactions.

- **Grok API (xAI) strengths for this work:**
  - Excellent at structured reasoning over small batches of real examples.
  - Fast path to rich labels + rationales ("For these 50 hard-gate cycles with 0.04–0.08% L1 + rlusd_heavy + mild momentum, which look like they were over-conservative given the subsequent fills and what Anodos secondary would have shown?").
  - Feature discovery, prompt iteration, and generating candidate policy text or adjustment logic.
  - Creating high-quality distillation targets (Grok labels hundreds of cycles → use as supervision for something small).

- **Local AI (Ollama, llama.cpp, small models) strengths:**
  - Runtime speed (<100 ms target on tiny context: L1 spread, age, secondary liq, skew, toxicity).
  - Zero marginal cost, private, repeatable.
  - Suitable for the analysis step in replay or (later) advisory in an experimental engine loop.

**Runtime reality check:** Calling Grok API on every decision cycle is unlikely to be "quicker" (latency + cost). It is powerful for **offline/batch** work on the corpus. Local small models (or even a tiny learned scorer) win for speed in the loop. Hybrid is the practical sweet spot: Grok (or this discussion) for labeling/insight on the growing run data → distill into fast local inference that suggests "relax 1 bp" or "quote near" on marginal cases where secondary confirms value.

**Quicker overall path to better rake + dominance:**
1. Collect more data under the current hard-gate regime (the live run keeps producing the exact "blocked but maybe skimmable" cases).
2. Use Grok API on exported batches for high-signal analysis and labels.
3. Implement the learnings back into the existing rules (fast) **or** a small local component (fast + cheap at runtime).
4. Re-measure everything with the orchestrator + replay on the identical 150-fill corpus (closed loop, zero risk to VPS).
5. Only after validation do we consider any experimental wiring (still on this branch, post-Gate 2 decision for main).

This is much faster iteration than pure manual rule writing while preserving the safety moat (the hard gate).

## How This Fits the Broader WS + 3rd-Party Work
- WS book feed (`experimental/ws_feed/`) gives fresher state + lower age (probe shows 0.1–5 s typical, high apply rates).
- Anodos-style secondary (`experimental/market_analysis/external_data.py`) provides the alternative mid/depth/liquidity view that can "disagree" with thin on-chain L1 — exactly the confirmation signal the AI micro-analyzer needs.
- AI sits on top as the rapid triage layer for "is the edge real for rake?"

Everything feeds the same goal: more safe quotes on the marginal books the current run is hitting, measured by presence, capture, and (later) Tier metrics — without more toxicity.

## Open Questions & Next Steps (as of this writing)
- How conservative should the real local model be on sub-0.05% L1 books even with secondary support? (Tune via re-runs against actual fill outcomes.)
- Best label design: strict "positive capture on this exact cycle" vs. "the book moved in a way that a quote at that level would likely have been hit profitably"?
- When to move from heuristic stub → real small model call inside `LocalLLMAnalyzer`? (User choice: local speed first, or Grok API for richer batch labeling first?)
- Should we also export "contrast pairs" (hard-blocked cycle + nearest successful quote cycle on similar L1) for few-shot prompting?
- How to incorporate longer history (recent fill rate, inventory trajectory) without making context too big for small local models?
- Eventually: train a tiny distilled model on Grok-labeled data from multiple long runs? Use as async advisory signal?

**Immediate actions available:**
- `python -m experimental.ai_analysis.replay_ai_orchestrator --decisions logs/decisions.jsonl --analyzer stub --export-training`
- Improve the exporter (more features, better trade joining, "future book movement" labels).
- Generate ready-to-paste Grok prompt batches from the exported training file (system prompt + hard cases + successful contrast + actual outcomes).
- Run the orchestrator with real outcome labels instead of pure stub and compare flip rates.
- User provides fresh decisions snapshots from the live 150-fill run → re-export + re-analyze.

**Grok / xAI API support (now live for competitor intelligence):**
- Config tab in the real-time HUD now drives `intel_ai_provider` (grok), `intel_ai_key` (xai-...), `intel_ai_model` (grok-beta), and enabled flag.
- Real calls go through the HUD server's `/analyze_competitor` POST (takes a competitor ledger r-address; uses current on-chain scrape context + book activity for "trending/strategy" analysis).
- Prompt focuses on XRPL MM patterns (spreads, cancels after fills, inventory skew, pressure) and how pure A-S can skim harder / compete.
- Fully advisory: output appears in Intelligence tab + decision notes / logs. **Never mutates A-S reservation price, optimal spread, or "would quote" decision** (pure A-S math inside the WS book remains the sole quoting guard).
- Llama3 / stub path deprecated for the intel use-case (kept only as fast fallback / per-sample heuristic that already folds in competitor pressure).
- Form "Apply" in Config tab does a live `/set_intel_config` push so key changes take effect immediately without tester restart.
- CLI support: `--intel-ai-provider grok --intel-ai-key xai-... --intel-ai-model grok-beta` (pre-fills the HUD form + state).
- Next: token rotation hygiene, cost tracking, richer prompts with full competitor profiles, distillation targets from Grok labels. More details to come.

## Rules for This Work
- Everything stays in `experimental/ai_analysis/` (and related experimental/ dirs) on `grok-ws-feed`.
- Current main engine long run + hard gate is the untouched data source and oracle.
- Use replay + orchestrator to quantify every proposed improvement on the exact same historical cases.
- No production impact until after Gate 2 judgment and explicit operator approval.
- Update this file (and `WS_HANDOFF.md` / `PROBE_RESULTS.md`) as the discussion and experiments evolve.
- Primary success metric: better good-rake capture and safe presence on the thin-book / 0-offer regimes the run is exposing, measured safely in replay first.

This document is the living home for the conversation. Add thoughts, new run results, prompt experiments, model comparisons, and decisions here as we go.

---

**Contact / related:** See `WS_HANDOFF.md` in ws_feed/ for the broader WS + secondary context. The long run with the hard gate active is our best teacher for when (and how) to be slightly braver on marginal opportunities while protecting competitive dominance through disciplined rake.

## 11k XRP-Only WS A-S Deployment & AI Role in Predator Scaling (June 2026 Session Observations)

**Context for this AI work:** Deploying the committed WS + pure A-S bot with *only* 11k XRP funding (no initial RLUSD). Starts 100% XRP heavy. Primary early activity is rebalancing via competitive L1/L2/L3 *asks* (inventory skew + explicit "XRP-only mode → competitive asks until RLUSD balance builds") while capturing spread on the sells. Once near 55% target, balanced two-sided quoting. Goal: higher presence than the gated long-run, scaling inventory → larger absolute L1/L2/L3 pull, compounding skim as capital grows (rebalance turnover + realized spread capture). Live ledger queries confirm large single orders (36k+ XRP) and total depth (200k+ asks / 280k+ bids) exist, with inside still tight — supportive of scaling L1 into the low thousands XRP without being sole liquidity; large deeper offers provide cover for rebalance sells.

**WS A-S path differences (key for AI utility):** Unlike the sacred long-run (frequent "0 quotes", "L1 too tight", `market_edge_met=false`, "hard gate; no live quotes", toxicity no-touch, edge guard size cuts, momentum pauses → low ~10-20% presence on thin books), this path is **pure A-S with built-in protections only** (reservation inside live WS best bid/ask via gamma for inventory risk; optimal spread via kappa + vol for adverse selection). WS book feed supplies fresher mid/L1/depth/age/message count. No outer hard gate as a blocker. Expected (and validated in grokster replays on the exact long-run corpus): 90%+ presence / 93%+ flip rate on historical blocked cases, with 0% modeled high-tox among the extra quotes. "Too tight" / edge signals remain useful for the operator and logs but do not veto quotes in the pure path.

**AI / Grok role (strictly advisory, as always — now in predator context):**
- Lives in **Intelligence tab** + **Config tab** of the real-time HUD (and main GUI stubs).
- Real Grok/xAI calls (provider=grok, key, model=grok-beta, enabled) via `/analyze_competitor` endpoint (POST competitor ledger `r...` address + current on-chain scrape + book activity context).
- Prompt tuned for XRPL MM patterns (spreads, sizes, cancels, skew, pressure) + "how pure A-S can skim harder / compete here".
- Output: rich rationale + "skim harder" suggestions (e.g., "low pressure on this maker → opportunity for tighter L1 asks or larger size on the observed spread"). Appears in Intelligence tab, decision notes, logs. **Never mutates A-S reservation, optimal spread, would_quote, or gamma/kappa.**
- Per-sample "AI rationale" in the HUD still uses the enhanced local stub (which folds in competitor_pressure) for speed / rate-limit avoidance. Dedicated address button triggers real Grok.
- Llama3/stub deprecated for this intel use-case.
- CLI: `--intel-ai-provider grok --intel-ai-key xai-... --intel-ai-model grok-beta`.

**How AI helps the 11k XRP predator scale & skim harder (without touching core math):**
- Low competitor pressure (defensive observed spreads / weak makers on the book) → AI surfaces "scrape harder here" (tighter effective quotes, larger L1 pull, more presence exactly on those books). Feeds the operator (or future distilled signals) so the pure A-S can be more aggressive where edge is real and competition soft.
- High pressure → AI + A-S math naturally more conservative (protection via reservation inside book).
- Ties directly to rebalance (XRP-heavy): AI can highlight when pressure is low on the ask side → lean into competitive asks for faster RLUSD build + skim capture.
- Ties to scaling/compounding: As inventory grows (rebalance sells + skim), AI helps identify *where* to deploy the larger L1/L2/L3 pull for max rake (e.g., "this competitor's profile + current pressure + WS-fresh depth suggests this level is skimmable with low tox risk"). Measurement loop: track AI suggestion acceptance + outcome delta (did following "skim harder" improve realized bps without tox spike?).
- Live ledger data (large 36k+ XRP offers + hundreds of k total depth) gives AI concrete "who is providing real liquidity right now" context for trending analysis.

**P&L / presence implications captured for AI work:**
- Conservative projections (grounded in long-run +3.957 XRP net / 429 fills baseline + WS uplift + no-gate higher presence + live user view of ~500 XRP equiv / 24h potential in good conditions, with compounding): blended daily 150–300+ XRP skim; year-end net P&L +25k–45k XRP equiv; end bot value 36k–56k XRP equiv from 11k start.
- Higher presence from pure path + live WS + pressure calibration directly multiplies absolute skim volume as capital grows. AI's job: help the operator (and later distilled models) push the "when competitors are defensive" presence bucket without increasing adverse selection.

**Rules for this work (unchanged but reinforced):**
- Everything stays in `experimental/ai_analysis/` (and related experimental/ dirs) on `grok-ws-feed`.
- Sacred long-run (hard gate active) is the untouched data source and oracle.
- Use replay_ai_orchestrator + grokster-style validation on the exact same historical cases (plus new 11k XRP run data) to quantify every proposed improvement.
- No production impact on main engine or VPS until after Gate 2 sign-off + explicit operator approval.
- AI remains **strictly advisory** — never hard rules, overrides, or mutations on pure A-S reservation math or the WS book's "would quote" decision.
- Update this file, `WS_HANDOFF.md`, `WS_AS_MANUAL.md`, and the main `IMPLEMENTATION_PLAN.md` as observations evolve.

**Immediate actions (tied to 11k XRP WS A-S predator deployment):**
- Generate Grok prompt batches focused on the 11k XRP rebalance cases (XRP-heavy + large ask L1/L2/L3 + low-pressure competitor profiles from live book queries).
- Run `replay_ai_orchestrator` on fresh decisions from the funded 11k instance (once running) + export training examples that include competitor_pressure features.
- In the HUD Config/Intelligence surface: ensure Grok "analyze competitor" button is prominent for trending addresses during rebalance; log acceptance + outcome.
- Extend the local stub (if needed) to more explicitly surface "low pressure → skim harder on asks" recommendations for XRP-heavy mode.
- Track new metrics in the AI loop: "presence when competitor pressure low vs high", "AI suggestion → realized bps delta on rebalance asks".

This keeps the AI work laser-focused on making the human (and the pure A-S math) the best, most profitable skimmer on the book — exactly the "predator" direction for the 11k XRP WS A-S bot.

---

**Contact / related (updated):** See the new dedicated subsection in `docs/IMPLEMENTATION_PLAN.md` (Tier 3) for the full 11k XRP scaling / predator observations and implementation actions. Cross-refs to `experimental/ws_feed/`, `WS_AS_MANUAL.md`, and `STRATEGY_MANUAL.md`. The sacred long-run remains the best teacher.