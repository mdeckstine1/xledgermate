"""RuntimeState round-trip for G4 fields (ws_pure_engine persist)."""

from __future__ import annotations

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
        portfolio_value_xrp=95.0,
        drawdown_pct=5.0,
        drawdown_daily_start_xrp=100.0,
        drawdown_daily_start_utc="2026-07-15T11:00:00",
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
    assert loaded.portfolio_value_xrp == 95.0
    assert loaded.drawdown_pct == 5.0
    assert loaded.drawdown_daily_start_xrp == 100.0
    assert loaded.drawdown_daily_start_utc == "2026-07-15T11:00:00"
