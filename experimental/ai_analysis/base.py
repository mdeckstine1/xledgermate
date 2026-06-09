from __future__ import annotations

"""
Base for AI / LLM analysis in WS book feed development.

At this initial stage (pre full engine adapter, using current main run data
as the testing ground), this is a *placeholder* for rapid analysis of:
- Edge quality on WS-updated book (fresher than poll).
- Whether a "thin book / L1 too tight / hard gate" trigger (as seen in
  the 150-fill run's hundreds of 0-offer cycles) is real or data artifact.
- Toxicity risk, suggested posture adjustments, confidence.

MM goal (per user): Good rake (spread capture when edge exists), competitive
dominance via better presence (Tier C) without more adverse selection.
Not about "trending" — about micro-structure: is the book paying real edge
right now? Use WS freshness + secondary (Anodos) + on-chain + AI for faster/
better decisions than rules alone.

Speed in decision making:
- Local AI (Ollama, llama.cpp, etc.) for low-latency in the loop (<100ms
  analysis on small context).
- API LLM (Grok, Claude, etc.) for heavier reasoning, batch analysis of
  run data, or when local models aren't strong enough yet.
- Hybrid: Local for fast triage, API for complex or offline (replay).

Design for expansion/growth on competitive MM:
- Pluggable providers (local vs API, different models).
- Inputs: WS BookState (fresh deltas, age), secondary data (Anodos mid/depth),
  on-chain metrics, run context (inventory, toxicity, recent fills).
- Outputs: Structured analysis (edge_quality_score, is_truly_skimmable,
  suggested_min_edge_adjust_pct, toxicity_risk, quote_posture, confidence,
  rationale) that can feed back into edge calc, policy, or hard gate.
- Future: Async in engine loop, trained on long-run "false edge thin"
  labels from current data, multi-horizon, cross-venue signals.
- Keep lightweight/experimental now. No hard dependency until post-Gate 2
  + WS adapter is solid. Use via replay first to measure impact on presence/rake
  from the 150-fill run's thin-book periods.

Do not wire into production engine yet. All in experimental/ai_analysis/
on this branch. Drive with current run data (decisions with hard-gate
messages, book spreads ~0.15%+, edge false, actual capture on fills that
landed).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AIAnalysis:
    """Structured output from AI analysis. Extend as needed."""
    edge_quality_score: float = 0.0          # 0-1: how real is the edge here?
    is_truly_skimmable: bool = False         # Should we be quoting?
    suggested_min_edge_adjust_pct: float = 0.0  # e.g. +0.02 or -0.01
    toxicity_risk: float = 0.0               # 0-1
    quote_posture: str = "off"               # at_touch, near, spread_mid, off
    confidence: float = 0.0                  # 0-1
    rationale: str = ""                      # Human-readable (for logs/replay)
    source: str = "placeholder"              # local-llm, api-llm, stub


class AIAnalyzer(ABC):
    """Pluggable AI analyzer for WS book + secondary data.

    Inputs should come from WsBookFeed (fresh state, age), Anodos/secondary
    (alternative mid/depth), and run context.

    For speed: Prefer local models for in-loop use. API for batch analysis
    of run data, or when local models aren't strong enough yet.
    """

    @abstractmethod
    async def analyze(
        self,
        book_state: Dict[str, Any],           # from WsBookFeed.current_order_book() + age
        secondary_data: Optional[Dict[str, Any]] = None,  # Anodos mid, liquidity, etc.
        run_context: Optional[Dict[str, Any]] = None,     # inventory, toxicity, recent fills, profile
        **kwargs
    ) -> AIAnalysis:
        """Return analysis. Should be fast for local; can be async for API."""
        ...

    def is_suitable_for_loop(self) -> bool:
        """Override: return False for slow API analyzers (use only in replay/offline)."""
        return True


class StubAIAnalyzer(AIAnalyzer):
    """
    Placeholder / rule-based stub. No real AI yet.

    Uses simple heuristics on book + secondary to mimic what a lightweight
    local model or fast API call might output. Perfect for initial stage:
    wire it into replay now, measure against the current run's hard-gate
    decisions, then swap in real local/API without changing callers.

    Driven by current data: In the 150-fill run, when book spread ~0.16%,
    edge calc says too tight, hard gate blocks — stub can say "edge_quality low
    because on-chain thin, but if secondary (Anodos) shows healthy depth,
    bump confidence and suggest near-touch".
    """

    async def analyze(
        self,
        book_state: Dict[str, Any],
        secondary_data: Optional[Dict[str, Any]] = None,
        run_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> AIAnalysis:
        bids = book_state.get("bids", [])
        asks = book_state.get("asks", [])
        age = book_state.get("age_s", 999.0)

        if not bids or not asks:
            return AIAnalysis(
                edge_quality_score=0.0,
                is_truly_skimmable=False,
                quote_posture="off",
                confidence=0.9,
                rationale="Empty book — no edge possible.",
                source="stub"
            )

        best_bid = max(b["price"] for b in bids)
        best_ask = min(a["price"] for a in asks)
        spread = (best_ask - best_bid) / ((best_bid + best_ask) / 2.0) * 100.0

        # Simple heuristic (will be replaced by real AI)
        edge_quality = max(0.0, min(1.0, (spread - 0.05) / 0.15))  # crude
        skimmable = spread > 0.10 and age < 10.0

        # Incorporate secondary (Anodos-style) if present
        sec_mid = None
        if secondary_data:
            sec_mid = secondary_data.get("mid_price")
            sec_liq = secondary_data.get("liquidity_score", 0.5)
            if sec_mid and sec_liq > 0.6:
                edge_quality = min(1.0, edge_quality + 0.2)  # secondary sees value
                skimmable = True

        # Incorporate competitor intel for competitive edge (new)
        comp_pressure = 0.5
        if run_context:
            comp_pressure = run_context.get("competitor_pressure", 0.5) or 0.5
            top_comps = run_context.get("top_competitors", [])
            if comp_pressure < 0.4 and top_comps:
                # Competitors look defensive → boost skimmability
                edge_quality = min(1.0, edge_quality + 0.25)
                skimmable = True

        posture = "near" if skimmable and spread > 0.12 else ("spread_mid" if skimmable else "off")

        rationale = (
            f"Spread {spread:.3f}%, age {age:.1f}s. "
            f"Edge quality ~{edge_quality:.2f}. "
            f"{'Secondary data supports skimming.' if secondary_data else 'No secondary data.'}"
            + (f" Competitor pressure {comp_pressure:.2f} — {'defensive, good to skim harder' if comp_pressure < 0.4 else 'aggressive'}." if run_context and run_context.get("competitor_pressure") is not None else "")
        )

        return AIAnalysis(
            edge_quality_score=edge_quality,
            is_truly_skimmable=skimmable,
            suggested_min_edge_adjust_pct=-0.01 if secondary_data else 0.0,
            toxicity_risk=0.3 if skimmable else 0.8,
            quote_posture=posture,
            confidence=0.6,
            rationale=rationale,
            source="stub"
        )

    def is_suitable_for_loop(self) -> bool:
        return True  # Stub is instant
