"""RuntimeState round-trip for G4 fields (ws_pure_engine persist)."""

from __future__ import annotations

import json

import pytest

import core.runtime_state as runtime_state_module
from core.runtime_state import RuntimeState, RuntimeStateStore


def test_runtime_state_save_load_g4_fields(tmp_path) -> None:
    store = RuntimeStateStore(path=str(tmp_path / "runtime_state.json"))
    state = RuntimeState(
        g4_size_mult=0.85,
        g4_grade="cautious",
        g4_active=True,
        g4_summary="G4 peer brake",
        ws_as_version="2.1.9",
        as_mode="pure",
    )
    store.save(state)
    loaded = store.load()
    assert loaded is not None
    assert loaded.g4_size_mult == 0.85
    assert loaded.g4_grade == "cautious"
    assert loaded.g4_active is True
    assert loaded.g4_summary == "G4 peer brake"
    assert loaded.ws_as_version == "2.1.9"
    assert loaded.as_mode == "pure"


def test_runtime_state_save_replace_failure_preserves_previous_snapshot(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "runtime_state.json"
    path.write_text(
        json.dumps({"version": "old", "network": "testnet"}),
        encoding="utf-8",
    )
    store = RuntimeStateStore(path=str(path))

    def fail_replace(src, dst) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(runtime_state_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        store.save(RuntimeState(version="new", network="mainnet"))

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "version": "old",
        "network": "testnet",
    }
    assert list(tmp_path.glob(".runtime_state.json.*.tmp")) == []
