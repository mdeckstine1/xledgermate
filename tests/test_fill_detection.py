from monitoring.fill_detection import (
    balance_delta_fill_reject_reason,
    detect_fill_from_balance_delta,
    is_coherent_fill_price,
)


def test_detect_sell_from_rlusd_increase() -> None:
    fill = detect_fill_from_balance_delta(
        prev_xrp=1000.0,
        prev_rlusd=0.0,
        curr_xrp=1000.0,
        curr_rlusd=32.5,
        mid_price=0.65,
    )
    assert fill is not None
    assert fill["side"] == "SELL"
    assert fill["rlusd_amount"] == 32.5


def test_detect_buy_from_rlusd_decrease() -> None:
    fill = detect_fill_from_balance_delta(
        prev_xrp=1000.0,
        prev_rlusd=50.0,
        curr_xrp=1050.0,
        curr_rlusd=17.5,
        mid_price=0.65,
    )
    assert fill is not None
    assert fill["side"] == "BUY"


def test_no_fill_on_noise() -> None:
    assert (
        detect_fill_from_balance_delta(
            prev_xrp=1000.0,
            prev_rlusd=0.0,
            curr_xrp=1000.0,
            curr_rlusd=0.0,
            mid_price=0.65,
        )
        is None
    )


def test_coherent_fill_near_mid() -> None:
    mid = 1.1567796348962887
    assert is_coherent_fill_price(1.157425, mid)
    assert is_coherent_fill_price(1.157425, mid, best_bid=1.156, best_ask=1.158)


def test_rejects_vps_negative_artifact() -> None:
    mid = 1.1567796348962887
    fill = detect_fill_from_balance_delta(
        prev_xrp=218.944737,
        prev_rlusd=200.752815,
        curr_xrp=216.325707,
        curr_rlusd=180.467128,
        mid_price=mid,
    )
    assert fill is not None
    assert fill["side"] == "BUY"
    assert not is_coherent_fill_price(fill["price_rlusd_per_xrp"], mid)
    assert balance_delta_fill_reject_reason(fill, mid) is not None


def test_rejects_vps_positive_artifact_sell() -> None:
    mid = 1.159805
    fill = detect_fill_from_balance_delta(
        prev_xrp=243.658037,
        prev_rlusd=148.747083,
        curr_xrp=244.657967,
        curr_rlusd=176.604021,
        mid_price=mid,
    )
    assert fill is not None
    assert fill["side"] == "SELL"
    assert fill["price_rlusd_per_xrp"] > 20.0
    assert not is_coherent_fill_price(fill["price_rlusd_per_xrp"], mid)
    assert balance_delta_fill_reject_reason(fill, mid) is not None


def test_rejects_vps_positive_artifact_large_sell() -> None:
    mid = 1.160194965074694
    fill = detect_fill_from_balance_delta(
        prev_xrp=219.617197,
        prev_rlusd=176.604021,
        curr_xrp=199.387787,
        curr_rlusd=223.528184,
        mid_price=mid,
    )
    assert fill is not None
    assert fill["side"] == "SELL"
    assert abs(fill["price_rlusd_per_xrp"] - 2.319601) < 0.01
    assert not is_coherent_fill_price(fill["price_rlusd_per_xrp"], mid)


def test_rejects_tiny_xrp_dust_fill() -> None:
    mid = 1.1578512480495369
    fill = {
        "side": "BUY",
        "xrp_amount": 0.00004,
        "rlusd_amount": 1.0,
        "price_rlusd_per_xrp": 25000.0,
    }
    assert balance_delta_fill_reject_reason(fill, mid) is not None
