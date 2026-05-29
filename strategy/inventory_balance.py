"""RLUSD / XRP inventory steering and rebalance guidance (advisory — no auto-swap)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RebalanceAdvice:
    action: str
    label: str
    summary: str
    suggested_xrp_to_convert: float = 0.0
    target_rlusd_after: float = 0.0


def assess_rebalance_need(
    *,
    xrp_balance: float,
    rlusd_balance: float,
    mid_price: float,
    target_xrp_ratio: float,
    spendable_xrp: float,
    xrp_reserve: float,
    min_order_xrp: float,
    fund_with_xrp_only: bool,
) -> RebalanceAdvice:
    """
    Recommend how to steer inventory without executing swaps on behalf of the operator.
    """
    if mid_price <= 0:
        return RebalanceAdvice(
            action="wait",
            label="unknown",
            summary="No valid mid — cannot assess inventory balance.",
        )

    total_xrp_equiv = xrp_balance + (rlusd_balance / mid_price)
    if total_xrp_equiv <= 0:
        return RebalanceAdvice(
            action="wait",
            label="empty",
            summary="No portfolio value to assess.",
        )

    ratio = xrp_balance / total_xrp_equiv
    deviation = ratio - target_xrp_ratio
    target_xrp = total_xrp_equiv * target_xrp_ratio
    target_rlusd = (total_xrp_equiv - target_xrp) * mid_price

    if fund_with_xrp_only and rlusd_balance <= min_order_xrp * mid_price * 0.5:
        return RebalanceAdvice(
            action="sell_xrp_via_asks",
            label="xrp_funded",
            summary=(
                "XRP-only mode: quote competitive asks to accumulate RLUSD from fills. "
                "Bids stay off until you hold RLUSD. When you have enough RLUSD, swap or "
                "fund manually to enable two-sided quoting and inventory balance."
            ),
            suggested_xrp_to_convert=0.0,
            target_rlusd_after=target_rlusd,
        )

    if abs(deviation) <= 0.06:
        return RebalanceAdvice(
            action="hold",
            label="balanced",
            summary=(
                f"Inventory near target (XRP {ratio:.0%} vs target {target_xrp_ratio:.0%}). "
                "Skew quotes lightly to maintain balance."
            ),
            target_rlusd_after=target_rlusd,
        )

    if deviation > 0.06:
        excess_xrp = max(0.0, xrp_balance - target_xrp - xrp_reserve)
        convert = min(excess_xrp, spendable_xrp * 0.25)
        return RebalanceAdvice(
            action="reduce_xrp",
            label="xrp_heavy",
            summary=(
                f"XRP-heavy ({ratio:.0%} vs target {target_xrp_ratio:.0%}): "
                "quote asks more aggressively; consider swapping "
                f"~{convert:.1f} XRP → RLUSD on-ledger when ready for two-sided quoting."
            ),
            suggested_xrp_to_convert=max(0.0, convert),
            target_rlusd_after=target_rlusd,
        )

    deficit_rlusd = max(0.0, target_rlusd - rlusd_balance)
    return RebalanceAdvice(
        action="accumulate_rlusd",
        label="rlusd_heavy",
        summary=(
            f"RLUSD-heavy ({ratio:.0%} XRP vs target {target_xrp_ratio:.0%}): "
            "quote bids more aggressively; pause or widen asks until XRP ratio recovers."
        ),
        suggested_xrp_to_convert=0.0,
        target_rlusd_after=target_rlusd,
    )
