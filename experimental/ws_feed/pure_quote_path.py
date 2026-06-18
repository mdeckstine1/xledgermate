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
from experimental.ws_feed.execution_envelope import (
    compute_execution_envelope,
    touch_prices_from_backoff,
)
from experimental.ws_feed.dynamic_sizing import build_pure_quote_ladder, compute_pure_l1_sizes
from experimental.ws_feed.pure_inventory_policy import (
    apply_pause_to_ladder,
    apply_pure_inventory_policy,
    count_active_l1_quotes,
)
from experimental.ws_feed.ws_book_age_modulator import apply_ws_book_age_modulator
from experimental.ws_feed.peer_lane_quoting import G4Adjustments, compute_g4_adjustments, prepare_quoting_intel
from experimental.ws_feed.spread_quality_scaler import G2Adjustments, compute_g2_adjustments
from strategy.fill_quality import FillQualityState
from experimental.ws_feed.as_safety import enforce_reservation_gate
from experimental.ws_feed.reservation_metrics import reservation_bbo_metrics
from experimental.ws_feed.zero_quote_notes import classify_and_explain_pure_zero_quote
from strategy.avellaneda_strategy import AvellanedaStrategy, AvellanedaQuote
from strategy.quote_decision import assess_inventory

_WS_AS_VERSION_FILE = Path(__file__).resolve().parent / "WS_AS_VERSION"


def _read_ws_as_version() -> str:
    if _WS_AS_VERSION_FILE.exists():
        return _WS_AS_VERSION_FILE.read_text(encoding="utf-8").strip()
    return "2.0.0"


def current_ws_as_version() -> str:
    """Read WS_AS_VERSION file each call — safe for long-running HUD/engine processes."""
    return _read_ws_as_version()


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
    path_version: str = field(default_factory=current_ws_as_version)
    g2_size_mult: float = 1.0
    g2_spread_mult: float = 1.0
    g2_grade: str = "neutral"
    g2_active: bool = False
    g2_summary: str = ""
    g4_size_mult: float = 1.0
    g4_bid_size_mult: float = 1.0
    g4_ask_size_mult: float = 1.0
    g4_grade: str = "neutral"
    g4_active: bool = False
    g4_summary: str = ""
    g4_peer_lane_count: int = 0
    g4_peer_pressure: Optional[float] = None
    pause_bids: bool = False
    pause_asks: bool = False
    inventory_limits_summary: str = ""
    inside_l1: bool = False
    reservation_to_bbo_delta_bps: Optional[float] = None
    effective_quote_age_at_fill_seconds: Optional[float] = None
    g7_summary: str = ""
    bid_touch_backoff_bps: float = 0.0
    ask_touch_backoff_bps: float = 0.0

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
            "pause_bids": self.pause_bids,
            "pause_asks": self.pause_asks,
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
            "inside_l1": self.inside_l1,
            "reservation_to_bbo_delta_bps": self.reservation_to_bbo_delta_bps,
            "effective_quote_age_at_fill_seconds": self.effective_quote_age_at_fill_seconds,
            "g7_summary": self.g7_summary,
            "bid_touch_backoff_bps": self.bid_touch_backoff_bps,
            "ask_touch_backoff_bps": self.ask_touch_backoff_bps,
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
    side_label = "two-sided" if n >= 2 else ("one-sided" if n == 1 else "zero")
    parts = [
        f"Generated {n} quotes ({side_label}) from mid={decision.mid:.6f} RLUSD/XRP",
        f"inventory={decision.inventory_label}",
        f"book={decision.book_spread_pct:.3f}%",
        (
            f"PURE A-S v{decision.path_version}: reservation={decision.as_reservation:.6f} "
            f"optimal_spread={decision.as_optimal_spread_pct:.3f}% "
            f"(gamma={decision.as_gamma:.2f}, kappa={decision.as_kappa:.2f})"
        ),
    ]
    if decision.would_quote:
        legs = []
        if decision.suggested_bid is not None:
            legs.append(f"bid~{decision.suggested_bid:.6f}")
        if decision.suggested_ask is not None:
            legs.append(f"ask~{decision.suggested_ask:.6f}")
        parts.append(f"would quote {' '.join(legs) or '—'}")
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
    if decision.g2_active and decision.g2_summary:
        parts.append(decision.g2_summary)
    if decision.g7_summary:
        parts.append(decision.g7_summary)
    if decision.g4_active and decision.g4_summary:
        parts.append(decision.g4_summary)
    if decision.inventory_limits_summary:
        parts.append(f"INV: {decision.inventory_limits_summary}")
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
        fill_quality: Optional[FillQualityState] = None,
        inventory_max_deviation: float = 0.12,
        inventory_mode: str = "market_make",
        xrp_reserve: float = 12.0,
        inventory_overshoot_slack: float = 0.03,
        g2_enabled: bool = True,
        g4_enabled: bool = True,
        competitor_pressure_enabled: bool = True,
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

        quoting_intel = prepare_quoting_intel(competitor_intel if competitor_pressure_enabled else None)
        pressure_model = from_intel_dict(quoting_intel) if competitor_pressure_enabled else None
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

        g2 = G2Adjustments()
        if g2_enabled and fill_quality and fill_quality.recent_fills > 0:
            g2 = compute_g2_adjustments(
                recent_fills=fill_quality.recent_fills,
                toxic_ratio=fill_quality.toxic_ratio,
                toxic_ratio_30s=fill_quality.toxic_ratio_30s,
                mean_markout_30s_pct=fill_quality.mean_markout_30s_pct,
            )
            effective_vol *= g2.spread_mult
            pressure_size_mult *= g2.size_mult

        if g4_enabled:
            g4 = compute_g4_adjustments(
                quoting_intel,
                inventory_skew=inv_skew,
                inventory_label=inv_state.label,
                g2_size_mult=g2.size_mult,
            )
            pressure_size_mult *= g4.size_mult
        else:
            g4 = G4Adjustments()

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
                    "peer_lane_count": g4.peer_lane_count,
                    "peer_pressure_score": g4.peer_pressure,
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

        would_quote_reservation = best_bid < as_quote.reservation_price < best_ask
        would_quote_reservation = enforce_reservation_gate(
            would_quote_reservation=would_quote_reservation,
            reservation=as_quote.reservation_price,
            best_bid=best_bid,
            best_ask=best_ask,
        )
        bbo_metrics = reservation_bbo_metrics(
            reservation=as_quote.reservation_price,
            best_bid=best_bid,
            best_ask=best_ask,
            mid=mid,
        ) or {}
        inside_l1 = bool(bbo_metrics.get("inside_l1", False))
        reservation_delta_bps = bbo_metrics.get("reservation_to_bbo_delta_bps")
        zero_reason, zero_detail, operator_note = classify_and_explain_pure_zero_quote(
            would_quote=would_quote_reservation,
            best_bid=best_bid,
            best_ask=best_ask,
            reservation=as_quote.reservation_price,
            book_spread_pct=book_spread_pct,
            optimal_spread_pct=as_quote.optimal_spread_pct,
            min_spread_floor_pct=self.min_spread_floor_pct,
        )
        tight_note = operator_note if would_quote_reservation else ""
        blocked_note = operator_note if not would_quote_reservation else ""

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
        inv_policy = apply_pure_inventory_policy(
            bid_size_xrp=sizes.bid_size_xrp,
            ask_size_xrp=sizes.ask_size_xrp,
            xrp_balance=xrp_bal,
            rlusd_balance=rlusd_bal,
            mid_price=mid,
            target_xrp_ratio=target_ratio,
            inventory_max_deviation=inventory_max_deviation,
            inventory_mode=inventory_mode,
            xrp_reserve=xrp_reserve,
            inventory_overshoot_slack=inventory_overshoot_slack,
            min_order_size_xrp=self.min_order_size_xrp,
            bid_size_mult=inv_state.bid_size_mult * g4.bid_size_mult,
            ask_size_mult=inv_state.ask_size_mult * g4.ask_size_mult,
        )
        size_rationale = sizes.rationale
        if inv_policy.policy_tag:
            size_rationale = f"{size_rationale} | {inv_policy.policy_tag}"

        g7 = compute_execution_envelope(
            inventory_label=inv_state.label,
            inventory_skew=inv_skew,
            g2_spread_mult=g2.spread_mult,
        )
        l1_bid_price, l1_ask_price = touch_prices_from_backoff(
            best_bid=best_bid,
            best_ask=best_ask,
            bid_backoff_bps=g7.bid_touch_backoff_bps,
            ask_backoff_bps=g7.ask_touch_backoff_bps,
        )

        ladder = build_pure_quote_ladder(
            mid=mid,
            l1_bid_price=l1_bid_price,
            l1_ask_price=l1_ask_price,
            l1_bid_size=inv_policy.bid_size_xrp,
            l1_ask_size=inv_policy.ask_size_xrp,
            optimal_spread_pct=as_quote.optimal_spread_pct,
            level_spread_increment=self.level_spread_increment,
            order_levels=self.order_levels,
            min_order_size_xrp=self.min_order_size_xrp,
            configured_level_sizes=self.configured_order_sizes,
            active=would_quote_reservation,
        )
        ladder = apply_pause_to_ladder(
            ladder,
            pause_bids=inv_policy.pause_bids,
            pause_asks=inv_policy.pause_asks,
            min_order_size_xrp=self.min_order_size_xrp,
        )
        active_quotes = count_active_l1_quotes(ladder)

        decision = PureQuoteDecision(
            would_quote=would_quote_reservation and active_quotes > 0,
            quote_count=active_quotes if would_quote_reservation else 0,
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
            quoting_policy_label="PURE A-S (inside L1)" if would_quote_reservation else "PURE A-S (math blocked)",
            competitor_pressure=competitor_pressure,
            pressure_rationale=pressure_rationale,
            ai_edge_quality=ai_edge,
            ai_is_skimmable=ai_skimmable,
            ai_rationale=ai_rationale,
            ai_suggested_posture=ai_posture,
            suggested_bid=l1_bid_price if would_quote_reservation and not inv_policy.pause_bids else None,
            suggested_ask=l1_ask_price if would_quote_reservation and not inv_policy.pause_asks else None,
            bid_size=inv_policy.bid_size_xrp,
            ask_size=inv_policy.ask_size_xrp,
            l1_xrp=sizes.l1_xrp,
            size_rationale=size_rationale,
            quote_intents=ladder,
            pause_bids=inv_policy.pause_bids,
            pause_asks=inv_policy.pause_asks,
            inventory_limits_summary=inv_policy.limits_summary,
            g2_size_mult=g2.size_mult,
            g2_spread_mult=g2.spread_mult,
            g2_grade=g2.grade,
            g2_active=g2.active,
            g2_summary=g2.summary,
            g4_size_mult=g4.size_mult,
            g4_bid_size_mult=g4.bid_size_mult,
            g4_ask_size_mult=g4.ask_size_mult,
            g4_grade=g4.grade,
            g4_active=g4.active,
            g4_summary=g4.summary,
            g4_peer_lane_count=g4.peer_lane_count,
            g4_peer_pressure=g4.peer_pressure,
            inside_l1=inside_l1,
            reservation_to_bbo_delta_bps=reservation_delta_bps,
            g7_summary=g7.summary,
            bid_touch_backoff_bps=g7.bid_touch_backoff_bps,
            ask_touch_backoff_bps=g7.ask_touch_backoff_bps,
        )
        skim = (competitor_intel or {}).get("competitor_skim_advice", "") or ""
        decision.quote_decision_summary = _build_summary(
            decision,
            competitor_skim=skim,
            ai_rationale=ai_rationale,
        )
        return decision
