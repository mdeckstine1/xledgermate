# Phase E: Dynamic Competitor Intelligence & Relative Peer Sizing

**Status:** Draft / Brainstorming in Progress  
**Branch:** grok-ws-feed (experimental)  
**Related:** WS + pure A-S path, Intelligence tab / HUD, sizing mechanisms, Grok exploitation layer  
**Date:** 2026-06-13  

## 1. Overview & Goals

Phase E evolves the competitor intelligence layer from static/top-10 analysis to a **dynamic, relative, inventory-scaled peer system**. 

The goal is to support consistent XRP bag building through disciplined market making while making intelligence actionable and proportional to the user's current inventory. The system should behave appropriately at current bag size while naturally improving as inventory grows from successful market making.

### Primary Objectives
- Use a dynamic relative peer band focused on similar-sized makers.
- Develop objective structural signals based on competitor behavior patterns and book structure.
- Allow modest edges on favorable structural setups while maintaining strong discipline.
- Keep the core Avellaneda-Stoikov logic protected.
- Design for natural scaling as the bag grows.

### Success Criteria
- More relevant competitor signals for the current inventory size.
- Consistent spread capture with controlled inventory growth.
- Clear visibility into why the bot is quoting or biasing in certain ways.
- Ability to edge modestly on good structural opportunities without excessive risk.

## 2. Core Design Philosophy

This is a **market making system** focused on collecting the spread (the rake) and supporting consistent long-term inventory growth.

Key principles:
- Focus on objective, current market structure and competitor behavior patterns.
- Avoid momentum chasing and tilt based on recent P&L.
- Intelligence should modulate how A-S is applied (size, bias, aggression) rather than override the reservation price.
- Build a solid, disciplined foundation now that can scale and improve as the bag grows.
- Accept controlled risk in exchange for better positioning on favorable structures — perfect is the enemy of good.

## 3. Proposed Architecture

### 3.1 Dynamic Relative Peer Band
- Automatically adjusts based on current inventory.
- Focuses on relevant peers rather than top whales.
- Naturally scales as the bag grows.

### 3.2 Structural Signals
- Objective, observable signals (cancellation behavior, sustained pressure, defense strength, book velocity relative to spread).
- Used to identify favorable structural situations for modest edges.

### 3.3 Conservative but Opportunity-Aware Performance Scaler
- Primarily acts as a risk brake.
- Can allow modest size increases when strong structural signals align and conditions are favorable.

### 3.4 Advisory Intelligence Layer
- All intelligence outputs are advisory.
- Modulates size_mult, side bias, and skim_harder through gated signals.
- Core A-S reservation price remains protected.

## 4. Key Mechanisms

### 4.1 Performance Scaler
- Conservative overall.
- Can support modest growth when structural conditions are good.
- Avoids aggressive ramping based purely on recent performance.

### 4.2 Structural Bias
- Light to moderate bias allowed on clearly favorable structural setups.
- Focus on competitor behavior and book structure rather than momentum.

### 4.3 Inventory Management
- A-S reservation price remains the primary mechanism.
- Intelligence supports consistent bag building over time.

## 5. Scaling with Inventory Growth

The system is designed to be appropriate at current size (~11k XRP) while improving as the bag grows:
- Smaller sizes: More conservative gating and lighter bias.
- Larger sizes: Stronger structural signals and more opportunity to edge on favorable setups.
- Advanced contrarian logic ("sell water in the desert / buy water cheaper") remains a future module.

## 6. Live Market Making Considerations

- Strong emphasis on observability and logging.
- Intelligence can start in advisory/monitoring mode.
- Gradual activation with clear rollback options.
- Focus on consistent, lower-drama bag building rather than aggressive short-term gains.

## 7. Phased Rollout

**Phase E.1** — Peer band + basic structural signals.
**Phase E.2** — Conservative but opportunity-aware performance scaler + gating.
**Phase E.3** — Async wiring and HUD visibility.
**Phase E.4** — Integration into quoting logic with strong but balanced gating.
**Phase E.5** — Replay validation and initial live market making testing.
**Phase E.6** — Gradual activation and refinement based on real results.

## 8. Open Questions & Next Steps
- Refining the exact structural signals and their strength.
- How aggressively to allow modest edges at current bag size.
- When to introduce lighter versions of advanced structural bias.

**Immediate Next Action:** Define implementation tasks for Cursor with a balanced, market-making-focused approach that supports consistent bag building.

---

*This document lives in experimental/ on the grok-ws-feed branch and will be updated as we implement and test.*