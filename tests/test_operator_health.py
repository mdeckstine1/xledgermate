"""Operator health summaries."""

from utils.operator_health import build_operator_health, toxic_metric_labels


def test_early_fills_not_defensive_by_default() -> None:
    runtime = {
        "fills_session": 1,
        "toxic_fill_ratio": 1.0,
        "toxic_fill_ratio_30s": 1.0,
        "market_edge_met": True,
        "book_spread_pct": 0.2,
        "best_bid_rlusd_per_xrp": 1.1,
        "best_ask_rlusd_per_xrp": 1.12,
        "mid_price": 1.11,
    }
    h = build_operator_health(runtime, engine_running=True, profile_name="safe")
    assert h.status in ("ok", "cautious")
    assert "not" in " ".join(h.bullets).lower() or "8" in " ".join(h.bullets)


def test_toxic_metric_asterisk_under_gate_fills() -> None:
    runtime = {"fills_session": 2, "toxic_fill_ratio": 0.5, "toxic_fill_ratio_30s": 1.0}
    label, _, _, _ = toxic_metric_labels(runtime, profile_name="safe")
    assert "*" in label
