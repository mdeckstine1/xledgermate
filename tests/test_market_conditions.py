from core.market_conditions import assess_market_conditions, recommend_profile, CONDITION_DEFENSIVE


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
