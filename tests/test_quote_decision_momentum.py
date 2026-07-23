from __future__ import annotations

from strategy.quote_decision import compute_mid_momentum_pct


def test_compute_mid_momentum_accepts_legacy_numeric_history() -> None:
    history = [1.00, 1.01, 1.02, 1.03, 1.04, 1.05]

    assert abs(compute_mid_momentum_pct(history) - 5.0) < 1e-9


def test_compute_mid_momentum_accepts_mixed_tick_history() -> None:
    history = [
        {"mid": "1.00", "ts_utc": "2026-07-23T00:00:00+00:00"},
        {"mid": 1.01},
        {"mid": 1.02},
        {"mid": 1.03},
        {"mid": 1.04},
        1.05,
    ]

    assert abs(compute_mid_momentum_pct(history) - 5.0) < 1e-9
