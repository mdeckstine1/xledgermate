"""
Pure WS + Avellaneda-Stoikov quote path (xledger-ws-as).

No trading profiles, no build_quote_adjustments, no min-edge hard gates.
Quoting guard: reservation strictly inside live best bid/ask.

Pressure + Grok are inputs only (vol, spread anchor, gamma scale, advisory notes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from experimental.competitor_pressure import apply_competitor_pressure, from_intel_dict
from experimental.ws_feed.dynamic_sizing import build_pure_quote_ladder, compute_pure_l1_sizes
from experimental.ws_feed.ws_book_age_modulator import apply_ws_book_age_modulator
from experimental.ws_feed.zero_quote_notes import classify_and_explain_pure_zero_quote
from strategy.avellaneda_strategy import AvellanedaStrategy, AvellanedaQuote
from strategy.quote_decision import assess_inventory

_WS_AS_VERSION_FILE = Path(__file__).resolve().parent / "WS_AS_VERSION"


def _read_ws_as_version() -> str:
    if _WS_AS_VERSION_FILE.exists():
        return _WS_AS_VERSION_FILE.read_text(encoding="utf-8").strip()
    return "2.0.0"


WS_AS_VERSION = _read_ws_as_version()
DEFAULT_INVENTORY_SKEW_STRENGTH = 1.0
DEFAULT_MIN_SPREAD_FLOOR_PCT = 0.04


def book_scaled_volatility_pct(book_spread_pct: float) -> float:
    """Vol input scaled to live L1 — never floor at 0.5% on ~0.10% XRPL books.

    Old ``max(0.5, spread*1.5)`` pushed adverse_term so reservation sat below bid
    on every tight-book sample (0% would_quote). Vol tracks book width instead.
    """
    if book_spread_pct <= 0:
        return 0.05
    return max(book_spread_pct * 0.85, 0.02)


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
    zero_quote_operator_note: str = ""
    tight_book_note: str = ""
    competitor_pressure: Optional[float] = None
    pressure_rationale: str = ""
    ws_book_age_s: float = 0.0
    book_age_rationale: str = ""
    base_volatility_pct: float = 0.0
    ai_edge_quality: float = 0.0
    ai_is_skimmable: bool = False
    ai_rationale: str = ""
    ai_suggested_posture: str = "off"
    suggested_bid: Optional[float] = None
    suggested_ask: Optional[float] = None
    bid_size: float = 0.0
    ask_size: float = 0.0
    l1_xrp: float = 0.0
    size_rationale: str = ""
    quote_intents: List[Dict[str, Any]] = field(default_factory=list)
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
            "l1_xrp": self.l1_xrp,
            "bid_size_xrp": self.bid_size,
            "ask_size_xrp": self.ask_size,
            "pure_as_size_rationale": self.size_rationale,
            "suggested_bid": self.suggested_bid,
            "suggested_ask": self.suggested_ask,
            "quote_intents": list(self.quote_intents),
        }
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
    if decision.book_age_rationale:
        parts.append(decision.book_age_rationale)
    if decision.pressure_rationale:
        parts.append(f"PRESSURE: {decision.pressure_rationale}")
    if competitor_skim:
        parts.append(f"COMPETITOR: {competitor_skim}")
    if ai_rationale:
        parts.append(f"AI: {ai_rationale}")
    if decision.size_rationale:
        parts.append(decision.size_rationale)
    note = decision.tight_book_note or decision.zero_quote_operator_note
    if note:
        parts.append(note)
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
        configured_l1_xrp: float = 150.0,
        min_order_size_xrp: float = 1.0,
        balance_fraction_k: float = 0.07,
        order_levels: int = 3,
        level_spread_increment: float = 0.0003,
        configured_order_sizes: Optional[Sequence[float]] = None,
    ) -> None:
        self.as_strat = AvellanedaStrategy(None, gamma=gamma, kappa=kappa, T=1.0)
        self.min_spread_floor_pct = min_spread_floor_pct
        self.inventory_skew_strength = inventory_skew_strength
        self.configured_l1_xrp = configured_l1_xrp
        self.min_order_size_xrp = min_order_size_xrp
        self.balance_fraction_k = balance_fraction_k
        self.order_levels = order_levels
        self.level_spread_increment = level_spread_increment
        self.configured_order_sizes = configured_order_sizes
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
        ws_book_age_s: float = 0.0,
    ) -> PureQuoteDecision:
        book_spread_pct = (best_ask - best_bid) / mid * 100.0 if mid else 0.0
        raw_vol = (
            base_volatility_pct
            if base_volatility_pct is not None
            else book_scaled_volatility_pct(book_spread_pct)
        )

        inv_state = assess_inventory(
            xrp_balance=xrp_bal,
            rlusd_balance=rlusd_bal,
            mid_price=mid,
            target_xrp_ratio=target_ratio,
            skew_strength=self.inventory_skew_strength,
        )
        inv_skew = _inventory_skew_from_label(inv_state.label)

        pressure_model = from_intel_dict(competitor_intel)
        pressure_preview = pressure_model.value if pressure_model else None
        age_adj = apply_ws_book_age_modulator(
            base_volatility_pct=raw_vol,
            ws_book_age_s=ws_book_age_s,
            competitor_pressure=pressure_preview,
        )
        volatility_pct = age_adj.volatility_pct
        age_size_mult = age_adj.size_mult

        effective_vol = volatility_pct
        effective_book_spread = book_spread_pct
        pressure_rationale = ""
        competitor_pressure: Optional[float] = None
        effective_pressure: Optional[float] = None
        pressure_size_mult = age_size_mult
        pressure_adj = None
        if pressure_model:
            pressure_adj = apply_competitor_pressure(
                pressure_model,
                base_volatility_pct=volatility_pct,
                base_book_spread_pct=book_spread_pct,
                inventory_skew=inv_skew,
                base_size_mult=age_size_mult,
            )
            effective_vol = pressure_adj.volatility_pct
            effective_book_spread = pressure_adj.book_spread_pct
            pressure_rationale = pressure_adj.rationale
            competitor_pressure = pressure_model.value
            effective_pressure = pressure_adj.effective_pressure
            pressure_size_mult = pressure_adj.size_mult

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
        zero_reason, zero_detail, operator_note = classify_and_explain_pure_zero_quote(
            would_quote=would_quote,
            best_bid=best_bid,
            best_ask=best_ask,
            reservation=as_quote.reservation_price,
            book_spread_pct=book_spread_pct,
            optimal_spread_pct=as_quote.optimal_spread_pct,
            min_spread_floor_pct=self.min_spread_floor_pct,
        )
        tight_note = operator_note if would_quote else ""
        blocked_note = operator_note if not would_quote else ""

        sizes = compute_pure_l1_sizes(
            xrp_balance=xrp_bal,
            configured_l1_xrp=self.configured_l1_xrp,
            min_order_size_xrp=self.min_order_size_xrp,
            balance_fraction_k=self.balance_fraction_k,
            inventory_skew=inv_skew,
            inventory_label=inv_state.label,
            pressure_size_mult=pressure_size_mult,
            effective_pressure=effective_pressure,
        )
        ladder = build_pure_quote_ladder(
            mid=mid,
            l1_bid_price=as_quote.bid_price,
            l1_ask_price=as_quote.ask_price,
            l1_bid_size=sizes.bid_size_xrp,
            l1_ask_size=sizes.ask_size_xrp,
            optimal_spread_pct=as_quote.optimal_spread_pct,
            level_spread_increment=self.level_spread_increment,
            order_levels=self.order_levels,
            min_order_size_xrp=self.min_order_size_xrp,
            configured_level_sizes=self.configured_order_sizes,
            active=would_quote,
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
            base_volatility_pct=raw_vol,
            ws_book_age_s=ws_book_age_s,
            book_age_rationale=age_adj.rationale,
            as_reservation=as_quote.reservation_price,
            as_optimal_spread_pct=as_quote.optimal_spread_pct,
            as_gamma=self.as_strat.gamma,
            as_kappa=self.as_strat.kappa,
            zero_quote_reason=zero_reason,
            zero_quote_detail=zero_detail,
            zero_quote_operator_note=blocked_note,
            tight_book_note=tight_note,
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
            bid_size=sizes.bid_size_xrp,
            ask_size=sizes.ask_size_xrp,
            l1_xrp=sizes.l1_xrp,
            size_rationale=sizes.rationale,
            quote_intents=ladder,
        )
        skim = (competitor_intel or {}).get("competitor_skim_advice", "") or ""
        decision.quote_decision_summary = _build_summary(
            decision,
            competitor_skim=skim,
            ai_rationale=ai_rationale,
        )
        return decision
