"""Operator status marquee — network, ledger, spread, session posture (no HTML boxes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from gui.ticker import TickerItem, _add


@dataclass(frozen=True)
class StatusTickerInput:
    dry_run: bool
    is_testnet: bool
    engine_running: bool
    has_bot_account: bool
    config_network_mismatch: bool
    engine_network: str
    saved_network: str
    profile_sync_text: str
    kill_switch_active: bool
    kill_switch_reason: str
    open_offers_count: int
    offers_at_touch: Optional[bool]
    quote_visibility_summary: str
    join_touch_active: Optional[bool]
    pause_bids: bool
    pause_asks: bool
    inventory_mode: str
    cycle_count: int
    spread_check_failed: bool
    spread_check_error: str
    session_status: str = ""
    session_headline: str = ""
    market_condition_label: str = ""
    last_execution_summary: str = ""


def build_status_ticker_items(inp: StatusTickerInput) -> list[TickerItem]:
    """Ordered operator alerts for the top status marquee."""
    items: list[TickerItem] = []
    seen: set[str] = set()

    if inp.kill_switch_active:
        reason = (inp.kill_switch_reason or "trading halted").strip()
        _add(
            items,
            seen,
            text=f"Kill switch — {reason}",
            kind="danger",
            priority=0,
        )

    if inp.config_network_mismatch:
        _add(
            items,
            seen,
            text=(
                f"Config mismatch — engine on {inp.engine_network.upper()}, "
                f"saved config {inp.saved_network.upper()}"
            ),
            kind="warn",
            priority=1,
        )

    if inp.profile_sync_text:
        _add(items, seen, text=inp.profile_sync_text, kind="warn", priority=1)

    if not inp.has_bot_account:
        _add(
            items,
            seen,
            text="Set bot account under Advanced → Bot account",
            kind="warn",
            priority=2,
        )

    if not inp.dry_run and not inp.is_testnet:
        _add(
            items,
            seen,
            text="Mainnet live — real orders on the ledger; spread check each cycle",
            kind="danger",
            priority=2,
        )
    elif inp.dry_run and not inp.is_testnet:
        _add(
            items,
            seen,
            text="Dry-run — quotes planned only; nothing submits to mainnet",
            kind="info",
            priority=3,
        )

    if not inp.dry_run and inp.is_testnet:
        _add(
            items,
            seen,
            text="Testnet live — real testnet orders (play money)",
            kind="warn",
            priority=3,
        )

    if inp.session_headline and inp.session_status in ("defensive", "cautious"):
        kind = "warn" if inp.session_status == "defensive" else "info"
        _add(items, seen, text=inp.session_headline, kind=kind, priority=2)

    if inp.market_condition_label:
        cond = inp.market_condition_label.strip()
        kind = "warn" if "defensive" in cond.casefold() or "hostile" in cond.casefold() else "info"
        _add(items, seen, text=f"Market: {cond}", kind=kind, priority=4)

    if inp.engine_running and not inp.dry_run:
        if inp.open_offers_count > 0:
            if inp.offers_at_touch is False:
                summary = (inp.quote_visibility_summary or "quotes off touch").strip()
                if "refresh paused" in inp.last_execution_summary.casefold():
                    hint = " — stale offers cancelled each cycle; new quotes when pause lifts"
                elif inp.join_touch_active is False:
                    hint = " — restart engine if policy stuck off-book"
                else:
                    hint = ""
                _add(
                    items,
                    seen,
                    text=f"Storefront hidden — {summary}{hint}",
                    kind="danger",
                    priority=2,
                )
            elif (
                inp.pause_asks
                and not inp.pause_bids
                and inp.inventory_mode.lower() == "rebalance"
            ):
                _add(
                    items,
                    seen,
                    text="One-sided rebalance — RLUSD-heavy: bids only (buy XRP)",
                    kind="warn",
                    priority=3,
                )
        elif inp.open_offers_count == 0:
            _add(
                items,
                seen,
                text="No offers on the ledger — nothing for takers to hit",
                kind="warn",
                priority=2,
            )

    if not inp.is_testnet and inp.cycle_count > 0 and inp.spread_check_failed:
        err = (inp.spread_check_error or "spread validation failed").strip()
        _add(
            items,
            seen,
            text=f"Spread check failed — live orders blocked: {err}",
            kind="danger",
            priority=1,
        )

    items.sort(key=lambda item: (item.priority, item.text.casefold()))
    return items[:12]
