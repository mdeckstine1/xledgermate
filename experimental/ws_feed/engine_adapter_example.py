#!/usr/bin/env python3
"""
WS book feed adapter — thin wrapper over PureQuotePath.

Future trading_engine integration point. No profiles, no sacred hard gates.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from experimental.ws_feed.book_feed import BookFeed
from experimental.ws_feed.pure_quote_path import PureQuotePath, PureQuoteDecision, WS_AS_VERSION
from strategy.fill_quality import FillQualityState


class WSBookFeedAdapter:
    """Engine-facing adapter: WS book + pure A-S decision."""

    def __init__(
        self,
        book_feed: BookFeed,
        gamma: float = 0.35,
        kappa: float = 3.5,
        *,
        configured_l1_xrp: float = 150.0,
        min_order_size_xrp: float = 1.0,
        balance_fraction_k: float = 0.07,
        order_levels: int = 3,
        level_spread_increment: float = 0.0003,
        configured_order_sizes: Optional[tuple] = None,
    ):
        self.book_feed = book_feed
        self.path = PureQuotePath(
            gamma=gamma,
            kappa=kappa,
            configured_l1_xrp=configured_l1_xrp,
            min_order_size_xrp=min_order_size_xrp,
            balance_fraction_k=balance_fraction_k,
            order_levels=order_levels,
            level_spread_increment=level_spread_increment,
            configured_order_sizes=configured_order_sizes,
        )

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
        volatility_pct: Optional[float] = None,
        ws_book_age_s: Optional[float] = None,
        competitor_intel: Optional[Dict[str, Any]] = None,
        inventory_skew_override: Optional[float] = None,
        ai_analyzer: Optional[Any] = None,
        intel_ai_enabled: bool = True,
        book_state_for_ai: Optional[Dict[str, Any]] = None,
        fill_quality: Optional[FillQualityState] = None,
        inventory_max_deviation: float = 0.12,
        inventory_mode: str = "market_make",
        xrp_reserve: float = 12.0,
        inventory_overshoot_slack: float = 0.03,
        g2_enabled: bool = True,
        g4_enabled: bool = True,
        competitor_pressure_enabled: bool = True,
        session_buy_capture_xrp: Optional[float] = None,
        session_sell_capture_xrp: Optional[float] = None,
        recent_fill_records: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        book_age = ws_book_age_s
        if book_age is None and hasattr(self.book_feed, "age_seconds"):
            book_age = self.book_feed.age_seconds()
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
            ws_book_age_s=float(book_age or 0.0),
            fill_quality=fill_quality,
            inventory_max_deviation=inventory_max_deviation,
            inventory_mode=inventory_mode,
            xrp_reserve=xrp_reserve,
            inventory_overshoot_slack=inventory_overshoot_slack,
            g2_enabled=g2_enabled,
            g4_enabled=g4_enabled,
            competitor_pressure_enabled=competitor_pressure_enabled,
            session_buy_capture_xrp=session_buy_capture_xrp,
            session_sell_capture_xrp=session_sell_capture_xrp,
            recent_fill_records=recent_fill_records,
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
        "zero_quote_operator_note": decision.zero_quote_operator_note,
        "tight_book_note": decision.tight_book_note,
        "as_reservation": decision.as_reservation,
        "as_optimal_spread_pct": decision.as_optimal_spread_pct,
        "as_gamma": decision.as_gamma,
        "as_kappa": decision.as_kappa,
        "as_mode": decision.as_mode,
        "ws_as_version": decision.path_version,
        "competitor_pressure": decision.competitor_pressure,
        "inventory_label": decision.inventory_label,
        "qd_bid_allowed": decision.qd_bid_allowed,
        "qd_ask_allowed": decision.qd_ask_allowed,
        "inventory_limits_summary": decision.inventory_limits_summary,
        "suggested_bid": decision.suggested_bid,
        "suggested_ask": decision.suggested_ask,
        "ws_book_age_s": decision.ws_book_age_s if decision.ws_book_age_s else ws_age,
        "book_age_rationale": decision.book_age_rationale,
        "base_volatility_pct": decision.base_volatility_pct,
        "book_spread_pct": decision.book_spread_pct,
        "volatility_pct": decision.volatility_pct,
        "ai_edge_quality": decision.ai_edge_quality,
        "ai_is_skimmable": decision.ai_is_skimmable,
        "ai_rationale": decision.ai_rationale,
        "ai_suggested_posture": decision.ai_suggested_posture,
        "bid_size": decision.bid_size,
        "ask_size": decision.ask_size,
        "l1_xrp": decision.l1_xrp,
        "pure_as_size_rationale": decision.size_rationale,
        "quote_intents": list(decision.quote_intents),
        "g2_size_mult": decision.g2_size_mult,
        "g2_spread_mult": decision.g2_spread_mult,
        "g2_grade": decision.g2_grade,
        "g2_active": decision.g2_active,
        "g2_summary": decision.g2_summary,
        "g4_size_mult": decision.g4_size_mult,
        "g4_bid_size_mult": decision.g4_bid_size_mult,
        "g4_ask_size_mult": decision.g4_ask_size_mult,
        "g4_grade": decision.g4_grade,
        "g4_active": decision.g4_active,
        "g4_summary": decision.g4_summary,
        "g4_peer_lane_count": decision.g4_peer_lane_count,
        "g4_peer_pressure": decision.g4_peer_pressure,
        "inside_l1": decision.inside_l1,
        "reservation_to_bbo_delta_bps": decision.reservation_to_bbo_delta_bps,
        "effective_quote_age_at_fill_seconds": decision.effective_quote_age_at_fill_seconds,
        "g7_summary": decision.g7_summary,
        "bid_touch_backoff_bps": decision.bid_touch_backoff_bps,
        "ask_touch_backoff_bps": decision.ask_touch_backoff_bps,
        "g7_bid_role": decision.g7_bid_role,
        "g7_ask_role": decision.g7_ask_role,
        "g7_solo_acquisition": decision.g7_solo_acquisition,
        "g7_ask_sell_defense": decision.g7_ask_sell_defense,
        "g7_scaler_label": decision.g7_scaler_label,
        "g2_scaler_label": decision.g2_scaler_label,
        "execution_brakes_summary": decision.execution_brakes_summary,
        "qd_intent": decision.qd_intent,
        "qd_bid_allowed": decision.qd_bid_allowed,
        "qd_ask_allowed": decision.qd_ask_allowed,
        "qd_would_quote": decision.qd_would_quote,
        "qd_layer_summary": decision.qd_layer_summary,
        "qd_bid_implied_bps": decision.qd_bid_implied_bps,
        "qd_ask_implied_bps": decision.qd_ask_implied_bps,
        "qd_bid_block_reason": decision.qd_bid_block_reason,
        "qd_ask_block_reason": decision.qd_ask_block_reason,
        "qd_bid_size_mult": decision.qd_bid_size_mult,
        "qd_ask_size_mult": decision.qd_ask_size_mult,
    }


__all__ = ["WSBookFeedAdapter", "WS_AS_VERSION"]
