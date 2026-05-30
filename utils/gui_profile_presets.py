"""GUI preset values for Apply profile (kept under utils/ to avoid stale core/ bytecode)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict

from core.perception import BUILT_IN_PROFILES, get_profile
from core.profile_edge import profile_min_edge_pct

if TYPE_CHECKING:
    from config.settings import BotConfig

# Bump when preset table or apply logic changes (invalidates old .pyc expectations).
PRESET_MODULE_VERSION = 3


@dataclass(frozen=True)
class ProfileGuiPreset:
    """Config.yaml fields updated on Apply profile (engine still applies profile multipliers)."""

    base_spread: float
    level_spread_increment: float
    edge_strictness: float
    book_pressure_sensitivity: float
    dynamic_min_edge_enabled: bool


PROFILE_GUI_PRESETS: Dict[str, ProfileGuiPreset] = {
    "safe": ProfileGuiPreset(
        base_spread=0.0010,
        level_spread_increment=0.0005,
        edge_strictness=1.0,
        book_pressure_sensitivity=1.25,
        dynamic_min_edge_enabled=False,
    ),
    "high_volatility": ProfileGuiPreset(
        base_spread=0.0012,
        level_spread_increment=0.0006,
        edge_strictness=1.15,
        book_pressure_sensitivity=1.35,
        dynamic_min_edge_enabled=False,
    ),
    "thin_liquidity": ProfileGuiPreset(
        base_spread=0.0011,
        level_spread_increment=0.0005,
        edge_strictness=1.0,
        book_pressure_sensitivity=1.50,
        dynamic_min_edge_enabled=False,
    ),
    "tight_spread": ProfileGuiPreset(
        base_spread=0.0006,
        level_spread_increment=0.0003,
        edge_strictness=0.85,
        book_pressure_sensitivity=0.85,
        dynamic_min_edge_enabled=True,
    ),
    "profit_mode": ProfileGuiPreset(
        base_spread=0.0004,
        level_spread_increment=0.0002,
        edge_strictness=0.85,
        book_pressure_sensitivity=0.72,
        dynamic_min_edge_enabled=True,
    ),
}


def _edge_label(strictness: float) -> str:
    if strictness <= 0.9:
        return "Low (0.85x)"
    if strictness >= 1.1:
        return "Strict (1.15x)"
    return "Normal (1.0x)"


def preset_for_profile(profile_name: str) -> ProfileGuiPreset:
    name = (profile_name or "safe").strip().lower()
    return PROFILE_GUI_PRESETS.get(name, PROFILE_GUI_PRESETS["safe"])


def apply_profile_gui_preset(config: "BotConfig", profile_name: str) -> str:
    """Write spread + defensive controls from the profile preset; returns a short summary."""
    name = (profile_name or "safe").strip().lower()
    if name not in BUILT_IN_PROFILES:
        name = "safe"
    preset = preset_for_profile(name)
    profile = get_profile(name)

    config.active_profile = name
    config.base_spread = preset.base_spread
    config.level_spread_increment = preset.level_spread_increment
    config.edge_strictness = preset.edge_strictness
    config.book_pressure_sensitivity = preset.book_pressure_sensitivity
    config.dynamic_min_edge_enabled = preset.dynamic_min_edge_enabled

    return (
        f"base spread **{preset.base_spread * 100:.2f}%**, "
        f"edge **{profile_min_edge_pct(profile):.2f}%** baseline @ "
        f"**{_edge_label(preset.edge_strictness)}**, "
        f"book pressure **{preset.book_pressure_sensitivity:.2f}**, "
        f"dynamic edge **{'on' if preset.dynamic_min_edge_enabled else 'off'}**"
    )


def preset_preview_lines(profile_name: str) -> str:
    """One-line hint for the Controls tab before Apply."""
    name = (profile_name or "safe").strip().lower()
    preset = PROFILE_GUI_PRESETS.get(name)
    if not preset:
        return ""
    profile = get_profile(name)
    return (
        f"Apply will set base spread **{preset.base_spread * 100:.2f}%**, "
        f"edge strictness **{_edge_label(preset.edge_strictness)}** "
        f"(profile min edge **{profile_min_edge_pct(profile):.2f}%**), "
        f"dynamic min edge **{'on' if preset.dynamic_min_edge_enabled else 'off'}**."
    )


def verify_profile_on_disk(profile_name: str, config: "BotConfig") -> tuple[bool, str]:
    """Confirm config.yaml matches the profile GUI preset after save."""
    name = (profile_name or "safe").strip().lower()
    preset = preset_for_profile(name)
    if (config.active_profile or "").strip().lower() != name:
        return False, f"active_profile is {config.active_profile!r}, expected {name!r}"
    if abs(float(config.base_spread) - preset.base_spread) > 1e-12:
        return (
            False,
            f"base_spread is {float(config.base_spread) * 100:.4f}%, "
            f"expected {preset.base_spread * 100:.2f}%",
        )
    if abs(float(config.level_spread_increment) - preset.level_spread_increment) > 1e-12:
        return False, "level_spread_increment does not match profile preset"
    if abs(float(config.edge_strictness) - preset.edge_strictness) > 0.01:
        return False, "edge_strictness does not match profile preset"
    if bool(config.dynamic_min_edge_enabled) != preset.dynamic_min_edge_enabled:
        return False, "dynamic_min_edge_enabled does not match profile preset"
    return True, "ok"
