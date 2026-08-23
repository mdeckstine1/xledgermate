"""Tests for walk-away preset."""

from __future__ import annotations

from alpha.hud.walkaway_preset import WALKAWAY_AGENT_PATCH, WALKAWAY_OPERATOR_OVERRIDES, walkaway_preset_payload


def test_walkaway_preset_has_trust_phase_and_agent_not_full() -> None:
    payload = walkaway_preset_payload()
    assert payload["operator_overrides"]["alpha_operator_phase"] == "trust"
    assert WALKAWAY_AGENT_PATCH["agent_enabled"] is True
    assert WALKAWAY_AGENT_PATCH["full_mode_enabled"] is False
    assert WALKAWAY_OPERATOR_OVERRIDES["alpha_max_pending_sells"] == 2
