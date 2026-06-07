from __future__ import annotations

"""
Example local LLM stub (Ollama-style) and API stub.

For rapid analysis in the loop: Use a small, fast local model (e.g. phi3, gemma2, llama3.2)
via Ollama or llama.cpp. Context is tiny (book spread, age, secondary mid, inventory skew,
recent toxicity) so even 1-2B models can give useful structured output.

For offline/batch on long run data: API (Grok, Claude, GPT) for deeper reasoning
or when local models hallucinate on edge cases.

Speed note: Local on decent hardware can do 50-200 tokens/sec for small models.
Keep prompts < 500 tokens, ask for JSON only. Cache aggressively.

This is *analysis*, not the hot path. The rules engine (assess_market_edge,
dynamic policy, hard gate) stays fast and deterministic. AI suggests adjustments
or flags "this thin book looks suspicious, Anodos says healthy depth, consider
relaxing 10%".
"""

import json
import logging
from typing import Any, Dict, Optional

from experimental.ai_analysis.base import AIAnalyzer, AIAnalysis

logger = logging.getLogger(__name__)


class LocalLLMAnalyzer(AIAnalyzer):
    """
    Placeholder for local LLM (Ollama / llama.cpp / etc.).

    In real use:
      import ollama
      response = ollama.chat(model='phi3', messages=[...])
      # parse JSON from response['message']['content']

    For now: rule-based with a "LLM would say" comment block so you can
    literally paste the prompt + expected output into a real local model
    and iterate.

    Current run data tie-in: Feed the exact "Book L1 spread 0.166%, edge false,
    hard gate, ask-heavy book -54%" from the 150-fill run. Ask the model:
    "Given Anodos secondary shows mid 1.093 and decent liquidity, is the on-chain
    thinness real or stale data? Suggest posture."
    """

    def __init__(self, model: str = "phi3:mini"):
        self.model = model

    async def analyze(
        self,
        book_state: Dict[str, Any],
        secondary_data: Optional[Dict[str, Any]] = None,
        run_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> AIAnalysis:
        # Build tiny prompt/context (this is what you'd send to local LLM)
        spread = book_state.get("book_spread_pct", 0.0)
        age = book_state.get("age_s", 999.0)
        bid = book_state.get("best_bid")
        ask = book_state.get("best_ask")

        sec_mid = secondary_data.get("mid_price") if secondary_data else None
        sec_liq = secondary_data.get("liquidity_score", 0.5) if secondary_data else 0.5

        inv_skew = (run_context or {}).get("inventory_skew", 0.0)
        toxicity = (run_context or {}).get("toxicity", 0.2)

        # === PROMPT YOU WOULD SEND TO LOCAL LLM (copy-paste ready) ===
        prompt = f"""You are a fast, conservative XRPL market-making analyst.
Book: spread={spread:.3f}%, best_bid={bid}, best_ask={ask}, age={age:.1f}s
Secondary (Anodos-like): mid={sec_mid}, liquidity={sec_liq:.2f}
Context: inventory_skew={inv_skew:.2f}, toxicity={toxicity:.2f}

The hard gate just blocked (edge_met=false, L1 too tight).
Is the thinness real or likely stale/poll artifact?
Give JSON only:
{{
  "edge_quality": 0.0-1.0,
  "truly_skimmable": true/false,
  "suggested_adjust_pct": -0.02 to +0.02,
  "toxicity_risk": 0.0-1.0,
  "posture": "at_touch|near|spread_mid|off",
  "confidence": 0.0-1.0,
  "rationale": "one sentence"
}}
"""
        # === END PROMPT ===

        # Current stub: rule-based approximation of what a small local model
        # would output after seeing the prompt + current run patterns.
        # (Replace this block with actual ollama.chat / llama.cpp call.)
        edge_q = max(0.1, min(0.9, (spread - 0.08) / 0.12 + (sec_liq - 0.5) * 0.4))
        skimmable = spread > 0.10 and sec_liq > 0.55 and toxicity < 0.35
        adjust = -0.015 if sec_liq > 0.65 and age > 2.0 else 0.0
        risk = 0.25 if skimmable else 0.75
        posture = "near" if skimmable and spread > 0.12 else ("spread_mid" if skimmable else "off")
        conf = 0.65 if sec_mid else 0.45

        rationale = (
            f"Spread {spread:.3f}%, age {age:.1f}s, sec_liq {sec_liq:.2f}. "
            f"{'Secondary data supports skimming.' if sec_liq > 0.6 else 'No strong secondary confirmation.'}"
        )

        # In a real local LLM call you would parse the JSON from the model output
        # and fall back to the heuristic above on parse failure.
        return AIAnalysis(
            edge_quality_score=edge_q,
            is_truly_skimmable=skimmable,
            suggested_min_edge_adjust_pct=adjust,
            toxicity_risk=risk,
            quote_posture=posture,
            confidence=conf,
            rationale=rationale + " [stub — replace with local LLM call]",
            source=f"local-{self.model}"
        )

    def is_suitable_for_loop(self) -> bool:
        # Local small models are fast enough for analysis (not the hot path).
        return True


class APIAIAnalyzer(AIAnalyzer):
    """
    Placeholder for remote LLM (Grok, Claude, GPT-4o, etc.).

    Use for:
    - Batch analysis of entire long runs ("explain all 200+ hard-gate cycles
      in the 150-fill run").
    - Higher quality reasoning when local models hallucinate on edge cases.
    - Generating training labels for a future small distilled model.

    NOT for the hot decision loop (latency + cost). Call asynchronously
    or only on demand / in replay.
    """

    async def analyze(
        self,
        book_state: Dict[str, Any],
        secondary_data: Optional[Dict[str, Any]] = None,
        run_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> AIAnalysis:
        # In real code you would call the API here (anthropic, openai, xai, etc.)
        # and parse structured output (JSON mode or tool calling).
        # For now just return a slightly more "thoughtful" stub.
        spread = book_state.get("book_spread_pct", 0.0)
        age = book_state.get("age_s", 999.0)
        sec_liq = secondary_data.get("liquidity_score", 0.5) if secondary_data else 0.5

        # Simulate a more nuanced remote model that has "seen" many thin RLUSD books.
        edge_q = max(0.15, min(0.95, (spread - 0.06) / 0.10 + (sec_liq - 0.4) * 0.5))
        skimmable = spread > 0.09 and sec_liq > 0.5 and age < 8.0
        adjust = -0.02 if sec_liq > 0.7 else 0.005
        risk = 0.22 if skimmable else 0.68
        posture = "near" if skimmable else "off"
        conf = 0.78

        rationale = (
            f"Remote analysis: spread {spread:.3f}%, secondary liquidity {sec_liq:.2f}. "
            f"{'Book looks artificially thin; secondary supports quoting.' if sec_liq > 0.65 else 'Insufficient confirmation.'}"
        )

        return AIAnalysis(
            edge_quality_score=edge_q,
            is_truly_skimmable=skimmable,
            suggested_min_edge_adjust_pct=adjust,
            toxicity_risk=risk,
            quote_posture=posture,
            confidence=conf,
            rationale=rationale + " [api-stub — replace with real LLM call]",
            source="api-llm"
        )

    def is_suitable_for_loop(self) -> bool:
        return False  # Too slow/expensive for per-cycle use
