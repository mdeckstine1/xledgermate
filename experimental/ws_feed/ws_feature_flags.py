"""WS-engine + HUD feature switches (read from BotConfig)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WsFeatureFlags:
    """Optional ws-engine / HUD capabilities — all default on for production soak."""

    competitor_intel: bool = True
    g2_scaler: bool = True
    g4_peer_lane: bool = True
    drawdown_kill: bool = True
    intel_log: bool = True
    fill_quality: bool = True
    telegram_kill_alerts: bool = True
    telegram_hourly_report: bool = True
    hud_enabled: bool = True
    hud_metrics: bool = True
    hud_grok: bool = True

    @classmethod
    def from_config(cls, config: Any) -> WsFeatureFlags:
        def _b(name: str, default: bool = True) -> bool:
            return bool(getattr(config, name, default))

        return cls(
            competitor_intel=_b("ws_competitor_intel_enabled"),
            g2_scaler=_b("ws_g2_scaler_enabled"),
            g4_peer_lane=_b("ws_g4_peer_lane_enabled"),
            drawdown_kill=_b("ws_drawdown_kill_enabled"),
            intel_log=_b("ws_intel_log_enabled"),
            fill_quality=_b("ws_fill_quality_enabled"),
            telegram_kill_alerts=_b("telegram_kill_alerts_enabled"),
            telegram_hourly_report=_b("telegram_hourly_report_enabled"),
            hud_enabled=_b("ws_hud_enabled"),
            hud_metrics=_b("ws_hud_metrics_enabled"),
            hud_grok=_b("ws_hud_grok_enabled"),
        )

    def summary(self) -> str:
        parts = []
        for name, on in (
            ("intel", self.competitor_intel),
            ("G2", self.g2_scaler),
            ("G4", self.g4_peer_lane),
            ("dd_kill", self.drawdown_kill),
            ("intel_log", self.intel_log),
            ("fill_q", self.fill_quality),
            ("tg_kill", self.telegram_kill_alerts),
            ("tg_hourly", self.telegram_hourly_report),
            ("hud", self.hud_enabled),
            ("hud_metrics", self.hud_metrics),
            ("hud_grok", self.hud_grok),
        ):
            parts.append(f"{name}={'on' if on else 'off'}")
        return "ws_features: " + " ".join(parts)
