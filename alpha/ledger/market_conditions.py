"""Market conditions snapshot for HUD — 1% depth and recommended entry sizes."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, TYPE_CHECKING

from alpha.decision.technical_analysis import TechnicalAnalysisSnapshot
from alpha.ledger.liquidity import depth_within_mid_band
from alpha.precision import DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS, price_decimals, round_rlusd_price
from alpha.types import LiquidityDepth, OrderBookSnapshot
from config.settings import BotConfig

if TYPE_CHECKING:
    from alpha.orders.types import BracketRecord

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


def _dca_grade(vs_mid_pct: Optional[float]) -> str:
    if vs_mid_pct is None:
        return "yellow"
    if vs_mid_pct >= 0.5:
        return "green"
    if vs_mid_pct <= -0.5:
        return "red"
    return "yellow"


def compute_bracket_dca(
    brackets: Iterable["BracketRecord"],
    *,
    mid: float,
    price_decimals: int = DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS,
) -> Dict[str, Any]:
    """Volume-weighted average entry for XRP in active brackets (open bag cost basis)."""
    from alpha.orders.types import BracketLifecycleState

    total_xrp = 0.0
    total_rlusd = 0.0
    lots = 0

    for record in brackets:
        if record.state != BracketLifecycleState.BRACKET_ACTIVE:
            continue
        entry = float(record.entry_price_rlusd_per_xrp or 0.0)
        if entry <= 0:
            continue
        size = float(record.bracketed_xrp or record.filled_xrp or 0.0)
        if size <= 0:
            continue
        total_xrp += size
        total_rlusd += size * entry
        lots += 1

    if total_xrp <= 0:
        return {
            "avg_entry_rlusd_per_xrp": None,
            "total_xrp": 0.0,
            "position_count": 0,
            "vs_mid_pct": None,
            "grade": "yellow",
        }

    avg_entry = total_rlusd / total_xrp
    vs_mid_pct: Optional[float] = None
    if mid > 0:
        vs_mid_pct = (mid - avg_entry) / avg_entry * 100.0

    return {
        "avg_entry_rlusd_per_xrp": round_rlusd_price(avg_entry, price_decimals),
        "total_xrp": round(total_xrp, 4),
        "position_count": lots,
        "vs_mid_pct": round(vs_mid_pct, 3) if vs_mid_pct is not None else None,
        "grade": _dca_grade(vs_mid_pct),
    }


def refresh_dca_vs_mid(market_conditions: Dict[str, Any], mid: float) -> None:
    """Update DCA vs-mid after a live book quote patch."""
    dca = market_conditions.get("dca")
    if not isinstance(dca, dict):
        return
    avg = dca.get("avg_entry_rlusd_per_xrp")
    if avg is None or mid <= 0:
        return
    vs_mid_pct = (mid - float(avg)) / float(avg) * 100.0
    dca["vs_mid_pct"] = round(vs_mid_pct, 3)
    dca["grade"] = _dca_grade(vs_mid_pct)


def count_filled_trades(log_dir: Path = Path("logs")) -> Dict[str, int]:
    """Count taxable BUY/SELL fill rows across all monthly trade CSVs."""
    purchases = 0
    sells = 0
    if not log_dir.is_dir():
        return {"purchase_fills": 0, "sell_fills": 0}
    for path in sorted(log_dir.glob("trades_*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    event = str(row.get("event_type") or "").strip().upper()
                    if event == "BUY":
                        purchases += 1
                    elif event == "SELL":
                        sells += 1
        except OSError:
            continue
    return {"purchase_fills": purchases, "sell_fills": sells}


def compute_open_order_counts(brackets: Iterable["BracketRecord"]) -> Dict[str, int]:
    """Open purchase (pending buy) and sell (TP/SL legs on book) order counts."""
    from alpha.orders.types import BracketLifecycleState

    open_buys = 0
    open_sells = 0
    for record in brackets:
        if record.state == BracketLifecycleState.PENDING_BUY:
            open_buys += 1
            continue
        if record.state != BracketLifecycleState.BRACKET_ACTIVE:
            continue
        for leg in (record.tp_leg, record.sl_leg):
            if leg is not None and leg.sequence is not None and leg.remaining_xrp > 0:
                open_sells += 1
    return {"open_purchases": open_buys, "open_sells": open_sells}


def compute_order_counts(
    brackets: Iterable["BracketRecord"],
    *,
    log_dir: Path = Path("logs"),
) -> Dict[str, Any]:
    """Filled trade totals (tax CSV) plus open bracket orders."""
    filled = count_filled_trades(log_dir)
    open_counts = compute_open_order_counts(brackets)
    return {
        **filled,
        **open_counts,
    }


def build_market_conditions(
    *,
    book: Optional[OrderBookSnapshot],
    liquidity: Optional[LiquidityDepth],
    config: BotConfig,
    portfolio_xrp_equiv: float,
    ta: Optional[TechnicalAnalysisSnapshot],
    brackets: Optional[Iterable["BracketRecord"]] = None,
    log_dir: Path = Path("logs"),
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

    dca = compute_bracket_dca(
        brackets or [],
        mid=mid_f,
        price_decimals=price_decimals(config),
    )
    order_counts = compute_order_counts(brackets or [], log_dir=log_dir)

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
        "price_decimals": price_decimals(config),
        "overall_grade": overall,
        "dca": dca,
        "order_counts": order_counts,
    }
