"""
Unified dynamic quoting policy — profile ranges scaled by live market conditions.

Maps (profile bounds + market assessment + book + toxicity + momentum) → touch posture,
visibility caps, and size scale so quotes stay relevant on the book without blind pickoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.market_conditions import (
    CONDITION_DEFENSIVE,
    CONDITION_FAVORABLE,
    CONDITION_HOSTILE,
    CONDITION_NEUTRAL,
    MarketAssessment,
)
from core.perception import Profile
from core.toxicity import effective_toxic_ratio
from strategy.fill_quality import FillQualityState
from strategy.market_microstructure import MarketEdgeAssessment, assess_market_edge

TOUCH_AT = "at_touch"
TOUCH_NEAR = "near_touch"
TOUCH_SPREAD = "spread_mid"
TOUCH_OFF = "off"

_TIGHT_BOOK_MAX_SPREAD_PCT = 0.20


@dataclass(frozen=True)
class ProfileQuotingBounds:
    """Per-profile envelope — market health slides inside these limits."""

    min_edge_pct: float
    max_edge_pct: float
    min_touch_backoff_pct: float
    max_touch_backoff_pct: float
    min_off_touch_pct: float
    max_off_touch_pct: float
    min_touch_size_mult: float = 0.52
    max_touch_size_mult: float = 0.78


_PROFILE_BOUNDS: dict[str, ProfileQuotingBounds] = {
    "safe": ProfileQuotingBounds(
        min_edge_pct=0.10,
        max_edge_pct=0.12,
        min_touch_backoff_pct=0.02,
        max_touch_backoff_pct=0.12,
        min_off_touch_pct=0.08,
        max_off_touch_pct=0.14,
        min_touch_size_mult=0.55,
        max_touch_size_mult=0.72,
    ),
    "tight_spread": ProfileQuotingBounds(
        min_edge_pct=0.06,
        max_edge_pct=0.08,
        min_touch_backoff_pct=0.01,
        max_touch_backoff_pct=0.08,
        min_off_touch_pct=0.06,
        max_off_touch_pct=0.10,
        min_touch_size_mult=0.62,
        max_touch_size_mult=0.85,
    ),
    "high_volatility": ProfileQuotingBounds(
        min_edge_pct=0.11,
        max_edge_pct=0.15,
        min_touch_backoff_pct=0.04,
        max_touch_backoff_pct=0.10,
        min_off_touch_pct=0.10,
        max_off_touch_pct=0.16,
        min_touch_size_mult=0.48,
        max_touch_size_mult=0.65,
    ),
    "thin_liquidity": ProfileQuotingBounds(
        min_edge_pct=0.09,
        max_edge_pct=0.12,
        min_touch_backoff_pct=0.03,
        max_touch_backoff_pct=0.10,
        min_off_touch_pct=0.09,
        max_off_touch_pct=0.15,
        min_touch_size_mult=0.50,
        max_touch_size_mult=0.68,
    ),
    "profit_mode": ProfileQuotingBounds(
        min_edge_pct=0.04,
        max_edge_pct=0.06,
        min_touch_backoff_pct=0.01,
        max_touch_backoff_pct=0.06,
        min_off_touch_pct=0.05,
        max_off_touch_pct=0.08,
        min_touch_size_mult=0.70,
        max_touch_size_mult=0.92,
    ),
}


def profile_quoting_bounds(profile: Profile) -> ProfileQuotingBounds:
    """Profile-owned bounds; min_edge_pct on Profile overrides envelope floor."""
    name = (profile.name or "safe").strip().lower()
    base = _PROFILE_BOUNDS.get(name, _PROFILE_BOUNDS["safe"])
    edge = float(getattr(profile, "min_edge_pct", base.min_edge_pct))
    edge = max(base.min_edge_pct, min(base.max_edge_pct, edge))
    return ProfileQuotingBounds(
        min_edge_pct=edge,
        max_edge_pct=max(edge, base.max_edge_pct),
        min_touch_backoff_pct=base.min_touch_backoff_pct,
        max_touch_backoff_pct=base.max_touch_backoff_pct,
        min_off_touch_pct=base.min_off_touch_pct,
        max_off_touch_pct=base.max_off_touch_pct,
        min_touch_size_mult=base.min_touch_size_mult,
        max_touch_size_mult=base.max_touch_size_mult,
    )


@dataclass(frozen=True)
class DynamicQuotingPolicy:
    touch_mode: str
    join_touch: bool
    touch_backoff_pct: float
    max_worse_than_touch_pct: float
    touch_size_mult: float
    market_edge_met: bool
    capture_edge_pct: float
    required_edge_pct: float
    summary: str
    label: str


def _lerp(lo: float, hi: float, t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    return float(lo) + (float(hi) - float(lo)) * t


def _relevance_factor(assessment: MarketAssessment, profile: Profile) -> float:
    """0–1: higher = more competitive / visible quoting inside profile envelope."""
    health = max(0.0, min(1.0, float(assessment.health_score) / 100.0))
    cond_scale = {
        CONDITION_FAVORABLE: 1.0,
        CONDITION_NEUTRAL: 0.78,
        CONDITION_DEFENSIVE: 0.48,
        CONDITION_HOSTILE: 0.18,
    }.get(assessment.condition, 0.5)
    aggression = max(0.0, min(1.0, float(profile.aggression)))
    return max(0.0, min(1.0, health * cond_scale * (0.65 + 0.35 * aggression)))


def _book_needs_touch(book_spread_pct: float, spread_status: str) -> bool:
    return book_spread_pct > 0 and (
        book_spread_pct <= _TIGHT_BOOK_MAX_SPREAD_PCT
        or spread_status in ("tight", "normal")
    )


def resolve_dynamic_quoting_policy(
    *,
    profile: Profile,
    assessment: MarketAssessment,
    book_spread_pct: float,
    effective_min_edge_pct: float,
    effective_spread_l1_pct: float,
    xrpl_fee_bps: float = 2.0,
    fill_quality: Optional[FillQualityState] = None,
    mm_mode: bool = True,
    mid_momentum_pct: float = 0.0,
) -> DynamicQuotingPolicy:
    """
    Single resolver for touch posture and storefront visibility.

    Principles:
    - Never join bare touch when book cannot pay required edge (pickoff).
    - When thin but relevant, near-touch backoff tracks edge gap × market health.
    - When off touch, cap distance from L1 so quotes stay visible (≤8–14 bps by profile).
    - Toxicity and hostile conditions pull toward spread_mid / off.
    """
    bounds = profile_quoting_bounds(profile)
    fq = fill_quality or FillQualityState()
    toxic = effective_toxic_ratio(fq)
    no_touch_ratio = float(profile.toxic_no_touch_ratio)
    relevance = _relevance_factor(assessment, profile)
    required = float(effective_min_edge_pct) + float(xrpl_fee_bps) / 100.0

    market_edge = assess_market_edge(
        book_spread_pct=book_spread_pct,
        our_l1_spread_pct=max(0.01, effective_spread_l1_pct),
        min_edge_pct=float(effective_min_edge_pct),
        xrpl_fee_bps=xrpl_fee_bps,
    )

    max_worse = _lerp(bounds.max_off_touch_pct, bounds.min_off_touch_pct, relevance)
    touch_size = _lerp(bounds.min_touch_size_mult, bounds.max_touch_size_mult, relevance)

    parts: list[str] = [
        f"dynamic policy ({profile.name}): {assessment.condition_label} "
        f"health {assessment.health_score:.0f}/100"
    ]

    if fq.recent_fills >= 3 and toxic >= no_touch_ratio:
        parts.append(
            f"toxicity {toxic:.0%} → no touch (limit {no_touch_ratio:.0%})"
        )
        label = f"Policy: off-book (toxic {toxic:.0%}) | max {max_worse * 100:.2f}% from touch"
        return DynamicQuotingPolicy(
            touch_mode=TOUCH_OFF,
            join_touch=False,
            touch_backoff_pct=0.0,
            max_worse_than_touch_pct=max_worse,
            touch_size_mult=touch_size * 0.85,
            market_edge_met=market_edge.met,
            capture_edge_pct=market_edge.capture_edge_pct,
            required_edge_pct=required,
            summary="; ".join(parts),
            label=label,
        )

    if assessment.condition == CONDITION_HOSTILE:
        parts.append("hostile → spread from mid, capital preservation")
        label = f"Policy: spread-mid (hostile) | visible ≤{max_worse * 100:.2f}%"
        return DynamicQuotingPolicy(
            touch_mode=TOUCH_SPREAD,
            join_touch=False,
            touch_backoff_pct=0.0,
            max_worse_than_touch_pct=max_worse,
            touch_size_mult=touch_size * 0.75,
            market_edge_met=market_edge.met,
            capture_edge_pct=market_edge.capture_edge_pct,
            required_edge_pct=required,
            summary="; ".join(parts),
            label=label,
        )

    if not mm_mode:
        parts.append("rebalance mode → touch rules set by inventory path")
        label = "Policy: rebalance (inventory-driven touch)"
        return DynamicQuotingPolicy(
            touch_mode=TOUCH_SPREAD,
            join_touch=False,
            touch_backoff_pct=0.0,
            max_worse_than_touch_pct=max_worse,
            touch_size_mult=1.0,
            market_edge_met=market_edge.met,
            capture_edge_pct=market_edge.capture_edge_pct,
            required_edge_pct=required,
            summary="; ".join(parts),
            label=label,
        )

    half_book = float(book_spread_pct) / 2.0 if book_spread_pct > 0 else 0.0
    needs_touch = _book_needs_touch(book_spread_pct, assessment.book_spread_status)

    if market_edge.met and needs_touch:
        backoff = _lerp(
            bounds.min_touch_backoff_pct,
            bounds.max_touch_backoff_pct,
            1.0 - relevance * 0.65,
        )
        if assessment.condition == CONDITION_DEFENSIVE:
            backoff = max(backoff, 0.05)
        parts.append(
            f"edge met → at touch backoff {backoff:.3f}% "
            f"(book {book_spread_pct:.3f}%, capture {market_edge.capture_edge_pct:+.3f}%)"
        )
        label = (
            f"Policy: at-touch backoff {backoff:.3f}% | "
            f"relevant (≤{max_worse * 100:.2f}% off touch)"
        )
        return DynamicQuotingPolicy(
            touch_mode=TOUCH_AT,
            join_touch=True,
            touch_backoff_pct=backoff,
            max_worse_than_touch_pct=max(max_worse, 0.50),
            touch_size_mult=touch_size,
            market_edge_met=True,
            capture_edge_pct=market_edge.capture_edge_pct,
            required_edge_pct=required,
            summary="; ".join(parts),
            label=label,
        )

    if market_edge.met and not needs_touch:
        parts.append("edge met + wide book → competitive spread from mid")
        label = f"Policy: spread-mid (edge met) | visible ≤{max_worse * 100:.2f}%"
        return DynamicQuotingPolicy(
            touch_mode=TOUCH_SPREAD,
            join_touch=False,
            touch_backoff_pct=0.0,
            max_worse_than_touch_pct=max_worse,
            touch_size_mult=touch_size,
            market_edge_met=True,
            capture_edge_pct=market_edge.capture_edge_pct,
            required_edge_pct=required,
            summary="; ".join(parts),
            label=label,
        )

    if (
        assessment.condition in (CONDITION_FAVORABLE, CONDITION_NEUTRAL)
        and book_spread_pct > 0
        and half_book < required
    ):
        gap = required - half_book
        backoff = max(
            bounds.min_touch_backoff_pct,
            min(
                bounds.max_touch_backoff_pct,
                gap * 100.0 * (0.82 + 0.18 * relevance),
            ),
        )
        if mid_momentum_pct >= 0.06:
            backoff = min(bounds.max_touch_backoff_pct, backoff * 1.08)
        elif mid_momentum_pct <= -0.06:
            backoff = max(bounds.min_touch_backoff_pct, backoff * 0.92)
        parts.append(
            f"thin book → near-touch backoff {backoff:.3f}% "
            f"(book {book_spread_pct:.3f}% < need {required:.3f}%)"
        )
        label = (
            f"Policy: near-touch {backoff:.3f}% | "
            f"relevant ≤{max_worse * 100:.2f}% from touch"
        )
        return DynamicQuotingPolicy(
            touch_mode=TOUCH_NEAR,
            join_touch=True,
            touch_backoff_pct=backoff,
            max_worse_than_touch_pct=max(max_worse, 0.50),
            touch_size_mult=touch_size,
            market_edge_met=False,
            capture_edge_pct=market_edge.capture_edge_pct,
            required_edge_pct=required,
            summary="; ".join(parts),
            label=label,
        )

    if assessment.condition == CONDITION_DEFENSIVE:
        touch_size *= 0.88
        parts.append("defensive + thin edge → spread-mid with tight visibility cap")

    parts.append(
        f"step off touch (book {book_spread_pct:.3f}% vs need {required:.3f}%)"
    )
    label = f"Policy: spread-mid | visible ≤{max_worse * 100:.2f}% from touch"
    return DynamicQuotingPolicy(
        touch_mode=TOUCH_SPREAD,
        join_touch=False,
        touch_backoff_pct=0.0,
        max_worse_than_touch_pct=max_worse,
        touch_size_mult=touch_size,
        market_edge_met=market_edge.met,
        capture_edge_pct=market_edge.capture_edge_pct,
        required_edge_pct=required,
        summary="; ".join(parts),
        label=label,
    )


def apply_dynamic_quoting_policy(
    adj,
    policy: DynamicQuotingPolicy,
    *,
    parts: list[str],
) -> None:
    """Write resolved policy onto QuoteAdjustments."""
    parts.append(policy.summary)
    adj.join_touch = policy.join_touch
    adj.touch_backoff_pct = policy.touch_backoff_pct
    adj.touch_mode = policy.touch_mode
    adj.max_worse_than_touch_pct = policy.max_worse_than_touch_pct
    adj.quoting_policy_label = policy.label
    adj.market_edge_met = policy.market_edge_met
    adj.market_edge_pct = policy.capture_edge_pct
    if policy.touch_size_mult != 1.0:
        adj.size_multiplier *= policy.touch_size_mult
