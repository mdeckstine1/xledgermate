"""Deprecated path — use utils.gui_profile_presets (avoids stale imports)."""

from utils.gui_profile_presets import (  # noqa: F401
    PRESET_MODULE_VERSION,
    PROFILE_GUI_PRESETS,
    ProfileGuiPreset,
    apply_profile_gui_preset,
    preset_for_profile,
    preset_preview_lines,
    verify_profile_on_disk,
)

# Legacy alias
expected_preset = preset_for_profile
