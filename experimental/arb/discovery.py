"""Paper-arb discovery scoring: fill ladder, maker bound, dwell, actionable flags."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from experimental.arb.book_provider import BookLevel, book_depth_from_json
from experimental.arb.clob_amm_monitor import augment_clob_amm_row
from experimental.arb.fill_simulator import (
    AmmPool,
    FillSimulationResult,
    amm_pool_from_json,
    amm_swap_rlusd_for_xrp,
    amm_swap_xrp_for_rlusd,
    best_roundtrip,
    mid_edge_bps,
    row_has_fill_snapshot,
    walk_asks_buy_xrp,
    walk_bids_sell_xrp,
)

logger = logging.getLogger(__name__)

DISCOVERY_NOTIONALS_RLUSD: Tuple[float, ...] = (250.0, 500.0, 1000.0)
ACTIONABLE_NOTIONAL_RLUSD = 500.0
ACTIONABLE_MIN_FILL_BPS = 3.0
DWELL_POLLS_REQUIRED = 2
DISCOVERY_STATE_PATH = Path("logs/arb_discovery_state.json")
BURST_SLEEP_SECONDS = 12
NORMAL_SLEEP_SECONDS = 60


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _profit_bps(start: float, profit: float) -> float:
    if start <= 0:
        return 0.0
    return (profit / start) * 10_000.0


def load_discovery_state(path: Path = DISCOVERY_STATE_PATH) -> Dict[str, Any]:
    if not path.is_file():
        return {"pairs": {}, "updated_utc": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"pairs": {}, "updated_utc": None}
        data.setdefault("pairs", {})
        return data
    except (OSError, json.JSONDecodeError):
        return {"pairs": {}, "updated_utc": None}


def save_discovery_state(state: Dict[str, Any], path: Path = DISCOVERY_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["updated_utc"] = _utc_now()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def paper_inventory_fundable(
    *,
    xrp: float,
    rlusd: float,
    mid: float,
    notional_rlusd: float,
) -> Dict[str, Any]:
    """Whether a paper wallet with current Alpha balances could fund a round-trip."""
    n = max(0.0, float(notional_rlusd))
    mid_f = float(mid) if mid and mid > 0 else 0.0
    xrp_needed = (n / mid_f) if mid_f > 0 else 0.0
    rlusd_ok = float(rlusd) + 1e-9 >= n
    xrp_ok = float(xrp) + 1e-9 >= xrp_needed * 0.5  # half-leg proxy either direction
    return {
        "notional_rlusd": n,
        "rlusd_balance": round(float(rlusd), 4),
        "xrp_balance": round(float(xrp), 4),
        "xrp_needed_proxy": round(xrp_needed, 4),
        "rlusd_ok": rlusd_ok,
        "xrp_ok": xrp_ok,
        "fundable": bool(rlusd_ok and (xrp_ok or rlusd_ok)),
        "note": "Paper check vs Alpha bot balances (wallet B later).",
    }


def _touch_roundtrip(
    *,
    notional_rlusd: float,
    book,
    pool: AmmPool,
    direction: str,
) -> FillSimulationResult:
    """Single-level touch walk (best bid/ask only) — tighter than full book, still taker."""
    start = float(notional_rlusd)
    asks = list(book.asks[:1]) if book.asks else []
    bids = list(book.bids[:1]) if book.bids else []
    if direction == "amm_cheaper":
        xrp_out, _ = amm_swap_rlusd_for_xrp(pool, start)
        if xrp_out <= 0:
            return FillSimulationResult(
                notional_rlusd=start,
                direction="touch_amm_cheaper",
                start_rlusd=start,
                end_rlusd=0.0,
                profit_rlusd=-start,
                profit_bps=-10_000.0,
                xrp_traded=0.0,
                clob_avg_price=None,
                amm_avg_price=None,
                feasible=False,
                note="amm_swap_failed",
            )
        end_rlusd, xrp_sold, clob_avg = walk_bids_sell_xrp(bids, xrp_out)
        profit = end_rlusd - start
        return FillSimulationResult(
            notional_rlusd=start,
            direction="touch_amm_cheaper",
            start_rlusd=start,
            end_rlusd=end_rlusd,
            profit_rlusd=profit,
            profit_bps=_profit_bps(start, profit),
            xrp_traded=xrp_sold,
            clob_avg_price=clob_avg,
            amm_avg_price=start / xrp_out if xrp_out else None,
            feasible=xrp_sold + 1e-9 >= xrp_out * 0.99,
            note="ok" if xrp_sold + 1e-9 >= xrp_out * 0.99 else "touch_bid_short",
        )
    xrp_out, spent, clob_avg = walk_asks_buy_xrp(asks, start)
    if xrp_out <= 0 or spent <= 0:
        return FillSimulationResult(
            notional_rlusd=start,
            direction="touch_clob_cheaper",
            start_rlusd=start,
            end_rlusd=0.0,
            profit_rlusd=-start,
            profit_bps=-10_000.0,
            xrp_traded=0.0,
            clob_avg_price=None,
            amm_avg_price=None,
            feasible=False,
            note="touch_ask_short",
        )
    end_rlusd, _ = amm_swap_xrp_for_rlusd(pool, xrp_out)
    profit = end_rlusd - start
    return FillSimulationResult(
        notional_rlusd=start,
        direction="touch_clob_cheaper",
        start_rlusd=start,
        end_rlusd=end_rlusd,
        profit_rlusd=profit,
        profit_bps=_profit_bps(start, profit),
        xrp_traded=xrp_out,
        clob_avg_price=clob_avg,
        amm_avg_price=end_rlusd / xrp_out if xrp_out else None,
        feasible=end_rlusd > 0,
        note="ok" if end_rlusd > 0 else "amm_swap_failed",
    )


def _maker_optimistic_roundtrip(
    *,
    notional_rlusd: float,
    book,
    pool: AmmPool,
    clob_mid: float,
    direction: str,
) -> FillSimulationResult:
    """
    Optimistic maker CLOB leg at mid (passive fill idealization) + AMM curve.

    Upper bound on maker-assisted edge — not guaranteed executable.
    """
    start = float(notional_rlusd)
    mid = float(clob_mid)
    if mid <= 0:
        return FillSimulationResult(
            notional_rlusd=start,
            direction="maker_optimistic",
            start_rlusd=start,
            end_rlusd=0.0,
            profit_rlusd=-start,
            profit_bps=-10_000.0,
            xrp_traded=0.0,
            clob_avg_price=None,
            amm_avg_price=None,
            feasible=False,
            note="no_mid",
        )
    if direction == "amm_cheaper":
        xrp_out, _ = amm_swap_rlusd_for_xrp(pool, start)
        if xrp_out <= 0:
            return FillSimulationResult(
                notional_rlusd=start,
                direction="maker_amm_first",
                start_rlusd=start,
                end_rlusd=0.0,
                profit_rlusd=-start,
                profit_bps=-10_000.0,
                xrp_traded=0.0,
                clob_avg_price=None,
                amm_avg_price=None,
                feasible=False,
                note="amm_swap_failed",
            )
        # Sell XRP on CLOB as maker @ mid
        end_rlusd = xrp_out * mid
        profit = end_rlusd - start
        return FillSimulationResult(
            notional_rlusd=start,
            direction="maker_amm_first",
            start_rlusd=start,
            end_rlusd=end_rlusd,
            profit_rlusd=profit,
            profit_bps=_profit_bps(start, profit),
            xrp_traded=xrp_out,
            clob_avg_price=mid,
            amm_avg_price=start / xrp_out,
            feasible=True,
            note="optimistic_maker_mid",
        )
    # Buy XRP on CLOB as maker @ mid, sell AMM
    xrp_out = start / mid
    end_rlusd, _ = amm_swap_xrp_for_rlusd(pool, xrp_out)
    profit = end_rlusd - start
    return FillSimulationResult(
        notional_rlusd=start,
        direction="maker_clob_first",
        start_rlusd=start,
        end_rlusd=end_rlusd,
        profit_rlusd=profit,
        profit_bps=_profit_bps(start, profit),
        xrp_traded=xrp_out,
        clob_avg_price=mid,
        amm_avg_price=end_rlusd / xrp_out if xrp_out else None,
        feasible=end_rlusd > 0,
        note="optimistic_maker_mid",
    )


def score_fill_ladder(
    row: Dict[str, Any],
    *,
    notionals: Sequence[float] = DISCOVERY_NOTIONALS_RLUSD,
) -> Dict[str, Any]:
    """Full book-walk ladder (taker both legs)."""
    out: Dict[str, Any] = {
        "available": False,
        "notionals_rlusd": [float(n) for n in notionals],
        "by_notional": {},
        "best_profit_bps": None,
        "best_notional": None,
        "note": "no_depth",
    }
    if not row_has_fill_snapshot(row):
        return out
    try:
        book = book_depth_from_json(row["book_depth"])
        pool = amm_pool_from_json(row)
    except (KeyError, TypeError, ValueError):
        out["note"] = "invalid_depth"
        return out
    if pool is None:
        out["note"] = "no_pool"
        return out
    out["available"] = True
    out["note"] = "book_walk+amm"
    best_bps = None
    best_n = None
    by: Dict[str, Any] = {}
    for n in notionals:
        n = float(n)
        if n <= 0:
            continue
        sim = best_roundtrip(notional_rlusd=n, book=book, pool=pool)
        payload = {
            "profit_bps": round(sim.profit_bps, 2),
            "profit_rlusd": round(sim.profit_rlusd, 4),
            "direction": sim.direction,
            "feasible": sim.feasible,
            "profitable": bool(sim.feasible and sim.profit_bps > 0),
            "note": sim.note,
        }
        key = str(int(n) if n == int(n) else n)
        by[key] = payload
        if sim.feasible and (best_bps is None or sim.profit_bps > best_bps):
            best_bps = sim.profit_bps
            best_n = n
    out["by_notional"] = by
    out["best_profit_bps"] = round(best_bps, 2) if best_bps is not None else None
    out["best_notional"] = best_n
    return out


def score_maker_ladder(
    row: Dict[str, Any],
    *,
    notionals: Sequence[float] = DISCOVERY_NOTIONALS_RLUSD,
) -> Dict[str, Any]:
    """Optimistic maker-at-mid CLOB leg + AMM (upper bound)."""
    out: Dict[str, Any] = {
        "available": False,
        "notionals_rlusd": [float(n) for n in notionals],
        "by_notional": {},
        "best_profit_bps": None,
        "note": "no_depth",
    }
    if not row_has_fill_snapshot(row):
        return out
    try:
        book = book_depth_from_json(row["book_depth"])
        pool = amm_pool_from_json(row)
    except (KeyError, TypeError, ValueError):
        out["note"] = "invalid_depth"
        return out
    if pool is None:
        return out
    clob_mid = float(row.get("clob_mid_rlusd_per_xrp") or book.mid or 0)
    amm_mid = float(row.get("amm_mid_rlusd_per_xrp") or pool.mid_rlusd_per_xrp or 0)
    direction = "amm_cheaper" if amm_mid and clob_mid and amm_mid < clob_mid else "clob_cheaper"
    out["available"] = True
    out["note"] = "optimistic_maker_mid+amm — upper bound only"
    by: Dict[str, Any] = {}
    best_bps = None
    for n in notionals:
        n = float(n)
        if n <= 0:
            continue
        sim = _maker_optimistic_roundtrip(
            notional_rlusd=n,
            book=book,
            pool=pool,
            clob_mid=clob_mid,
            direction=direction,
        )
        touch = _touch_roundtrip(
            notional_rlusd=n,
            book=book,
            pool=pool,
            direction=direction,
        )
        key = str(int(n) if n == int(n) else n)
        by[key] = {
            "maker_opt_profit_bps": round(sim.profit_bps, 2),
            "maker_opt_profitable": bool(sim.feasible and sim.profit_bps > 0),
            "touch_profit_bps": round(touch.profit_bps, 2),
            "touch_profitable": bool(touch.feasible and touch.profit_bps > 0),
            "direction": sim.direction,
            "note": sim.note,
        }
        if sim.feasible and (best_bps is None or sim.profit_bps > best_bps):
            best_bps = sim.profit_bps
    out["by_notional"] = by
    out["best_profit_bps"] = round(best_bps, 2) if best_bps is not None else None
    return out


def _fill_bps_at(ladder: Dict[str, Any], notional: float) -> Optional[float]:
    key = str(int(notional) if notional == int(notional) else notional)
    cell = (ladder.get("by_notional") or {}).get(key) or {}
    if not cell.get("feasible", True) and "profit_bps" in cell:
        # full walk uses feasible flag
        if not cell.get("feasible"):
            return None
    if "profit_bps" in cell:
        try:
            return float(cell["profit_bps"])
        except (TypeError, ValueError):
            return None
    return None


def update_dwell_and_flags(
    *,
    pair_id: str,
    fill_bps_500: Optional[float],
    mid_net_bps: Optional[float],
    fundable_500: bool,
    state: Dict[str, Any],
    min_fill_bps: float = ACTIONABLE_MIN_FILL_BPS,
    dwell_required: int = DWELL_POLLS_REQUIRED,
) -> Dict[str, Any]:
    pairs = state.setdefault("pairs", {})
    st = dict(pairs.get(pair_id) or {})
    fill_pos = fill_bps_500 is not None and fill_bps_500 >= min_fill_bps
    mid_pos = mid_net_bps is not None and mid_net_bps > 0
    if fill_pos:
        st["fill_pos_streak"] = int(st.get("fill_pos_streak") or 0) + 1
    else:
        st["fill_pos_streak"] = 0
    if mid_pos:
        st["mid_pos_streak"] = int(st.get("mid_pos_streak") or 0) + 1
    else:
        st["mid_pos_streak"] = 0
    st["last_fill_bps_500"] = fill_bps_500
    st["last_mid_net_bps"] = mid_net_bps
    st["last_ts_utc"] = _utc_now()
    dwell_ok = int(st["fill_pos_streak"]) >= dwell_required
    actionable = bool(fill_pos and dwell_ok and fundable_500)
    st["actionable"] = actionable
    st["dwell_ok"] = dwell_ok
    pairs[pair_id] = st
    state["pairs"] = pairs
    return {
        "fill_pos_streak": st["fill_pos_streak"],
        "mid_pos_streak": st.get("mid_pos_streak", 0),
        "dwell_ok": dwell_ok,
        "dwell_required": dwell_required,
        "actionable": actionable,
        "fill_positive": fill_pos,
        "mid_positive": mid_pos,
        "fundable_500": fundable_500,
        "min_fill_bps": min_fill_bps,
    }


def build_discovery_score(
    row: Optional[Dict[str, Any]],
    *,
    xrp: float = 0.0,
    rlusd: float = 0.0,
    state_path: Path = DISCOVERY_STATE_PATH,
    notionals: Sequence[float] = DISCOVERY_NOTIONALS_RLUSD,
    pair_id: str = "rlusd_xrp",
    update_dwell: bool = True,
) -> Dict[str, Any]:
    """Full discovery block for primary RLUSD/XRP depth row."""
    mid_net = mid_edge_bps(row) if row else None
    mid = float((row or {}).get("clob_mid_rlusd_per_xrp") or 0)
    fill_ladder = score_fill_ladder(row or {}, notionals=notionals)
    maker_ladder = score_maker_ladder(row or {}, notionals=notionals)
    inv_500 = paper_inventory_fundable(
        xrp=xrp,
        rlusd=rlusd,
        mid=mid,
        notional_rlusd=ACTIONABLE_NOTIONAL_RLUSD,
    )
    fill_500 = _fill_bps_at(fill_ladder, ACTIONABLE_NOTIONAL_RLUSD)
    if fill_500 is None and fill_ladder.get("by_notional"):
        cell = fill_ladder["by_notional"].get("500") or {}
        if cell.get("feasible") and cell.get("profit_bps") is not None:
            fill_500 = float(cell["profit_bps"])

    state = load_discovery_state(state_path)
    if update_dwell:
        dwell = update_dwell_and_flags(
            pair_id=pair_id,
            fill_bps_500=fill_500,
            mid_net_bps=mid_net,
            fundable_500=bool(inv_500.get("fundable")),
            state=state,
        )
        save_discovery_state(state, state_path)
    else:
        st = (state.get("pairs") or {}).get(pair_id) or {}
        dwell = {
            "fill_pos_streak": int(st.get("fill_pos_streak") or 0),
            "mid_pos_streak": int(st.get("mid_pos_streak") or 0),
            "dwell_ok": bool(st.get("dwell_ok")),
            "dwell_required": DWELL_POLLS_REQUIRED,
            "actionable": bool(st.get("actionable")),
            "fill_positive": fill_500 is not None and fill_500 >= ACTIONABLE_MIN_FILL_BPS,
            "mid_positive": mid_net is not None and mid_net > 0,
            "fundable_500": bool(inv_500.get("fundable")),
            "min_fill_bps": ACTIONABLE_MIN_FILL_BPS,
        }

    flag = "ok"
    if dwell.get("actionable"):
        flag = "ACTIONABLE"
    elif fill_500 is not None and fill_500 > 0:
        flag = "FILL+"
    elif mid_net is not None and mid_net > 0:
        flag = "MID+"
    elif row and row.get("dislocation"):
        flag = "GROSS"

    burst = bool(
        (row and row.get("dislocation"))
        or (fill_500 is not None and fill_500 > 0)
        or int(dwell.get("fill_pos_streak") or 0) >= 1
        or dwell.get("actionable")
    )

    return {
        "pair_id": pair_id,
        "mid_net_bps": mid_net,
        "fill_ladder": fill_ladder,
        "maker_ladder": maker_ladder,
        "fill_profit_bps_250": _fill_bps_at(fill_ladder, 250.0),
        "fill_profit_bps_500": fill_500,
        "fill_profit_bps_1000": _fill_bps_at(fill_ladder, 1000.0),
        "maker_opt_bps_500": (
            (maker_ladder.get("by_notional") or {}).get("500") or {}
        ).get("maker_opt_profit_bps"),
        "touch_bps_500": (
            (maker_ladder.get("by_notional") or {}).get("500") or {}
        ).get("touch_profit_bps"),
        "inventory": inv_500,
        "dwell": dwell,
        "flag": flag,
        "actionable": bool(dwell.get("actionable")),
        "burst_recommended": burst,
        "poll_sleep_seconds": BURST_SLEEP_SECONDS if burst else NORMAL_SLEEP_SECONDS,
        "thresholds": {
            "actionable_notional_rlusd": ACTIONABLE_NOTIONAL_RLUSD,
            "actionable_min_fill_bps": ACTIONABLE_MIN_FILL_BPS,
            "dwell_polls": DWELL_POLLS_REQUIRED,
            "discovery_notionals": list(notionals),
        },
        "note": (
            "Paper discovery only. ACTIONABLE = fill@500 ≥ +3 bps for "
            f"{DWELL_POLLS_REQUIRED}+ polls and paper-fundable. "
            "Maker column is optimistic upper bound (CLOB@mid)."
        ),
    }


def attach_discovery_to_universe(
    universe: Dict[str, Any],
    discovery: Dict[str, Any],
) -> Dict[str, Any]:
    """Annotate universe pairs with discovery fields for HUD."""
    out = dict(universe)
    pairs = []
    for p in universe.get("pairs") or []:
        if not isinstance(p, dict):
            continue
        row = dict(p)
        if row.get("id") == discovery.get("pair_id"):
            row["mid_net_bps"] = discovery.get("mid_net_bps")
            row["fill_profit_bps_500"] = discovery.get("fill_profit_bps_500")
            row["fill_profit_bps_250"] = discovery.get("fill_profit_bps_250")
            row["fill_profit_bps_1000"] = discovery.get("fill_profit_bps_1000")
            row["maker_opt_bps_500"] = discovery.get("maker_opt_bps_500")
            row["touch_bps_500"] = discovery.get("touch_bps_500")
            row["discovery_flag"] = discovery.get("flag")
            row["actionable"] = discovery.get("actionable")
            row["dwell"] = discovery.get("dwell")
        pairs.append(row)
    out["pairs"] = pairs
    out["discovery"] = {
        "actionable": discovery.get("actionable"),
        "flag": discovery.get("flag"),
        "fill_profit_bps_500": discovery.get("fill_profit_bps_500"),
        "dwell": discovery.get("dwell"),
        "burst_recommended": discovery.get("burst_recommended"),
        "poll_sleep_seconds": discovery.get("poll_sleep_seconds"),
    }
    out["actionable_count"] = sum(1 for p in pairs if p.get("actionable"))
    return out
