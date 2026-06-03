from core.market_conditions import (
    CONDITION_DEFENSIVE,
    assess_market_conditions,
    ideal_for_profit_mode,
    profile_for_auto_switch,
    recommend_profile,
    resolve_quoting_posture,
)


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


def test_quoting_posture_joins_touch_when_favorable_and_edge_thin() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.85,
        book_spread_pct=0.044,
        active_profile="tight_spread",
    )
    posture = resolve_quoting_posture(
        assessment, "tight_spread", market_edge_met=False
    )
    assert posture.join_touch is True
    assert posture.touch_backoff_pct == 0.0
    assert "Favorable" in posture.summary


def test_quoting_posture_defensive_high_vol_near_touch() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.5,
        liquidity_score=0.6,
        book_spread_pct=0.044,
        active_profile="high_volatility",
    )
    posture = resolve_quoting_posture(
        assessment, "high_volatility", market_edge_met=False
    )
    assert posture.join_touch is True
    assert posture.touch_backoff_pct >= 0.05


def test_quoting_posture_hostile_no_touch() -> None:
    assessment = assess_market_conditions(
        volatility_pct=1.2,
        liquidity_score=0.15,
        book_spread_pct=0.044,
        active_profile="safe",
    )
    assert assessment.condition == "hostile"
    posture = resolve_quoting_posture(assessment, "safe", market_edge_met=False)
    assert posture.join_touch is False


def test_quoting_posture_joins_touch_when_edge_met_on_tight_book() -> None:
    assessment = assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.95,
        book_spread_pct=0.07,
        active_profile="safe",
    )
    posture = resolve_quoting_posture(assessment, "safe", market_edge_met=True)
    assert posture.join_touch is True
    assert posture.touch_backoff_pct == 0.0
