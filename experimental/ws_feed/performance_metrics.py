"""G3 — Performance Metrics grades (Phase E §7) for HUD / reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from experimental.ws_feed.intel_decisions_log import tail_intel_records

WS_FILL_MARKER = "WS pure fill"


@dataclass(frozen=True)
class MetricGrade:
    id: str
    label: str
    value: str
    grade: str  # good | attention | unknown
    detail: str

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)


def _grade(positive: bool, *, unknown: bool = False) -> str:
    if unknown:
        return "unknown"
    return "good" if positive else "attention"


def _ws_fills_from_trades(logs_dir: Path) -> List[Dict[str, str]]:
    import csv

    rows: List[Dict[str, str]] = []
    for path in sorted(logs_dir.glob("trades_*.csv")):
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for row in csv.DictReader(handle):
                    notes = row.get("notes") or ""
                    if WS_FILL_MARKER not in notes:
                        continue
                    rows.append(row)
        except OSError:
            continue
    return rows


def _fill_capture_stats(fills: List[Dict[str, str]]) -> Dict[str, Any]:
    if not fills:
        return {
            "ws_fills": 0,
            "positive_capture_pct": None,
            "avg_capture_bps": None,
            "neg_capture_count": 0,
            "total_capture_xrp": 0.0,
        }
    pos = 0
    neg = 0
    bps_sum = 0.0
    bps_n = 0
    total_cap = 0.0
    for row in fills:
        try:
            cap = float(row.get("profit_xrp_equiv") or 0)
        except (TypeError, ValueError):
            cap = 0.0
        total_cap += cap
        if cap >= 0:
            pos += 1
        else:
            neg += 1
        try:
            xrp_amt = float(row.get("xrp_amount") or 0)
        except (TypeError, ValueError):
            xrp_amt = 0.0
        if xrp_amt > 0 and cap != 0:
            bps_sum += (cap / xrp_amt) * 10_000.0
            bps_n += 1
    n = len(fills)
    return {
        "ws_fills": n,
        "positive_capture_pct": round(100.0 * pos / n, 1) if n else None,
        "avg_capture_bps": round(bps_sum / bps_n, 2) if bps_n else None,
        "neg_capture_count": neg,
        "neg_capture_pct": round(100.0 * neg / n, 1) if n else None,
        "total_capture_xrp": round(total_cap, 4),
    }


def _peer_coverage_pct(intel_rows: List[Dict[str, Any]]) -> Optional[float]:
    scrapes = [r for r in intel_rows if r.get("kind") == "peer_scrape"]
    if not scrapes:
        return None
    with_peers = sum(1 for r in scrapes if int(r.get("peer_lane_count") or 0) >= 1)
    return round(100.0 * with_peers / len(scrapes), 1)


def build_performance_metrics(
    *,
    runtime: Dict[str, Any],
    logs_dir: Path = Path("logs"),
    intel_tail_limit: int = 400,
) -> Dict[str, Any]:
    """HUD payload: §7 grades + fill stats + recent intel tail."""
    rt = runtime or {}
    fills = _ws_fills_from_trades(logs_dir)
    cap = _fill_capture_stats(fills)
    intel_tail = tail_intel_records(limit=intel_tail_limit, path=logs_dir / "intel_decisions.jsonl")
    peer_cov = _peer_coverage_pct(intel_tail)

    pos_pct = cap.get("positive_capture_pct")
    avg_bps = cap.get("avg_capture_bps")
    neg_pct = cap.get("neg_capture_pct")
    n_fills = int(cap.get("ws_fills") or 0)

    capture_good = (
        n_fills >= 8
        and pos_pct is not None
        and avg_bps is not None
        and pos_pct >= 70.0
        and avg_bps >= 8.0
    )
    capture_attention = (
        n_fills >= 8
        and pos_pct is not None
        and avg_bps is not None
        and (pos_pct < 60.0 or avg_bps < 5.0)
    )

    target_pct = float(rt.get("inventory_target_xrp_pct") or rt.get("inventory_target_xrp_ratio", 0.55) * 100)
    if "inventory_target_xrp_pct" not in rt and "inventory_target_xrp_ratio" in rt:
        target_pct = float(rt["inventory_target_xrp_ratio"]) * 100.0
    xrp_share = rt.get("inventory_xrp_ratio_pct")
    if xrp_share is None and rt.get("xrp_ratio_pct") is not None:
        xrp_share = rt.get("xrp_ratio_pct")
    dev = None
    if xrp_share is not None:
        dev = abs(float(xrp_share) - target_pct)
    inv_good = dev is not None and dev <= 10.0 and (capture_good or n_fills < 8)
    inv_attention = dev is not None and dev > 12.0

    toxic_30 = rt.get("toxic_fill_ratio_30s")
    try:
        toxic_30_f = float(toxic_30) if toxic_30 is not None else None
    except (TypeError, ValueError):
        toxic_30_f = None
    tox_good = toxic_30_f is not None and n_fills >= 8 and toxic_30_f <= 0.20
    tox_attention = toxic_30_f is not None and n_fills >= 8 and toxic_30_f > 0.25

    drawdown = rt.get("drawdown_pct")
    try:
        dd = float(drawdown) if drawdown is not None else None
    except (TypeError, ValueError):
        dd = None
    dd_good = dd is not None and dd <= 10.0
    dd_attention = dd is not None and dd > 15.0

    peer_good = peer_cov is not None and peer_cov >= 50.0
    peer_attention = peer_cov is not None and peer_cov < 30.0

    grades: List[MetricGrade] = [
        MetricGrade(
            id="spread_capture",
            label="Spread capture (§7.1)",
            value=(
                f"{pos_pct}% pos · {avg_bps} bps avg"
                if pos_pct is not None and avg_bps is not None
                else f"{n_fills} fills"
            ),
            grade=_grade(capture_good, unknown=not capture_good and not capture_attention),
            detail="Good: ≥70% positive, ≥8 bps (n≥8)",
        ),
        MetricGrade(
            id="inventory_health",
            label="Inventory vs target (§7.2)",
            value=(
                f"{float(xrp_share):.1f}% XRP (target {target_pct:.0f}%)"
                if xrp_share is not None
                else str(rt.get("inventory_label") or "—")
            ),
            grade=_grade(inv_good, unknown=dev is None),
            detail="Steering metric — deviation within ±10%",
        ),
        MetricGrade(
            id="toxicity",
            label="Toxicity / neg capture (§7.3)",
            value=(
                f"{neg_pct}% neg · toxic@30s {toxic_30_f:.0%}"
                if neg_pct is not None and toxic_30_f is not None
                else (f"{neg_pct}% neg" if neg_pct is not None else "—")
            ),
            grade=_grade(tox_good, unknown=not tox_good and not tox_attention),
            detail="Good: toxic@30s ≤20%",
        ),
        MetricGrade(
            id="drawdown",
            label="Session drawdown (§7.5)",
            value=f"{dd:.2f}%" if dd is not None else "—",
            grade=_grade(dd_good, unknown=dd is None),
            detail="Good: ≤10% daily drawdown mark",
        ),
        MetricGrade(
            id="peer_lane",
            label="Peer lane coverage (§7.6)",
            value=f"{peer_cov}% cycles w/ peer" if peer_cov is not None else "no scrapes yet",
            grade=_grade(peer_good, unknown=peer_cov is None),
            detail="Good: ≥50% scrapes with ≥1 peer in lane",
        ),
    ]

    recent_intel = intel_tail[-12:]
    from experimental.ws_feed.live_activation_grading import summarize_activation

    activation = summarize_activation(
        runtime=rt,
        performance_metrics={
            "grades": [g.as_dict() for g in grades],
            "capture": cap,
        },
        intel_rows=intel_tail,
    )
    return {
        "grades": [g.as_dict() for g in grades],
        "capture": cap,
        "peer_coverage_pct": peer_cov,
        "intel_log_lines": len(intel_tail),
        "recent_intel": recent_intel,
        "e15_fills_gate": 50,
        "e15_fills_met": n_fills >= 50,
        "activation": activation,
    }
