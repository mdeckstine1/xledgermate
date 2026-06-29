"""Inventory posture from balances — portfolio % sizing and imbalance guardrails."""

from __future__ import annotations

import logging

from alpha.types import BalanceSnapshot, InventorySnapshot
from config.settings import BotConfig
from risk.inventory_limits import assess_inventory_limits, cap_leg_size_for_inventory

logger = logging.getLogger(__name__)


def _inventory_label(deviation: float) -> str:
    if deviation >= 0.15:
        return "heavy_xrp"
    if deviation >= 0.08:
        return "xrp_heavy"
    if deviation <= -0.15:
        return "heavy_rlusd"
    if deviation <= -0.08:
        return "rlusd_heavy"
    return "balanced"


class InventoryManager:
    """Portfolio skew vs target; real-time allocation % and entry sizing caps."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config

    def snapshot(self, balances: BalanceSnapshot) -> InventorySnapshot:
        mid = balances.mid_rlusd_per_xrp
        portfolio = balances.portfolio_xrp_equiv
        max_imbalance = self._config.alpha_max_inventory_imbalance_pct

        if mid is None or mid <= 0:
            return InventorySnapshot(
                xrp_ratio=0.5,
                target_xrp_ratio=self._config.inventory_target_xrp_ratio,
                deviation=0.0,
                label="unknown",
                pause_bids=True,
                pause_asks=True,
                summary="No mid price — inventory unknown",
                portfolio_xrp_equiv=portfolio,
            )

        xrp_value = balances.xrp
        rlusd_value = balances.rlusd / mid
        total = xrp_value + rlusd_value
        ratio = 0.5 if total <= 0 else xrp_value / total

        target = self._config.inventory_target_xrp_ratio
        deviation = ratio - target
        label = _inventory_label(deviation)

        xrp_alloc = ratio * 100.0
        rlusd_alloc = (1.0 - ratio) * 100.0
        buy_blocked = deviation > max_imbalance
        sell_blocked = deviation < -max_imbalance

        limits = assess_inventory_limits(
            xrp_ratio=ratio,
            target_xrp_ratio=target,
            max_deviation=self._config.inventory_max_deviation,
            inventory_mode=self._config.inventory_mode,
            hard_pause_deviation=self._config.inventory_hard_pause_deviation,
        )

        summary = (
            f"alloc XRP={xrp_alloc:.1f}% RLUSD={rlusd_alloc:.1f}% | "
            f"target={target:.0%} dev={deviation:+.3f} | "
            f"buy_block={buy_blocked} sell_block={sell_blocked} | "
            f"pause_bids={limits.pause_bids} pause_asks={limits.pause_asks}"
        )
        logger.info("inventory_snapshot | %s | label=%s", summary, label)

        return InventorySnapshot(
            xrp_ratio=ratio,
            target_xrp_ratio=target,
            deviation=deviation,
            label=label,
            pause_bids=limits.pause_bids or buy_blocked,
            pause_asks=limits.pause_asks or sell_blocked,
            summary=summary,
            portfolio_xrp_equiv=portfolio,
            xrp_allocation_pct=xrp_alloc,
            rlusd_allocation_pct=rlusd_alloc,
            buy_blocked_imbalance=buy_blocked,
            sell_blocked_imbalance=sell_blocked,
        )

    def allows_buy(self, inventory: InventorySnapshot) -> bool:
        if inventory.pause_bids or inventory.buy_blocked_imbalance:
            return False
        return inventory.deviation <= -self._config.alpha_weakness_deviation

    def allows_sell(self, inventory: InventorySnapshot) -> bool:
        if inventory.pause_asks or inventory.sell_blocked_imbalance:
            return False
        return inventory.deviation >= self._config.alpha_strength_deviation

    def cap_entry_size_xrp(
        self,
        *,
        side: str,
        size_xrp: float,
        balances: BalanceSnapshot,
        inventory: InventorySnapshot,
        risk_per_trade_pct: float | None = None,
    ) -> float:
        """Shrink entry to respect portfolio % and inventory overshoot rules."""
        mid = balances.mid_rlusd_per_xrp
        if mid is None or mid <= 0 or size_xrp <= 0:
            return 0.0

        capped = cap_leg_size_for_inventory(
            side=side,
            size_xrp=size_xrp,
            xrp_balance=balances.xrp,
            rlusd_balance=balances.rlusd,
            mid_price=mid,
            target_xrp_ratio=inventory.target_xrp_ratio,
            xrp_reserve=self._config.xrp_reserve,
            inventory_mode="rebalance",
            overshoot_slack=0.0,
            pause_bids=inventory.pause_bids,
            pause_asks=inventory.pause_asks,
            min_size=self._config.min_order_size_xrp,
        )
        pct = risk_per_trade_pct if risk_per_trade_pct is not None else self._config.alpha_risk_per_trade_pct
        if inventory.portfolio_xrp_equiv > 0 and pct > 0:
            risk_cap = inventory.portfolio_xrp_equiv * (pct / 100.0)
            capped = min(capped, risk_cap)
        return round(max(0.0, capped), 4)
