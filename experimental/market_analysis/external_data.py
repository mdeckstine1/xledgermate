from __future__ import annotations

"""
Starter for 3rd-party market analysis / external signals.

Goal (per user direction): Begin looking at external data sources to improve
volatility, liquidity, depth, and other signals beyond on-chain book poll/WS.
This feeds better edge detection, profile selection, and skimming without
increasing toxic risk.

Current main run (150-fill long run post hard-gate) shows many "edge thin /
L1 too tight / Generated 0 / off-book (toxic)" cycles on thin books. External
data (e.g., cross-venue vol, funding, order-flow proxies, on-chain metrics
from other sources) can help decide when the book is "truly" skimmable vs.
when the poll/WS view is misleading due to thinness or manipulation.

Design for expansion/growth on competitive MM:
- Abstract providers (Kaiko, CoinGecko, Dune Analytics, proprietary feeds,
  other DEX order books, CEX depth, etc.).
- Fuse with on-chain WS/poll data in perception or a new "MarketContext".
- Future: full A-S model inputs, ML toxicity prediction, multi-venue arb,
  dynamic min_edge based on external regime detection.
- Keep lightweight now; no hard dependency on any 3rd party until after
  Gate 2 judgment and WS integration.

All work here in experimental/ on grok-ws-feed. Use replay_long_run.py
+ current run logs to backtest whether adding an external vol signal would
have flipped edge_met in the 0-offer periods of the 150-fill (and prior) runs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExternalMarketSnapshot:
    """Normalized external signals. Extend as we add providers."""
    volatility_pct: Optional[float] = None      # annualized or short-term realized
    liquidity_score: Optional[float] = None     # 0-1 normalized depth/volume
    mid_price: Optional[float] = None           # external reference mid (for drift detection)
    source: str = "unknown"
    age_seconds: float = float("inf")


class ExternalMarketDataProvider(ABC):
    """Base for 3rd-party / external market data sources.

    Start simple (stub + one public example). Expand later for competitive
    growth (multi-source fusion, latency-aware, regime detection for
    aggressive skimming on good external conditions).
    """

    @abstractmethod
    async def fetch_snapshot(self) -> ExternalMarketSnapshot:
        """Return latest external view. Should be fast and cached."""
        ...

    def is_fresh(self, snap: ExternalMarketSnapshot, max_age_s: float = 60.0) -> bool:
        return snap.age_seconds < max_age_s


class StubExternalProvider(ExternalMarketDataProvider):
    """No-op provider for now. Replace with real 3rd party (e.g. public REST
    for 24h vol, or paid depth from Kaiko/others).

    In replay mode we can inject signals derived from the long run's own
    portfolio_snapshots or decisions to simulate "what if we had external vol
    telling us the book was healthy".
    """

    async def fetch_snapshot(self) -> ExternalMarketSnapshot:
        return ExternalMarketSnapshot(source="stub")


class AnodosFinanceProvider(ExternalMarketDataProvider):
    """
    Secondary data provider using Anodos Finance (or similar XRPL analytics
    services) for enriched / backup book and market data.

    Why secondary: Direct rippled WS/HTTP can be thin, load-balanced to stale
    nodes, or missing good snapshots (exactly the issues seen in the current
    150-fill run: many hard-gate triggers on "thin book", L1 spreads 0.15%+ but
    edge calc says too tight, 0 offers, low visibility).

    Anodos (and peers) often provide:
    - More reliable / aggregated order book snapshots
    - Historical depth, better mid/liquidity estimates
    - Cross-referenced trades, holder data, on-chain metrics
    - Potentially lower latency or cached "last good" views

    Use cases for WS book dev (driven by current run data):
    - Initial snapshot on subscribe (instead of or in addition to direct BookOffers)
    - Reconciliation / drift detection: compare WS mid to Anodos mid; if drift > threshold, force resync or blend
    - Trust / edge enhancement: if on-chain book looks thin but Anodos shows healthy depth/liquidity, relax the hard gate or widen less aggressively
    - Backtest: In replay_long_run.py, simulate "what if we had Anodos secondary mid/snapshot" during the cycles where the poll-based system (and hard gate) produced 0 quotes on thin books. Measure impact on presence (the main Gap 2 / Tier C issue in the 150-fill and prior runs).

    API note: Anodos typically exposes REST endpoints (e.g. /api/v1/book or similar for XRP/RLUSD).
    This is a stub; in real use you'd add aiohttp requests, caching, rate limiting,
    and fallback logic. No auth needed for basic public endpoints in many cases.

    Expansion for competitive MM:
    - Fuse Anodos + direct WS + other providers (Kaiko, CEX depth, on-chain analytics)
    - Feed into perception / edge / policy for dynamic min_edge based on "secondary confidence"
    - Long-term: multi-venue book aggregation, external order flow signals for toxicity prediction,
      regime detection (low vol = more aggressive skimming).
    - Keep this experimental until post-Gate 2 + WS adapter is solid on the main branch.
    """

    def __init__(self, base_url: str = "https://api.anodos.finance", pair: str = "XRP/RLUSD"):
        self.base_url = base_url.rstrip("/")
        self.pair = pair

    async def fetch_snapshot(self) -> ExternalMarketSnapshot:
        # Stub implementation.
        # Real version would do something like:
        #   async with aiohttp.ClientSession() as session:
        #       async with session.get(f"{self.base_url}/v1/book?pair={self.pair}&limit=20") as resp:
        #           data = await resp.json()
        #           # Parse bids/asks, compute mid, depth, etc.
        #           return ExternalMarketSnapshot(
        #               mid_price=parsed_mid,
        #               liquidity_score=computed_depth_score,
        #               source="anodos",
        #               age_seconds=0
        #           )
        #
        # For now, return a placeholder that can be overridden in replay mode
        # with data derived from the current long run (e.g. the "trusted" mid
        # from a later cycle or smoothed version).
        return ExternalMarketSnapshot(
            source="anodos-stub",
            mid_price=None,  # Will be filled in replay with real-run-derived value
            liquidity_score=0.7,  # Example: assume secondary sees decent liquidity
            age_seconds=5.0       # Example: secondary data is reasonably fresh
        )

    # Helper for replay: allow injecting a "real" mid from the long run data
    # so we can simulate "what if Anodos gave us this mid during the thin-book cycle"
    def inject_mid_for_replay(self, mid: float, liquidity: float = 0.7, age: float = 3.0) -> ExternalMarketSnapshot:
        return ExternalMarketSnapshot(
            volatility_pct=None,
            liquidity_score=liquidity,
            mid_price=mid,
            source="anodos-replay",
            age_seconds=age
        )


# TODO (expansion for competitive MM):
# - Competitor on-chain scraping (see competitor_intel.py): profile other makers'
#   posted spreads, sizes, cancel rates, pressure. Use as "observed market spread"
#   and adverse vol proxy so pure A-S can scrape harder (tighter reservation) when
#   competitors are wide/defensive.
# - Add CoinGecko / CoinMarketCap vol fetcher (24h change, volume).
# - Cross-venue liquidity (other DEXes on XRPL or CEX XRP pairs) for true depth.
# - On-chain analytics (e.g., from XRPL data providers or Dune) for holder
#   concentration, large transfer signals (toxicity predictors).
# - Fuse in core/perception.py or a new MarketContext: external_vol overrides
#   or blends with on-chain vol for better min_edge and profile choice.
# - Use in edge calc: if external says "high vol regime" even if on-chain book
#   looks tight, widen or pause (protect skimming).
# - For growth: multi-venue quoting, latency arb between WS local + external,
#   ML model trained on long-run "false edge thin" labels + external features.
#
# Current run data (150 fills, many hard-gate 0-offer cycles on ~0.15% spreads)
# is the perfect backtest set: did external signals correlate with periods
# where the gate was too conservative (missed skimming) or correctly defensive?
#
# Do not wire into production engine until post-Gate 2 + WS adapter is solid.
# Keep all in experimental/market_analysis/ on this branch.