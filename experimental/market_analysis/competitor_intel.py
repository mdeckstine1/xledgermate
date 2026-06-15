#!/usr/bin/env python3
"""
Aggressive on-chain competitor intelligence for RLUSD/XRP MM.

Goal: Scrape harder than the competition. XRPL is fully public — every offer,
cancel, and fill is visible forever. Other MM bots' quoting behavior, sizes,
reaction times, inventory management (inferred), and aggressiveness are all
scrapeable.

This extends the external_data pattern. Use it to:
- Build profiles of top makers on the book.
- Detect when competitors are "wide" or "defensive" → opportunity for tighter A-S quotes.
- Spot "toxic flow" patterns from their cancel behavior before adverse moves.
- Infer effective liquidity they provide.
- Feed as signals into pure A-S inputs (vol proxy, liquidity, book pressure, adverse selection proxy)
  or the replicated wiring (for richer decision strings), while keeping the
  final presence decision as A-S reservation inside the book.

No hard gates. Pure A-S math decides quoting. Competitor data just makes the
math smarter (better vol, better "is edge real" assessment).

All experimental. Use with replay_long_run.py on the sacred data to backtest
"what if we had seen competitor X posting 0.12% while on-chain said 0.05% thin".
Drive with current 150-fill+ run's thin-book 0-offer cycles.

How to scrape harder:
1. Real-time: WS subscribe to books + transactions. Group offers by account.
2. Historical: Repeated BookOffers snapshots + AccountTx for active makers.
3. Pattern match: Accounts with high offer volume, frequent small cancels,
   consistent two-sided quoting, size changes correlated with fills/price.
4. Metrics per competitor:
   - avg_posted_spread
   - size_at_touch
   - cancel_rate (esp. after our fills or price moves)
   - time_in_book
   - skew behavior (more aggressive on one side?)
5. Aggregate:
   - total_competitor_depth
   - "observed_market_spread" (min of what competitors actually post)
   - pressure signals (if many competitors cancel on one side → toxicity?)

Expansion:
- Track specific known competitor accounts (add to config or discover dynamically).
- Persist profiles to jsonl or DB for long-term learning.
- Use in AI analyzer (stub_llm) as extra context: "competitors posting wide, low cancel rate → skimmable".
- Fuse with Anodos secondary for "real depth vs on-chain thin + competitor behavior".
- In live pure A-S tester: inject live competitor signals, see A-S reservation move.

Do not touch sacred long-run. Keep in experimental/market_analysis/.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from connectors.xrpl_connector import XRPLConnector
from experimental.market_analysis.external_data import ExternalMarketDataProvider, ExternalMarketSnapshot
from experimental.market_analysis.peer_lane import (
    PeerLaneConfig,
    aggregate_peer_pressure,
    book_best_prices,
    compute_touch_by_account,
    detect_fled_touch,
    select_peer_lane,
)

logger = logging.getLogger(__name__)


@dataclass
class CompetitorProfile:
    """Profile of one observed MM bot / active maker."""
    account: str
    total_offers_seen: int = 0
    total_cancels: int = 0
    avg_spread_pct: float = 0.0
    last_spread_pct: float = 0.0
    avg_size_xrp: float = 0.0
    last_seen_ts: float = 0.0
    cancel_after_fill_count: int = 0  # rough toxicity proxy
    sides_quoted: Dict[str, int] = field(default_factory=lambda: {"bid": 0, "ask": 0})
    domain: Optional[str] = None  # On-chain Domain from AccountInfo (best "name" we get)
    # Note on IDs: XRPL has **no native "full name" or username tokens** on-chain (unlike some other chains).
    # - Primary identifier: the r-address (pseudonymous).
    # - Best on-ledger "name": the optional `Domain` field (set in AccountSet tx, stored hex-encoded; we decode it). Can be verified externally via DNS TXT if the owner set it up.
    # - No standard "ledger tokens" used for identity here. Some issuers create custom NFTs or issued currencies as badges, but MM bots rarely use them.
    # - To go further: cross-reference with public known-accounts lists (Bithomp, XRPSCAN, xrpl.org known issuers), or scan memos in their txs, or funding history via AccountTx.
    # We now fetch Domain automatically for better labeling in the Intelligence tab.
    # Future: cross with public known-accounts DBs (bithomp, xrpscan, etc.) or memo scanning.


@dataclass
class CompetitorSnapshot:
    """Aggregated competitor intel at a point in time. Feed to A-S / wiring."""
    top_makers: List[CompetitorProfile] = field(default_factory=list)
    observed_market_spread_pct: float = 0.0   # tightest actual competitor spread
    total_competitor_depth_xrp: float = 0.0
    avg_competitor_cancel_rate: float = 0.0
    num_active_makers: int = 0
    pressure_score: float = 0.5  # 0=defensive (good for us to be aggressive), 1=aggressive
    source: str = "onchain-competitor"
    age_seconds: float = 0.0
    # G1 peer lane (posted touch band)
    our_lane_xrp: float = 0.0
    peer_lane_count: int = 0
    peer_lane_low_xrp: float = 0.0
    peer_lane_high_xrp: float = 0.0
    peer_pressure_score: float = 0.5
    peer_observed_spread_pct: float = 0.0
    peer_fled_touch_count: int = 0
    peer_fled_events: List[Dict[str, Any]] = field(default_factory=list)
    top_peers: List[CompetitorProfile] = field(default_factory=list)
    peer_lane_widened: bool = False
    peer_lane_empty: bool = False


class CompetitorIntelProvider(ExternalMarketDataProvider):
    """
    On-chain scraper + profiler for other makers on the RLUSD/XRP book.

    "Scrape harder": 
    - Continuously monitor the live book via connector (or WS feed).
    - Group every visible offer by account.
    - Maintain rolling profiles.
    - Compute aggregate signals that pure A-S can use as better inputs
      (e.g. "real" liquidity is higher/lower than on-chain thin view because
       of what competitors are actually posting/cancelling).

    Usage in pure A-S path (future):
        intel = await competitor_provider.fetch_snapshot()
        extra_vol = intel.pressure_score * 0.5   # or something
        as_quote = strat.compute_avellaneda_quote(..., book_spread_pct=..., 
                                                  competitor_liquidity=intel.total_competitor_depth_xrp)
        # Then still: reservation inside book decides quoting. No hard gate.

    In replay: inject historical competitor profiles derived from past run data
    or concurrent scrape during the sacred long-run.

    To go even harder (add later):
    - WS transaction stream filtered to OfferCreate/Cancel for the pair.
    - Track specific high-volume accounts over days/weeks.
    - Correlate their cancels with subsequent price moves (adverse selection detector).
    - Cross with our own fills: did a competitor get hit right before us?
    """

    def __init__(
        self,
        connector: XRPLConnector,
        pair: Any,
        lookback_offers: int = 40,
        peer_lane_config: Optional[PeerLaneConfig] = None,
    ):
        self.connector = connector
        self.pair = pair
        self.lookback_offers = lookback_offers
        self.peer_lane_config = peer_lane_config or PeerLaneConfig()
        self._profiles: Dict[str, CompetitorProfile] = {}
        self._last_fetch = 0.0
        self._cache: Optional[CompetitorSnapshot] = None
        self._prev_touch: Dict[str, float] = {}
        self._prev_fetch_ts: float = 0.0
        self._recent_fled: List[Dict[str, Any]] = []
        self._last_touch_by_account: Dict[str, float] = {}

    async def fetch_snapshot(
        self,
        *,
        our_lane_xrp: Optional[float] = None,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None,
        ws_bids: Optional[List[Dict[str, Any]]] = None,
        ws_asks: Optional[List[Dict[str, Any]]] = None,
    ) -> CompetitorSnapshot:
        """Scrape current book, update profiles, return aggregate intel."""
        now = time.monotonic()
        peer_mode = our_lane_xrp is not None and float(our_lane_xrp) > 0
        if self._cache and (now - self._last_fetch) < 10 and not peer_mode:
            return self._cache

        try:
            book = await self.connector.fetch_order_book(limit=self.lookback_offers)
        except Exception:
            logger.exception("Competitor scrape failed, returning stale")
            return self._cache or CompetitorSnapshot(source="onchain-competitor-failed")

        bids = book.get("bids", [])
        asks = book.get("asks", [])
        all_offers = bids + asks

        # Group by account (raw offers from connector should have 'account' or we normalize)
        # NOTE: In real use, ensure _normalize_offers or raw keeps the account.
        # For stub, we simulate accounts if missing.
        maker_offers: Dict[str, List[Dict]] = defaultdict(list)
        for o in all_offers:
            acct = o.get("account") or o.get("Account") or f"unknown_{hash(str(o)) % 1000}"
            maker_offers[acct].append(o)

        # Update profiles (aggressive scraping: every offer counts)
        for acct, offers in maker_offers.items():
            if acct not in self._profiles:
                self._profiles[acct] = CompetitorProfile(account=acct)

            prof = self._profiles[acct]
            prof.total_offers_seen += len(offers)
            prof.last_seen_ts = now

            # Compute spreads/sizes for this maker's current quotes
            maker_bids = [o for o in offers if o.get("side") == "bid"]
            maker_asks = [o for o in offers if o.get("side") == "ask"]
            if maker_bids and maker_asks:
                bb = max(b["price"] for b in maker_bids)
                ba = min(a["price"] for a in maker_asks)
                if bb and ba and bb > 0:
                    mid = (bb + ba) / 2
                    spr = (ba - bb) / mid * 100.0
                    prof.last_spread_pct = spr
                    # simple EWMA for avg
                    prof.avg_spread_pct = 0.9 * prof.avg_spread_pct + 0.1 * spr if prof.avg_spread_pct else spr

            total_size = sum(o.get("size", 0) for o in offers)
            if total_size:
                prof.avg_size_xrp = 0.9 * prof.avg_size_xrp + 0.1 * total_size if prof.avg_size_xrp else total_size

            prof.sides_quoted["bid"] += len(maker_bids)
            prof.sides_quoted["ask"] += len(maker_asks)

            # Enrich with on-chain identity (Domain is the closest to "full name" on XRPL)
            if not prof.domain:
                try:
                    domain = await self._fetch_account_domain(acct)
                    if domain:
                        prof.domain = domain
                        logger.info(f"Identified competitor {acct[:8]}... with domain: {domain}")
                except Exception:
                    pass  # silent, many accounts have no domain

        # Aggregate snapshot (this is what feeds A-S / HUD / replay)
        active = [p for p in self._profiles.values() if now - p.last_seen_ts < 300]
        if not active:
            snap = CompetitorSnapshot(source="onchain-competitor-no-active")
        else:
            # "observed market spread" = tightest actual competitor quotes
            spreads = [p.last_spread_pct for p in active if p.last_spread_pct > 0]
            obs_spread = min(spreads) if spreads else 0.0

            total_depth = sum(p.avg_size_xrp for p in active)
            cancel_rate = sum(p.total_cancels for p in active) / max(1, sum(p.total_offers_seen for p in active))

            # Pressure: if observed spreads are wide + high cancel rate → competitors defensive → good for us to scrape harder
            pressure = min(1.0, (obs_spread / 0.20) * 0.6 + cancel_rate * 0.4) if obs_spread else 0.5

            snap = CompetitorSnapshot(
                top_makers=sorted(active, key=lambda p: p.total_offers_seen, reverse=True)[:5],
                observed_market_spread_pct=obs_spread,
                total_competitor_depth_xrp=round(total_depth, 2),
                avg_competitor_cancel_rate=round(cancel_rate, 3),
                num_active_makers=len(active),
                pressure_score=round(pressure, 3),
                source="onchain-competitor",
                age_seconds=0.0,
            )

        snap = self._apply_peer_lane(
            snap,
            bids=bids,
            asks=asks,
            our_lane_xrp=our_lane_xrp,
            best_bid=best_bid,
            best_ask=best_ask,
            ws_bids=ws_bids,
            ws_asks=ws_asks,
            now=now,
        )

        self._cache = snap
        self._last_fetch = now
        return snap

    def _apply_peer_lane(
        self,
        snap: CompetitorSnapshot,
        *,
        bids: List[Dict[str, Any]],
        asks: List[Dict[str, Any]],
        our_lane_xrp: Optional[float],
        best_bid: Optional[float],
        best_ask: Optional[float],
        ws_bids: Optional[List[Dict[str, Any]]],
        ws_asks: Optional[List[Dict[str, Any]]],
        now: float,
    ) -> CompetitorSnapshot:
        """Posted-touch peer band + fled-touch detection (G1 / E.1)."""
        lane = float(our_lane_xrp or 0.0)
        if lane <= 0:
            return snap

        touch_bids = ws_bids if ws_bids is not None else bids
        touch_asks = ws_asks if ws_asks is not None else asks
        bb = best_bid
        ba = best_ask
        if bb is None or ba is None:
            bb, ba = book_best_prices(touch_bids, touch_asks)

        touch_by_account = compute_touch_by_account(
            touch_bids,
            touch_asks,
            best_bid=bb,
            best_ask=ba,
            eps=self.peer_lane_config.price_match_eps,
        )
        peer_result = select_peer_lane(touch_by_account, lane, self.peer_lane_config)

        age_s = now - self._prev_fetch_ts if self._prev_fetch_ts > 0 else 0.0
        fled_events = detect_fled_touch(
            self._prev_touch,
            touch_by_account,
            our_lane_xrp=lane,
            config=self.peer_lane_config,
            age_s=age_s,
            max_age_s=self.peer_lane_config.fled_max_age_s,
        )
        fled_in_lane = [e for e in fled_events if e.in_peer_lane]
        for event in fled_events:
            prof = self._profiles.get(event.account)
            if prof is None:
                prof = CompetitorProfile(account=event.account)
                self._profiles[event.account] = prof
            prof.total_cancels += 1
            if event.in_peer_lane:
                prof.cancel_after_fill_count += 1

        fled_payload = [
            {
                "account": e.account[:12] + "...",
                "account_full": e.account,
                "previous_touch_xrp": round(e.previous_touch_xrp, 2),
                "age_s": round(e.age_s, 1),
                "in_peer_lane": e.in_peer_lane,
            }
            for e in fled_events[:10]
        ]
        if fled_payload:
            self._recent_fled = (fled_payload + self._recent_fled)[:20]

        peer_profiles = [
            self._profiles[a]
            for a in peer_result.peer_accounts
            if a in self._profiles
        ]
        peer_spreads = [p.last_spread_pct for p in peer_profiles if p.last_spread_pct > 0]
        peer_obs = min(peer_spreads) if peer_spreads else snap.observed_market_spread_pct
        peer_cancel_rate = 0.0
        if peer_profiles:
            offers = sum(p.total_offers_seen for p in peer_profiles)
            cancels = sum(p.total_cancels for p in peer_profiles)
            peer_cancel_rate = cancels / max(1, offers)

        peer_pressure = aggregate_peer_pressure(
            peer_spreads=peer_spreads,
            global_spread=snap.observed_market_spread_pct,
            peer_count=peer_result.peer_lane_count,
            fled_in_lane_count=len(fled_in_lane),
            cancel_proxy_rate=peer_cancel_rate,
        )

        snap.our_lane_xrp = round(lane, 2)
        snap.peer_lane_count = peer_result.peer_lane_count
        snap.peer_lane_low_xrp = round(peer_result.peer_low_xrp, 2)
        snap.peer_lane_high_xrp = round(peer_result.peer_high_xrp, 2)
        snap.peer_pressure_score = peer_pressure
        snap.peer_observed_spread_pct = round(peer_obs, 4)
        snap.peer_fled_touch_count = len(fled_in_lane)
        snap.peer_fled_events = fled_payload
        snap.top_peers = peer_profiles[:5]
        snap.peer_lane_widened = peer_result.widened
        snap.peer_lane_empty = peer_result.empty
        if peer_result.peer_lane_count > 0:
            snap.pressure_score = peer_pressure

        self._prev_touch = dict(touch_by_account)
        self._prev_fetch_ts = now
        self._last_touch_by_account = touch_by_account
        return snap

    async def scrape_historical(self, hours: int = 1) -> List[Dict[str, Any]]:
        """
        Harder scrape: walk recent history (via AccountTx or repeated snapshots).
        For production use a full history node or service.
        Returns list of "offer events" for analysis / replay injection.
        """
        # Placeholder — real impl would use connector.account_tx or ledger iteration
        # filtered to the pair + OfferCreate/Cancel.
        logger.info("Historical competitor scrape stub called for last %d hours", hours)
        return []  # TODO: implement with connector + filtering

    async def _fetch_account_domain(self, acct: str) -> Optional[str]:
        """Fetch AccountInfo and extract + decode the Domain field if present.
        This is the main on-chain 'name' / identifier we can get without external DBs.
        Domain is stored hex-encoded on-ledger.
        """
        try:
            from xrpl.models.requests import AccountInfo
            req = AccountInfo(account=acct, ledger_index="validated")
            # Use the connector's low-level request if available
            if hasattr(self.connector, "_request"):
                result = await self.connector._request(req)
            else:
                # Fallback: direct client if exposed (xrpl-py style)
                async with self.connector._client as client:  # may need adjustment
                    result = await client.request(req)
            data = result.result.get("account_data", {})
            if "Domain" in data and data["Domain"]:
                domain_hex = data["Domain"]
                try:
                    domain = bytes.fromhex(domain_hex).decode("utf-8", errors="ignore").strip()
                    return domain if domain else None
                except Exception:
                    return None
            return None
        except Exception as e:
            logger.debug(f"Could not fetch domain for {acct}: {e}")
            return None

    def get_pressure_as_vol_proxy(self, snap: Optional[CompetitorSnapshot] = None) -> float:
        """Convenience: turn competitor pressure into a vol-like input for A-S."""
        if snap is None:
            snap = self._cache
        if not snap or snap.pressure_score is None:
            return 0.5
        # Higher pressure (aggressive competitors) → treat as higher "adverse" vol
        return max(0.3, min(2.0, snap.pressure_score * 1.5))

    def get_skim_recommendation(self, snap: Optional[CompetitorSnapshot] = None) -> str:
        """Pure A-S focused advice for skimming harder based on competitor intel.
        Low pressure = competitors are wide/defensive → A-S can be more aggressive (tighter quotes, more presence).
        High pressure = they are fighting hard → let A-S math protect by being more conservative.
        """
        if snap is None:
            snap = self._cache
        if not snap:
            return "No competitor data yet. Run with live book to start scraping."

        p = snap.pressure_score
        fled_note = ""
        if snap.peer_fled_touch_count > 0:
            fled_note = (
                f" {snap.peer_fled_touch_count} peer(s) fled touch since last scrape "
                "(panic-cancel proxy) — defensive weakness, skim opportunity."
            )
        if p < 0.3:
            return (
                "SCRAPE HARDER: Low competitor pressure (defensive/wide). Blend lower effective vol into A-S. "
                "Expect tighter reservation, more two-sided presence. Beat them by posting inside their observed spread when math allows."
                + fled_note
            )
        elif p > 0.7:
            return (
                "CAUTIOUS: High pressure (aggressive competitors). A-S will naturally back off via higher effective vol. "
                "Use their liquidity as signal but let reservation decide. Don't over-scrape."
                + fled_note
            )
        else:
            return (
                "NEUTRAL: Monitor. Use observed spread as 'real' market spread for A-S inputs. "
                "Good for calibration of gamma/kappa against what competitors actually post."
                + fled_note
            )

    def to_hud_state(self, snap: Optional[CompetitorSnapshot] = None) -> Dict[str, Any]:
        """Serialize for HUD / runtime (top makers, aggregates, advice)."""
        if snap is None:
            snap = self._cache
        if not snap:
            return {"competitor_error": "no data"}
        effective_pressure = (
            snap.peer_pressure_score if snap.peer_lane_count > 0 else snap.pressure_score
        )
        effective_spread = (
            snap.peer_observed_spread_pct
            if snap.peer_lane_count > 0 and snap.peer_observed_spread_pct > 0
            else snap.observed_market_spread_pct
        )
        peer_list = snap.top_peers if snap.top_peers else snap.top_makers

        def _profile_row(p: CompetitorProfile, *, touch_xrp: float = 0.0) -> Dict[str, Any]:
            tx = touch_xrp or self._last_touch_by_account.get(p.account, 0.0)
            return {
                "account": p.account[:12] + "...",
                "account_full": p.account,
                "last_spread": round(p.last_spread_pct, 3),
                "avg_spread": round(p.avg_spread_pct, 3),
                "activity": p.total_offers_seen,
                "sides": f"b{p.sides_quoted.get('bid', 0)}/a{p.sides_quoted.get('ask', 0)}",
                "domain": p.domain or "no-domain",
                "touch_xrp": round(tx, 2),
                "cancels": p.total_cancels,
            }

        return {
            "competitor_observed_spread_pct": effective_spread,
            "competitor_pressure": effective_pressure,
            "competitor_depth_xrp": snap.total_competitor_depth_xrp,
            "num_active_mms": snap.num_active_makers,
            "competitor_skim_advice": self.get_skim_recommendation(snap),
            "our_lane_xrp": snap.our_lane_xrp,
            "peer_lane_count": snap.peer_lane_count,
            "peer_lane_low_xrp": snap.peer_lane_low_xrp,
            "peer_lane_high_xrp": snap.peer_lane_high_xrp,
            "peer_pressure_score": snap.peer_pressure_score,
            "peer_observed_spread_pct": snap.peer_observed_spread_pct,
            "peer_fled_touch_count": snap.peer_fled_touch_count,
            "peer_fled_events": snap.peer_fled_events or self._recent_fled[:5],
            "peer_lane_widened": snap.peer_lane_widened,
            "peer_lane_empty": snap.peer_lane_empty,
            "top_competitors": [_profile_row(p) for p in snap.top_makers[:5]],
            "top_peers": [_profile_row(p) for p in peer_list[:5]],
        }


# Example integration stub (use in live tester or replay)
async def get_competitor_signals(
    provider: CompetitorIntelProvider,
    *,
    our_lane_xrp: Optional[float] = None,
    best_bid: Optional[float] = None,
    best_ask: Optional[float] = None,
    ws_bids: Optional[List[Dict[str, Any]]] = None,
    ws_asks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    snap = await provider.fetch_snapshot(
        our_lane_xrp=our_lane_xrp,
        best_bid=best_bid,
        best_ask=best_ask,
        ws_bids=ws_bids,
        ws_asks=ws_asks,
    )
    pressure = snap.peer_pressure_score if snap.peer_lane_count > 0 else snap.pressure_score
    spread = (
        snap.peer_observed_spread_pct
        if snap.peer_lane_count > 0 and snap.peer_observed_spread_pct > 0
        else snap.observed_market_spread_pct
    )
    return {
        "competitor_observed_spread_pct": spread,
        "competitor_depth_xrp": snap.total_competitor_depth_xrp,
        "competitor_pressure": pressure,
        "peer_competitor_pressure": snap.peer_pressure_score,
        "num_active_mms": snap.num_active_makers,
        "peer_lane_count": snap.peer_lane_count,
        "peer_fled_touch_count": snap.peer_fled_touch_count,
        "our_lane_xrp": snap.our_lane_xrp,
        "top_maker_spreads": [p.last_spread_pct for p in snap.top_makers[:3]],
        "top_peer_spreads": [p.last_spread_pct for p in snap.top_peers[:3]],
    }


if __name__ == "__main__":
    # Quick manual scrape test (run from repo root with venv)
    # python -m experimental.market_analysis.competitor_intel
    import sys
    sys.path.insert(0, ".")
    from config.settings import BotConfig
    from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
    from experimental.ws_feed.pair_books import RlusdXrpPair

    async def _demo():
        cfg = BotConfig.load()
        conn = XRPLConnector(
            account_address=cfg.bot_account_address or "r...",
            secret=None,
            rlusd_issuer=cfg.resolved_rlusd_issuer(),
            rlusd_currency=cfg.rlusd_currency,
            network=XRPLNetworkConfig(json_rpc_url=cfg.resolved_rpc_url()),
        )
        pair = RlusdXrpPair(rlusd_issuer=cfg.resolved_rlusd_issuer(), rlusd_currency=cfg.rlusd_currency)
        prov = CompetitorIntelProvider(conn, pair)
        snap = await prov.fetch_snapshot()
        print("Competitor intel snapshot:")
        print(f"  Active makers: {snap.num_active_makers}")
        print(f"  Observed market spread: {snap.observed_market_spread_pct:.4f}%")
        print(f"  Pressure (0=defensive/good for us): {snap.pressure_score}")
        print(f"  Top makers (by activity): {[ (p.account[:8], round(p.last_spread_pct,3)) for p in snap.top_makers[:3] ]}")
        print("Use this as extra input to pure A-S for smarter skimming.")

    asyncio.run(_demo())
