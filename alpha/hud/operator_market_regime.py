"""Operator market regime — SKYNET bias for bull / neutral / bear conditions."""

from __future__ import annotations

from typing import Any, Dict, List

OPERATOR_MARKET_REGIME_KEY = "alpha_operator_market_regime"

MARKET_REGIMES: tuple[str, ...] = ("bull", "neutral", "bear")
DEFAULT_MARKET_REGIME = "neutral"

_REGIME_META: Dict[str, Dict[str, str]] = {
    "bull": {
        "label": "Bull",
        "headline": "Trend up or constructive dips — favor patient accumulation",
        "when": "Higher lows, RLUSD deploy OK, TA bullish or neutral-bullish",
        "skynet_bias": (
            "Accumulation regime (default on): on bull tape ARMED → deploy RLUSD with tight offset (~0.06%), "
            "chase drift (~0.08%), max_pending 2–3, bypass re-entry weakness on rips. "
            "Set alpha_operator_market_regime=bull when chart trends up. "
            "Do not recommend dip-only patience while accumulation_regime is ARMED."
        ),
    },
    "neutral": {
        "label": "Neutral",
        "headline": "Chop / range — fewer entries, tighter edge, anti-churn",
        "when": "Sideways tape, mixed TA, SL streak, or max_pending full with scratch stops",
        "skynet_bias": (
            "Prioritize anti-churn: max_pending_buys 1–2, buy_offset ≥ 0.18, weakness ≥ 0.05, "
            "ta_min_buy_score↑ if ta_buy_blocked. Widen stale drift before lowering offset. "
            "After SL clusters: sl_cooldown↑, re-entry stabilization↑ — do NOT stack new bids "
            "at the top of the range. Judge bleed from realized_bracket_pnl, not session MTM."
        ),
    },
    "bear": {
        "label": "Bear",
        "headline": "Defensive — protect RLUSD, slow buys, survive the dip",
        "when": "Downtrend, bearish TA, repeated SLs, underwater brackets, or operator wants defense",
        "skynet_bias": (
            "Capital preservation first: risk_per_trade_pct↓, max_pending_buys 1, buy_offset↑ "
            "(0.20–0.30), weakness_deviation↑, sl_cooldown_cycles↑, ta_min_buy_score↑, "
            "ta_weight toward 1.0 if knife-catching. Suggest trust operator phase. "
            "Do NOT lower offset or crank risk after an SL-heavy night. "
            "Strength sells only if XRP-heavy — do not sell the bag in a crash without plan."
        ),
    },
}


def normalize_market_regime(value: Any) -> str:
    if value is None:
        return DEFAULT_MARKET_REGIME
    regime = str(value).strip().lower()
    if regime in MARKET_REGIMES:
        return regime
    aliases = {
        "bullish": "bull",
        "up": "bull",
        "sideways": "neutral",
        "chop": "neutral",
        "range": "neutral",
        "defensive": "bear",
        "bearish": "bear",
        "down": "bear",
    }
    return aliases.get(regime, DEFAULT_MARKET_REGIME)


def market_regime_snapshot_fields(overrides: Dict[str, Any] | None) -> Dict[str, Any]:
    regime = normalize_market_regime((overrides or {}).get(OPERATOR_MARKET_REGIME_KEY))
    meta = _REGIME_META[regime]
    return {
        OPERATOR_MARKET_REGIME_KEY: regime,
        "alpha_operator_market_regime_label": meta["label"],
    }


def build_market_regime_context_block(regime: str) -> str:
    r = normalize_market_regime(regime)
    meta = _REGIME_META[r]
    return "\n".join(
        [
            "=== Operator market regime (PRIMARY tape bias — pairs with operator phase) ===",
            f"market_regime={r} ({meta['label']})",
            f"intent: {meta['headline']}",
            f"use_when: {meta['when']}",
            f"skynet_rules: {meta['skynet_bias']}",
            "",
            "Regime change: operator sets alpha_operator_market_regime in HUD (bull | neutral | bear).",
            "Do NOT suggest regime change unless operator explicitly asks or SL/TP stats demand defense.",
        ]
    )


def market_regime_user_message_rules(regime: str) -> List[str]:
    r = normalize_market_regime(regime)
    meta = _REGIME_META[r]
    lines = [
        f"7. MARKET REGIME active: {r} ({meta['label']}) — {meta['headline']}",
        f"   {meta['skynet_bias']}",
    ]
    if r == "bear":
        lines.append(
            "   In bear regime: if realized_bracket_pnl shows SL-heavy recent exits, recommend "
            "defensive knobs and trust phase — never more aggression."
        )
    elif r == "neutral":
        lines.append(
            "   In neutral/chop: scratch SLs at breakeven are churn — favor wider entries and "
            "fewer concurrent pending buys over offset↓."
        )
    return lines
