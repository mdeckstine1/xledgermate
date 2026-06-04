"""Toxicity gate minimum fill count."""

from core.dynamic_quoting_policy import TOUCH_OFF, resolve_dynamic_quoting_policy
from core.market_conditions import assess_market_conditions
from core.perception import get_profile
from core.toxicity import (
    effective_toxic_ratio,
    gates_apply_for_fill_count,
    update_toxic_off_touch_latch,
)
from strategy.fill_quality import FillQualityState


def _assess():
    return assess_market_conditions(
        volatility_pct=0.0,
        liquidity_score=0.9,
        book_spread_pct=0.30,
        active_profile="safe",
    )


def test_effective_toxic_zero_below_min_fills() -> None:
    fq = FillQualityState(recent_fills=4, toxic_ratio=0.5, toxic_ratio_30s=0.5)
    assert effective_toxic_ratio(fq, min_fills_for_gates=8) == 0.0
    assert not gates_apply_for_fill_count(4, min_fills_for_gates=8)


def test_off_book_not_triggered_on_four_fills_at_fifty_percent() -> None:
    fq = FillQualityState(recent_fills=4, toxic_ratio=0.5, toxic_ratio_30s=0.5)
    policy = resolve_dynamic_quoting_policy(
        profile=get_profile("safe"),
        assessment=_assess(),
        book_spread_pct=0.30,
        effective_min_edge_pct=0.12,
        effective_spread_l1_pct=0.16,
        fill_quality=fq,
        mm_mode=True,
    )
    assert policy.touch_mode != TOUCH_OFF


def test_toxic_hysteresis_holds_between_exit_and_enter() -> None:
    profile = get_profile("safe")
    fq = FillQualityState(recent_fills=10, toxic_ratio=0.17, toxic_ratio_30s=0.17)
    latched = update_toxic_off_touch_latch(True, fq, profile)
    assert latched is True
    fq2 = FillQualityState(recent_fills=10, toxic_ratio=0.16, toxic_ratio_30s=0.16)
    latched2 = update_toxic_off_touch_latch(latched, fq2, profile)
    assert latched2 is True
    fq3 = FillQualityState(recent_fills=10, toxic_ratio=0.14, toxic_ratio_30s=0.14)
    latched3 = update_toxic_off_touch_latch(latched2, fq3, profile)
    assert latched3 is False


def test_off_book_still_triggers_with_enough_fills() -> None:
    fq = FillQualityState(recent_fills=10, toxic_ratio=0.25, toxic_ratio_30s=0.25)
    policy = resolve_dynamic_quoting_policy(
        profile=get_profile("safe"),
        assessment=_assess(),
        book_spread_pct=0.30,
        effective_min_edge_pct=0.12,
        effective_spread_l1_pct=0.16,
        fill_quality=fq,
        mm_mode=True,
    )
    assert policy.touch_mode == TOUCH_OFF
