"""
Shared pure A-S would-quote logic for grokster, replay, and adapter.

Grok/xAI is intentionally NOT part of quoting decisions here — advisory and
competition research only until post-swap sign-off (see PURE_AS_CRITICAL_PATH.md).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from experimental.competitor_pressure import CompetitorPressure, apply_competitor_pressure
from strategy.avellaneda_strategy import AvellanedaStrategy


@dataclass(frozen=True)
class DecisionBookContext:
    cycle: int
    spread_frac: float
    inventory_skew: float
    mid: float
    best_bid: float
    best_ask: float


def parse_decision_context(line: str, default_mid: float = 1.09) -> Optional[DecisionBookContext]:
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return None
    cycle = int(d.get("cycle") or 0)
    reasons = " ".join(e.get("message", "") for e in d.get("events", []))
    mid = float(d.get("mid_rlusd_per_xrp") or default_mid)

    spread_m = re.search(r"Book L1 spread ([\d.]+)% \(bid ([\d.]+) ask ([\d.]+)\)", reasons)
    if spread_m:
        spread_frac = float(spread_m.group(1)) / 100.0
        bb = float(spread_m.group(2))
        ba = float(spread_m.group(3))
    else:
        spread_m2 = re.search(r"Book L1 spread ([\d.]+)%", reasons)
        spread_frac = float(spread_m2.group(1)) / 100.0 if spread_m2 else 0.001
        half = spread_frac / 2.0
        bb = mid * (1.0 - half)
        ba = mid * (1.0 + half)

    inv = 0.0
    lower = reasons.lower()
    if "xrp_heavy" in lower:
        inv = 0.30 if "slight" not in lower else 0.08
    elif "rlusd_heavy" in lower:
        inv = -0.30 if "slight" not in lower else -0.08

    return DecisionBookContext(
        cycle=cycle,
        spread_frac=spread_frac,
        inventory_skew=inv,
        mid=mid,
        best_bid=bb,
        best_ask=ba,
    )


def _reservation_inside_book(
    as_strat: AvellanedaStrategy,
    ctx: DecisionBookContext,
    *,
    volatility_pct: float,
    book_spread_frac: float,
    gamma_scale: float = 1.0,
    sacred_replay: bool = False,
) -> bool:
    base_gamma = as_strat.gamma
    as_strat.gamma = base_gamma * gamma_scale
    try:
        if sacred_replay:
            # Match grokster sacred-corpus heuristic (vol=0, legacy spread units).
            quote = as_strat.compute_avellaneda_quote(
                mid_price=ctx.mid,
                inventory_skew=ctx.inventory_skew,
                volatility_pct=0.0,
                book_spread_pct=book_spread_frac,
            )
        else:
            quote = as_strat.compute_avellaneda_quote(
                mid_price=ctx.mid,
                inventory_skew=ctx.inventory_skew,
                volatility_pct=volatility_pct,
                best_bid=ctx.best_bid,
                best_ask=ctx.best_ask,
                book_spread_pct=book_spread_frac * 100.0,
            )
    finally:
        as_strat.gamma = base_gamma

    if sacred_replay:
        half = max(ctx.spread_frac / 2.0, 0.0001)
        return abs(quote.reservation_price - ctx.mid) / half < 0.35

    if ctx.best_bid > 0 and ctx.best_ask > 0:
        return ctx.best_bid < quote.reservation_price < ctx.best_ask

    half = max(ctx.spread_frac / 2.0, 0.0001)
    return abs(quote.reservation_price - ctx.mid) / half < 0.35


def would_quote_pure(
    as_strat: AvellanedaStrategy,
    line: str,
    *,
    base_volatility_pct: Optional[float] = None,
    sacred_replay: bool = True,
) -> bool:
    ctx = parse_decision_context(line)
    if not ctx or ctx.cycle <= 0:
        return False
    vol = base_volatility_pct if base_volatility_pct is not None else max(0.5, ctx.spread_frac * 100.0 * 1.5)
    return _reservation_inside_book(
        as_strat,
        ctx,
        volatility_pct=vol,
        book_spread_frac=ctx.spread_frac,
        sacred_replay=sacred_replay,
    )


def would_quote_pure_with_pressure(
    as_strat: AvellanedaStrategy,
    line: str,
    pressure_value: float,
    *,
    base_volatility_pct: Optional[float] = None,
    sacred_replay: bool = True,
) -> bool:
    ctx = parse_decision_context(line)
    if not ctx or ctx.cycle <= 0:
        return False
    vol = base_volatility_pct if base_volatility_pct is not None else max(0.5, ctx.spread_frac * 100.0 * 1.5)
    obs_pct = ctx.spread_frac * 100.0
    pressure = CompetitorPressure(
        value=pressure_value,
        observed_l1_spread_pct=obs_pct,
        ask_pressure=pressure_value if ctx.inventory_skew > 0.15 else None,
        bid_pressure=pressure_value if ctx.inventory_skew < -0.15 else None,
    )
    adj = apply_competitor_pressure(
        pressure,
        base_volatility_pct=vol,
        base_book_spread_pct=obs_pct,
        inventory_skew=ctx.inventory_skew,
    )
    book_frac = ctx.spread_frac if sacred_replay else adj.book_spread_pct / 100.0
    vol_use = 0.0 if sacred_replay else adj.volatility_pct
    return _reservation_inside_book(
        as_strat,
        ctx,
        volatility_pct=vol_use,
        book_spread_frac=book_frac,
        gamma_scale=adj.gamma_scale,
        sacred_replay=sacred_replay,
    )


def make_would_quote_fn(
    as_strat: AvellanedaStrategy,
    mode: str = "pure",
    pressure_value: float = 0.25,
    *,
    sacred_replay: bool = True,
):
    """Factory for sacred_economics.compute_marginal_economics callbacks."""
    if mode == "pure":
        return lambda line: would_quote_pure(as_strat, line, sacred_replay=sacred_replay)
    if mode == "pressure":
        p = pressure_value
        return lambda line: would_quote_pure_with_pressure(
            as_strat, line, p, sacred_replay=sacred_replay
        )
    raise ValueError(f"unknown mode: {mode}")
