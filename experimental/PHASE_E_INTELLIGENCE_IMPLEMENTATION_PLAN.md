# Phase E: Dynamic Competitor Intelligence & Relative Peer Sizing

**Status:** Draft / Brainstorming in Progress  
**Branch:** grok-ws-feed (experimental)  
**Related:** WS + pure A-S path, Intelligence tab / HUD, sizing mechanisms, Grok exploitation layer  
**Date:** 2026-06-13  

## 1. Overview & Goals

Phase E evolves the competitor intelligence layer from static/top-10 analysis to a **dynamic, relative, inventory-scaled peer system**. 

The goal is to make intelligence actionable and proportional to the user's current bag size, automatically scaling as successful skim grows inventory. This supports the Balanced Mix approach for sizing while keeping pure A-S protections intact.

### Primary Objectives
- Replace or augment fixed "top 10 ledger addresses" with **similar-sized / relevant peers** (dynamic band around current inventory).
- Enable **automatic scaling** of peer group and quote sizes as inventory grows from skim success.
- Move from manual button-triggered pulls to **steady/automated analysis + Grok-suggested relevant data sets**.
- Feed relative competitor signals directly into sizing mechanisms (size_mult, depth_factor, performance scaler, skim_harder).
- Maintain full auditability, advisory-only nature, and integration with existing wiring (assess_inventory, build_quote_adjustments, AIAdvisorySignal, etc.).

### Success Criteria
- More relevant and less noisy competitor signals for smaller-to-medium accounts.
- Automatic, no-manual-intervention sizing that grows with proven skim performance.
- Clear visibility in Intelligence tab/HUD of current peer set and Grok recommendations.
- Measurable improvement in presence/capture on replay and live runs without increased toxicity or inventory risk.

## 2. Current State

- Competitor pressure model exists (`experimental/competitor_pressure.py`).
- AI analysis scaffolding with exploitation fields (`experimental/ai_analysis/base.py` — AIAnalysis, AIAdvisorySignal).
- Partial integration in `engine_adapter_example.py`.
- Intelligence tab / HUD supports on-demand pulls and Grok analysis (button-triggered).
- Currently pulls fixed top-N ledger addresses.
- Sizing is mostly static/config-driven + pressure + basic A-S reservation.
- Performance-based dynamic sizing and relative peer awareness are missing or manual.

## 3. Proposed Architecture

### 3.1 Dynamic Relative Peer Band
- Configurable band relative to current inventory (e.g., 0.3x – 5x user's XRP/RLUSD equivalent inventory, or percentile band).
- As inventory grows from successful fills, the band automatically shifts upward.
- Query/filter ledger data for accounts with recent offers whose size/activity falls in the band.
- Cache results with metadata (timestamp, observed sizes, spreads, activity).

### 3.2 Steady + Smart Pulls
- Background/periodic refresh (timer or inventory-change triggered).
- Keep manual button for deep dives.
- Incremental updates to reduce load.

### 3.3 Grok-Enhanced Relative Suggestions
- Package context: current bag size, recent skim performance (capture rate, PnL delta), target ratio, profile.
- Send to Grok with structured prompt asking for:
  - Filtered relevant peer subset (similar size/activity).
  - Exploitable patterns, typical offer sizes at this scale.
  - Suggested sizing/pressure adjustments.
  - Rationale.
- Parse into structured output usable by sizing logic and HUD.

### 3.4 Integration with Sizing (Balanced Mix)
Final effective size = base_config_size × A-S inventory_factor × performance_mult × depth_factor (from relevant peers) × AI_size_mult (from Grok/pressure).

## 4. Key Mechanisms

### 4.1 Performance Scaler (Skim Success 	o Size Growth)
- Track rolling metrics (e.g., % positive capture last N fills or session balance delta).
- Increase `performance_mult` when above thresholds (smoothed, e.g., EMA).
- Tie to inventory growth: stronger scaling when net inventory is rising from skim.
- Output feeds `AIAdvisorySignal` or dedicated scaler.

### 4.2 Competitor Depth / Size Factor
- From WS BookState or relevant peers cache, compute median/average offer size or visible depth in relevant band.
- `depth_factor` = f(user_size, peer_typical_size, book_depth) — e.g., target 10-40% of typical peer size or fraction of depth.
- Prevents tiny irrelevant quotes or oversized exposure.

### 4.3 Grok Exploitation Signals
- Extend `AIAdvisorySignal` with relative-peer insights.
- Map to size_mult, side bias, skim_harder, vol_mult.
- Keep advisory-only (never overrides A-S reservation math).

### 4.4 Inventory-Aware Scaling
- Leverage existing `assess_inventory` and A-S reservation price for mean-reversion.
- Layer performance and peer-based multipliers on top.
- Hard caps on deviation, risk capital, daily limits.

## 5. Data Capture & Storage
- Lightweight persistent store (e.g., `relevant_peers.jsonl` or database table in experimental/).
- Fields: address, timestamp, offer_size_metrics, observed_spread, activity_score, estimated_inventory (if derivable), relevance_score to user_bag.
- Versioned snapshots for replay/testing.

## 6. Automation & Grok Integration
- New module or extension: `experimental/ai_analysis/relative_peers.py` or similar.
- Prompt engineering for Grok (structured output preferred: JSON with filtered list + suggestions).
- Caching + rate limiting for API calls.
- Fallback to rule-based peer filtering when Grok unavailable.

## 7. Intelligence Tab / HUD Updates
- New section: "Relevant Peers (scaled to your current bag)" — list or summary with size comparison.
- Grok Suggestions panel: filtered peers + rationale + recommended sizing adjustments.
- Visuals: peer size distribution vs your size, influence on current size_mult.
- One-click apply suggestion (advisory preview before live).

## 8. Phased Rollout

**Phase E.1** — Define peer band logic + basic capture (config + filtering function).
**Phase E.2** — Performance scaler + depth_factor from peers.
**Phase E.3** — Grok relative suggestion prompt + parsing.
**Phase E.4** — Automation (background pulls) + HUD integration.
**Phase E.5** — Full wiring into engine_adapter / sizing + replay validation.
**Phase E.6** — Live testing on VPS (advisory mode first) + metrics tracking.

## 9. Testing Strategy
- Primary: Extend `replay_long_run.py` with performance/depth/relative-peer modes. Compare presence, capture, and sizing behavior on historical long-run data.
- A/B in live tester / HUD.
- Metrics: flip rate on thin books, effective size scaling vs inventory growth, peer relevance score, toxicity/inventory deviation.
- Safety regression: ensure A-S protections and existing gates remain effective.

## 10. Risks & Mitigations
- Noisy or sparse similar-sized data → Fallback to broader band or rule-based defaults.
- Over-scaling on short-term hot streaks → Strong smoothing + hard caps + cooldown periods.
- Grok API cost/latency → Caching, async where possible, replay-first usage.
- Privacy / data freshness → Only public ledger data; clear staleness indicators in HUD.

## 11. Open Questions & Next Steps
- Exact peer band parameters and how aggressively to scale with inventory.
- Preferred data source for ledger account sizes/offers (current indexer vs direct queries).
- Grok prompt template (we should draft and iterate).
- Storage backend (simple JSONL vs something more queryable).
- How deeply to integrate Grok suggestions into live sizing vs advisory-only initially.

**Immediate Next Action:** Draft and refine the Grok prompt for relative peer suggestions + define the peer band config schema.

---

*This document lives in experimental/ on the grok-ws-feed branch and will be updated as we implement and test.*