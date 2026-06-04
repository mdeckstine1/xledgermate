"""Toxic-fill kill switch gating."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from config.settings import BotConfig
from engine.trading_engine import TradingEngine


def test_toxic_kill_skipped_when_disabled() -> None:
    engine = TradingEngine(BotConfig.load())
    engine.kill_switch = MagicMock()
    engine.kill_switch.is_active.return_value = False
    engine._activate_kill_switch = AsyncMock()

    config = BotConfig.load()
    config.toxic_fill_kill_enabled = False
    fq = SimpleNamespace(recent_fills=10, toxic_fills=9)

    asyncio.run(engine._maybe_kill_on_toxic_fills(config, fq, MagicMock()))
    engine._activate_kill_switch.assert_not_called()


def test_toxic_kill_fires_when_enabled_and_over_threshold() -> None:
    engine = TradingEngine(BotConfig.load())
    engine.kill_switch = MagicMock()
    engine.kill_switch.is_active.return_value = False
    engine._activate_kill_switch = AsyncMock()

    config = BotConfig.load()
    config.toxic_fill_kill_enabled = True
    config.toxic_fill_min_count = 5
    config.toxic_fill_ratio_kill_threshold = 0.55
    fq = SimpleNamespace(recent_fills=5, toxic_fills=3)

    asyncio.run(engine._maybe_kill_on_toxic_fills(config, fq, MagicMock()))
    engine._activate_kill_switch.assert_called_once()
