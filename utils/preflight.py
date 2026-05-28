"""Pre-cycle checks before quoting or placing orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from config.settings import BotConfig


@dataclass
class PreflightResult:
    ready: bool
    checks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ready:
            return "Preflight OK — ready to quote."
        return "Preflight FAILED — " + "; ".join(self.errors[:3])


def evaluate_preflight(
    *,
    config: BotConfig,
    xrp_balance: float,
    rlusd_balance: float,
    trust_line_limit: Optional[float],
    has_trust_line: bool,
    mid_price: Optional[float],
    kill_switch_active: bool,
    xrp_reserve: float = 12.0,
    min_order_xrp: float = 1.0,
) -> PreflightResult:
    checks: List[str] = []
    warnings: List[str] = []
    errors: List[str] = []

    if not config.bot_account_address.strip():
        errors.append("bot_account_address is not set")
    else:
        checks.append("Bot account configured")

    if not config.dry_run and not (config.bot_secret_key or "").strip():
        errors.append("bot_secret_key required for live trading")

    if config.testnet:
        checks.append("Network: testnet")
    else:
        warnings.append("Network: mainnet — real funds")

    if kill_switch_active:
        errors.append("Kill switch is active")

    if mid_price is None or mid_price <= 0:
        errors.append("No valid mid price from order book")
    else:
        checks.append(f"Mid price OK ({mid_price:.6f} RLUSD/XRP)")

    if config.fund_with_xrp_only:
        checks.append("Funding mode: XRP only (sell-XRP / ask quotes)")
        if xrp_balance >= min_order_xrp:
            checks.append("XRP balance OK for ask quotes")
        if not has_trust_line:
            warnings.append(
                f"No RLUSD trust line yet — OK for dry-run and planning. "
                f"Run setup-trust before live asks (you receive RLUSD when sells fill)."
            )
        elif rlusd_balance <= 0:
            warnings.append(
                "RLUSD balance is 0 — bid (buy XRP) quotes disabled until you hold RLUSD"
            )
        else:
            checks.append(f"RLUSD available ({rlusd_balance:.4f}) — two-sided quoting enabled")
    elif not has_trust_line:
        msg = (
            f"No RLUSD trust line to issuer {config.resolved_rlusd_issuer()}. "
            "Create a trust line before live trading."
        )
        if config.dry_run:
            warnings.append(msg)
        else:
            errors.append(msg)
    else:
        checks.append(f"RLUSD trust line exists (limit {trust_line_limit or 0:.2f})")
        if rlusd_balance <= 0:
            warnings.append("RLUSD balance is 0 — bid quotes disabled until you hold RLUSD")

    spendable_xrp = max(0.0, xrp_balance - xrp_reserve)
    if spendable_xrp < min_order_xrp:
        errors.append(
            f"Not enough spendable XRP ({spendable_xrp:.2f}) after {xrp_reserve:.0f} XRP reserve"
        )
    else:
        checks.append(f"Spendable XRP: {spendable_xrp:.2f}")

    active_sizes = [s for s in config.order_sizes if s > 0]
    if not active_sizes:
        errors.append("All order_sizes are 0 — set at least one level size in config")
    else:
        checks.append(f"Active order levels: {len(active_sizes)}")

    if xrp_balance > config.risk_capital_xrp * 1.05:
        warnings.append(
            f"Wallet XRP ({xrp_balance:.0f}) exceeds risk_capital_xrp "
            f"({config.risk_capital_xrp:.0f}) — caps still apply to quote sizes"
        )

    ready = len(errors) == 0
    return PreflightResult(ready=ready, checks=checks, warnings=warnings, errors=errors)
