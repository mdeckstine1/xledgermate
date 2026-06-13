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

## 2. Core Design Philosophy

This system is built as a **market maker collecting the rake**, not a momentum trader.

Key principles:

- **Read what is right in front of it**: The bot should focus on objective, current data — competitor behavior patterns, book structure, spread velocity, and depth dynamics — rather than recent P&L or emotional reactions.
- **No tilt**: Recent good or bad performance streaks are mostly short-term variance. They should have limited influence on real-time aggression or sizing decisions.
- **Competitor pattern focus**: Primary value comes from understanding how similar-sized makers are currently defending, canceling, and positioning — not from chasing or fading short-term results.
- **Structural edge over momentum**: Exploitation signals should be based on observable market structure and competitor behavior, not on recent fill outcomes.
- **Protect the A-S core**: The Avellaneda-Stoikov reservation price and inventory logic remain the foundation. Intelligence layers modulate *how* A-S is applied, but do not override it.
- **Appropriate sizing with growth path**: The system must behave responsibly at current inventory levels while being architected to naturally improve and scale as the bag grows (no major rewrites required).

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
- Package context focused on current structure: peer behavior patterns, book velocity, spread dynamics, and inventory position.
- Send to Grok with structured prompt asking for objective observations on competitor strategy quality and potential structural opportunities.
- Parse into structured output usable by sizing logic and HUD.

### 3.4 Integration with Sizing (Balanced Mix)
Final effective size = base_config_size × A-S inventory_factor × performance_mult (conservative) × depth_factor (from relevant peers) × AI_size_mult (from Grok/pressure, gated).

## 4. Key Mechanisms

### 4.1 Performance Scaler (Conservative Role)
- Recent performance has **limited influence**.
- It acts primarily as a **soft veto** when recent results have been poor (to avoid compounding risk).
- It does **not** act as a strong accelerator when recent results have been good.
- Main purpose: Prevent over-aggression during unfavorable short-term variance while keeping the system focused on structural signals.

### 4.2 Competitor Depth / Size Factor
- From WS BookState or relevant peers cache, compute median/average offer size or visible depth in relevant band.
- `depth_factor` = f(user_size, peer_typical_size, book_depth).
- Focuses on structural competitiveness rather than momentum.

### 4.3 Grok Exploitation Signals
- Focused on observable competitor patterns and book structure (cancellation behavior, defense strength, velocity relative to spread).
- Maps to size_mult, side bias, skim_harder only when structural conditions support it.
- Keep advisory-only and gated by confidence + toxicity risk.

### 4.4 Inventory-Aware Scaling
- Leverage existing `assess_inventory` and A-S reservation price for mean-reversion.
- Layer conservative performance and peer-based multipliers on top.
- Hard caps on deviation, risk capital, daily limits.

## 5. Scaling with Inventory Growth

The system is explicitly designed to be **appropriate at current bag size while improving as inventory grows**.

- **At smaller sizes** (~10k–20k XRP): More conservative gating, focus on relevant peer behavior, and strong protection of the A-S core.
- **As bag grows**: Peer band automatically widens, structural signals become more meaningful, and more advanced bias logic can be enabled with minimal code changes.
- The more advanced "sell water in the desert / buy water cheaper to hold" contrarian logic is treated as a **future add-on module** to be activated when the bag has significant weight.
- All major components (peer band, signals, gating, performance scaler) use relative/inventory-aware logic to support natural scaling.

## 6. Data Capture & Storage
- Lightweight persistent store (e.g., `relevant_peers.jsonl`).
- Focus on current structural data: peer behavior patterns, offer sizes, cancellation frequency, depth dynamics.
- Versioned snapshots for replay/testing.

## 7. Automation & Grok Integration
- Lightweight local preprocessing layer (rule + statistics based) builds clean context.
- Grok is called selectively on promising structural situations.
- Caching + rate limiting for API calls.
- Fallback to rule-based peer filtering when Grok unavailable.

## 8. Intelligence Tab / HUD Updates
- New section focused on current structural observations: peer behavior patterns, book velocity, and competitor strategy signals.
- Grok Suggestions panel shows objective structural insights rather than performance-based advice.

## 9. Phased Rollout

**Phase E.1** — Define peer band logic + basic capture (config + filtering function).
**Phase E.2** — Conservative performance scaler + depth_factor from peers.
**Phase E.3** — Grok relative suggestion prompt focused on structural patterns.
**Phase E.4** — Automation (background pulls) + HUD integration.
**Phase E.5** — Full wiring into engine_adapter / sizing + replay validation.
**Phase E.6** — Live testing on VPS (advisory mode first) + metrics tracking.

## 10. Risks & Mitigations

### 10.1 Data Staleness and Quality
- **Risk**: Stale peer or book data leading to poor decisions.
- **Mitigation**: Smart refresh triggers, staleness scoring in HUD, incremental updates, and fallback to broader rules when relevant peer data is sparse.

### 10.2 Grok API Latency and Over-Interpretation
- **Risk**: Grok adding latency or over-interpreting noise.
- **Mitigation**: Async/background execution, structured input focused on current structure, confidence gating, and fast fallback to pure A-S + pressure model.

### 10.3 False Signals from Performance Focus
- **Risk**: System reacting to short-term P&L variance instead of structure.
- **Mitigation**: Performance scaler kept conservative. Main signals come from competitor behavior patterns and book structure. Recent results used only as soft veto, not accelerator.

## 11. Async Intelligence Architecture (Keeping Core A-S Fast)

- Core A-S decision path remains fully synchronous and lightweight.
- Intelligence components run asynchronously in background.
- Main trading loop reads latest cached advisory signals.
- Grok used primarily for deeper structural analysis on promising situations.

## 12. Toxicity Management with Fresh WebSocket Data

WebSocket data significantly reduces false toxic triggers caused by stale book information. Toxicity logic factors in data freshness and focuses on real adverse selection risk rather than data artifacts.

## 13. Peer Band Configuration & Filtering Logic (Detailed)

### Config Parameters
```yaml
peer_band:
  min_mult: 0.3
  max_mult: 5.0
  min_peer_count: 5
  fallback_band_mult: 10.0
  refresh_on_inventory_pct: 5
  max_age_seconds: 1800
```

### Filtering Logic
Focus on observable structural data from peers in the band (offer sizes, cancellation patterns, defense behavior) rather than historical performance.

## 14. Performance Scaler Implementation (Conservative)

- Metrics tracked for monitoring only.
- Used primarily as a soft risk brake when recent results are poor.
- Does not drive size increases based on recent good performance.
- Keeps the system focused on structural signals.

## 15. Enhanced Toxicity Detection Logic (WS-aware)

Inputs include WS book freshness, fill quality, inventory skew, and structural signals from peers. Aggressive intelligence suggestions are only applied when toxicity risk is low.

## 16. Open Questions & Next Steps
- Refining objective signals for detecting strong vs weak competitor strategies.
- Exact peer band parameters.
- Grok prompt focused on current structural patterns.
- Storage and preprocessing details.

**Immediate Next Action:** Continue refining structural signals for competitor behavior and book velocity while keeping scaling behavior in mind.

---

*This document lives in experimental/ on the grok-ws-feed branch and will be updated as we implement and test.*