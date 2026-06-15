"""Tests for G2 spread-quality scaler."""

from experimental.ws_feed.spread_quality_scaler import compute_g2_adjustments


def test_g2_neutral_when_no_fills() -> None:
    g2 = compute_g2_adjustments()
    assert g2.size_mult == 1.0
    assert g2.spread_mult == 1.0
    assert not g2.active


def test_g2_no_win_chase_on_good_markout() -> None:
    g2 = compute_g2_adjustments(
        recent_fills=12,
        toxic_ratio=0.10,
        toxic_ratio_30s=0.10,
        mean_markout_30s_pct=0.12,
        markout_samples_30s=8,
    )
    assert g2.size_mult == 1.0
    assert g2.spread_mult == 1.0
    assert "no chase" in g2.summary.lower() or g2.grade == "ok"


def test_g2_defensive_brake_high_toxic() -> None:
    g2 = compute_g2_adjustments(
        recent_fills=12,
        toxic_ratio=0.55,
        toxic_ratio_30s=0.55,
        markout_samples_30s=6,
    )
    assert g2.size_mult < 1.0
    assert g2.spread_mult > 1.0
    assert g2.active
    assert g2.size_mult <= 1.0


def test_g2_early_sample_lighter_brake() -> None:
    g2 = compute_g2_adjustments(
        recent_fills=4,
        toxic_ratio=0.60,
        toxic_ratio_30s=0.60,
        markout_samples_30s=4,
        min_fills=8,
    )
    assert g2.size_mult == 0.82
    assert g2.spread_mult == 1.08
