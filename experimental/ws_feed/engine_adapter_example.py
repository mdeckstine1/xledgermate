#!/usr/bin/env python3
"""
Minimal adapter example showing how the main engine would consume the WS + pure A-S path.

This file lives in experimental/ only. It is documentation + a working sketch.
It demonstrates the clean surface the future trading_engine would use.

Key principle (user requirement):
"The WS version must have the same provable wiring we have in long run, but with the ws architecture.
When we make the switch we should have to replace what is running on the remote server with the ws version."

Pure A-S only: The Avellaneda-Stoikov strategy (reservation inside the book + optimal spread)
provides the protections. No additional hard gates or legacy heuristics.

We do NOT modify engine/trading_engine.py, core/, or any sacred long-run code.
All work here supports the eventual wholesale swap after Gate 2.

Usage sketch (for future):
    from experimental.ws_feed.engine_adapter_example import WSBookFeedAdapter
    adapter = WSBookFeedAdapter(config)
    book = adapter.get_current_book()
    decision = adapter.compute_pure_as_decision(book, inventory_state, ...)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from experimental.ws_feed.book_feed import BookFeed
from experimental.ws_feed.ws_book_feed import WsBookFeed
from strategy.avellaneda_strategy import AvellanedaStrategy
from strategy.quote_decision import assess_inventory, build_quote_adjustments
from core.perception import get_profile
from core.profile_edge import profile_min_edge_pct


class WSBookFeedAdapter:
    """
    Thin adapter that the main engine could use.

    Responsibilities in the committed pure A-S world:
    - Provide a fresh Book (via WS or fallback)
    - Run the *exact same* long-run wiring (assess_inventory + build_quote_adjustments)
    - Use pure A-S (reservation inside book) as the final presence/quoting decision
    - Return rich decision strings for logging/GUI parity + the A-S specific numbers
    """

    def __init__(self, book_feed: BookFeed, gamma: float = 0.35, kappa: float = 3.5):
        self.book_feed = book_feed
        self.as_strat = AvellanedaStrategy(None, gamma=gamma, kappa=kappa, T=1.0)
        self.profile_name = "tight_spread"  # or loaded from config

    def get_current_book(self) -> Dict[str, Any]:
        """Return normalized book. Engine calls this instead of direct BookOffers."""
        if hasattr(self.book_feed, "current_order_book"):
            return self.book_feed.current_order_book()
        return {"bids": [], "asks": []}

    def compute_pure_as_decision(
        self,
        mid: float,
        best_bid: float,
        best_ask: float,
        xrp_bal: float,
        rlusd_bal: float,
        target_ratio: float = 0.55,
        book_spread_pct: Optional[float] = None,
        volatility_pct: float = 0.5,
    ) -> Dict[str, Any]:
        """
        The core of the WS + pure A-S engine.

        Returns a dict that is compatible with what the current GUI/runtime expects
        plus the new pure A-S fields.
        """
        if book_spread_pct is None:
            book_spread_pct = ((best_ask - best_bid) / mid * 100.0) if mid else 0.1

        profile = get_profile(self.profile_name)
        min_edge = profile_min_edge_pct(profile)

        inv_state = assess_inventory(
            xrp_balance=xrp_bal,
            rlusd_balance=rlusd_bal,
            mid_price=mid,
            target_xrp_ratio=target_ratio,
            skew_strength=getattr(profile, "inventory_skew_strength", 1.0),
        )

        inv_skew = 0.0
        if "xrp_heavy" in inv_state.label:
            inv_skew = 0.30 if "slight" not in inv_state.label else 0.08
        elif "rlusd_heavy" in inv_state.label:
            inv_skew = -0.30 if "slight" not in inv_state.label else -0.08

        # Full long-run wiring for rich context strings (inventory, momentum, policy, etc.)
        assessment = _make_minimal_assessment(book_spread_pct)  # minimal stub so dynamic policy runs
        adj = build_quote_adjustments(
            profile=profile,
            assessment=assessment,
            inventory=inv_state,
            mid_momentum_pct=0.0,
            effective_spread_l1_pct=book_spread_pct / 2.0,
            book_spread_pct=book_spread_pct,
            depth_imbalance=0.0,
            min_edge_pct=min_edge,
            fill_quality=None,
            xrpl_fee_bps=2.0,
            fund_with_xrp_only=False,
            rlusd_balance=rlusd_bal,
            min_order_xrp=0.1,
            target_xrp_ratio=target_ratio,
            inventory_max_deviation=0.12,
            inventory_mode="market_make",
            toxic_off_touch_latched=False,
        )

        # Pure A-S
        as_quote = self.as_strat.compute_avellaneda_quote(
            mid_price=mid,
            inventory_skew=inv_skew,
            volatility_pct=volatility_pct,
            best_bid=best_bid,
            best_ask=best_ask,
            book_spread_pct=book_spread_pct,
            profile=profile,
        )

        # The only presence decision in the committed path:
        as_met = (as_quote.reservation_price > best_bid and as_quote.reservation_price < best_ask)

        note = (
            f"{adj.decision_summary} | "
            f"PURE A-S (built-in protection): reservation={as_quote.reservation_price:.6f} "
            f"spread={as_quote.optimal_spread_pct:.3f}% (gamma={self.as_strat.gamma}, kappa={self.as_strat.kappa})"
        )

        return {
            "market_edge_met": as_met,          # compatibility for existing GUI
            "would_quote": as_met,
            "quote_decision_summary": note,
            "as_reservation": as_quote.reservation_price,
            "as_optimal_spread_pct": as_quote.optimal_spread_pct,
            "as_gamma": self.as_strat.gamma,
            "as_kappa": self.as_strat.kappa,
            "as_mode": "pure",
            "ws_book_age_s": getattr(self.book_feed, "age_seconds", lambda: None)(),
            "inventory_label": inv_state.label,
            "pause_bids": adj.pause_bids,
            "pause_asks": adj.pause_asks,
            # The engine would then call order_manager with A-S prices instead of the old ladder
            "suggested_bid": as_quote.bid_price if as_met else None,
            "suggested_ask": as_quote.ask_price if as_met else None,
        }


def _make_minimal_assessment(book_spread_pct: float):
    """Stub so the rich dynamic policy / inventory / momentum strings still run."""
    from core.market_conditions import (
        CONDITION_FAVORABLE, CONDITION_NEUTRAL, CONDITION_DEFENSIVE, CONDITION_HOSTILE, MarketAssessment,
    )
    if book_spread_pct < 0.10:
        cond, health, label = CONDITION_FAVORABLE, 75, "favorable"
    elif book_spread_pct > 0.25:
        cond, health, label = CONDITION_HOSTILE, 25, "hostile"
    elif book_spread_pct > 0.18:
        cond, health, label = CONDITION_DEFENSIVE, 42, "defensive"
    else:
        cond, health, label = CONDITION_NEUTRAL, 60, "neutral"

    return MarketAssessment(
        condition=cond,
        condition_label=label,
        volatility_pct=0.0,
        volatility_level="low",
        liquidity_score=0.78,
        liquidity_level="high" if book_spread_pct < 0.15 else "moderate",
        book_spread_pct=book_spread_pct,
        book_spread_status="tight" if book_spread_pct <= 0.12 else "normal",
        health_score=health,
        recommended_profile="tight_spread",
        recommendation_reason=f"{label} live book",
        summary=f"{label} (health {health}) spread {book_spread_pct:.3f}%",
    )


# Example of what a future engine integration might look like (pseudo):
#
# if config.book_feed_mode == "ws":
#     ws_feed = WsBookFeed(...)
#     adapter = WSBookFeedAdapter(ws_feed, gamma=0.32, kappa=3.8)  # from calibration
# else:
#     adapter = HttpAdapter(...)
#
# book = adapter.get_current_book()
# decision = adapter.compute_pure_as_decision(...)
# if decision["would_quote"]:
#     # place orders using decision["suggested_bid"] etc.
#     # log decision["quote_decision_summary"]  (contains full wiring + PURE A-S line)
