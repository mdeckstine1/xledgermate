"""
Internal bridge: CycleQuoteInputs → strategy/quote_decision_layers → QuotingDecision.

Canonical layer logic lives in strategy/quote_decision_layers/ (sacred path + tests).
This module only translates I/O shapes and WS-only guards (reservation).
"""

from __future__ import annotations

from strategy.fill_quality import FillQualityState
from strategy.quote_decision_layers.bleed import apply_bleed_protection
from strategy.quote_decision_layers.edge import evaluate_side_edge, min_net_edge_pct
from strategy.quote_decision_layers.intent import select_intent
from strategy.quote_decision_layers.pipeline import run_layered_quote_decision
from strategy.quote_decision_layers.types import (
    LayerQuotingDecision,
    QuoteIntent as StrategyQuoteIntent,
)
from experimental.ws_feed.quote_decision.types import (
    BookMode,
    BookPosture,
    CycleQuoteInputs,
    DriftBand,
    EdgeViability,
    InventoryDrift,
    LayerTrace,
    PostureSnapshot,
    QuotingDecision,
    QuoteIntent,
    SideFillQuality,
    SidePermission,
)


def _pct_to_bps(pct: float) -> float:
    return pct * 100.0


def _edge_half_spreads(inputs: CycleQuoteInputs) -> tuple[float, float, float]:
    """
    Spread inputs for L3 edge evaluation.

    Production (pure_quote_path) passes AS optimal half-spreads — same as sacred
    build_quote_adjustments. When omitted, derive from G7 touch L1 prices (tests).
    """
    mid = float(inputs.mid)
    if mid <= 0:
        return 0.0, 0.0, 0.0
    book_spread_pct = (float(inputs.best_ask) - float(inputs.best_bid)) / mid * 100.0
    if inputs.bid_half_spread_pct is not None and inputs.ask_half_spread_pct is not None:
        return (
            book_spread_pct,
            max(0.0, float(inputs.bid_half_spread_pct)),
            max(0.0, float(inputs.ask_half_spread_pct)),
        )
    bid_half = max(0.0, (mid - float(inputs.l1_bid_price)) / mid * 100.0)
    ask_half = max(0.0, (float(inputs.l1_ask_price) - mid) / mid * 100.0)
    return book_spread_pct, bid_half, ask_half


def _spread_pcts(inputs: CycleQuoteInputs) -> tuple[float, float, float]:
    return _edge_half_spreads(inputs)


def _resolve_fill_quality(inputs: CycleQuoteInputs) -> FillQualityState:
    if inputs.fill_quality is not None:
        return inputs.fill_quality
    return FillQualityState()


def _strategy_intent_to_ws(intent: StrategyQuoteIntent) -> QuoteIntent:
    try:
        return QuoteIntent(intent.value)
    except ValueError:
        return QuoteIntent.PATIENT_SOLO


def _edge_to_ws(
    edge,
    *,
    book_mode: BookMode,
) -> EdgeViability:
    return EdgeViability(
        implied_edge_bps=_pct_to_bps(edge.implied_edge_pct),
        min_edge_bps=_pct_to_bps(edge.min_edge_pct),
        viable=edge.viable,
        reason=edge.reason,
    )


def _side_to_ws(perm) -> SidePermission:
    return SidePermission(
        allowed=perm.allowed,
        size_mult=perm.size_mult,
        implied_edge_bps=_pct_to_bps(perm.implied_edge_pct),
        block_reason=perm.block_reason,
        pause_cause=str(getattr(perm, "pause_cause", "") or ""),
    )


def _apply_reservation(
    perm: SidePermission,
    *,
    reservation_ok: bool,
) -> SidePermission:
    if perm.allowed and not reservation_ok:
        return SidePermission(
            allowed=False,
            size_mult=0.0,
            implied_edge_bps=perm.implied_edge_bps,
            block_reason="reservation_blocks_side",
        )
    return perm


def _posture_snapshot(layer: LayerQuotingDecision, inputs: CycleQuoteInputs) -> PostureSnapshot:
    p = layer.posture
    return PostureSnapshot(
        book=BookPosture(
            solo=p.book.solo,
            peer_lane_count=p.book.peer_lane_count,
            mode=BookMode(p.book.mode.value),
        ),
        inventory=InventoryDrift(
            xrp_ratio=p.inventory.xrp_ratio,
            target_xrp_ratio=p.inventory.target_xrp_ratio,
            deviation=p.inventory.deviation,
            label=p.inventory.label,
            band=DriftBand(p.inventory.band.value),
        ),
        buy_quality=SideFillQuality(
            fill_count=p.buy_quality.fill_count,
            session_capture_xrp=float(inputs.session_buy_capture_xrp or 0.0),
            recent_capture_xrp=0.0,
            avg_edge_bps=(
                _pct_to_bps(p.buy_quality.mean_markout_30s_pct)
                if p.buy_quality.fill_count > 0
                else None
            ),
            bleeding=p.buy_quality.bleeding,
            bleed_reason=p.buy_quality.bleed_reason,
        ),
        sell_quality=SideFillQuality(
            fill_count=p.sell_quality.fill_count,
            session_capture_xrp=float(inputs.session_sell_capture_xrp or 0.0),
            recent_capture_xrp=0.0,
            avg_edge_bps=(
                _pct_to_bps(p.sell_quality.mean_markout_30s_pct)
                if p.sell_quality.fill_count > 0
                else None
            ),
            bleeding=p.sell_quality.bleeding,
            bleed_reason=p.sell_quality.bleed_reason,
        ),
        toxic_ratio_30s=float(inputs.toxic_ratio_30s or 0.0),
        g2_spread_mult=float(inputs.g2_spread_mult or 1.0),
        g2_grade=(inputs.g2_grade or "").strip().lower(),
    )


def run_strategy_layers(inputs: CycleQuoteInputs) -> LayerQuotingDecision:
    """Execute canonical strategy stack from WS cycle inputs."""
    book_spread_pct, bid_half, ask_half = _spread_pcts(inputs)
    fill_quality = _resolve_fill_quality(inputs)

    return run_layered_quote_decision(
        xrp_ratio=float(inputs.xrp_ratio),
        inventory_label=(inputs.inventory_label or "balanced").strip().lower(),
        fill_quality=fill_quality,
        target_xrp_ratio=float(inputs.target_xrp_ratio),
        market_condition=inputs.market_condition,
        mid_momentum_pct=float(inputs.mid_momentum_pct),
        book_spread_pct=book_spread_pct,
        bid_half_spread_pct=bid_half,
        ask_half_spread_pct=ask_half,
        min_edge_pct=float(inputs.min_edge_pct),
        market_edge_met=bool(inputs.market_edge_met),
        solo_edge_mult=float(inputs.solo_edge_mult),
        solo_edge_absolute_floor_pct=float(inputs.solo_edge_absolute_floor_pct),
        inventory_max_deviation=float(inputs.inventory_max_deviation),
        inventory_mode=inputs.inventory_mode,
        acquiring_rlusd=bool(inputs.acquiring_rlusd),
        mm_mode=bool(inputs.mm_mode),
        momentum_pause_vulnerable=bool(inputs.momentum_pause_vulnerable),
        peer_lane_empty=bool(inputs.peer_lane_empty),
        peer_lane_count=int(inputs.peer_lane_count),
        low_book_pressure=bool(inputs.low_book_pressure),
        peer_intel_present=bool(inputs.peer_intel_present),
        ops_path="ws",
    )


def layer_to_quoting_decision(
    layer: LayerQuotingDecision,
    inputs: CycleQuoteInputs,
) -> QuotingDecision:
    """Map strategy LayerQuotingDecision → WS QuotingDecision (reservation applied)."""
    book_spread_pct, bid_half, ask_half = _spread_pcts(inputs)
    book_mode = BookMode(layer.posture.book.mode.value)

    bid_edge = evaluate_side_edge(
        side="bid",
        book_spread_pct=book_spread_pct,
        our_half_spread_pct=bid_half,
        profile_min_edge_pct=float(inputs.min_edge_pct),
        book_mode=layer.posture.book.mode,
        market_edge_met=bool(inputs.market_edge_met),
    )
    ask_edge = evaluate_side_edge(
        side="ask",
        book_spread_pct=book_spread_pct,
        our_half_spread_pct=ask_half,
        profile_min_edge_pct=float(inputs.min_edge_pct),
        book_mode=layer.posture.book.mode,
        market_edge_met=bool(inputs.market_edge_met),
    )
    intent_sel = select_intent(
        layer.posture,
        buy_edge_viable=bid_edge.viable,
        sell_edge_viable=ask_edge.viable,
    )
    bleed = apply_bleed_protection(layer.posture)

    bid = _apply_reservation(
        _side_to_ws(layer.bid),
        reservation_ok=bool(inputs.reservation_allows_bid),
    )
    ask = _apply_reservation(
        _side_to_ws(layer.ask),
        reservation_ok=bool(inputs.reservation_allows_ask),
    )

    would_quote = (bid.allowed and bid.size_mult > 0) or (
        ask.allowed and ask.size_mult > 0
    )

    trace = LayerTrace(
        intent=_strategy_intent_to_ws(layer.intent),
        intent_reason=intent_sel.reason,
        bid_edge=_edge_to_ws(bid_edge, book_mode=book_mode),
        ask_edge=_edge_to_ws(ask_edge, book_mode=book_mode),
        bid_bleed_note=bleed.bid_note,
        ask_bleed_note=bleed.ask_note,
    )

    return QuotingDecision(
        bid=bid,
        ask=ask,
        intent=_strategy_intent_to_ws(layer.intent),
        posture=_posture_snapshot(layer, inputs),
        trace=trace,
        summary=layer.summary,
        would_quote=would_quote,
        inventory_cb_mode=layer.inventory_cb_mode,
        inventory_cb_note=layer.inventory_cb_note,
        heavy_drift_l5_deferred=layer.heavy_drift_l5_deferred,
    )


__all__ = [
    "layer_to_quoting_decision",
    "min_net_edge_pct",
    "run_strategy_layers",
]
