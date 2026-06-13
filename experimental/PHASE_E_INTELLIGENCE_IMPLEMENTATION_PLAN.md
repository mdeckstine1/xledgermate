# Phase E: Dynamic Competitor Intelligence & Relative Peer Sizing

**Status:** Draft / Brainstorming in Progress  
**Branch:** grok-ws-feed (experimental)  
**Related:** WS + pure A-S path, Intelligence tab / HUD, sizing mechanisms, Grok exploitation layer  
**Date:** 2026-06-13  

## 1. Overview & Goals

Phase E evolves the competitor intelligence layer from static/top-10 analysis to a **dynamic, relative, inventory-scaled peer system**. 

The goal is to support consistent XRP bag building through disciplined market making while making intelligence actionable and proportional to the user's current inventory.

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
- Accept controlled risk in exchange for better positioning on favorable structures.

## 3. Proposed Architecture

### 3.1 Dynamic Relative Peer Band
- Automatically adjusts based on current inventory.
- Focuses on relevant peers rather than top whales.
- Naturally scales as the bag grows.

### 3.2 Structural Signals
- Objective, observable signals (cancellation behavior, sustained one-sided pressure, defense strength, book velocity relative to spread).
- Used to identify situations where modest edges are favorable.

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

The system is designed to be appropriate at current size while improving as the bag grows:
- Smaller sizes: More conservative gating and lighter bias.
- Larger sizes: Stronger structural signals and more opportunity to edge on favorable setups.
- Advanced contrarian logic remains a future module.

## 6. Live Market Making Considerations

- Strong emphasis on observability and logging.
- Intelligence can start in advisory/monitoring mode.
- Gradual activation with clear rollback options.
- Focus on consistent, lower-drama bag building.

## 7. Performance Grading & Evaluation Criteria

To evaluate how the bot is performing in live market making and guide tweaks, we will track the following categories:

### 7.1 Spread Capture Quality
- % of fills with positive capture
- Average bps per fill

**Good**: >70% positive capture, average >8-10 bps  
**Needs Attention**: <60% positive capture, average <5 bps

### 7.2 Inventory / Bag Growth
- Net inventory growth from fills (not deposits)
- Inventory deviation stability

**Good**: Steady positive growth, deviation mostly within ±8-10%  
**Needs Attention**: Flat/negative growth from fills, frequent large deviations

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

### 7.6 Peer Band Relevance
- % of time relevant peers are found
- Quality and usefulness of peer data

**Good**: Good peer coverage, signals feel relevant  
**Needs Attention**: Frequent sparse data, noisy or irrelevant signals

### 7.7 How to Use These Criteria
- Track over rolling periods (last 100 fills, last 7 days, last 30 days).
- Review regularly during live market making.
- Use results to guide tweaks (e.g., gating strictness, signal strength, performance scaler permissiveness).

## 8. Phased Rollout

**Phase E.1** — Peer band + basic structural signals.
**Phase E.2** — Balanced performance scaler + gating.
**Phase E.3** — Async wiring and HUD visibility (including new Performance Metrics tab).
**Phase E.4** — Integration into quoting logic.
**Phase E.5** — Replay validation and initial live testing.
**Phase E.6** — Gradual activation and refinement using performance grading criteria.

## 9. Open Questions & Next Steps
- Refining the exact structural signals and their strength.
- How aggressively to allow modest edges at current bag size.
- Exact metrics and display for the new Performance Metrics tab.

**Immediate Next Action:** Define implementation tasks for Cursor, including the new Performance Metrics tab in the HUD.

---

*This document lives in experimental/ on the grok-ws-feed branch and will be updated as we implement and test.*