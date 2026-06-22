"""Alpha config validation — uses existing BotConfig.load(); does not change load path."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from alpha.decision.ta_config import validate_ta_config
from config.settings import BotConfig


@dataclass(frozen=True)
class AlphaConfigValidation:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "Alpha config validation OK"
        return "Alpha config validation FAILED: " + "; ".join(self.errors)


def load_validated_config() -> tuple[BotConfig, AlphaConfigValidation]:
    """Load config via existing hooks and run Alpha-specific validation."""
    config = BotConfig.load()
    validation = validate_alpha_config(config)
    return config, validation


def validate_alpha_config(config: BotConfig) -> AlphaConfigValidation:
    errors: List[str] = []
    warnings: List[str] = []

    if not (config.bot_account_address or "").strip():
        errors.append("bot_account_address is required")

    if not config.dry_run and not (config.bot_secret_key or "").strip():
        errors.append("bot_secret_key required when dry_run is false (live trading)")

    if config.testnet:
        warnings.append("testnet=true — Alpha targets mainnet; set testnet: false for production")

    if not config.dry_run:
        warnings.append("dry_run=false — LIVE mainnet trading enabled")

    if config.dry_run and not (config.bot_secret_key or "").strip():
        warnings.append("No bot_secret_key — read-only ledger access in dry-run is OK")

    issuer = config.resolved_rlusd_issuer()
    if not issuer.startswith("r"):
        errors.append("resolved RLUSD issuer address is invalid")

    if config.max_daily_drawdown_percent <= 0:
        errors.append("max_daily_drawdown_percent must be positive")

    if config.initial_stop_loss_pct <= 0 or config.initial_stop_loss_pct >= 1.0:
        errors.append("initial_stop_loss_pct must be between 0 and 1 (exclusive)")

    mode = (config.partial_fill_mode or "").strip().lower()
    if mode not in ("wait_full", "proportional"):
        errors.append("partial_fill_mode must be wait_full or proportional")

    if config.min_fill_size_xrp_for_oco < 0:
        errors.append("min_fill_size_xrp_for_oco must be non-negative")

    if config.take_profit_rr <= 0 and config.take_profit_pct <= 0:
        errors.append("set take_profit_rr > 0 or take_profit_pct > 0")

    if config.alpha_risk_per_trade_pct <= 0 or config.alpha_risk_per_trade_pct > 100:
        errors.append("alpha_risk_per_trade_pct must be between 0 and 100 (exclusive of 0)")

    if config.alpha_min_edge_threshold_pct < 0:
        errors.append("alpha_min_edge_threshold_pct must be non-negative")

    if config.alpha_buy_limit_offset_pct <= 0:
        errors.append("alpha_buy_limit_offset_pct must be positive")

    if config.alpha_max_inventory_imbalance_pct < 0:
        errors.append("alpha_max_inventory_imbalance_pct must be non-negative")

    if config.alpha_max_pending_buys < 1:
        errors.append("alpha_max_pending_buys must be at least 1")

    if config.alpha_cycle_interval_seconds < 5:
        warnings.append("alpha_cycle_interval_seconds < 5 may hammer RPC")

    if config.alpha_breakout_pct <= 0:
        errors.append("alpha_breakout_pct must be positive")

    if config.alpha_structure_lookback < 3:
        errors.append("alpha_structure_lookback must be at least 3")

    from alpha.decision.price_history import VALID_PRICE_SOURCES

    src = (config.alpha_structure_price_source or "ask").strip().lower()
    if src not in VALID_PRICE_SOURCES:
        errors.append("alpha_structure_price_source must be bid, ask, mid, or last")

    chart_src = (config.alpha_chart_price_source or "mid").strip().lower()
    if chart_src not in VALID_PRICE_SOURCES:
        errors.append("alpha_chart_price_source must be bid, ask, mid, or last")

    if config.alpha_price_sample_interval_seconds < 0:
        errors.append("alpha_price_sample_interval_seconds must be >= 0")
    elif (
        config.alpha_price_sample_interval_seconds > 0
        and config.alpha_price_sample_interval_seconds < 5
    ):
        warnings.append("alpha_price_sample_interval_seconds < 5 may hammer RPC")

    if config.alpha_weakness_deviation <= 0 or config.alpha_strength_deviation <= 0:
        errors.append("alpha_weakness_deviation and alpha_strength_deviation must be positive")

    if config.alpha_max_slippage_pct <= 0:
        errors.append("alpha_max_slippage_pct must be positive")

    if config.alpha_base_order_size_xrp < config.min_order_size_xrp:
        warnings.append("alpha_base_order_size_xrp below min_order_size_xrp")

    if config.alpha_buy_limit_offset_pct < config.alpha_min_edge_threshold_pct:
        warnings.append(
            "alpha_buy_limit_offset_pct < alpha_min_edge_threshold_pct — buys may never pass edge gate"
        )

    if config.inventory_target_xrp_ratio <= 0 or config.inventory_target_xrp_ratio >= 1:
        errors.append("inventory_target_xrp_ratio must be between 0 and 1")

    errors.extend(validate_ta_config(config.alpha_technical_analysis))

    return AlphaConfigValidation(
        ok=not errors,
        errors=errors,
        warnings=warnings,
    )
