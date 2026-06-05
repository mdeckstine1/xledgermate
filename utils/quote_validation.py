"""Validate planned quotes against the live XRPL order book before live submission."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from core.runtime_state import QuoteIntent

# Small slack so clamped quotes stay inside validation after float rounding.
_TOUCH_TOLERANCE_PCT = 0.01


@dataclass
class QuoteValidationResult:
    """Outcome of comparing quote intents to live bid/ask/mid."""

    ok: bool
    summary: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checks: List[str] = field(default_factory=list)
    lines: List[Dict[str, Any]] = field(default_factory=list)
    # Bad RPC book (no mid, crossed, incomplete) — pause live orders but do not streak toward kill.
    book_unreliable: bool = False

    def summary_for_live(self) -> str:
        if self.ok:
            return "Spread check OK — quotes are near the live book."
        return "Spread check FAILED — " + "; ".join(self.errors[:2])


def _pct_diff(from_price: float, to_price: float) -> float:
    if from_price <= 0:
        return 0.0
    return ((to_price - from_price) / from_price) * 100.0


def validate_quotes_against_book(
    intents: Sequence[QuoteIntent],
    *,
    mid_price: Optional[float],
    best_bid: Optional[float],
    best_ask: Optional[float],
    max_half_spread_from_mid_pct: float = 1.0,
    max_worse_than_touch_pct: float = 0.50,
    max_improve_touch_pct: float = 0.15,
    require_intents_when_trading: bool = True,
) -> QuoteValidationResult:
    """
    Ensure planned offers are competitive vs the live book (not 8% off touch).

    - Ask must not be more than max_worse_than_touch_pct above best ask (too high to fill).
    - Bid must not be more than max_worse_than_touch_pct below best bid.
    - Quotes may improve touch slightly (cross toward mid) up to max_improve_touch_pct.
    - Each quote must be within max_half_spread_from_mid_pct of mid.
    """
    errors: List[str] = []
    warnings: List[str] = []
    checks: List[str] = []
    lines: List[Dict[str, Any]] = []

    if mid_price is None or mid_price <= 0:
        return QuoteValidationResult(
            ok=False,
            summary="Spread check skipped — no mid price.",
            errors=["No valid mid price for spread check"],
            book_unreliable=True,
        )

    if best_bid is None or best_ask is None or best_bid <= 0 or best_ask <= 0:
        return QuoteValidationResult(
            ok=False,
            summary="Spread check skipped — incomplete book.",
            errors=["Live best bid/ask required for spread check"],
            book_unreliable=True,
        )

    if best_ask < best_bid:
        errors.append(
            f"Inverted book (bid {best_bid:.6f} > ask {best_ask:.6f}) — check RLUSD pair"
        )
        return QuoteValidationResult(
            ok=False,
            summary="Spread check skipped — inverted book.",
            errors=errors,
            book_unreliable=True,
        )

    book_spread_pct = _pct_diff(best_bid, best_ask)
    checks.append(f"Book L1 spread {book_spread_pct:.3f}% (bid {best_bid:.6f} / ask {best_ask:.6f})")

    if not intents:
        if require_intents_when_trading:
            warnings.append("No quote intents generated this cycle")
        return QuoteValidationResult(
            ok=len(errors) == 0,
            summary="Spread check OK (no quotes planned)." if not errors else "Spread check FAILED.",
            errors=errors,
            warnings=warnings,
            checks=checks,
            lines=lines,
        )

    mid = float(mid_price)
    for intent in intents:
        price = float(intent.price)
        side = str(intent.side).lower()
        level = int(intent.level)
        vs_mid_pct = _pct_diff(mid, price)
        if side == "bid":
            vs_mid_pct = -vs_mid_pct

        line: Dict[str, Any] = {
            "level": level,
            "side": side,
            "price": price,
            "vs_mid_pct": round(vs_mid_pct, 4),
            "ok": True,
            "note": "",
        }

        if abs(vs_mid_pct) > max_half_spread_from_mid_pct:
            line["ok"] = False
            line["note"] = f">{max_half_spread_from_mid_pct:.2f}% from mid"
            errors.append(
                f"L{level} {side} {price:.6f} is {abs(vs_mid_pct):.2f}% from mid "
                f"(limit {max_half_spread_from_mid_pct:.2f}%)"
            )

        if side == "ask":
            touch = float(best_ask)
            vs_touch_pct = _pct_diff(touch, price)
            line["book_touch"] = touch
            line["vs_touch_pct"] = round(vs_touch_pct, 4)
            if vs_touch_pct > max_worse_than_touch_pct + _TOUCH_TOLERANCE_PCT:
                line["ok"] = False
                line["note"] = f"{vs_touch_pct:.2f}% above best ask (too high to fill)"
                errors.append(
                    f"L{level} ask {price:.6f} is {vs_touch_pct:.2f}% above best ask "
                    f"{touch:.6f} (max +{max_worse_than_touch_pct:.2f}%)"
                )
            elif vs_touch_pct < -max_improve_touch_pct - _TOUCH_TOLERANCE_PCT:
                line["ok"] = False
                line["note"] = f"{-vs_touch_pct:.2f}% below best ask (crossing book)"
                errors.append(
                    f"L{level} ask {price:.6f} crosses best ask by {-vs_touch_pct:.2f}% "
                    f"(max improve {max_improve_touch_pct:.2f}%)"
                )
            elif vs_touch_pct < 0:
                checks.append(
                    f"L{level} ask {price:.6f} improves touch by {-vs_touch_pct:.3f}%"
                )
            else:
                checks.append(
                    f"L{level} ask {price:.6f} is +{vs_touch_pct:.3f}% vs ask {touch:.6f}"
                )
            if price < best_bid:
                line["ok"] = False
                errors.append(f"L{level} ask {price:.6f} is below best bid {best_bid:.6f}")

        elif side == "bid":
            touch = float(best_bid)
            vs_touch_pct = _pct_diff(touch, price)
            line["book_touch"] = touch
            line["vs_touch_pct"] = round(vs_touch_pct, 4)
            if vs_touch_pct < -max_worse_than_touch_pct - _TOUCH_TOLERANCE_PCT:
                line["ok"] = False
                line["note"] = f"{-vs_touch_pct:.2f}% below best bid (too low to fill)"
                errors.append(
                    f"L{level} bid {price:.6f} is {-vs_touch_pct:.2f}% below best bid "
                    f"{touch:.6f} (max -{max_worse_than_touch_pct:.2f}%)"
                )
            elif vs_touch_pct > max_improve_touch_pct + _TOUCH_TOLERANCE_PCT:
                line["ok"] = False
                line["note"] = f"{vs_touch_pct:.2f}% above best bid (crossing book)"
                errors.append(
                    f"L{level} bid {price:.6f} crosses best bid by {vs_touch_pct:.2f}%"
                )
            elif vs_touch_pct > 0:
                checks.append(
                    f"L{level} bid {price:.6f} improves touch by {vs_touch_pct:.3f}%"
                )
            else:
                checks.append(
                    f"L{level} bid {price:.6f} is {vs_touch_pct:.3f}% vs bid {touch:.6f}"
                )
            if price > best_ask:
                line["ok"] = False
                errors.append(f"L{level} bid {price:.6f} is above best ask {best_ask:.6f}")
        else:
            line["ok"] = False
            errors.append(f"L{level} unknown side {side!r}")

        lines.append(line)

    ok = len(errors) == 0
    summary = (
        QuoteValidationResult(ok=True, summary="").summary_for_live()
        if ok
        else "Spread check FAILED — quotes not competitive vs live book."
    )
    return QuoteValidationResult(
        ok=ok,
        summary=summary,
        errors=errors,
        warnings=warnings,
        checks=checks,
        lines=lines,
    )
