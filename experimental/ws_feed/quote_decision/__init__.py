"""
Layered quote decision stack — WS public API (v2.2.x).

Converged on strategy/quote_decision_layers/ as the single canonical implementation
(solo spread-capture edge gate, side-local markout bleed, peer-lane posture). This
package retains stable WS types and compute_quoting_decision(); see adapter.py and
_strategy_bridge.py for CycleQuoteInputs translation.

See docs/QUOTE_DECISION_LAYERS.md for architecture history.
"""

from experimental.ws_feed.quote_decision.adapter import (
    compute_quoting_decision,
    shadow_compare_legacy,
)
from experimental.ws_feed.quote_decision.pipeline import run_quote_decision_pipeline
from experimental.ws_feed.quote_decision.types import (
    QUOTE_DECISION_VERSION,
    QuotingDecision,
    QuoteIntent,
)

__all__ = [
    "QUOTE_DECISION_VERSION",
    "QuotingDecision",
    "QuoteIntent",
    "compute_quoting_decision",
    "run_quote_decision_pipeline",
    "shadow_compare_legacy",
]
