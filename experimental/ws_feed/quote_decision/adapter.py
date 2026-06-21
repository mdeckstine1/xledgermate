"""
Thin integration adapter — maps pure_quote_path / engine inputs to the layered stack.

Convergence (Ashigaru-Shoshin):
  Canonical layer logic lives in strategy/quote_decision_layers/ (sacred engine +
  test_strategy_quote_decision_layers.py). This package keeps the stable WS public
  API (compute_quoting_decision, run_quote_decision_pipeline, QuotingDecision) and
  translates CycleQuoteInputs ↔ strategy params via _strategy_bridge.py.

  WS-only concerns handled here: reservation_allows_bid/ask (A-S reservation guard).
  Solo spread-capture edge gate + side-local markout bleed run through strategy layers.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from experimental.ws_feed.quote_decision.pipeline import run_quote_decision_pipeline
from experimental.ws_feed.quote_decision.types import CycleQuoteInputs, QuotingDecision

try:
    from strategy.fill_quality import FillQualityState
except ImportError:  # pragma: no cover
    FillQualityState = Any  # type: ignore[misc, assignment]


def _portfolio_xrp_ratio(
    *,
    xrp_balance: float,
    rlusd_balance: float,
    mid: float,
) -> float:
    if mid <= 0:
        return 0.5
    total = xrp_balance + rlusd_balance / mid
    return xrp_balance / total if total > 0 else 0.5


def _split_recent_fills(
    records: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Dict[str, Any], ...], tuple[Dict[str, Any], ...]]:
    buys: list[Dict[str, Any]] = []
    sells: list[Dict[str, Any]] = []
    for row in records:
        item = dict(row)
        side = str(item.get("side") or "").upper()
        if side == "BUY":
            buys.append(item)
        elif side == "SELL":
            sells.append(item)
    return tuple(buys), tuple(sells)


def build_cycle_inputs(
    *,
    mid: float,
    best_bid: float,
    best_ask: float,
    l1_bid_price: float,
    l1_ask_price: float,
    xrp_balance: float,
    rlusd_balance: float,
    target_xrp_ratio: float,
    inventory_label: str,
    peer_lane_empty: bool,
    peer_lane_count: int = 0,
    toxic_ratio_30s: float = 0.0,
    g2_spread_mult: float = 1.0,
    g2_grade: str = "",
    session_buy_capture_xrp: Optional[float] = None,
    session_sell_capture_xrp: Optional[float] = None,
    recent_fills: Optional[Sequence[Mapping[str, Any]]] = None,
    reservation_allows_bid: bool = True,
    reservation_allows_ask: bool = True,
    fill_quality: Optional[FillQualityState] = None,
    market_condition: str = "favorable",
    mid_momentum_pct: float = 0.0,
    min_edge_pct: float = 0.0,
    market_edge_met: bool = True,
    inventory_max_deviation: float = 0.12,
    inventory_mode: str = "market_make",
    acquiring_rlusd: bool = False,
    mm_mode: bool = True,
    momentum_pause_vulnerable: bool = False,
    low_book_pressure: bool = False,
    peer_intel_present: bool = False,
    bid_half_spread_pct: Optional[float] = None,
    ask_half_spread_pct: Optional[float] = None,
) -> CycleQuoteInputs:
    ratio = _portfolio_xrp_ratio(
        xrp_balance=xrp_balance,
        rlusd_balance=rlusd_balance,
        mid=mid,
    )
    buys, sells = _split_recent_fills(recent_fills or ())
    return CycleQuoteInputs(
        mid=mid,
        best_bid=best_bid,
        best_ask=best_ask,
        l1_bid_price=l1_bid_price,
        l1_ask_price=l1_ask_price,
        xrp_ratio=ratio,
        target_xrp_ratio=target_xrp_ratio,
        inventory_label=inventory_label,
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        toxic_ratio_30s=toxic_ratio_30s,
        g2_spread_mult=g2_spread_mult,
        g2_grade=g2_grade,
        session_buy_capture_xrp=session_buy_capture_xrp,
        session_sell_capture_xrp=session_sell_capture_xrp,
        recent_buys=buys,
        recent_sells=sells,
        reservation_allows_bid=reservation_allows_bid,
        reservation_allows_ask=reservation_allows_ask,
        fill_quality=fill_quality,
        market_condition=market_condition,
        mid_momentum_pct=mid_momentum_pct,
        min_edge_pct=min_edge_pct,
        market_edge_met=market_edge_met,
        inventory_max_deviation=inventory_max_deviation,
        inventory_mode=inventory_mode,
        acquiring_rlusd=acquiring_rlusd,
        mm_mode=mm_mode,
        momentum_pause_vulnerable=momentum_pause_vulnerable,
        low_book_pressure=low_book_pressure,
        peer_intel_present=peer_intel_present,
        bid_half_spread_pct=bid_half_spread_pct,
        ask_half_spread_pct=ask_half_spread_pct,
    )


def compute_quoting_decision(
    *,
    mid: float,
    best_bid: float,
    best_ask: float,
    l1_bid_price: float,
    l1_ask_price: float,
    xrp_balance: float,
    rlusd_balance: float,
    target_xrp_ratio: float,
    inventory_label: str,
    peer_lane_empty: bool,
    peer_lane_count: int = 0,
    toxic_ratio_30s: float = 0.0,
    g2_spread_mult: float = 1.0,
    g2_grade: str = "",
    session_buy_capture_xrp: Optional[float] = None,
    session_sell_capture_xrp: Optional[float] = None,
    recent_fills: Optional[Sequence[Mapping[str, Any]]] = None,
    reservation_allows_bid: bool = True,
    reservation_allows_ask: bool = True,
    fill_quality: Optional[FillQualityState] = None,
    market_condition: str = "favorable",
    mid_momentum_pct: float = 0.0,
    min_edge_pct: float = 0.0,
    market_edge_met: bool = True,
    inventory_max_deviation: float = 0.12,
    inventory_mode: str = "market_make",
    acquiring_rlusd: bool = False,
    mm_mode: bool = True,
    momentum_pause_vulnerable: bool = False,
    low_book_pressure: bool = False,
    peer_intel_present: bool = False,
    bid_half_spread_pct: Optional[float] = None,
    ask_half_spread_pct: Optional[float] = None,
) -> QuotingDecision:
    """Public integration entry — call from pure_quote_path after G7 touch prices."""
    inputs = build_cycle_inputs(
        mid=mid,
        best_bid=best_bid,
        best_ask=best_ask,
        l1_bid_price=l1_bid_price,
        l1_ask_price=l1_ask_price,
        xrp_balance=xrp_balance,
        rlusd_balance=rlusd_balance,
        target_xrp_ratio=target_xrp_ratio,
        inventory_label=inventory_label,
        peer_lane_empty=peer_lane_empty,
        peer_lane_count=peer_lane_count,
        toxic_ratio_30s=toxic_ratio_30s,
        g2_spread_mult=g2_spread_mult,
        g2_grade=g2_grade,
        session_buy_capture_xrp=session_buy_capture_xrp,
        session_sell_capture_xrp=session_sell_capture_xrp,
        recent_fills=recent_fills,
        reservation_allows_bid=reservation_allows_bid,
        reservation_allows_ask=reservation_allows_ask,
        fill_quality=fill_quality,
        market_condition=market_condition,
        mid_momentum_pct=mid_momentum_pct,
        min_edge_pct=min_edge_pct,
        market_edge_met=market_edge_met,
        inventory_max_deviation=inventory_max_deviation,
        inventory_mode=inventory_mode,
        acquiring_rlusd=acquiring_rlusd,
        mm_mode=mm_mode,
        momentum_pause_vulnerable=momentum_pause_vulnerable,
        low_book_pressure=low_book_pressure,
        peer_intel_present=peer_intel_present,
        bid_half_spread_pct=bid_half_spread_pct,
        ask_half_spread_pct=ask_half_spread_pct,
    )
    return run_quote_decision_pipeline(inputs)


def shadow_compare_legacy(
    qd: QuotingDecision,
    *,
    legacy_pause_bids: bool,
    legacy_pause_asks: bool,
    legacy_would_quote: bool,
) -> Dict[str, Any]:
    """Log-friendly diff for Phase 0 soak — detect conflicts before cutover."""
    conflicts: list[str] = []
    legacy_bid_allowed = not legacy_pause_bids
    legacy_ask_allowed = not legacy_pause_asks
    if qd.bid.allowed != legacy_bid_allowed:
        conflicts.append(
            f"bid: QD allowed={qd.bid.allowed} legacy={legacy_bid_allowed}"
        )
    if qd.ask.allowed != legacy_ask_allowed:
        conflicts.append(
            f"ask: QD allowed={qd.ask.allowed} legacy={legacy_ask_allowed}"
        )
    if qd.would_quote != legacy_would_quote:
        conflicts.append(
            f"would_quote QD={qd.would_quote} legacy={legacy_would_quote}"
        )
    return {
        "quote_decision_conflicts": conflicts,
        "quote_decision_shadow": qd.to_legacy_flags(),
    }


__all__ = [
    "build_cycle_inputs",
    "compute_quoting_decision",
    "shadow_compare_legacy",
]
