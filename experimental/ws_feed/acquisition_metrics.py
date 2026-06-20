"""Session acquisition metrics — edge-positive inventory growth vs spot."""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from experimental.ws_feed.acquisition_context import (
    ACQUISITION_POSTURES,
    solo_acquire_bid_join_fired,
    solo_acquire_bid_join_opportunity,
    solo_acquire_fired,
    solo_acquire_opportunity,
    _norm_posture,
)


def _ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _side_cap_bucket(
    buckets: Dict[str, Dict[str, float]],
    label: str,
    *,
    side: str,
    cap: float,
    xrp: float,
) -> None:
    key = _norm_posture(label) or "unknown"
    buckets.setdefault(key, {"n": 0.0, "cap": 0.0, "xrp": 0.0})
    buckets[key]["n"] += 1.0
    buckets[key]["cap"] += cap
    buckets[key]["xrp"] += xrp


def _fill_bps(capture_xrp: float, xrp_amount: float) -> Optional[float]:
    if xrp_amount <= 0 or capture_xrp == 0:
        return None
    return capture_xrp / xrp_amount * 10_000.0


def _solo_fire_rates(intel_cycles: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    opp = 0
    fired = 0
    bid_join_opp = 0
    bid_join_fired = 0
    visibility_samples: List[float] = []

    for row in intel_cycles:
        if row.get("kind") not in (None, "cycle"):
            continue
        peer_empty = bool(row.get("peer_lane_empty"))
        toxic = float(row.get("toxic_fill_ratio_30s") or row.get("toxic_fill_ratio") or 0.0)
        g2_mult = float(row.get("g2_spread_mult") or 1.0)
        would = bool(row.get("would_quote", True))
        inv = str(row.get("inventory_label") or "")
        solo = bool(row.get("g7_solo_acquisition"))
        bid_role = str(row.get("g7_bid_role") or "")

        if solo_acquire_opportunity(
            peer_lane_empty=peer_empty,
            toxic_ratio_30s=toxic,
            g2_spread_mult=g2_mult,
            would_quote=would,
        ):
            opp += 1
            if solo_acquire_fired(g7_solo_acquisition=solo):
                fired += 1
                wvt = row.get("worst_vs_touch_bps")
                if wvt is not None:
                    visibility_samples.append(float(wvt))

        if solo_acquire_bid_join_opportunity(
            peer_lane_empty=peer_empty,
            toxic_ratio_30s=toxic,
            g2_spread_mult=g2_mult,
            inventory_label=inv,
            would_quote=would,
        ):
            bid_join_opp += 1
            if solo_acquire_bid_join_fired(g7_solo_acquisition=solo, g7_bid_role=bid_role):
                bid_join_fired += 1

    return {
        "solo_acquire_fire_rate": round(fired / opp, 4) if opp else None,
        "solo_acquire_opportunities": opp,
        "solo_acquire_fired_cycles": fired,
        "bid_join_fire_rate": round(bid_join_fired / bid_join_opp, 4) if bid_join_opp else None,
        "bid_join_opportunities": bid_join_opp,
        "bid_join_fired_cycles": bid_join_fired,
        "visibility_when_solo_bps_mean": (
            round(statistics.mean(visibility_samples), 2) if visibility_samples else None
        ),
    }


def build_acquisition_metrics(
    *,
    runtime: Mapping[str, Any],
    session_fills: Sequence[Mapping[str, Any]],
    intel_cycles: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build acquisition_metrics dict for runtime / reports.

    session_fills: M6 rows or trades rows with side, xrp_amount/xrp, capture_xrp/cap,
    inventory_label, fill_price_rlusd_per_xrp/price (optional).
    """
    intel_cycles = intel_cycles or []

    buys: List[Mapping[str, Any]] = []
    sells: List[Mapping[str, Any]] = []
    buy_capture_by_state: Dict[str, Dict[str, float]] = {}
    sell_capture_by_state: Dict[str, Dict[str, float]] = {}

    for row in session_fills:
        side = str(row.get("side") or "").upper()
        try:
            xrp = float(row.get("xrp_amount") or row.get("xrp") or 0.0)
        except (TypeError, ValueError):
            xrp = 0.0
        try:
            cap = float(row.get("capture_xrp") or row.get("cap") or row.get("profit_xrp_equiv") or 0.0)
        except (TypeError, ValueError):
            cap = 0.0
        inv = str(row.get("inventory_label") or "unknown")
        item = {"side": side, "xrp": xrp, "cap": cap, "inventory_label": inv}
        if side == "BUY":
            buys.append(item)
            _side_cap_bucket(buy_capture_by_state, inv, side="BUY", cap=cap, xrp=xrp)
        elif side == "SELL":
            sells.append(item)
            _side_cap_bucket(sell_capture_by_state, inv, side="SELL", cap=cap, xrp=xrp)

    acq_buys = [b for b in buys if _norm_posture(str(b["inventory_label"])) in ACQUISITION_POSTURES]

    xrp_bought = sum(b["xrp"] for b in acq_buys)
    rlusd_spent = 0.0
    for row in session_fills:
        if str(row.get("side") or "").upper() != "BUY":
            continue
        if _norm_posture(str(row.get("inventory_label") or "")) not in ACQUISITION_POSTURES:
            continue
        try:
            xrp = float(row.get("xrp_amount") or row.get("xrp") or 0.0)
            price = float(
                row.get("fill_price_rlusd_per_xrp")
                or row.get("price_rlusd_per_xrp")
                or row.get("price")
                or 0.0
            )
        except (TypeError, ValueError):
            continue
        if xrp > 0 and price > 0:
            rlusd_spent += xrp * price

    buy_bps_list: List[float] = []
    for b in buys:
        bps = _fill_bps(float(b["cap"]), float(b["xrp"]))
        if bps is not None:
            buy_bps_list.append(bps)

    buy_capture_total = sum(b["cap"] for b in buys)
    baseline_xrp = runtime.get("session_baseline_xrp")
    balance_xrp = runtime.get("balance_xrp")
    delta_xrp: Optional[float] = None
    if baseline_xrp is not None and balance_xrp is not None:
        delta_xrp = float(balance_xrp) - float(baseline_xrp)

    skim = float(runtime.get("session_spread_capture_xrp") or runtime.get("skim_delta_rlusd") or 0.0)
    spot = runtime.get("spot_delta_rlusd")
    spot_f: Optional[float] = float(spot) if spot is not None else None
    acq_vs_spot: Optional[float] = None
    if spot_f is not None and abs(spot_f) > 1e-9:
        acq_vs_spot = round(abs(skim) / abs(spot_f), 4)

    fire = _solo_fire_rates(intel_cycles)

    return {
        "xrp_per_rlusd_spent": (
            round(xrp_bought / rlusd_spent, 8) if rlusd_spent > 0 else None
        ),
        "rlusd_spent_acquisition_states": round(rlusd_spent, 6) if rlusd_spent else None,
        "xrp_bought_acquisition_states": round(xrp_bought, 4) if xrp_bought else None,
        "buy_cost_vs_mid_bps": (
            round(statistics.mean(buy_bps_list), 2) if buy_bps_list else None
        ),
        "buy_cost_vs_mid_bps_median": (
            round(statistics.median(buy_bps_list), 2) if buy_bps_list else None
        ),
        "inventory_growth_at_edge": {
            "delta_xrp": round(delta_xrp, 6) if delta_xrp is not None else None,
            "buy_capture_xrp": round(buy_capture_total, 6),
            "at_edge": bool(
                delta_xrp is not None and delta_xrp > 0 and buy_capture_total > 0
            ),
        },
        "buy_capture_by_state": buy_capture_by_state,
        "sell_capture_by_state": sell_capture_by_state,
        "spot_contribution_rlusd": spot_f,
        "acquisition_vs_spot_ratio": acq_vs_spot,
        **fire,
    }


def format_acquisition_report(metrics: Dict[str, Any], *, runtime: Mapping[str, Any]) -> str:
    """Human-readable acquisition metrics block."""
    lines = ["=== Acquisition metrics (session) ==="]
    boot = runtime.get("session_boot_utc") or "—"
    ver = runtime.get("ws_as_version") or "—"
    fills = runtime.get("fills_session")
    lines.append(f"boot: {boot}  ws: {ver}  fills: {fills}")
    lines.append("")

    xpr = metrics.get("xrp_per_rlusd_spent")
    if xpr is not None:
        lines.append(f"xrp_per_rlusd_spent (balanced/rlusd_heavy BUY): {xpr:.8f}")
    bps = metrics.get("buy_cost_vs_mid_bps")
    if bps is not None:
        lines.append(f"buy_cost_vs_mid_bps (mean): {bps:+.2f}")
    ig = metrics.get("inventory_growth_at_edge") or {}
    lines.append(
        f"inventory_growth_at_edge: delta_xrp={ig.get('delta_xrp')} "
        f"buy_cap={ig.get('buy_capture_xrp')} at_edge={ig.get('at_edge')}"
    )
    sfr = metrics.get("solo_acquire_fire_rate")
    if sfr is not None:
        lines.append(
            f"solo_acquire_fire_rate: {sfr:.1%} "
            f"({metrics.get('solo_acquire_fired_cycles')}/{metrics.get('solo_acquire_opportunities')} cycles)"
        )
    bj = metrics.get("bid_join_fire_rate")
    if bj is not None:
        lines.append(
            f"bid_join_fire_rate: {bj:.1%} "
            f"({metrics.get('bid_join_fired_cycles')}/{metrics.get('bid_join_opportunities')} cycles)"
        )
    vis = metrics.get("visibility_when_solo_bps_mean")
    if vis is not None:
        lines.append(f"visibility_when_solo_bps_mean: {vis:.1f}")

    lines.append("")
    lines.append("buy_capture_by_state:")
    for state, v in sorted((metrics.get("buy_capture_by_state") or {}).items()):
        lines.append(f"  {state}: n={int(v['n'])} cap={v['cap']:+.6f} xrp={v['xrp']:.2f}")
    lines.append("sell_capture_by_state:")
    for state, v in sorted((metrics.get("sell_capture_by_state") or {}).items()):
        lines.append(f"  {state}: n={int(v['n'])} cap={v['cap']:+.6f} xrp={v['xrp']:.2f}")

    spot = metrics.get("spot_contribution_rlusd")
    if spot is not None:
        lines.append(f"\nspot_delta_rlusd: {spot:+.4f}")
    ratio = metrics.get("acquisition_vs_spot_ratio")
    if ratio is not None:
        lines.append(f"acquisition_vs_spot_ratio (|skim|/|spot|): {ratio:.4f}")

    return "\n".join(lines)
