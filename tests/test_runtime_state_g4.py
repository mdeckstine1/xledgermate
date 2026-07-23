"""RuntimeState round-trip for G4 fields (ws_pure_engine persist)."""

from __future__ import annotations

import json

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


def test_runtime_state_load_normalizes_legacy_numeric_price_history(tmp_path) -> None:
    path = tmp_path / "runtime_state.json"
    path.write_text(
        json.dumps(
            {
                "price_history": [
                    1.1,
                    {"mid": "1.2", "bid": "1.19", "ask": "1.21"},
                    {"mid": None},
                    "not-a-price",
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded = RuntimeStateStore(path=str(path)).load()

    assert loaded is not None
    assert loaded.price_history == [
        {"mid": 1.1},
        {"mid": 1.2, "bid": 1.19, "ask": 1.21},
    ]
