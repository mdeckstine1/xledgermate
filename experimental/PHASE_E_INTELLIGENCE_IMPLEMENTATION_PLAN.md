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

### 4.1 Performance Scaler (Skim Success → Size Growth)
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

### 10.1 Data Staleness and Quality
- **Risk**: Stale peer or book data leading to poor sizing decisions or false signals.
- **Mitigation**: Smart refresh triggers (inventory change + time-based max age), staleness scoring shown in HUD, incremental updates, and graceful fallback to broader rule-based pressure when relevant peer data is sparse or old.

### 10.2 Grok API Latency and "Decision Constipation"
- **Risk**: Grok calls adding latency or producing overly complex/conflicting advice that slows the core quoting loop.
- **Mitigation**: Run Grok analysis asynchronously or on a slower background cadence (timer or event-triggered). Cache responses. Force structured JSON output with confidence scores. Only apply suggestions when confidence is high. Always maintain a fast synchronous fallback path using pure A-S + pressure model.

### 10.3 False Toxic States from Data Quality
- **Risk**: Bot incorrectly entering defensive/off-book mode due to bad data.
- **Mitigation**: With WebSocket, book age drops dramatically (often < 5s, frequently sub-second). This significantly reduces false toxic triggers compared to polling. Combine with confidence-weighted intelligence and hard caps so imperfect data makes the bot more conservative rather than more aggressive.

## 11. Async Intelligence Architecture (Keeping Core A-S Fast)

To prevent the intelligence layer from slowing down the Avellaneda-Stoikov quoting engine:

- Core A-S decision path (`compute_avellaneda_quote`, reservation price, optimal spread) remains fully synchronous and lightweight.
- Intelligence components (Grok calls, peer set refresh, performance scaler updates) run **asynchronously** in background threads or on a separate timer/event loop.
- The main trading loop reads the latest *cached* values from `AIAdvisorySignal` and peer data without waiting.
- Grok is primarily used for:
  - Background analysis and suggestion generation
  - Replay / offline calibration
  - On-demand deep dives via the Intelligence tab button
- During live quoting, the bot uses the most recent cached advisory signal (or falls back to pressure model + pure A-S if cache is stale or low-confidence).

This design ensures the A-S strategy stays fast even if Grok is slow, rate-limited, or temporarily unavailable.

## 12. Toxicity Management with Fresh WebSocket Data

**Key Improvement over Polling Version**

In the original HTTP polling setup, stale book data (often 12–30+ seconds old) frequently caused the bot to incorrectly classify the environment as toxic. This led to unnecessary defensive behavior (pulling quotes, widening spreads, or going off-book).

With WebSocket:
- Book age is typically under 5 seconds and often 0.1–2 seconds during active periods.
- Edge detection (`assess_market_edge`), toxicity proxies, and dynamic policy operate on significantly fresher data.
- False "toxic environment" signals caused purely by staleness should decrease substantially.

**Remaining Toxicity Sources (Still Need Management)**
- Genuine adverse selection on fills
- Rapid inventory skew from unbalanced flow
- Truly thin or fast-moving books (even with fresh data)
- Overly aggressive sizing from the intelligence layer

**Recommended Approach**
- Keep existing toxicity guards (`toxic_off_touch_latched`, off-book defense, session kill thresholds).
- Weight toxicity signals by data freshness/confidence.
- When intelligence layer suggests more aggressive sizing, require higher confidence thresholds during periods of elevated toxicity risk.
- Use WS book age as an explicit input to the dynamic policy and performance scaler.

**Net Effect**: The bot should become less *falsely* defensive while remaining appropriately cautious when real toxicity risk is present.

## 13. Peer Band Configuration & Filtering Logic (Detailed)

### Config Parameters (proposed)
```yaml
peer_band:
  min_mult: 0.3          # Minimum multiplier of user's current inventory
  max_mult: 5.0          # Maximum multiplier of user's current inventory
  min_peer_count: 5      # Minimum number of peers required before using band
  fallback_band_mult: 10.0  # Wider band if not enough peers found
  refresh_on_inventory_pct: 5   # Refresh when inventory changes by this %
  max_age_seconds: 1800  # Hard max age for peer data (30 min)
```

### Filtering Logic
1. Get current user inventory value (XRP + RLUSD equivalent at mid).
2. Calculate band: [inventory * min_mult, inventory * max_mult].
3. Query recent offer creators on the pair whose offer sizes or account balances fall inside the band.
4. If fewer than `min_peer_count` peers found, temporarily widen to `fallback_band_mult`.
5. Score and rank peers by relevance (size proximity + recent activity + observed behavior similarity).
6. Cache the filtered set with timestamp and relevance scores.

This logic lives in a new module (e.g. `experimental/ai_analysis/peer_band.py`).

## 14. Performance Scaler Implementation

### Metrics to Track
- Rolling positive capture rate (last 30–50 fills)
- Session / recent balance PnL delta
- Inventory growth rate from fills (not deposits)

### Smoothing & Output
- Use Exponential Moving Average (EMA) for stability.
- Base `performance_mult` starts at 1.0.
- Increase gradually when metrics are strong (example ramp: +0.05 per 5% above target positive capture).
- Apply cooldown period after large increases.
- Output is added to `AIAdvisorySignal.size_mult` (or a dedicated field).

### Safety
- Hard cap on `performance_mult` (e.g. max 1.5–2.0 initially).
- Reset or reduce on any toxicity event or inventory deviation breach.
- Only allow scaling when overall toxicity risk is low.

## 15. Enhanced Toxicity Detection Logic (WS-aware)

### Inputs
- WS book age / freshness score
- Recent fill quality (capture bps, negative capture %)
- Current inventory skew (from `assess_inventory`)
- Rolling toxicity proxy (markout or off-book rate)
- Intelligence layer confidence (lower confidence = treat as higher risk)

### Decision Rules (example)
- If book age > threshold and intelligence confidence low → increase conservatism (reduce size_mult, favor off-book more).
- If recent fills show rising negative capture → temporarily pause performance scaler increases.
- Combine with existing `toxic_off_touch_latched` and session kill logic.

### Integration with Intelligence
- Aggressive suggestions from Grok/pressure are only applied when toxicity risk score is low.
- When toxicity risk is elevated, the system defaults to more conservative sizing even if intelligence suggests otherwise.

This keeps the bot appropriately defensive when needed while taking advantage of fresh WS data to avoid unnecessary defensiveness.

## 16. Open Questions & Next Steps
- Exact peer band parameters and how aggressively to scale with inventory.
- Preferred data source for ledger account sizes/offers (current indexer vs direct queries).
- Grok prompt template (we should draft and iterate).
- Storage backend (simple JSONL vs something more queryable).
- How deeply to integrate Grok suggestions into live sizing vs advisory-only initially.

**Immediate Next Action:** Draft and refine the Grok prompt for relative peer suggestions + define the peer band config schema.

---

*This document lives in experimental/ on the grok-ws-feed branch and will be updated as we implement and test.*