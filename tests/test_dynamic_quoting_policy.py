"""Table-driven tests for unified dynamic quoting policy."""

from core.dynamic_quoting_policy import (
    TOUCH_AT,
    TOUCH_NEAR,
    TOUCH_OFF,
    TOUCH_SPREAD,
    profile_quoting_bounds,
    resolve_dynamic_quoting_policy,
)
from core.market_conditions import assess_market_conditions
from core.perception import get_profile
from strategy.fill_quality import FillQualityState


def _assess(**kwargs):
    defaults = dict(
        volatility_pct=0.0,
        liquidity_score=0.9,
        book_spread_pct=0.06,
        active_profile="safe",
    )
    defaults.update(kwargs)
    return assess_market_conditions(**defaults)


def test_safe_near_touch_on_6bp_book() -> None:
    policy = resolve_dynamic_quoting_policy(
        profile=get_profile("safe"),
        assessment=_assess(book_spread_pct=0.061),
        book_spread_pct=0.061,
        effective_min_edge_pct=0.12,
        effective_spread_l1_pct=0.19,
        fill_quality=FillQualityState(),
        mm_mode=True,
    )
    assert policy.touch_mode == TOUCH_NEAR
    assert policy.join_touch
    assert 0.02 <= policy.touch_backoff_pct <= 0.12
    assert "near-touch" in policy.label.casefold()


def test_safe_at_touch_when_book_pays_edge() -> None:
    policy = resolve_dynamic_quoting_policy(
        profile=get_profile("safe"),
        assessment=_assess(book_spread_pct=0.30),
        book_spread_pct=0.30,
        effective_min_edge_pct=0.12,
        effective_spread_l1_pct=0.16,
        mm_mode=True,
    )
    assert policy.touch_mode == TOUCH_AT
    assert policy.join_touch
    assert policy.market_edge_met


def test_toxic_blocks_touch() -> None:
    fq = FillQualityState(
        recent_fills=10,
        toxic_ratio=0.25,
        toxic_ratio_30s=0.25,
    )
    policy = resolve_dynamic_quoting_policy(
        profile=get_profile("safe"),
        assessment=_assess(book_spread_pct=0.30),
        book_spread_pct=0.30,
        effective_min_edge_pct=0.12,
        effective_spread_l1_pct=0.16,
        fill_quality=fq,
        mm_mode=True,
    )
    assert policy.touch_mode == TOUCH_OFF
    assert not policy.join_touch
    assert not policy.join_touch
    assert policy.touch_mode == TOUCH_OFF


def test_hostile_spread_mid() -> None:
    policy = resolve_dynamic_quoting_policy(
        profile=get_profile("safe"),
        assessment=_assess(
            volatility_pct=8.0,
            liquidity_score=0.15,
            book_spread_pct=0.20,
        ),
        book_spread_pct=0.20,
        effective_min_edge_pct=0.12,
        effective_spread_l1_pct=0.20,
        mm_mode=True,
    )
    assert policy.touch_mode == TOUCH_SPREAD
    assert not policy.join_touch


def test_tight_spread_more_visible_cap_than_safe() -> None:
    assessment = _assess(book_spread_pct=0.10, active_profile="tight_spread")
    safe = resolve_dynamic_quoting_policy(
        profile=get_profile("safe"),
        assessment=assessment,
        book_spread_pct=0.10,
        effective_min_edge_pct=0.12,
        effective_spread_l1_pct=0.16,
        mm_mode=True,
    )
    tight = resolve_dynamic_quoting_policy(
        profile=get_profile("tight_spread"),
        assessment=assessment,
        book_spread_pct=0.10,
        effective_min_edge_pct=0.08,
        effective_spread_l1_pct=0.116,
        mm_mode=True,
    )
    assert tight.max_worse_than_touch_pct <= safe.max_worse_than_touch_pct
