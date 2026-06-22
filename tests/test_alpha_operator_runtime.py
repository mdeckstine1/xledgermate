"""Tests for Alpha operator runtime (overrides, commands, apply)."""

from __future__ import annotations

import json

import pytest

from alpha.operator.runtime import (
    OperatorRuntimeStore,
    apply_overrides,
    derive_posture,
    validate_override_updates,
)
from config.settings import BotConfig


def test_apply_overrides_merges_without_mutating_base():
    base = BotConfig()
    base.alpha_risk_per_trade_pct = 0.5
    overrides = {"alpha_risk_per_trade_pct": 1.2, "dry_run": False}
    effective = apply_overrides(base, overrides)
    assert effective.alpha_risk_per_trade_pct == 1.2
    assert effective.dry_run is False
    assert base.alpha_risk_per_trade_pct == 0.5
    assert base.dry_run is True


def test_validate_override_rejects_bad_values():
    _, errors = validate_override_updates({"alpha_risk_per_trade_pct": 0})
    assert errors
    assert any("alpha_risk_per_trade_pct" in e for e in errors)


def test_validate_override_accepts_good_patch():
    sanitized, errors = validate_override_updates(
        {
            "alpha_min_edge_threshold_pct": 0.1,
            "bracket_trailing_enabled": True,
        }
    )
    assert not errors
    assert sanitized["alpha_min_edge_threshold_pct"] == 0.1
    assert sanitized["bracket_trailing_enabled"] is True


def test_runtime_store_overrides_and_commands(tmp_path):
    store = OperatorRuntimeStore(
        overrides_path=tmp_path / "alpha_overrides.json",
        commands_path=tmp_path / "alpha_commands.json",
    )
    merged, errors = store.patch_overrides({"alpha_breakout_pct": 0.03})
    assert not errors
    assert merged["alpha_breakout_pct"] == 0.03
    assert store.load_overrides()["alpha_breakout_pct"] == 0.03

    store.queue_command({"type": "cancel_all"})
    drained = store.drain_commands()
    assert len(drained) == 1
    assert drained[0]["type"] == "cancel_all"
    assert store.drain_commands() == []


def test_set_dry_run_requires_valid_confirm_path(tmp_path):
    store = OperatorRuntimeStore(
        overrides_path=tmp_path / "alpha_overrides.json",
        commands_path=tmp_path / "alpha_commands.json",
    )
    overrides = store.set_dry_run(False)
    assert overrides["dry_run"] is False


def test_derive_posture():
    assert derive_posture(decision_action="hold", pending_buys=0, active_brackets=0) == "patient"
    assert derive_posture(decision_action="place_bid", pending_buys=0, active_brackets=0) == "buying"
    assert derive_posture(decision_action="hold", pending_buys=1, active_brackets=0) == "buying"
    assert derive_posture(decision_action="hold", pending_buys=0, active_brackets=2) == "in_position"


def test_dry_run_persist_yaml(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("dry_run: true\ntrading_enabled: true\n", encoding="utf-8")
    monkeypatch.setattr("config.settings.CONFIG_FILE", cfg_path)
    monkeypatch.setattr("alpha.operator.runtime.patch_config_file", lambda updates, filepath=None: None)

    store = OperatorRuntimeStore(
        overrides_path=tmp_path / "overrides.json",
        commands_path=tmp_path / "commands.json",
    )
    store.set_dry_run(False, persist_yaml=True)
    assert store.load_overrides()["dry_run"] is False
