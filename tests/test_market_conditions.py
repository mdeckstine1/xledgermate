from core.market_conditions import (
    CONDITION_DEFENSIVE,
    assess_market_conditions,
    ideal_for_profit_mode,
    profile_for_auto_switch,
    recommend_profile,
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


def test_recommend_profit_mode_on_ideal_book() -> None:
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
    assert profile == "profit_mode"
    assert "tight spread" in reason.lower()


def test_favorable_moderate_vol_recommends_tight_spread_not_profit() -> None:
    profile, _ = recommend_profile(
        condition="favorable",
        volatility_level="moderate",
        liquidity_level="high",
        book_spread_status="tight",
    )
    assert profile == "tight_spread"


def test_auto_switch_can_move_to_profit_mode() -> None:
    a = assess_market_conditions(
        volatility_pct=0.05,
        liquidity_score=0.7,
        book_spread_pct=0.1,
        active_profile="safe",
    )
    assert a.recommended_profile == "profit_mode"
    assert profile_for_auto_switch(a, active_profile="safe") == "profit_mode"
    assert profile_for_auto_switch(a, active_profile="profit_mode") is None


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
