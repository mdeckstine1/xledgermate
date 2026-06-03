from core.dynamic_quoting_policy import TOUCH_AT, TOUCH_OFF, TOUCH_SPREAD, resolve_dynamic_quoting_policy
from core.market_conditions import (
    CONDITION_DEFENSIVE,
    assess_market_conditions,
    ideal_for_profit_mode,
    profile_for_auto_switch,
    recommend_profile,
)
from core.perception import get_profile


def test_recommend_safe_on_hostile() -> None:
    profile, _ = recommend_profile(
        condition="hostile",
        volatility_level="high",
        liquidity_level="low",
        book_spread_status="wide",
    )
    assert profile == "safe"


def test_assessment_health_score_range() -> None:
    a = assess_market_conditions(
        volatility_pct=0.05,
        liquidity_score=0.6,
        book_spread_pct=0.2,
        active_profile="safe",
    )
    assert 0 <= a.health_score <= 100
    assert a.condition in ("favorable", "neutral", "defensive", "hostile")


def test_defensive_on_high_vol() -> None:
    a = assess_market_conditions(
        volatility_pct=0.5,
        liquidity_score=0.5,
        book_spread_pct=0.3,
        active_profile="tight_spread",
    )
    assert a.condition in (CONDITION_DEFENSIVE, "hostile")


def test_recommend_tight_spread_on_ideal_book() -> None:
    assert ideal_for_profit_mode(
        condition="favorable",
        volatility_level="low",
        liquidity_level="high",
        book_spread_status="tight",
    )
    profile, reason = recommend_profile(
        condition="favorable",
        volatility_level="low",
        liquidity_level="high",
        book_spread_status="tight",
    )
    assert profile == "tight_spread"
    assert "tight spread" in reason.lower()
    assert "profit mode" in reason.lower()


def test_favorable_moderate_vol_recommends_tight_spread_not_profit() -> None:
    profile, _ = recommend_profile(
        condition="favorable",
        volatility_level="moderate",
        liquidity_level="high",
        book_spread_status="tight",
    )
    assert profile == "tight_spread"


def test_normalize_maps_legacy_profit_suggestion() -> None:
    from utils.profile_recommendation import normalize_profile_recommendation

    profile, reason = normalize_profile_recommendation(
        "profit_mode",
        "Good conditions for tight spreads — Profit mode maximizes size.",
    )
    assert profile == "tight_spread"
    assert "manual" in reason.lower()


def test_auto_switch_never_targets_profit_mode() -> None:
    a = assess_market_conditions(
        volatility_pct=0.05,
        liquidity_score=0.7,
        book_spread_pct=0.1,
        active_profile="safe",
    )
    assert a.recommended_profile == "tight_spread"
    assert profile_for_auto_switch(a, active_profile="safe") == "tight_spread"
    assert profile_for_auto_switch(a, active_profile="profit_mode") == "tight_spread"
    assert profile_for_auto_switch(a, active_profile="tight_spread") is None


def test_auto_switch_can_move_to_tight_spread() -> None:
    a = assess_market_conditions(
        volatility_pct=0.09,
        liquidity_score=0.7,
        book_spread_pct=0.12,
        active_profile="safe",
    )
    assert a.recommended_profile == "tight_spread"
    assert profile_for_auto_switch(a, active_profile="safe") == "tight_spread"


def test_profit_mode_profile_exists_and_is_aggressive() -> None:
    from core.perception import BUILT_IN_PROFILES, get_profile

    assert "profit_mode" in BUILT_IN_PROFILES
    profit = get_profile("profit_mode")
    tight = get_profile("tight_spread")
    assert profit.spread_multiplier < tight.spread_multiplier
    assert profit.size_multiplier > tight.size_multiplier
    assert profit.min_edge_pct < tight.min_edge_pct
    assert profit.aggression > tight.aggression


def test_dynamic_policy_near_touch_when_edge_not_met() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.85,
        book_spread_pct=0.044,
        active_profile="tight_spread",
    )
    policy = resolve_dynamic_quoting_policy(
        profile=get_profile("tight_spread"),
        assessment=assessment,
        book_spread_pct=0.044,
        effective_min_edge_pct=0.08,
        effective_spread_l1_pct=0.12,
        mm_mode=True,
    )
    assert policy.touch_mode in ("near_touch", "spread_mid")
    assert "thin book" in policy.summary or "step off" in policy.summary


def test_dynamic_policy_hostile_no_touch() -> None:
    assessment = assess_market_conditions(
        volatility_pct=1.2,
        liquidity_score=0.15,
        book_spread_pct=0.044,
        active_profile="safe",
    )
    assert assessment.condition == "hostile"
    policy = resolve_dynamic_quoting_policy(
        profile=get_profile("safe"),
        assessment=assessment,
        book_spread_pct=0.044,
        effective_min_edge_pct=0.12,
        effective_spread_l1_pct=0.16,
        mm_mode=True,
    )
    assert policy.touch_mode == TOUCH_SPREAD
    assert not policy.join_touch


def test_dynamic_policy_at_touch_when_edge_met_on_tight_book() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.95,
        book_spread_pct=0.14,
        active_profile="safe",
    )
    policy = resolve_dynamic_quoting_policy(
        profile=get_profile("safe"),
        assessment=assessment,
        book_spread_pct=0.14,
        effective_min_edge_pct=0.12,
        effective_spread_l1_pct=0.16,
        mm_mode=True,
    )
    assert policy.touch_mode == TOUCH_AT
    assert policy.join_touch is True
