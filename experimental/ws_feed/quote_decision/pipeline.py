"""
Quote decision pipeline — WS entry point delegating to strategy/quote_decision_layers.

Core layer logic (solo edge gate, side-local bleed, intent, L5) is canonical in
strategy/quote_decision_layers/. This module orchestrates I/O translation only.
"""

from __future__ import annotations

from experimental.ws_feed.quote_decision._strategy_bridge import (
    layer_to_quoting_decision,
    run_strategy_layers,
)
from experimental.ws_feed.quote_decision.types import CycleQuoteInputs, QuotingDecision


def run_quote_decision_pipeline(inputs: CycleQuoteInputs) -> QuotingDecision:
    """
    Execute the full layered stack for one cycle.

    Flow (canonical in strategy/quote_decision_layers/):
      L1 posture (read-only)
      L3 edge preview (needed for L2 intent)
      L2 intent
      L4 bleed (side-local)
      L5 final permissions
    """
    layer = run_strategy_layers(inputs)
    return layer_to_quoting_decision(layer, inputs)


__all__ = ["run_quote_decision_pipeline"]
