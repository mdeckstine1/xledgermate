"""Tests for M-Purpose HUD scoreboard."""

from experimental.ws_feed.purpose_hud import evaluate_purpose_gate, build_purpose_hud_fields


def test_evaluate_purpose_gate_pass() -> None:
    out = evaluate_purpose_gate(
        session_spread_capture_xrp=0.05,
        delta_xrp=10.0,
        buy_capture_xrp=0.03,
        sell_capture_xrp=0.02,
        at_edge=True,
        fills_session=5,
    )
    assert out["purpose_gate_pass"] is True
    assert out["purpose_gate_status"] == "pass"


def test_evaluate_purpose_gate_fail_sell_led() -> None:
    out = evaluate_purpose_gate(
        session_spread_capture_xrp=0.029,
        delta_xrp=-5.0,
        buy_capture_xrp=-0.013,
        sell_capture_xrp=0.042,
        at_edge=False,
        fills_session=18,
    )
    assert out["purpose_gate_pass"] is False
    assert out["purpose_gate_status"] == "fail"
    assert out["purpose_gate_checks"]["at_edge"] is False


def test_evaluate_purpose_gate_warming() -> None:
    out = evaluate_purpose_gate(
        session_spread_capture_xrp=0.0,
        delta_xrp=None,
        buy_capture_xrp=0.0,
        sell_capture_xrp=0.0,
        at_edge=False,
        fills_session=0,
    )
    assert out["purpose_gate_status"] == "warming"


def test_build_purpose_hud_fields_empty_runtime() -> None:
    fields = build_purpose_hud_fields({}, logs_dir=__import__("pathlib").Path("/nonexistent"))
    assert fields["purpose_hud_version"]
    assert fields["purpose_gate_status"] == "warming"
