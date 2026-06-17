from experimental.ws_feed.reservation_metrics import (
    enrich_runtime_reservation_metrics,
    format_reservation_bbo_delta,
    reservation_bbo_metrics,
)


def test_inside_l1_positive_bps() -> None:
    m = reservation_bbo_metrics(
        reservation=1.005,
        best_bid=1.000,
        best_ask=1.010,
        mid=1.005,
    )
    assert m is not None
    assert m["inside_l1"] is True
    assert m["reservation_to_bbo_delta_bps"] > 0


def test_outside_l1_negative_bps() -> None:
    m = reservation_bbo_metrics(
        reservation=0.995,
        best_bid=1.000,
        best_ask=1.010,
        mid=1.005,
    )
    assert m is not None
    assert m["inside_l1"] is False
    assert m["reservation_to_bbo_delta_bps"] < 0


def test_format_delta_labels() -> None:
    assert "inside" in format_reservation_bbo_delta(4.2, inside_l1=True)
    assert "outside" in format_reservation_bbo_delta(-11.8, inside_l1=False)


def test_enrich_runtime_idempotent() -> None:
    rt = enrich_runtime_reservation_metrics(
        {
            "as_reservation": 1.005,
            "best_bid_rlusd_per_xrp": 1.0,
            "best_ask_rlusd_per_xrp": 1.01,
            "mid_price": 1.005,
        }
    )
    assert "inside_l1" in rt
    assert "reservation_to_bbo_delta_bps" in rt
    again = enrich_runtime_reservation_metrics(rt)
    assert again["reservation_to_bbo_delta_bps"] == rt["reservation_to_bbo_delta_bps"]
