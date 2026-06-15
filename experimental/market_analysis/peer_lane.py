"""
G1 — posted-touch peer lane + fled-touch detection (Phase G / E.1).

Peer lane ruler: our posted L1 touch vs competitors' touch size on the live book.
Fled touch: account was at BBO last scrape, gone from touch this scrape (panic-cancel proxy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class PeerLaneConfig:
    peer_low_mult: float = 0.4
    peer_high_mult: float = 2.5
    min_peers: int = 1
    widen_factor: float = 1.5
    price_match_eps: float = 1e-6
    fled_max_age_s: float = 120.0


@dataclass
class PeerLaneResult:
    our_lane_xrp: float
    peer_low_xrp: float
    peer_high_xrp: float
    peer_lane_count: int = 0
    peer_accounts: List[str] = field(default_factory=list)
    touch_by_account: Dict[str, float] = field(default_factory=dict)
    widened: bool = False
    empty: bool = False


@dataclass
class FledTouchEvent:
    account: str
    previous_touch_xrp: float
    age_s: float
    in_peer_lane: bool


def our_lane_from_runtime(
    *,
    l1_xrp: Optional[float] = None,
    bid_size_xrp: Optional[float] = None,
    ask_size_xrp: Optional[float] = None,
    quote_intents: Optional[Sequence[Mapping[str, Any]]] = None,
) -> float:
    """Posted touch size for peer matching (max L1 active side)."""
    if quote_intents:
        touch_sizes: List[float] = []
        for intent in quote_intents:
            if int(intent.get("level") or 0) != 1:
                continue
            if intent.get("active") is False:
                continue
            try:
                touch_sizes.append(float(intent.get("size_xrp") or 0))
            except (TypeError, ValueError):
                continue
        if touch_sizes:
            return max(touch_sizes)
    candidates: List[float] = []
    for v in (l1_xrp, bid_size_xrp, ask_size_xrp):
        if v is not None:
            try:
                f = float(v)
                if f > 0:
                    candidates.append(f)
            except (TypeError, ValueError):
                pass
    return max(candidates) if candidates else 0.0


def book_best_prices(
    bids: Sequence[Mapping[str, Any]],
    asks: Sequence[Mapping[str, Any]],
) -> Tuple[Optional[float], Optional[float]]:
    bid_prices = [_float(o.get("price")) for o in bids if _float(o.get("price"))]
    ask_prices = [_float(o.get("price")) for o in asks if _float(o.get("price"))]
    best_bid = max(bid_prices) if bid_prices else None
    best_ask = min(ask_prices) if ask_prices else None
    return best_bid, best_ask


def compute_touch_by_account(
    bids: Sequence[Mapping[str, Any]],
    asks: Sequence[Mapping[str, Any]],
    *,
    best_bid: Optional[float],
    best_ask: Optional[float],
    eps: float = PeerLaneConfig.price_match_eps,
) -> Dict[str, float]:
    """Per-account max size at global best bid / best ask (posted touch)."""
    bid_touch: Dict[str, float] = {}
    ask_touch: Dict[str, float] = {}
    if best_bid is not None:
        for o in bids:
            price = _float(o.get("price"))
            if price is None or abs(price - best_bid) > eps:
                continue
            acct = _account(o)
            if not acct:
                continue
            size = _float(o.get("size")) or 0.0
            bid_touch[acct] = bid_touch.get(acct, 0.0) + size
    if best_ask is not None:
        for o in asks:
            price = _float(o.get("price"))
            if price is None or abs(price - best_ask) > eps:
                continue
            acct = _account(o)
            if not acct:
                continue
            size = _float(o.get("size")) or 0.0
            ask_touch[acct] = ask_touch.get(acct, 0.0) + size
    touch: Dict[str, float] = {}
    for acct in set(bid_touch) | set(ask_touch):
        touch[acct] = max(bid_touch.get(acct, 0.0), ask_touch.get(acct, 0.0))
    return touch


def select_peer_lane(
    touch_by_account: Mapping[str, float],
    our_lane_xrp: float,
    config: Optional[PeerLaneConfig] = None,
) -> PeerLaneResult:
    cfg = config or PeerLaneConfig()
    our_lane = max(0.0, float(our_lane_xrp))
    result = PeerLaneResult(
        our_lane_xrp=our_lane,
        peer_low_xrp=0.0,
        peer_high_xrp=0.0,
        touch_by_account=dict(touch_by_account),
    )
    if our_lane <= 0:
        result.empty = True
        return result

    low = our_lane * cfg.peer_low_mult
    high = our_lane * cfg.peer_high_mult
    result.peer_low_xrp = low
    result.peer_high_xrp = high

    def _in_band(touch: float, lo: float, hi: float) -> bool:
        return lo <= touch <= hi

    peers = [a for a, t in touch_by_account.items() if _in_band(t, low, high)]
    if len(peers) < cfg.min_peers:
        low_w = low / cfg.widen_factor
        high_w = high * cfg.widen_factor
        peers = [a for a, t in touch_by_account.items() if _in_band(t, low_w, high_w)]
        if len(peers) >= cfg.min_peers:
            result.widened = True
            result.peer_low_xrp = low_w
            result.peer_high_xrp = high_w

    result.peer_accounts = sorted(peers, key=lambda a: touch_by_account.get(a, 0.0), reverse=True)
    result.peer_lane_count = len(result.peer_accounts)
    result.empty = result.peer_lane_count == 0
    return result


def touch_in_peer_band(
    touch_xrp: float,
    our_lane_xrp: float,
    config: Optional[PeerLaneConfig] = None,
    *,
    allow_widen: bool = True,
) -> bool:
    cfg = config or PeerLaneConfig()
    lane = max(0.0, float(our_lane_xrp))
    touch = float(touch_xrp)
    if lane <= 0 or touch <= 0:
        return False
    low = lane * cfg.peer_low_mult
    high = lane * cfg.peer_high_mult
    if low <= touch <= high:
        return True
    if allow_widen:
        low_w = low / cfg.widen_factor
        high_w = high * cfg.widen_factor
        return low_w <= touch <= high_w
    return False


def detect_fled_touch(
    prev_touch: Mapping[str, float],
    current_touch: Mapping[str, float],
    *,
    our_lane_xrp: float,
    config: Optional[PeerLaneConfig] = None,
    age_s: float,
    max_age_s: float = PeerLaneConfig.fled_max_age_s,
) -> List[FledTouchEvent]:
    """Accounts that were at BBO touch last scrape but not at touch now."""
    if age_s <= 0 or age_s > max_age_s:
        return []
    cfg = config or PeerLaneConfig()
    events: List[FledTouchEvent] = []
    for acct, prev_size in prev_touch.items():
        if acct in current_touch:
            continue
        events.append(
            FledTouchEvent(
                account=acct,
                previous_touch_xrp=float(prev_size),
                age_s=float(age_s),
                in_peer_lane=touch_in_peer_band(prev_size, our_lane_xrp, cfg),
            )
        )
    return events


def aggregate_peer_pressure(
    *,
    peer_spreads: Sequence[float],
    global_spread: float,
    peer_count: int,
    fled_in_lane_count: int,
    cancel_proxy_rate: float = 0.0,
) -> float:
    """
    Pressure from peer-lane makers only. Lower = more defensive / skim opportunity.
    Fled-touch peers in lane nudge pressure down (they left touch — weakness).
    """
    if peer_count <= 0:
        return 0.5
    obs = min(peer_spreads) if peer_spreads else global_spread
    if obs <= 0:
        return 0.5
    pressure = min(1.0, (obs / 0.20) * 0.6 + cancel_proxy_rate * 0.4)
    if fled_in_lane_count > 0:
        pressure = max(0.0, pressure - 0.06 * min(fled_in_lane_count, 4))
    return round(pressure, 3)


def _float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _account(offer: Mapping[str, Any]) -> str:
    return str(
        offer.get("account")
        or offer.get("Account")
        or offer.get("Owner")
        or ""
    ).strip()
