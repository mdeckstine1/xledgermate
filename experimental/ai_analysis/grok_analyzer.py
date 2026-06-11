from __future__ import annotations

"""
GrokAIAnalyzer: real xAI Grok implementation of AIAnalyzer for the WS + pure A-S path.

When a valid --intel-ai-provider grok --intel-ai-key ... is passed to the tester,
this replaces the StubAIAnalyzer for per-sample analysis.

It reuses the same backend call pattern as the HUD's /analyze_competitor (for consistency),
but uses a micro-structure / edge-quality focused prompt suitable for the tight per-sample loop
(competitor pressure, current book freshness, inventory state, etc.).

Outputs AIAnalysis (which the tester can log / push to HUD Intelligence cards, and the
adapter can map to AIAdvisorySignal for vol/size adjustments — still advisory only).

Rate limit note: Real Grok calls are relatively slow/expensive. The tester should only use
this when explicitly configured with a key. For high-frequency per-sample, the stub (or a
local model) is still preferred. The on-demand "Analyze with AI" button in the HUD remains
the place for rich, one-off competitor address analysis.
"""

import json
from typing import Any, Dict, Optional

import requests

from experimental.ai_analysis.base import AIAnalyzer, AIAnalysis


class GrokAIAnalyzer(AIAnalyzer):
    """
    Pluggable real Grok analyzer.

    Usage:
        analyzer = GrokAIAnalyzer(api_key="xai-...", model="grok-3")
        result = await analyzer.analyze(book_state, run_context=ctx)
    """

    def __init__(self, api_key: str, model: str = "grok-3", timeout: int = 30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.endpoint = "https://api.x.ai/v1/chat/completions"

    def is_suitable_for_loop(self) -> bool:
        # Real API calls are not suitable for the tight per-sample loop by default.
        # Return False so callers can fall back or rate-limit.
        # You can override to True if you want every sample to hit Grok (not recommended).
        return False

    async def analyze(
        self,
        book_state: Dict[str, Any],
        secondary_data: Optional[Dict[str, Any]] = None,
        run_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> AIAnalysis:
        """
        Call real Grok with a prompt focused on current book edge quality + competitor pressure.
        Returns structured AIAnalysis.
        """
        bids = book_state.get("bids", []) or []
        asks = book_state.get("asks", []) or []
        age = book_state.get("age_s", 999.0)

        if not bids or not asks:
            return AIAnalysis(
                edge_quality_score=0.0,
                is_truly_skimmable=False,
                quote_posture="off",
                confidence=0.9,
                rationale="Empty book — no edge possible.",
                source=f"grok:{self.model}"
            )

        best_bid = max(b["price"] for b in bids)
        best_ask = min(a["price"] for a in asks)
        spread = (best_ask - best_bid) / ((best_bid + best_ask) / 2.0) * 100.0 if best_bid and best_ask else 0.0

        # Build compact context for the prompt
        comp_pressure = 0.5
        inv_label = "unknown"
        top_comps_summary = ""
        if run_context:
            comp_pressure = run_context.get("competitor_pressure", 0.5) or 0.5
            inv_label = run_context.get("inventory_label", "unknown")
            tops = run_context.get("top_competitors", [])[:3]
            if tops:
                top_comps_summary = ", ".join(
                    f"{c.get('account','?')[:8]}:{c.get('activity',0)}" for c in tops
                )

        # Current per-sample prompt (compact, for high-frequency use in the loop)
        current_prompt = (
            "You are an expert on-chain XRPL market-maker micro-structure analyst.\n"
            "Analyze the CURRENT live book state for a pure Avellaneda-Stoikov (A-S) market maker.\n"
            "Focus on: Is the current edge real or a data artifact? Skimmability right now?\n"
            "Most importantly: deeply read the competitors' observed behavior and identify specific holes or patterns we can exploit "
            "to win better queue positions, increase our realized skim (spread capture), and help fill the bag more effectively.\n\n"
            f"Live book: best_bid={best_bid:.6f}, best_ask={best_ask:.6f}, spread={spread:.3f}%, age={age:.1f}s\n"
            f"Competitor pressure (0=defensive/good to skim harder): {comp_pressure:.2f}\n"
            f"Inventory posture: {inv_label}\n"
            f"Top active competitors: {top_comps_summary or 'none profiled'}\n\n"
            "Return ONLY a single valid JSON object with exactly these keys (no extra text, no markdown):\n"
            "{\n"
            '  "edge_quality_score": <float 0.0-1.0>,\n'
            '  "is_truly_skimmable": <bool>,\n'
            '  "suggested_min_edge_adjust_pct": <float e.g. -0.02 or +0.01>,\n'
            '  "toxicity_risk": <float 0.0-1.0>,\n'
            '  "quote_posture": "off" | "near" | "at_touch" | "spread_mid",\n'
            '  "confidence": <float 0.0-1.0>,\n'
            '  "rationale": "<concise 1-2 sentence explanation>",\n'
            '  "competitor_strategy_summary": "<high-level read on what the visible competitors seem to be doing>",\n'
            '  "exploitable_holes": "<specific weaknesses or repeatable patterns we can exploit (e.g. they cancel one side aggressively after taking a fill)>",\n'
            '  "suggested_exploitative_tactics": "<concrete ways to take advantage right now — positioning, sizing, timing, queue jumping, stepping inside their levels, etc.>",\n'
            '  "expected_skim_impact": "<rough idea of how this could improve our spread capture or fill rate>",\n'
            '  "positioning_advice": "<best positions/levels/sides to fight for to win the book and increase long-term skim>"\n'
            "}\n"
            "Be aggressive about finding exploitable edges while staying realistic about toxicity risk. Be conservative on skimmable/edge_quality if the book is very fresh or pressure is high."
        )

        prompt = current_prompt

        # TODO (future - once we start live MM with this bot):
        # Build a much richer prompt for "winning strategies" analysis.
        # We can send:
        #   - Full top-of-book (multiple levels + sizes)
        #   - Recent book history (last N mids/spreads/ages from WS feed)
        #   - More complete competitor profiles (not just top 3)
        #   - Our own recent quote/fill outcomes + markouts
        #   - Recent successful "skim harder" periods (low pressure + good fills)
        #   - What the current pure A-S math is outputting (reservation, optimal spread)
        # Goal: Ask Grok to extract patterns of what behaviors (our own or observed competitors)
        # are actually winning right now, and suggest concrete posture/size/edge adjustments.
        #
        # Example future prompt skeleton:
        #   "Here is the current live book snapshot + last 30s of book updates + our recent fills + top competitors' current behavior.
        #    Analyze what 'winning' looks like right now (high fill rate + positive markout with acceptable toxicity).
        #    Return JSON with recommended quote_posture, size_mult, edge_adjust, and a short 'why this is winning' rationale."
        #
        # We can keep the current compact prompt for high-frequency per-sample use,
        # and only use the rich "winning strategies" version on demand or at lower frequency.

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.4,
            }

            resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()

            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            # Try to extract JSON
            content = content.strip()
            if content.startswith("```"):
                # strip possible markdown
                content = content.split("```", 2)[1] if "```" in content else content
                content = content.replace("json", "", 1).strip()

            data = json.loads(content)

            return AIAnalysis(
                edge_quality_score=float(data.get("edge_quality_score", 0.5)),
                is_truly_skimmable=bool(data.get("is_truly_skimmable", False)),
                suggested_min_edge_adjust_pct=float(data.get("suggested_min_edge_adjust_pct", 0.0)),
                toxicity_risk=float(data.get("toxicity_risk", 0.5)),
                quote_posture=str(data.get("quote_posture", "spread_mid")),
                confidence=float(data.get("confidence", 0.6)),
                rationale=str(data.get("rationale", "Grok analysis (no rationale)")),
                source=f"grok:{self.model}",
            )

        except Exception as e:
            # Graceful fallback — never break the decision loop
            return AIAnalysis(
                edge_quality_score=0.5,
                is_truly_skimmable=False,
                quote_posture="spread_mid",
                confidence=0.3,
                rationale=f"Grok call failed or unparsable ({type(e).__name__}). Falling back to neutral.",
                source=f"grok:{self.model}:error",
            )


# Convenience for the tester / adapter
def create_grok_analyzer_from_config(intel_ai_key: str, intel_ai_model: str) -> Optional[GrokAIAnalyzer]:
    if not intel_ai_key:
        return None
    return GrokAIAnalyzer(api_key=intel_ai_key, model=intel_ai_model or "grok-3")
