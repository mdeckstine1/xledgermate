"""
Pure WS + Avellaneda-Stoikov quote path (xledger-ws-as).

No trading profiles, no build_quote_adjustments, no min-edge hard gates.
Quoting guard: reservation strictly inside live best bid/ask.

Pressure + Grok are inputs only (vol, spread anchor, gamma scale, advisory notes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from experimental.competitor_pressure import apply_competitor_pressure, from_intel_dict
from experimental.ws_runtime_analysis import classify_zero_quote_reason
from strategy.avellaneda_strategy import AvellanedaStrategy, AvellanedaQuote
from strategy.quote_decision import assess_inventory

WS_AS_VERSION = "0.1.0"
DEFAULT_INVENTORY_SKEW_STRENGTH = 1.0
DEFAULT_MIN_SPREAD_FLOOR_PCT = 0.04


@dataclass
class PureQuoteDecision:
    would_quote: bool
    quote_count: int
    mid: float
    best_bid: float
    best_ask: float
    book_spread_pct: float
    inventory_label: str
    inventory_skew: float
    volatility_pct: float
    as_reservation: float
    as_optimal_spread_pct: float
    as_gamma: float
    as_kappa: float
    zero_quote_reason: str
    zero_quote_detail: str
    quote_decision_summary: str
    quoting_policy_label: str
    competitor_pressure: Optional[float] = None
    pressure_rationale: str = ""
    ai_edge_quality: float = 0.0
    ai_is_skimmable: bool = False
    ai_rationale: str = ""
    ai_suggested_posture: str = "off"
    suggested_bid: Optional[float] = None
    suggested_ask: Optional[float] = None
    bid_size: float = 0.0
    ask_size: float = 0.0
    as_mode: str = "pure"
    path_version: str = WS_AS_VERSION

    def to_runtime_dict(self, *, competitor_intel: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "mid_price": self.mid,
            "best_bid_rlusd_per_xrp": self.best_bid,
            "best_ask_rlusd_per_xrp": self.best_ask,
            "book_spread_pct": self.book_spread_pct,
            "volatility_pct": self.volatility_pct,
            "inventory_label": self.inventory_label,
            "quote_decision_summary": self.quote_decision_summary,
            "quoting_policy_label": self.quoting_policy_label,
            "market_edge_met": self.would_quote,
            "market_edge_pct": self.as_optimal_spread_pct / 2.0,
            "as_mode": self.as_mode,
            "ws_as_version": self.path_version,
            "as_reservation": self.as_reservation,
            "as_optimal_spread_pct": self.as_optimal_spread_pct,
            "as_gamma": self.as_gamma,
            "as_kappa": self.as_kappa,
            "as_protected": True,
            "pause_bids": False,
            "pause_asks": False,
            "ai_edge_quality": self.ai_edge_quality,
            "ai_is_skimmable": self.ai_is_skimmable,
            "ai_rationale": self.ai_rationale,
            "ai_suggested_posture": self.ai_suggested_posture,
            "quote_intents": [],
        }
        if self.would_quote:
            out["quote_intents"] = [
                {"level": 1, "side": "bid", "price": self.suggested_bid, "size_xrp": self.bid_size},
                {"level": 1, "side": "ask", "price": self.suggested_ask, "size_xrp": self.ask_size},
            ]
        if competitor_intel:
            out.update({k: v for k, v in competitor_intel.items() if k != "top_competitors"})
            out["top_competitors"] = competitor_intel.get("top_competitors", [])
        return out


@dataclass
class _MinSpreadProfile:
    """Minimal object for AvellanedaStrategy min_spread_floor only (no trading profile)."""

    min_spread_floor_pct: float = DEFAULT_MIN_SPREAD_FLOOR_PCT
    name: str = "pure_as"


def _inventory_skew_from_label(label: str) -> float:
    lower = label.lower()
    if "xrp_heavy" in lower:
        return 0.30 if "slight" not in lower else 0.08
    if "rlusd_heavy" in lower:
        return -0.30 if "slight" not in lower else -0.08
    return 0.0


def _zero_quote_detail(
    reason: str,
    *,
    reservation: float,
    best_bid: float,
    best_ask: float,
    book_spread_pct: float,
    optimal_spread_pct: float,
) -> str:
    if reason == "reservation_outside_l1":
        if reservation <= best_bid:
            return f"reservation {reservation:.6f} <= bid {best_bid:.6f}"
        if reservation >= best_ask:
            return f"reservation {reservation:.6f} >= ask {best_ask:.6f}"
        return "reservation not strictly inside L1"
    if reason == "optimal_spread_wider_than_book":
        return f"optimal {optimal_spread_pct:.3f}% > book {book_spread_pct:.3f}%"
    if reason == "quoted":
        return "reservation inside L1"
    return reason


def _build_summary(
    decision: PureQuoteDecision,
    *,
    competitor_skim: str = "",
    ai_rationale: str = "",
) -> str:
    n = decision.quote_count
    parts = [
        f"Generated {n} quotes (two-sided) from mid={decision.mid:.6f} RLUSD/XRP",
        f"inventory={decision.inventory_label}",
        f"book={decision.book_spread_pct:.3f}%",
        (
            f"PURE A-S v{decision.path_version}: reservation={decision.as_reservation:.6f} "
            f"optimal_spread={decision.as_optimal_spread_pct:.3f}% "
            f"(gamma={decision.as_gamma:.2f}, kappa={decision.as_kappa:.2f})"
        ),
    ]
    if decision.would_quote:
        parts.append(
            f"would quote bid~{decision.suggested_bid:.6f} ask~{decision.suggested_ask:.6f}"
        )
    else:
        parts.append(f"0 quotes: {decision.zero_quote_reason} ({decision.zero_quote_detail})")
    if decision.pressure_rationale:
        parts.append(f"PRESSURE: {decision.pressure_rationale}")
    if competitor_skim:
        parts.append(f"COMPETITOR: {competitor_skim}")
    if ai_rationale:
        parts.append(f"AI: {ai_rationale}")
    return " | ".join(parts)


class PureQuotePath:
    """Single production-shaped pure A-S decision path for WS book feeds."""

    def __init__(
        self,
        *,
        gamma: float = 0.35,
        kappa: float = 3.5,
        min_spread_floor_pct: float = DEFAULT_MIN_SPREAD_FLOOR_PCT,
        inventory_skew_strength: float = DEFAULT_INVENTORY_SKEW_STRENGTH,
    ) -> None:
        self.as_strat = AvellanedaStrategy(None, gamma=gamma, kappa=kappa, T=1.0)
        self.min_spread_floor_pct = min_spread_floor_pct
        self.inventory_skew_strength = inventory_skew_strength
        self._spread_profile = _MinSpreadProfile(min_spread_floor_pct=min_spread_floor_pct)

    async def compute_decision(
        self,
        *,
        mid: float,
        best_bid: float,
        best_ask: float,
        xrp_bal: float,
        rlusd_bal: float,
        target_ratio: float = 0.55,
        competitor_intel: Optional[Dict[str, Any]] = None,
        ai_analyzer: Optional[Any] = None,
        intel_ai_enabled: bool = True,
        book_state_for_ai: Optional[Dict[str, Any]] = None,
        base_volatility_pct: Optional[float] = None,
    ) -> PureQuoteDecision:
        book_spread_pct = (best_ask - best_bid) / mid * 100.0 if mid else 0.0
        volatility_pct = base_volatility_pct if base_volatility_pct is not None else max(0.5, book_spread_pct * 1.5)

        inv_state = assess_inventory(
            xrp_balance=xrp_bal,
            rlusd_balance=rlusd_bal,
            mid_price=mid,
            target_xrp_ratio=target_ratio,
            skew_strength=self.inventory_skew_strength,
        )
        inv_skew = _inventory_skew_from_label(inv_state.label)

        effective_vol = volatility_pct
        effective_book_spread = book_spread_pct
        pressure_rationale = ""
        competitor_pressure: Optional[float] = None
        pressure_adj = None
        pressure_model = from_intel_dict(competitor_intel)
        if pressure_model:
            pressure_adj = apply_competitor_pressure(
                pressure_model,
                base_volatility_pct=volatility_pct,
                base_book_spread_pct=book_spread_pct,
                inventory_skew=inv_skew,
            )
            effective_vol = pressure_adj.volatility_pct
            effective_book_spread = pressure_adj.book_spread_pct
            pressure_rationale = pressure_adj.rationale
            competitor_pressure = pressure_model.value

        ai_rationale = ""
        ai_edge = 0.0
        ai_skimmable = False
        ai_posture = "off"
        if ai_analyzer and intel_ai_enabled:
            try:
                book_for_ai = book_state_for_ai or {
                    "bids": [{"price": best_bid}],
                    "asks": [{"price": best_ask}],
                    "age_s": 0.0,
                }
                run_ctx = {
                    "inventory_label": inv_state.label,
                    "inventory_skew": inv_skew,
                    "competitor_pressure": competitor_pressure,
                    "top_competitors": (competitor_intel or {}).get("top_competitors", []),
                }
                ai = await ai_analyzer.analyze(book_for_ai, run_context=run_ctx)
                if ai:
                    ai_rationale = ai.rationale or ""
                    ai_edge = float(getattr(ai, "edge_quality_score", 0.0) or 0.0)
                    ai_skimmable = bool(getattr(ai, "is_truly_skimmable", False))
                    ai_posture = str(getattr(ai, "quote_posture", "off"))
            except Exception:
                pass

        base_gamma = self.as_strat.gamma
        if pressure_adj:
            self.as_strat.gamma = base_gamma * pressure_adj.gamma_scale
        try:
            as_quote = self.as_strat.compute_avellaneda_quote(
                mid_price=mid,
                inventory_skew=inv_skew,
                volatility_pct=effective_vol,
                best_bid=best_bid,
                best_ask=best_ask,
                book_spread_pct=effective_book_spread,
                profile=self._spread_profile,
            )
        finally:
            self.as_strat.gamma = base_gamma

        would_quote = best_bid < as_quote.reservation_price < best_ask
        zero_reason = classify_zero_quote_reason(
            would_quote=would_quote,
            best_bid=best_bid,
            best_ask=best_ask,
            reservation=as_quote.reservation_price,
            book_spread_pct=book_spread_pct,
            optimal_spread_pct=as_quote.optimal_spread_pct,
        )
        zero_detail = _zero_quote_detail(
            zero_reason,
            reservation=as_quote.reservation_price,
            best_bid=best_bid,
            best_ask=best_ask,
            book_spread_pct=book_spread_pct,
            optimal_spread_pct=as_quote.optimal_spread_pct,
        )

        decision = PureQuoteDecision(
            would_quote=would_quote,
            quote_count=2 if would_quote else 0,
            mid=mid,
            best_bid=best_bid,
            best_ask=best_ask,
            book_spread_pct=book_spread_pct,
            inventory_label=inv_state.label,
            inventory_skew=inv_skew,
            volatility_pct=effective_vol,
            as_reservation=as_quote.reservation_price,
            as_optimal_spread_pct=as_quote.optimal_spread_pct,
            as_gamma=self.as_strat.gamma,
            as_kappa=self.as_strat.kappa,
            zero_quote_reason=zero_reason,
            zero_quote_detail=zero_detail,
            quote_decision_summary="",
            quoting_policy_label="PURE A-S (inside L1)" if would_quote else "PURE A-S (math blocked)",
            competitor_pressure=competitor_pressure,
            pressure_rationale=pressure_rationale,
            ai_edge_quality=ai_edge,
            ai_is_skimmable=ai_skimmable,
            ai_rationale=ai_rationale,
            ai_suggested_posture=ai_posture,
            suggested_bid=as_quote.bid_price if would_quote else None,
            suggested_ask=as_quote.ask_price if would_quote else None,
            bid_size=as_quote.bid_size,
            ask_size=as_quote.ask_size,
        )
        skim = (competitor_intel or {}).get("competitor_skim_advice", "") or ""
        decision.quote_decision_summary = _build_summary(
            decision,
            competitor_skim=skim,
            ai_rationale=ai_rationale,
        )
        return decision
