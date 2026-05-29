from utils.auto_profile_state import (
    AutoProfileState,
    load_auto_profile_state,
    minutes_since_auto_switch,
    save_auto_profile_state,
)


def test_auto_profile_pending_accumulates() -> None:
    state = AutoProfileState()
    state.pending_profile = "profit_mode"
    state.pending_cycles = 1
    assert state.pending_profile == "profit_mode"
    state.pending_cycles += 1
    assert state.pending_cycles == 2


def test_minutes_since_auto_switch_empty() -> None:
    assert minutes_since_auto_switch(AutoProfileState()) > 1000
