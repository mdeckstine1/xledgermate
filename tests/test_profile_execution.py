"""Tests for profile-owned Tier 2 execution settings."""

from config.settings import BotConfig
from core import get_profile
from core.profile_execution import resolve_profile_execution


def test_safe_profile_keeps_wider_queue_tolerance_than_profit_mode() -> None:
    safe = resolve_profile_execution(get_profile("safe"), BotConfig())
    profit = resolve_profile_execution(get_profile("profit_mode"), BotConfig())
    assert safe.order_price_tolerance_pct > profit.order_price_tolerance_pct
    assert safe.order_size_tolerance_xrp > profit.order_size_tolerance_xrp


def test_tight_spread_polls_faster_than_high_volatility() -> None:
    tight = resolve_profile_execution(get_profile("tight_spread"), BotConfig())
    hv = resolve_profile_execution(get_profile("high_volatility"), BotConfig())
    assert tight.book_poll_interval_seconds <= hv.book_poll_interval_seconds
    assert tight.full_refresh_every_n_polls * tight.book_poll_interval_seconds <= (
        hv.full_refresh_every_n_polls * hv.book_poll_interval_seconds
    )


def test_config_can_tighten_tolerance_not_loosen() -> None:
    cfg = BotConfig()
    cfg.order_price_tolerance_pct = 0.05
    resolved = resolve_profile_execution(get_profile("safe"), cfg)
    assert resolved.order_price_tolerance_pct == 0.05
