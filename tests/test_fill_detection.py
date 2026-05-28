from monitoring.fill_detection import detect_fill_from_balance_delta


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
