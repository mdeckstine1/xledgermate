"""Walk CLOB book + AMM pool to estimate round-trip arb P&L at size (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from experimental.arb.book_provider import BookLevel, TokenXrpBookDepth, book_depth_from_json
from experimental.arb.clob_amm_monitor import augment_clob_amm_row


@dataclass(frozen=True)
class AmmPool:
    xrp_reserve: float
    rlusd_reserve: float
    fee_bps: float

    @property
    def mid_rlusd_per_xrp(self) -> float:
        if self.xrp_reserve <= 0:
            return 0.0
        return self.rlusd_reserve / self.xrp_reserve


@dataclass(frozen=True)
class FillSimulationResult:
    notional_rlusd: float
    direction: str
    start_rlusd: float
    end_rlusd: float
    profit_rlusd: float
    profit_bps: float
    xrp_traded: float
    clob_avg_price: Optional[float]
    amm_avg_price: Optional[float]
    feasible: bool
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notional_rlusd": round(self.notional_rlusd, 4),
            "direction": self.direction,
            "start_rlusd": round(self.start_rlusd, 6),
            "end_rlusd": round(self.end_rlusd, 6),
            "profit_rlusd": round(self.profit_rlusd, 6),
            "profit_bps": round(self.profit_bps, 2),
            "xrp_traded": round(self.xrp_traded, 6),
            "clob_avg_price": round(self.clob_avg_price, 6) if self.clob_avg_price else None,
            "amm_avg_price": round(self.amm_avg_price, 6) if self.amm_avg_price else None,
            "feasible": self.feasible,
            "note": self.note,
        }


def amm_pool_from_json(row: Dict[str, Any]) -> Optional[AmmPool]:
    xrp = row.get("amm_xrp_reserve")
    rlusd = row.get("amm_rlusd_reserve")
    fee = row.get("amm_fee_bps")
    if xrp is None or rlusd is None:
        return None
    try:
        x = float(xrp)
        y = float(rlusd)
        fee_bps = float(fee) if fee is not None else 10.0
    except (TypeError, ValueError):
        return None
    if x <= 0 or y <= 0:
        return None
    return AmmPool(xrp_reserve=x, rlusd_reserve=y, fee_bps=fee_bps)


def _fee_fraction(fee_bps: float) -> float:
    return max(0.0, float(fee_bps)) / 10_000.0


def amm_swap_rlusd_for_xrp(
    pool: AmmPool,
    rlusd_in: float,
) -> Tuple[float, AmmPool]:
    """Swap RLUSD into pool; receive XRP (constant product, fee on input)."""
    if rlusd_in <= 0 or pool.xrp_reserve <= 0 or pool.rlusd_reserve <= 0:
        return 0.0, pool
    fee = _fee_fraction(pool.fee_bps)
    effective_in = rlusd_in * (1.0 - fee)
    k = pool.xrp_reserve * pool.rlusd_reserve
    new_rlusd = pool.rlusd_reserve + effective_in
    new_xrp = k / new_rlusd
    xrp_out = pool.xrp_reserve - new_xrp
    if xrp_out <= 0:
        return 0.0, pool
    return xrp_out, AmmPool(xrp_reserve=new_xrp, rlusd_reserve=new_rlusd, fee_bps=pool.fee_bps)


def amm_swap_xrp_for_rlusd(
    pool: AmmPool,
    xrp_in: float,
) -> Tuple[float, AmmPool]:
    """Swap XRP into pool; receive RLUSD."""
    if xrp_in <= 0 or pool.xrp_reserve <= 0 or pool.rlusd_reserve <= 0:
        return 0.0, pool
    fee = _fee_fraction(pool.fee_bps)
    effective_in = xrp_in * (1.0 - fee)
    k = pool.xrp_reserve * pool.rlusd_reserve
    new_xrp = pool.xrp_reserve + effective_in
    new_rlusd = k / new_xrp
    rlusd_out = pool.rlusd_reserve - new_rlusd
    if rlusd_out <= 0:
        return 0.0, pool
    return rlusd_out, AmmPool(xrp_reserve=new_xrp, rlusd_reserve=new_rlusd, fee_bps=pool.fee_bps)


def walk_asks_buy_xrp(
    asks: Sequence[BookLevel],
    rlusd_budget: float,
) -> Tuple[float, float, Optional[float]]:
    """Spend RLUSD on asks; return (xrp_out, rlusd_spent, avg_price)."""
    if rlusd_budget <= 0:
        return 0.0, 0.0, None
    remaining = rlusd_budget
    xrp_out = 0.0
    spent = 0.0
    for level in asks:
        if remaining <= 1e-12:
            break
        level_cost = level.xrp_amount * level.price_rlusd_per_xrp
        if level_cost <= remaining + 1e-12:
            xrp_out += level.xrp_amount
            spent += level_cost
            remaining -= level_cost
        else:
            partial_xrp = remaining / level.price_rlusd_per_xrp
            xrp_out += partial_xrp
            spent += remaining
            remaining = 0.0
    avg = spent / xrp_out if xrp_out > 0 else None
    return xrp_out, spent, avg


def walk_bids_sell_xrp(
    bids: Sequence[BookLevel],
    xrp_amount: float,
) -> Tuple[float, float, Optional[float]]:
    """Sell XRP into bids; return (rlusd_out, xrp_sold, avg_price)."""
    if xrp_amount <= 0:
        return 0.0, 0.0, None
    remaining = xrp_amount
    rlusd_out = 0.0
    sold = 0.0
    for level in bids:
        if remaining <= 1e-12:
            break
        take = min(remaining, level.xrp_amount)
        rlusd_out += take * level.price_rlusd_per_xrp
        sold += take
        remaining -= take
    avg = rlusd_out / sold if sold > 0 else None
    return rlusd_out, sold, avg


def _profit_bps(notional: float, profit: float) -> float:
    if notional <= 0:
        return 0.0
    return profit / notional * 10_000.0


def simulate_rlusd_xrp_roundtrip(
    *,
    notional_rlusd: float,
    book: TokenXrpBookDepth,
    pool: AmmPool,
    direction: Optional[str] = None,
) -> FillSimulationResult:
    """
    Instantaneous 2-leg roundtrip starting with ``notional_rlusd``.

    ``amm_cheaper``: buy XRP on AMM, sell on CLOB.
    ``clob_cheaper``: buy XRP on CLOB, sell on AMM.
    """
    start = float(notional_rlusd)
    if start <= 0:
        return FillSimulationResult(
            notional_rlusd=start,
            direction="none",
            start_rlusd=0.0,
            end_rlusd=0.0,
            profit_rlusd=0.0,
            profit_bps=0.0,
            xrp_traded=0.0,
            clob_avg_price=None,
            amm_avg_price=None,
            feasible=False,
            note="notional<=0",
        )

    clob_mid = book.mid or 0.0
    amm_mid = pool.mid_rlusd_per_xrp
    if direction is None:
        if clob_mid > 0 and amm_mid > 0:
            direction = "amm_cheaper" if amm_mid < clob_mid else "clob_cheaper"
        else:
            direction = "amm_cheaper"

    if direction == "amm_cheaper":
        xrp_out, _pool = amm_swap_rlusd_for_xrp(pool, start)
        if xrp_out <= 0:
            return FillSimulationResult(
                notional_rlusd=start,
                direction=direction,
                start_rlusd=start,
                end_rlusd=0.0,
                profit_rlusd=-start,
                profit_bps=-10_000.0,
                xrp_traded=0.0,
                clob_avg_price=None,
                amm_avg_price=start / xrp_out if xrp_out else None,
                feasible=False,
                note="amm_swap_failed",
            )
        amm_avg = start / xrp_out
        end_rlusd, xrp_sold, clob_avg = walk_bids_sell_xrp(book.bids, xrp_out)
        feasible = xrp_sold + 1e-9 >= xrp_out
        note = "ok" if feasible else f"clob_depth_short xrp={xrp_out:.4f} filled={xrp_sold:.4f}"
        profit = end_rlusd - start
        return FillSimulationResult(
            notional_rlusd=start,
            direction=direction,
            start_rlusd=start,
            end_rlusd=end_rlusd,
            profit_rlusd=profit,
            profit_bps=_profit_bps(start, profit),
            xrp_traded=xrp_sold,
            clob_avg_price=clob_avg,
            amm_avg_price=amm_avg,
            feasible=feasible,
            note=note,
        )

    xrp_out, spent, clob_avg = walk_asks_buy_xrp(book.asks, start)
    if xrp_out <= 0 or spent <= 0:
        return FillSimulationResult(
            notional_rlusd=start,
            direction="clob_cheaper",
            start_rlusd=start,
            end_rlusd=0.0,
            profit_rlusd=-start,
            profit_bps=-10_000.0,
            xrp_traded=0.0,
            clob_avg_price=None,
            amm_avg_price=None,
            feasible=False,
            note="clob_buy_failed",
        )
    end_rlusd, _pool = amm_swap_xrp_for_rlusd(pool, xrp_out)
    amm_avg = end_rlusd / xrp_out if xrp_out > 0 else None
    feasible = end_rlusd > 0
    note = "ok" if feasible else "amm_swap_failed"
    profit = end_rlusd - start
    return FillSimulationResult(
        notional_rlusd=start,
        direction="clob_cheaper",
        start_rlusd=start,
        end_rlusd=end_rlusd,
        profit_rlusd=profit,
        profit_bps=_profit_bps(start, profit),
        xrp_traded=xrp_out,
        clob_avg_price=clob_avg,
        amm_avg_price=amm_avg,
        feasible=feasible,
        note=note,
    )


def simulate_both_directions(
    *,
    notional_rlusd: float,
    book: TokenXrpBookDepth,
    pool: AmmPool,
) -> Tuple[FillSimulationResult, FillSimulationResult]:
    a = simulate_rlusd_xrp_roundtrip(
        notional_rlusd=notional_rlusd,
        book=book,
        pool=pool,
        direction="amm_cheaper",
    )
    b = simulate_rlusd_xrp_roundtrip(
        notional_rlusd=notional_rlusd,
        book=book,
        pool=pool,
        direction="clob_cheaper",
    )
    return a, b


def best_roundtrip(
    *,
    notional_rlusd: float,
    book: TokenXrpBookDepth,
    pool: AmmPool,
) -> FillSimulationResult:
    a, b = simulate_both_directions(
        notional_rlusd=notional_rlusd,
        book=book,
        pool=pool,
    )
    candidates = [r for r in (a, b) if r.feasible]
    if not candidates:
        return a if a.profit_rlusd >= b.profit_rlusd else b
    return max(candidates, key=lambda r: r.profit_rlusd)


def row_has_fill_snapshot(row: Dict[str, Any]) -> bool:
    return bool(row.get("book_depth") and row.get("amm_xrp_reserve") and row.get("amm_rlusd_reserve"))


def simulate_from_soak_row(
    row: Dict[str, Any],
    *,
    notional_rlusd: float,
) -> Optional[FillSimulationResult]:
    """Replay one JSONL row that includes embedded book_depth + AMM reserves."""
    if not row_has_fill_snapshot(row):
        return None
    try:
        book = book_depth_from_json(row["book_depth"])
        pool = amm_pool_from_json(row)
    except (KeyError, TypeError, ValueError):
        return None
    if pool is None:
        return None
    clob_mid = float(row.get("clob_mid_rlusd_per_xrp") or book.mid or 0)
    amm_mid = float(row.get("amm_mid_rlusd_per_xrp") or pool.mid_rlusd_per_xrp)
    direction = "amm_cheaper" if amm_mid < clob_mid else "clob_cheaper"
    return simulate_rlusd_xrp_roundtrip(
        notional_rlusd=notional_rlusd,
        book=book,
        pool=pool,
        direction=direction,
    )


def mid_edge_bps(row: Dict[str, Any]) -> Optional[float]:
    enriched = augment_clob_amm_row(dict(row))
    val = enriched.get("net_edge_bps")
    return float(val) if val is not None else None


def summarize_fill_results(
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not results:
        return {"samples": 0}
    feasible = [r for r in results if r.get("feasible")]
    profitable = [r for r in feasible if float(r.get("profit_bps", 0)) > 0]
    profits = [float(r["profit_bps"]) for r in feasible]
    mid_edges = [float(r["mid_edge_bps"]) for r in results if r.get("mid_edge_bps") is not None]
    fill_edges = [float(r["profit_bps"]) for r in feasible]
    summary = {
        "samples": len(results),
        "feasible": len(feasible),
        "profitable": len(profitable),
        "feasible_pct": round(len(feasible) / len(results) * 100.0, 1),
        "profitable_pct": round(len(profitable) / len(results) * 100.0, 1),
        "avg_mid_edge_bps": round(sum(mid_edges) / len(mid_edges), 2) if mid_edges else None,
        "avg_fill_edge_bps": round(sum(fill_edges) / len(fill_edges), 2) if fill_edges else None,
        "avg_profit_bps_all": round(sum(profits) / len(profits), 2) if profits else None,
        "median_profit_bps": round(sorted(profits)[len(profits) // 2], 2) if profits else None,
        "max_profit_bps": round(max(profits), 2) if profits else None,
        "min_profit_bps": round(min(profits), 2) if profits else None,
    }
    if summary.get("avg_mid_edge_bps") is not None and summary.get("avg_fill_edge_bps") is not None:
        summary["haircut_bps"] = round(
            summary["avg_mid_edge_bps"] - summary["avg_fill_edge_bps"],
            2,
        )
    return summary


DEFAULT_FILL_NOTIONALS_RLUSD: Tuple[float, ...] = (500.0, 1000.0, 2000.0)


def live_fill_simulation_payload(
    row: Optional[Dict[str, Any]],
    *,
    notionals: Sequence[float] = DEFAULT_FILL_NOTIONALS_RLUSD,
) -> Dict[str, Any]:
    """HUD block: walk book+AMM at size for the latest soak row."""
    out: Dict[str, Any] = {
        "available": False,
        "notionals_rlusd": [float(n) for n in notionals],
        "mid_net_bps": mid_edge_bps(row) if row else None,
        "book_bid_levels": 0,
        "book_ask_levels": 0,
        "amm_xrp_reserve": None,
        "amm_rlusd_reserve": None,
        "amm_fee_bps": None,
        "rows": [],
        "note": "Depth snapshot missing — wait for next arb poll.",
    }
    if not row or not row_has_fill_snapshot(row):
        return out

    try:
        book = book_depth_from_json(row["book_depth"])
        pool = amm_pool_from_json(row)
    except (KeyError, TypeError, ValueError):
        out["note"] = "Invalid depth snapshot on latest row."
        return out
    if pool is None:
        out["note"] = "AMM pool reserves missing on latest row."
        return out

    out["available"] = True
    out["book_bid_levels"] = len(book.bids)
    out["book_ask_levels"] = len(book.asks)
    out["amm_xrp_reserve"] = round(pool.xrp_reserve, 2)
    out["amm_rlusd_reserve"] = round(pool.rlusd_reserve, 2)
    out["amm_fee_bps"] = round(pool.fee_bps, 2)
    out["note"] = "Instantaneous 2-leg roundtrip at poll time (best direction per size)."

    rows: List[Dict[str, Any]] = []
    for notional in notionals:
        n = float(notional)
        if n <= 0:
            continue
        sim = best_roundtrip(notional_rlusd=n, book=book, pool=pool)
        rows.append(
            {
                "notional_rlusd": n,
                "direction": sim.direction,
                "profit_bps": round(sim.profit_bps, 2),
                "profit_rlusd": round(sim.profit_rlusd, 4),
                "feasible": sim.feasible,
                "profitable": bool(sim.profit_bps > 0),
                "note": sim.note,
            }
        )
    out["rows"] = rows
    return out


def _load_soak_rows_for_replay(path: Path) -> List[Tuple[Any, Dict[str, Any]]]:
    import json
    from datetime import datetime

    rows: List[Tuple[Any, Dict[str, Any]]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") != "ok" or not row_has_fill_snapshot(row):
            continue
        ts = row.get("ts_utc")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        rows.append((dt, row))
    rows.sort(key=lambda item: item[0])
    return rows


def soak_fill_replay_payload(
    logs_dir: Path,
    *,
    hours: float = 24.0,
    notionals: Sequence[float] = DEFAULT_FILL_NOTIONALS_RLUSD,
) -> Dict[str, Any]:
    """HUD block: replay depth snapshots from JSONL over a rolling window."""
    from datetime import timedelta

    path = logs_dir / "clob_amm_spread.jsonl"
    all_rows = _load_soak_rows_for_replay(path)
    out: Dict[str, Any] = {
        "window_hours": float(hours),
        "depth_samples": 0,
        "notionals_rlusd": [float(n) for n in notionals],
        "by_notional": {},
        "note": "No depth snapshots in soak yet — collector adds book+pool each poll.",
    }
    if not all_rows:
        return out

    end = all_rows[-1][0]
    since = end - timedelta(hours=max(0.25, float(hours)))
    window = [(dt, row) for dt, row in all_rows if dt >= since]
    out["depth_samples"] = len(window)
    out["window_start_utc"] = since.isoformat()
    out["window_end_utc"] = end.isoformat()
    if not window:
        return out

    out["note"] = (
        f"Replay {len(window)} depth snapshots · book walk + AMM pool · "
        f"not mid estimate."
    )

    by_notional: Dict[str, Any] = {}
    for notional in notionals:
        n = float(notional)
        if n <= 0:
            continue
        results: List[Dict[str, Any]] = []
        for _dt, row in window:
            sim = simulate_from_soak_row(row, notional_rlusd=n)
            if sim is None:
                continue
            payload = sim.to_dict()
            payload["mid_edge_bps"] = mid_edge_bps(row)
            results.append(payload)
        by_notional[str(int(n) if n == int(n) else n)] = summarize_fill_results(results)
    out["by_notional"] = by_notional
    return out


def build_arb_fill_simulation_payload(
    *,
    latest: Optional[Dict[str, Any]],
    logs_dir: Path,
    notionals: Sequence[float] = DEFAULT_FILL_NOTIONALS_RLUSD,
    soak_hours: float = 24.0,
) -> Dict[str, Any]:
    return {
        "live": live_fill_simulation_payload(latest, notionals=notionals),
        "soak_replay": soak_fill_replay_payload(
            logs_dir,
            hours=soak_hours,
            notionals=notionals,
        ),
    }

