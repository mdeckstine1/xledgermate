"""Tests for WS feature flag wiring."""

from __future__ import annotations

from config.settings import BotConfig
from experimental.ws_feed.ws_feature_flags import WsFeatureFlags


def test_ws_feature_flags_defaults_on() -> None:
    cfg = BotConfig()
    flags = WsFeatureFlags.from_config(cfg)
    assert flags.competitor_intel is True
    assert flags.telegram_hourly_report is True
    assert "intel=on" in flags.summary()


def test_ws_feature_flags_respect_config_off() -> None:
    cfg = BotConfig(
        ws_competitor_intel_enabled=False,
        ws_g2_scaler_enabled=False,
        telegram_hourly_report_enabled=False,
        ws_hud_grok_enabled=False,
    )
    flags = WsFeatureFlags.from_config(cfg)
    assert flags.competitor_intel is False
    assert flags.g2_scaler is False
    assert flags.telegram_hourly_report is False
    assert flags.hud_grok is False
