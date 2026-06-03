from config.settings import BotConfig
from utils.gui_profile_presets import apply_profile_gui_preset


def test_apply_safe_preset_updates_spread_and_edge():
    config = BotConfig()
    config.base_spread = 0.0003
    config.edge_strictness = 0.85
    config.dynamic_min_edge_enabled = True

    apply_profile_gui_preset(config, "safe")

    assert config.active_profile == "safe"
    assert config.base_spread == 0.0010
    assert config.edge_strictness == 1.0
    assert config.dynamic_min_edge_enabled is False
    assert config.book_pressure_sensitivity == 1.0
    assert config.inventory_mode == "rebalance"


def test_apply_tight_spread_sets_market_make():
    config = BotConfig()
    apply_profile_gui_preset(config, "tight_spread")
    assert config.inventory_mode == "market_make"


def test_apply_profit_mode_preset_is_tighter():
    config = BotConfig()
    apply_profile_gui_preset(config, "profit_mode")

    assert config.base_spread == 0.0004
    assert config.dynamic_min_edge_enabled is True
