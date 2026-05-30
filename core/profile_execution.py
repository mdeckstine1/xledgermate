"""Profile-owned execution cadence and queue-preservation tolerances."""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import BotConfig
from core.perception import Profile


@dataclass(frozen=True)
class ProfileExecution:
    """Resolved execution knobs for the active profile (Tier 2)."""

    order_price_tolerance_pct: float
    order_size_tolerance_xrp: float
    book_poll_interval_seconds: int
    full_refresh_every_n_polls: int
    toxic_refresh_pause_ratio: float
    markout_toxic_threshold_pct: float
    mid_requote_trigger_pct: float


def resolve_profile_execution(profile: Profile, config: BotConfig) -> ProfileExecution:
    """
    Map active profile → live execution behavior.

    Global config tolerances act as a ceiling when profile would be looser than
    operator-configured guardrails (never tighter than profile — profiles own strategy).
    """
    price_tol = float(profile.order_keep_price_tolerance_pct)
    size_tol = float(profile.order_keep_size_tolerance_xrp)
    cfg_price = float(getattr(config, "order_price_tolerance_pct", price_tol))
    cfg_size = float(getattr(config, "order_size_tolerance_xrp", size_tol))
    # Profile owns strategy; config can only tighten (smaller tolerance = more churn).
    price_tol = min(price_tol, cfg_price) if cfg_price > 0 else price_tol
    size_tol = min(size_tol, cfg_size) if cfg_size > 0 else size_tol

    poll_sec = max(10, int(profile.book_poll_interval_seconds))
    full_sec = max(poll_sec, int(profile.full_quote_refresh_seconds))
    full_every = max(1, full_sec // poll_sec)

    # Aggressive profiles re-quote sooner when mid moves; defensive profiles hold queue.
    mid_trigger = 0.08 + (1.0 - float(profile.aggression)) * 0.12

    return ProfileExecution(
        order_price_tolerance_pct=price_tol,
        order_size_tolerance_xrp=size_tol,
        book_poll_interval_seconds=poll_sec,
        full_refresh_every_n_polls=full_every,
        toxic_refresh_pause_ratio=float(profile.toxic_refresh_pause_ratio),
        markout_toxic_threshold_pct=float(profile.markout_toxic_threshold_pct),
        mid_requote_trigger_pct=mid_trigger,
    )
