"""Tests for bracket edge cleanup preset."""

from __future__ import annotations

from alpha.hud.bracket_edge_preset import (
    BRACKET_EDGE_CLEANUP_OVERRIDES,
    bracket_edge_preset_payload,
)


def test_bracket_edge_preset_trust_and_closer_tp() -> None:
    payload = bracket_edge_preset_payload()
    assert payload["operator_overrides"]["alpha_operator_phase"] == "trust"
    assert BRACKET_EDGE_CLEANUP_OVERRIDES["take_profit_pct"] == 0.025
    assert BRACKET_EDGE_CLEANUP_OVERRIDES["take_profit_rr"] == 1.5
    assert BRACKET_EDGE_CLEANUP_OVERRIDES["initial_stop_loss_pct"] == 0.025
    assert BRACKET_EDGE_CLEANUP_OVERRIDES["alpha_max_pending_buys"] == 1
    assert BRACKET_EDGE_CLEANUP_OVERRIDES["alpha_ta_min_buy_score"] == 3.0
