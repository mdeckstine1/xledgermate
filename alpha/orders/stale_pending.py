"""Shared stale pending-buy policy (OrderManager + SKYNET context)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from alpha.precision import (
    DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS,
    clamp_price_decimals,
    price_eps,
    round_rlusd_price,
)


def target_buy_limit_price(
    mid: float,
    offset_pct: float,
    *,
    bid_offset_pct: float = 0.0,
    price_decimals: int = DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS,
) -> float:
    if offset_pct <= 0:
        offset_pct = bid_offset_pct
    raw = mid * (1.0 - offset_pct / 100.0)
    return round_rlusd_price(raw, price_decimals, direction="down")


def target_sell_limit_price(
    mid: float,
    offset_pct: float,
    *,
    price_decimals: int = DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS,
) -> float:
    """Passive inventory ask: mid * (1 + offset%)."""
    if offset_pct < 0:
        offset_pct = 0.0
    raw = mid * (1.0 + offset_pct / 100.0)
    return round_rlusd_price(raw, price_decimals, direction="up")


def stale_pending_buy_reason(
    entry: float,
    mid: float,
    *,
    offset_pct: float,
    max_drift_pct: float,
    stale_enabled: bool,
    max_age_seconds: float = 0.0,
    age_seconds: Optional[float] = None,
    bid_offset_pct: float = 0.0,
    price_decimals: int = DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS,
) -> Optional[str]:
    """Return cancel reason when a resting bid no longer matches current entry policy."""
    eps = price_eps(price_decimals)
    if not stale_enabled:
        return None
    if mid <= 0 or entry <= 0:
        return None

    if max_drift_pct > 0:
        if entry > mid + eps:
            overshoot_pct = (entry - mid) / mid * 100.0
            return f"entry_above_mid={overshoot_pct:.3f}%"

        if mid > entry + eps:
            passed_pct = (mid - entry) / mid * 100.0
            if passed_pct > max_drift_pct + eps:
                return f"mid_passed_entry={passed_pct:.3f}%>{max_drift_pct:g}%"

        target = target_buy_limit_price(
            mid,
            offset_pct,
            bid_offset_pct=bid_offset_pct,
            price_decimals=price_decimals,
        )
        drift_pct = abs(entry - target) / mid * 100.0
        if drift_pct > max_drift_pct + eps:
            return f"entry_drift={drift_pct:.3f}%>{max_drift_pct:g}%"

    if max_age_seconds > 0 and age_seconds is not None and age_seconds > max_age_seconds:
        return f"age={age_seconds:.0f}s>{max_age_seconds:.0f}s"
    return None


def stale_pending_sell_reason(
    ask: float,
    mid: float,
    *,
    offset_pct: float,
    max_drift_pct: float,
    stale_enabled: bool,
    max_age_seconds: float = 0.0,
    age_seconds: Optional[float] = None,
    price_decimals: int = DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS,
) -> Optional[str]:
    """
    Return cancel reason when a resting inventory ask no longer matches policy.

    Strength/harvest/reload asks sit *above* mid. When mid falls away, zombies
    occupy max_pending_sells and brick autonomous trims — cancel so the next
    cycle can re-place near the current target.
    """
    eps = price_eps(price_decimals)
    if not stale_enabled:
        return None
    if mid <= 0 or ask <= 0:
        return None

    # Ask below mid is marketable / filling path — do not cancel as "stale high".
    if ask + eps < mid:
        if max_age_seconds > 0 and age_seconds is not None and age_seconds > max_age_seconds:
            return f"age={age_seconds:.0f}s>{max_age_seconds:.0f}s"
        return None

    if max_drift_pct > 0:
        # Gap from mid beyond intentional offset + allowed drift → zombie.
        above_mid_pct = max(0.0, (ask - mid) / mid * 100.0)
        allowed_above = max(0.0, float(offset_pct)) + float(max_drift_pct)
        if above_mid_pct > allowed_above + eps:
            return (
                f"ask_above_mid={above_mid_pct:.3f}%>"
                f"offset+drift={allowed_above:g}%"
            )

        target = target_sell_limit_price(mid, offset_pct, price_decimals=price_decimals)
        if ask > target + eps:
            drift_pct = (ask - target) / mid * 100.0
            if drift_pct > max_drift_pct + eps:
                return f"ask_drift={drift_pct:.3f}%>{max_drift_pct:g}%"

    if max_age_seconds > 0 and age_seconds is not None and age_seconds > max_age_seconds:
        return f"age={age_seconds:.0f}s>{max_age_seconds:.0f}s"
    return None


def _parse_age_seconds(created_at: Any) -> Optional[float]:
    if not created_at:
        return None
    try:
        if isinstance(created_at, datetime):
            ts = created_at
        else:
            ts = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(tz=timezone.utc) - ts).total_seconds()
    except (TypeError, ValueError):
        return None


def build_pending_buy_stale_snapshot(
    *,
    mid: float,
    operator_config: Dict[str, Any],
    pending_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Summarize which pending buys are stale under current operator knobs."""
    offset = float(operator_config.get("alpha_buy_limit_offset_pct") or 0.15)
    max_drift = float(operator_config.get("alpha_stale_pending_buy_max_drift_pct") or 0.15)
    max_age = float(operator_config.get("alpha_stale_pending_buy_max_age_seconds") or 0.0)
    stale_on = operator_config.get("alpha_stale_pending_buy_enabled", True) is not False
    cap = int(operator_config.get("alpha_max_pending_buys") or 1)
    bid_offset = float(operator_config.get("alpha_bid_offset_pct") or 0.0)
    dec = price_decimals_from_config(operator_config)

    target = target_buy_limit_price(mid, offset, bid_offset_pct=bid_offset, price_decimals=dec) if mid > 0 else 0.0
    rows: List[Dict[str, Any]] = []
    would_cancel = 0
    for record in pending_records:
        if str(record.get("state") or "") != "pending_buy":
            continue
        entry = float(record.get("entry") or 0.0)
        if entry <= 0:
            continue
        age_s = _parse_age_seconds(record.get("created_at"))
        reason = stale_pending_buy_reason(
            entry,
            mid,
            offset_pct=offset,
            max_drift_pct=max_drift,
            stale_enabled=stale_on,
            max_age_seconds=max_age,
            age_seconds=age_s,
            bid_offset_pct=bid_offset,
            price_decimals=dec,
        )
        drift_pct = abs(entry - target) / mid * 100.0 if mid > 0 and target > 0 else 0.0
        passed_pct = (mid - entry) / mid * 100.0 if mid > entry else 0.0
        if reason:
            would_cancel += 1
        rows.append(
            {
                "bracket_id": record.get("bracket_id"),
                "entry": round_rlusd_price(entry, dec),
                "buy_sequence": record.get("buy_sequence"),
                "drift_pct": round(drift_pct, 3),
                "mid_passed_pct": round(passed_pct, 3),
                "would_cancel": bool(reason),
                "reason": reason,
            }
        )

    over_cap = max(0, len(rows) - cap)
    return {
        "stale_enabled": stale_on,
        "buy_limit_offset_pct": offset,
        "max_drift_pct": max_drift,
        "max_age_seconds": max_age,
        "max_pending_buys": cap,
        "price_decimals": dec,
        "target_entry": target,
        "pending_count": len(rows),
        "would_cancel_count": would_cancel,
        "would_keep_count": len(rows) - would_cancel,
        "over_cap_count": over_cap,
        "note": (
            "Limit bids fill when best ask hits the bid, not when mid crosses entry. "
            "Cancels run one ledger offer per engine cycle (~cycle_interval_seconds). "
            "Align max_drift_pct with buy_limit_offset_pct to avoid ladder clutter."
        ),
        "pending_bids": rows[:25],
    }


def price_decimals_from_config(operator_config: Dict[str, Any]) -> int:
    raw = operator_config.get("alpha_rlusd_price_decimals")
    if raw is None:
        return DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS
    try:
        return clamp_price_decimals(int(raw))
    except (TypeError, ValueError):
        return DEFAULT_ALPHA_RLUSD_PRICE_DECIMALS
