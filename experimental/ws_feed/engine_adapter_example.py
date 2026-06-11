#!/usr/bin/env python3
"""
WS book feed adapter — thin wrapper over PureQuotePath.

Future trading_engine integration point. No profiles, no sacred hard gates.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from experimental.ws_feed.book_feed import BookFeed
from experimental.ws_feed.pure_quote_path import PureQuotePath, PureQuoteDecision, WS_AS_VERSION


class WSBookFeedAdapter:
    """Engine-facing adapter: WS book + pure A-S decision."""

    def __init__(self, book_feed: BookFeed, gamma: float = 0.35, kappa: float = 3.5):
        self.book_feed = book_feed
        self.path = PureQuotePath(gamma=gamma, kappa=kappa)

    def get_current_book(self) -> Dict[str, Any]:
        if hasattr(self.book_feed, "current_order_book"):
            return self.book_feed.current_order_book()
        return {"bids": [], "asks": []}

    async def compute_pure_as_decision(
        self,
        mid: float,
        best_bid: float,
        best_ask: float,
        xrp_bal: float,
        rlusd_bal: float,
        target_ratio: float = 0.55,
        book_spread_pct: Optional[float] = None,
        volatility_pct: float = 0.5,
        competitor_intel: Optional[Dict[str, Any]] = None,
        inventory_skew_override: Optional[float] = None,
        ai_analyzer: Optional[Any] = None,
        intel_ai_enabled: bool = True,
        book_state_for_ai: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        decision = await self.path.compute_decision(
            mid=mid,
            best_bid=best_bid,
            best_ask=best_ask,
            xrp_bal=xrp_bal,
            rlusd_bal=rlusd_bal,
            target_ratio=target_ratio,
            competitor_intel=competitor_intel,
            ai_analyzer=ai_analyzer,
            intel_ai_enabled=intel_ai_enabled,
            book_state_for_ai=book_state_for_ai,
            base_volatility_pct=volatility_pct,
        )
        if inventory_skew_override is not None:
            pass  # reserved for future override hook
        return _decision_to_engine_dict(decision, book_feed=self.book_feed)


def _decision_to_engine_dict(decision: PureQuoteDecision, *, book_feed: Optional[BookFeed] = None) -> Dict[str, Any]:
    ws_age = None
    if book_feed is not None and hasattr(book_feed, "age_seconds"):
        ws_age = book_feed.age_seconds()
    return {
        "market_edge_met": decision.would_quote,
        "would_quote": decision.would_quote,
        "quote_decision_summary": decision.quote_decision_summary,
        "quoting_policy_label": decision.quoting_policy_label,
        "zero_quote_reason": decision.zero_quote_reason,
        "zero_quote_detail": decision.zero_quote_detail,
        "as_reservation": decision.as_reservation,
        "as_optimal_spread_pct": decision.as_optimal_spread_pct,
        "as_gamma": decision.as_gamma,
        "as_kappa": decision.as_kappa,
        "as_mode": decision.as_mode,
        "ws_as_version": decision.path_version,
        "competitor_pressure": decision.competitor_pressure,
        "inventory_label": decision.inventory_label,
        "pause_bids": False,
        "pause_asks": False,
        "suggested_bid": decision.suggested_bid,
        "suggested_ask": decision.suggested_ask,
        "ws_book_age_s": ws_age,
        "book_spread_pct": decision.book_spread_pct,
        "volatility_pct": decision.volatility_pct,
        "ai_edge_quality": decision.ai_edge_quality,
        "ai_is_skimmable": decision.ai_is_skimmable,
        "ai_rationale": decision.ai_rationale,
        "ai_suggested_posture": decision.ai_suggested_posture,
    }


__all__ = ["WSBookFeedAdapter", "WS_AS_VERSION"]
