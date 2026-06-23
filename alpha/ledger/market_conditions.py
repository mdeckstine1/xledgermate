"""Market conditions snapshot for HUD — 1% depth and recommended entry sizes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
from alpha.ledger.liquidity import depth_within_mid_band
from alpha.types import LiquidityDepth, OrderBookSnapshot
from config.settings import BotConfig

# HUD card: XRP depth within this % band around mid.
HUD_DEPTH_MID_BAND_PCT = 1.0


def _liquidity_grade(*, depth_xrp: float, min_size: float, base_size: float) -> str:
    if depth_xrp < min_size:
        return "red"
    if depth_xrp < base_size:
        return "yellow"
    return "green"


def _recommended_cap(
    *,
    depth_xrp: float,
    config: BotConfig,
    portfolio_xrp_equiv: float,
    mid: float,
) -> float:
    """Mirror DecisionEngine depth/risk/leg caps (without inventory balance cap)."""
    min_size = config.min_order_size_xrp
    if depth_xrp < min_size or mid <= 0:
        return 0.0
    capital_xrp = config.effective_risk_capital_xrp(mid)
    leg_cap = capital_xrp * config.max_leg_size_pct_of_capital
    risk_cap = 0.0
    if portfolio_xrp_equiv > 0 and config.alpha_risk_per_trade_pct > 0:
        risk_cap = portfolio_xrp_equiv * (config.alpha_risk_per_trade_pct / 100.0)
    caps = [depth_xrp, leg_cap]
    if risk_cap > 0:
        caps.append(risk_cap)
    capped = min(c for c in caps if c > 0)
    return round(capped, 4) if capped >= min_size else 0.0


def build_market_conditions(
    *,
    book: Optional[OrderBookSnapshot],
    liquidity: Optional[LiquidityDepth],
    config: BotConfig,
    portfolio_xrp_equiv: float,
    ta: Optional[TechnicalAnalysisSnapshot],
) -> Dict[str, Any]:
    """Serialize live market conditions for the operator HUD."""
    mid = book.mid if book and book.mid else (liquidity.mid if liquidity else None)
    spread_pct = book.spread_pct if book and book.spread_pct is not None else (
        liquidity.spread_pct if liquidity else None
    )
    mid_f = float(mid) if mid and mid > 0 else 0.0

    bid_depth_1pct = 0.0
    ask_depth_1pct = 0.0
    if book is not None and mid_f > 0:
        bid_depth_1pct = depth_within_mid_band(
            book.bids, side="bid", mid=mid_f, band_pct=HUD_DEPTH_MID_BAND_PCT
        )
        ask_depth_1pct = depth_within_mid_band(
            book.asks, side="ask", mid=mid_f, band_pct=HUD_DEPTH_MID_BAND_PCT
        )

    min_size = config.min_order_size_xrp
    base_size = config.alpha_base_order_size_xrp
    bid_grade = _liquidity_grade(depth_xrp=bid_depth_1pct, min_size=min_size, base_size=base_size)
    ask_grade = _liquidity_grade(depth_xrp=ask_depth_1pct, min_size=min_size, base_size=base_size)

    liquidity_health = "green"
    if bid_grade == "red" or ask_grade == "red":
        liquidity_health = "red"
    elif bid_grade == "yellow" or ask_grade == "yellow":
        liquidity_health = "yellow"

    max_buy = _recommended_cap(
        depth_xrp=ask_depth_1pct,
        config=config,
        portfolio_xrp_equiv=portfolio_xrp_equiv,
        mid=mid_f,
    )
    max_sell = _recommended_cap(
        depth_xrp=bid_depth_1pct,
        config=config,
        portfolio_xrp_equiv=portfolio_xrp_equiv,
        mid=mid_f,
    )

    spread_grade = "green"
    if spread_pct is not None:
        if spread_pct > config.alpha_min_edge_threshold_pct * 2:
            spread_grade = "green"
        elif spread_pct >= config.alpha_min_edge_threshold_pct:
            spread_grade = "yellow"
        else:
            spread_grade = "red"

    ta_enabled = bool(ta and ta.enabled)
    ta_summary = {
        "enabled": ta_enabled,
        "buy_score": round(ta.buy_score, 2) if ta_enabled else None,
        "sell_score": round(ta.sell_score, 2) if ta_enabled else None,
        "bias": ta.bias if ta_enabled else None,
    }

    overall = "green"
    if bid_grade == "red" or ask_grade == "red" or spread_grade == "red":
        overall = "red"
    elif bid_grade == "yellow" or ask_grade == "yellow" or spread_grade == "yellow":
        overall = "yellow"

    return {
        "mid": mid,
        "spread_pct": spread_pct,
        "spread_grade": spread_grade,
        "depth_mid_band_pct": HUD_DEPTH_MID_BAND_PCT,
        "bid_depth_xrp": round(bid_depth_1pct, 2),
        "ask_depth_xrp": round(ask_depth_1pct, 2),
        "bid_depth_grade": bid_grade,
        "ask_depth_grade": ask_grade,
        "liquidity_health": liquidity_health,
        "recommended_max_buy_xrp": max_buy,
        "recommended_max_sell_xrp": max_sell,
        "ta": ta_summary,
        "cycle_interval_seconds": int(config.alpha_cycle_interval_seconds),
        "overall_grade": overall,
    }
