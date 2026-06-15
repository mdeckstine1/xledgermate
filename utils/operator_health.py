"""Single operator-facing health summary (engine + ledger + toxicity + book)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional

from connectors.xrpl_connector import is_book_crossed, is_trustworthy_rlusd_mid
from core.perception import get_profile


@dataclass
class OperatorHealth:
    status: str  # ok | cautious | defensive | misconfigured
    headline: str
    bullets: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)


def _book_ok(runtime: Mapping[str, Any]) -> tuple[bool, str]:
    bid = runtime.get("best_bid_rlusd_per_xrp")
    ask = runtime.get("best_ask_rlusd_per_xrp")
    mid = runtime.get("mid_price")
    if bid is None or ask is None:
        return True, "Book not loaded yet."
    if is_book_crossed(
        float(bid) if bid is not None else None,
        float(ask) if ask is not None else None,
    ):
        return False, f"Book **crossed** (bid {float(bid):.4f} > ask {float(ask):.4f}) — mid/P&L unreliable."
    if mid is not None and not is_trustworthy_rlusd_mid(
        float(mid),
        best_bid=float(bid),
        best_ask=float(ask),
    ):
        return False, "Mid **not trustworthy** for RLUSD/XRP — check BookOffers."
    spread = float(runtime.get("book_spread_pct") or 0)
    if spread > 0 and spread < 0.12:
        return True, f"Book very tight ({spread:.3f}%) — engine may quote **defensive only**."
    return True, f"Book OK (spread {spread:.3f}%)." if spread else "Book OK."


def build_operator_health(
    runtime: Mapping[str, Any],
    *,
    engine_running: bool,
    profile_name: str = "safe",
    ledger_offer_count: Optional[int] = None,
) -> OperatorHealth:
    """
    One checklist: is the bot wired correctly and are metrics meaningful?

    ledger_offer_count: live RPC count when engine stopped (overrides stale runtime).
    """
    profile = get_profile((profile_name or "safe").strip().lower())
    min_gate_fills = int(getattr(profile, "toxic_min_fills_for_gates", 8))
    toxic_limit = float(profile.toxic_refresh_pause_ratio)
    is_ws = (
        runtime.get("as_mode") == "pure"
        or runtime.get("price_source") == "ws_book_feed"
    )

    fills = int(runtime.get("fills_session") or 0)
    toxic = float(runtime.get("toxic_fill_ratio") or 0)
    toxic_30 = float(runtime.get("toxic_fill_ratio_30s") or 0)
    last_exec = str(runtime.get("last_execution_summary") or "")
    refresh_paused = "Refresh paused" in last_exec or "refresh paused" in last_exec.lower()

    runtime_offers = int(runtime.get("open_offers_count") or 0)
    live_offers = (
        ledger_offer_count
        if ledger_offer_count is not None
        else runtime_offers
    )

    bullets: List[str] = []
    actions: List[str] = []
    status = "ok"

    if engine_running:
        if is_ws:
            cycle_s = int(runtime.get("book_poll_interval_seconds") or 8)
            bullets.append(
                f"**ws-engine live** — WS book + pure A-S (~{cycle_s}s cycle, not HTTP poll)."
            )
        else:
            bullets.append("**Engine running** — metrics update each cycle (~15–60s poll).")
    else:
        bullets.append("**Engine stopped** — use ledger sync for balances/offers; session P&L is frozen.")
        if live_offers > 0:
            status = "cautious"
            bullets.append(
                f"**{live_offers} offer(s) still on the DEX** — stop does not cancel. "
                "Cancel before a clean Gate 2 pilot run."
            )
            actions.append("Cancel all offers (Controls or Advanced → Safety), then Sync from ledger.")

    if ledger_offer_count is not None and ledger_offer_count != runtime_offers:
        bullets.append(
            f"Display was stale ({runtime_offers} in file vs **{ledger_offer_count}** on ledger) — refreshed."
        )

    book_ok, book_msg = _book_ok(runtime)
    bullets.append(book_msg)
    if not book_ok:
        status = "misconfigured" if status == "ok" else status
        actions.append("Do not trust portfolio/toxic until book bid/ask look sane; restart after v1.4.4+ book fix.")

    if not bool(runtime.get("market_edge_met", True)):
        status = "cautious" if status == "ok" else status
        if is_ws:
            bullets.append(
                "**No quote this cycle** — A-S reservation outside L1; resting offers are pulled when blocked."
            )
        else:
            bullets.append("**Market edge not met** — quotes wider than book pays; few fills expected.")
            actions.append("Enable Dynamic min edge (Controls) or widen base spread on tight books.")

    if fills < min_gate_fills:
        if fills > 0 and toxic >= 0.5:
            bullets.append(
                f"Toxic **{toxic:.0%}** on only **{fills}** fill(s) — **not** gate-active until "
                f"{min_gate_fills}+ fills (often noise, not a broken bot)."
            )
        elif fills > 0:
            bullets.append(
                f"**{fills}** session fill(s) — toxicity gates engage at **{min_gate_fills}+** fills."
            )
        else:
            bullets.append("No session fills yet — toxicity will read 0% until fills occur.")
    else:
        bullets.append(
            f"Toxic **{toxic:.0%}** (30s horizon **{toxic_30:.0%}**) over **{fills}** fills — "
            f"refresh pauses at **{toxic_limit:.0%}**."
        )
        if toxic >= toxic_limit or refresh_paused:
            status = "defensive"
            if is_ws:
                bullets.append(
                    "**Adverse fill sample** — monitor markout; ws-engine does not use legacy refresh pause."
                )
                actions.append(
                    "Review fills in Logs; inventory skew may block quoting until A-S reservation re-enters L1."
                )
            else:
                bullets.append("**Refresh paused or defensive** — bot is protecting queue, not failing silently.")
                actions.append(
                    "Review fills in Logs; restart engine to clear in-memory toxic window after fixing book/inventory."
                )
        elif toxic >= 0.18:
            status = "cautious" if status == "ok" else status

    if refresh_paused and engine_running and not is_ws:
        status = "defensive"

    if status == "defensive":
        headline = "Defensive — toxicity or refresh pause"
    elif status == "misconfigured":
        headline = "Book/mark — fix before trusting metrics"
    elif status == "cautious":
        headline = "Cautious — idle offers, edge, or early toxicity"
    else:
        headline = "OK — wiring and sample size look reasonable"

    if not actions and not engine_running and live_offers == 0:
        actions.append(
            "Start engine for Gate 2 — try **tight_spread** (or **safe** if toxicity/book is stressed)."
        )

    return OperatorHealth(status=status, headline=headline, bullets=bullets, actions=actions)


def toxic_metric_labels(
    runtime: Mapping[str, Any],
    *,
    profile_name: str = "safe",
) -> tuple[str, str, str, str]:
    """Dashboard labels for toxic columns (include sample-size context)."""
    profile = get_profile((profile_name or "safe").strip().lower())
    min_gate = int(getattr(profile, "toxic_min_fills_for_gates", 8))
    n = int(runtime.get("fills_session") or 0)
    toxic = float(runtime.get("toxic_fill_ratio") or 0)
    toxic_30 = float(runtime.get("toxic_fill_ratio_30s") or 0)

    if n < min_gate:
        r_label = f"{toxic * 100:.0f}%*" if n else "—"
        r_help = (
            f"{n} fill(s) — gates at {min_gate}+. "
            "Asterisk = early sample; toxicity gates engage at 8+ fills on safe."
        )
    else:
        r_label = f"{toxic * 100:.0f}%"
        r_help = f"Adverse markout / {n} recent fills (gates active)."

    if n < 3:
        t_label = "—"
        t_help = "30s markout needs a few fills; ignore until n≥3."
    elif n < min_gate:
        t_label = f"{toxic_30 * 100:.0f}%*"
        t_help = f"Early 30s sample ({n} fills) — trust Toxic ratio* until {min_gate}+ fills."
    else:
        t_label = f"{toxic_30 * 100:.0f}%"
        t_help = "30-second markout horizon (adverse selection)."

    return r_label, r_help, t_label, t_help
