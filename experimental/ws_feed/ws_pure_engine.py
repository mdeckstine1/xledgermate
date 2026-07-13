"""
E4 — WS + pure A-S production engine (v2).

Uses the same BotConfig / credentials as the legacy poll engine.
Book: WsBookFeed. Quotes: PureQuotePath (no profiles, no hard gate).
Orders: selective sync via plan_order_sync + XRPLConnector.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig, is_trustworthy_rlusd_mid
from core import DecisionLog, VERSION
from core.runtime_state import QuoteIntent, RuntimeState, RuntimeStateStore
from engine.order_sync import find_offer_sequence_for_intent, plan_order_sync
from experimental.ws_feed.engine_adapter_example import WSBookFeedAdapter
from experimental.ws_feed.hud_intel_support import fetch_competitor_quoting_intel
from core.wealth_metrics import compute_wealth_metrics
from experimental.ws_feed.intel_decisions_log import (
    append_intel_record,
    build_cycle_intel_record,
    build_peer_scrape_intel_record,
    tail_intel_records,
)
from experimental.ws_feed.fill_quote_age_log import (
    append_fill_quote_age_record,
    build_fill_quote_age_record,
    push_recent_fill_age,
)
from experimental.ws_feed.ws_feature_flags import WsFeatureFlags
from experimental.ws_feed.offer_age_tracker import OfferAgeTracker
from experimental.ws_feed.acquisition_context import extract_acquisition_fill_context
from experimental.ws_feed.acquisition_metrics import build_acquisition_metrics
from experimental.ws_feed.peer_lane_quoting import is_peer_lane_empty
from experimental.ws_feed.pure_quote_path import current_ws_as_version
from experimental.ws_feed.stale_quote_guard import stale_quote_cancel_decisions
from experimental.ws_feed.stale_cross import detect_stale_cross
from experimental.ws_runtime_analysis import append_runtime_sample
from experimental.ws_feed.pair_books import RlusdXrpPair
from experimental.ws_feed.network_urls import rpc_url_to_websocket_url
from experimental.ws_feed.ws_book_feed import WsBookFeed
from monitoring.balance_logger import BalanceLogger
from monitoring.csv_logger import CSVLogger
from monitoring.fill_detection import (
    balance_delta_fill_reject_reason,
    detect_fill_from_balance_delta,
)
from monitoring.fill_economics import estimate_spread_capture_xrp
from monitoring.telegram_alerts import TelegramAlerts
from utils.book_visibility import enrich_open_offers, quote_visibility
from risk.drawdown import DrawdownMonitor, portfolio_value_xrp, session_pnl_balance_delta_xrp
from risk.kill_switch import KillSwitch
from strategy.fill_quality import FillQualityState, FillQualityTracker
from utils.preflight import evaluate_preflight

logger = logging.getLogger(__name__)

ENGINE_STOP_FILE = Path("logs/engine.stop")
WS_STALE_REFRESH_S = 12.0
DEFAULT_SAMPLE_INTERVAL_S = 5.0


def _execution_brakes_summary_with_queue(summary: str, quote_visibility_summary: str) -> str:
    if not quote_visibility_summary:
        return summary
    queue_part = f"queue {quote_visibility_summary}"
    if summary and queue_part not in summary:
        return f"{summary} | {queue_part}"
    return summary or queue_part
COMP_SCRAPE_INTERVAL_S = 15.0
COMP_INTEL_MAX_STALE_S = COMP_SCRAPE_INTERVAL_S * 2.0
WS_MID_MOVE_REFRESH_BPS = 8.0
WS_TOXIC_PRESERVE_OFF_RATIO = 0.35


def fill_side_to_offer_age_side(side: str) -> Optional[str]:
    """Map balance-delta fill side (BUY/SELL) to offer-age tracker side (bid/ask)."""
    normalized = (side or "").strip().upper()
    if normalized == "BUY":
        return "bid"
    if normalized == "SELL":
        return "ask"
    return None


def resolve_ws_sync_tolerances(
    *,
    mid: Optional[float],
    last_sync_mid: Optional[float],
    toxic_ratio_30s: float,
    recent_fills: int,
    g2_active: bool,
    base_price_tolerance_pct: float,
    mid_move_refresh_bps: float = WS_MID_MOVE_REFRESH_BPS,
    peer_lane_empty: bool = False,
    solo_acquisition: bool = False,
) -> tuple[float, bool]:
    """
    WS quote-sync policy: faster refresh when mid moves or toxicity is elevated.

    Returns (price_tolerance_pct, preserve_touch_queue).
    preserve_touch_queue keeps offers that still hug touch even when A-S intent
    moved — good for queue, bad when mid drifts (stale quotes → toxic fills).
    """
    preserve_touch_queue = True
    price_tol = float(base_price_tolerance_pct)

    if g2_active or (
        recent_fills >= 3 and toxic_ratio_30s >= WS_TOXIC_PRESERVE_OFF_RATIO
    ):
        preserve_touch_queue = False
        price_tol = min(price_tol, 0.04)

    if (
        solo_acquisition
        and peer_lane_empty
        and not g2_active
        and toxic_ratio_30s < 0.20
    ):
        # Lever 4 (all-4 experiment): solo relax sync — preserve queue more, looser tol.
        # Reduce "kept/cancel/place" flipping and churn on empty low-toxic lane.
        # Opposite of previous "refresh hard" — let quotes rest to get hit.
        preserve_touch_queue = True
        price_tol = max(price_tol, 0.08)

    if mid and last_sync_mid and last_sync_mid > 0:
        move_bps = abs(mid - last_sync_mid) / last_sync_mid * 10_000.0
        if move_bps >= mid_move_refresh_bps:
            preserve_touch_queue = False
            price_tol = min(price_tol, 0.03)

    return price_tol, preserve_touch_queue


def _ladder_row_to_quote_intent(row: Mapping[str, Any]) -> Optional[QuoteIntent]:
    side = str(row.get("side") or "").lower()
    if side not in ("bid", "ask"):
        return None
    price = float(row.get("price") or 0)
    size = float(row.get("size_xrp") or 0)
    level = int(row.get("level") or 1)
    if price <= 0 or size <= 0:
        return None
    return QuoteIntent(level=level, side=side, price=price, size_xrp=size)


def pure_intents_to_quote_intents(
    quote_intents: Sequence[Dict[str, Any]],
    *,
    would_quote: bool,
) -> List[QuoteIntent]:
    """Active L1 intents from PureQuotePath ladder → engine QuoteIntent."""
    if not would_quote:
        return []
    out: List[QuoteIntent] = []
    for row in quote_intents:
        if not row.get("active"):
            continue
        intent = _ladder_row_to_quote_intent(row)
        if intent is not None:
            out.append(intent)
    return out


def ladder_intents_for_hud(
    quote_intents: Sequence[Dict[str, Any]],
) -> List[QuoteIntent]:
    """Full L1–L3 ladder for runtime/HUD (includes planned depth levels)."""
    out: List[QuoteIntent] = []
    for row in quote_intents:
        intent = _ladder_row_to_quote_intent(row)
        if intent is not None:
            out.append(intent)
    return out


class WsPureTradingEngine:
    """WS book + pure A-S loop with real (or dry-run) ledger offers."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.kill_switch = KillSwitch()
        self.drawdown_monitor = DrawdownMonitor(
            max_drawdown_percent=config.max_daily_drawdown_percent
        )
        self.decision_log = DecisionLog(max_entries=150)
        self.state_store = RuntimeStateStore()
        self.csv_logger = CSVLogger()
        self.balance_logger = BalanceLogger()
        self.alerts = TelegramAlerts(
            token=config.telegram_token,
            chat_id=config.telegram_chat_id,
            enabled=config.telegram_enabled,
        )
        self.connector: Optional[XRPLConnector] = None
        self._ws_feed: Optional[WsBookFeed] = None
        self._adapter: Optional[WSBookFeedAdapter] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False
        self._cycle_count = 0
        self._session_fills = 0
        self._session_spread_capture = 0.0
        self._last_session_buy_capture_xrp: Optional[float] = None
        self._last_session_sell_capture_xrp: Optional[float] = None
        self._session_baseline_xrp: Optional[float] = None
        self._session_baseline_rlusd: Optional[float] = None
        self._session_baseline_mid: Optional[float] = None
        self._last_valid_mid: Optional[float] = None
        self._decision_log_path = Path("logs/decisions.jsonl")
        self._decision_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._offers_cancelled = 0
        self._offers_kept = 0
        self._would_quote_cycles = 0
        self._fill_quality = FillQualityTracker()
        self._fill_quality.set_toxic_threshold_pct(0.06)
        self._price_history: list[float] = []
        self._sample_interval_s = DEFAULT_SAMPLE_INTERVAL_S
        self._last_sync_mid: Optional[float] = None
        self._comp_provider: Any = None
        self._last_comp_scrape: float = 0.0
        self._last_comp_intel: Dict[str, Any] = {}
        self._comp_intel_cache: Dict[str, Any] = {}
        self._last_our_lane_xrp: float = 0.0
        self._last_ws_book_age_s: Optional[float] = None
        self._offer_age = OfferAgeTracker()
        self._last_fill_quote_age_seconds: Optional[float] = None
        self._recent_fill_quote_ages: List[Dict[str, Any]] = []
        self._session_fill_records: List[Dict[str, Any]] = []
        self._reservation_crossed_after_ws_sample = False
        self._session_boot_utc = datetime.now(tz=timezone.utc).isoformat()
        self._analysis_bundle: Dict[str, Any] = {"sample_history": []}

    def stop(self) -> None:
        self._running = False

    async def _build_connector(self) -> XRPLConnector:
        config = self.config
        return XRPLConnector(
            account_address=config.bot_account_address.strip(),
            secret=config.bot_secret_key or None,
            rlusd_issuer=config.resolved_rlusd_issuer(),
            rlusd_currency=config.resolved_rlusd_currency_code(),
            network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
        )

    async def _ensure_ws_stack(self) -> None:
        if self._ws_feed is not None:
            return
        config = self.config
        connector = await self._build_connector()
        self.connector = connector
        rpc = config.resolved_rpc_url()
        ws_url = rpc_url_to_websocket_url(rpc)
        taker = (config.bot_account_address or "").strip()
        pair = RlusdXrpPair(
            rlusd_issuer=config.resolved_rlusd_issuer(),
            rlusd_currency=config.rlusd_currency,
            taker=taker,
        )
        self._ws_feed = WsBookFeed(connector=connector, ws_url=ws_url, pair=pair)
        l1 = float(config.order_sizes[0]) if config.order_sizes else 150.0
        sizes = tuple(float(x) for x in (config.order_sizes or [l1]))
        self._adapter = WSBookFeedAdapter(
            self._ws_feed,
            configured_l1_xrp=l1,
            min_order_size_xrp=float(config.min_order_size_xrp),
            order_levels=int(config.order_levels),
            level_spread_increment=float(config.level_spread_increment),
            configured_order_sizes=sizes,
        )
        self._ws_task = asyncio.create_task(
            self._ws_feed.run_forever(http_refresh_seconds=20.0),
            name="ws_pure_engine_feed",
        )
        try:
            from experimental.market_analysis.competitor_intel import CompetitorIntelProvider

            self._comp_provider = CompetitorIntelProvider(connector, pair)
        except Exception:
            logger.warning("CompetitorIntelProvider unavailable — G4 peer lane off", exc_info=True)
            self._comp_provider = None
        self._last_our_lane_xrp = l1
        await asyncio.sleep(2.0)

    async def _refresh_book_state(self) -> tuple[Any, Optional[float], Optional[float], Optional[float]]:
        """Re-seed WS book when stale; return (state, best_bid, best_ask, mid)."""
        assert self._ws_feed is not None
        await self._ws_feed.refresh_if_stale(WS_STALE_REFRESH_S)
        state = self._ws_feed.state
        bb, ba = state.best_prices()
        mid = (bb + ba) / 2.0 if bb and ba else None
        return state, bb, ba, mid

    def _usable_comp_intel_cache(self, *, now: float) -> Optional[Dict[str, Any]]:
        """Return cached competitor intel only while peer-lane data is still fresh."""
        if not self._comp_intel_cache or self._last_comp_scrape <= 0:
            return None
        if now - self._last_comp_scrape <= COMP_INTEL_MAX_STALE_S:
            return self._comp_intel_cache
        self.decision_log.add(
            "intel",
            (
                "G4 competitor scrape stale "
                f"({now - self._last_comp_scrape:.1f}s) - ignoring cached peer lane"
            ),
        )
        return None

    async def _maybe_refresh_competitor_intel(self, config: BotConfig) -> Optional[Dict[str, Any]]:
        """Periodic on-chain peer-lane scrape for G4 quoting (cached ~15s)."""
        flags = WsFeatureFlags.from_config(config)
        if not flags.competitor_intel:
            return self._last_comp_intel or self._comp_intel_cache or None
        if not self._comp_provider or not self._ws_feed:
            return self._comp_intel_cache or None

        now = time.monotonic()
        if (
            now - self._last_comp_scrape < COMP_SCRAPE_INTERVAL_S
            and self._comp_intel_cache
        ):
            return self._comp_intel_cache

        fallback_l1 = float(config.order_sizes[0]) if config.order_sizes else 150.0
        our_lane = self._last_our_lane_xrp if self._last_our_lane_xrp > 0 else fallback_l1
        try:
            fields = await fetch_competitor_quoting_intel(
                self._comp_provider,
                self._ws_feed,
                our_lane_xrp=our_lane,
                fallback_l1_xrp=fallback_l1,
            )
            if fields.get("competitor_error"):
                return self._usable_comp_intel_cache(now=now)
            self._comp_intel_cache = fields
            self._last_comp_scrape = now
            if flags.intel_log:
                try:
                    append_intel_record(build_peer_scrape_intel_record(fields))
                except OSError:
                    pass
            self._last_comp_intel = dict(fields)
            return fields
        except Exception:
            logger.warning("G4 competitor scrape failed", exc_info=True)
            return self._usable_comp_intel_cache(now=now)

    async def run(self, *, sample_interval_s: float = DEFAULT_SAMPLE_INTERVAL_S) -> None:
        self._running = True
        self._sample_interval_s = float(sample_interval_s)
        logger.info(
            "WsPureTradingEngine v%s | WS + pure A-S | dry_run=%s | %s",
            current_ws_as_version(),
            self.config.dry_run,
            WsFeatureFlags.from_config(self.config).summary(),
        )
        self.csv_logger.log_major(
            network=self.config.network_name(),
            notes=(
                f"WS-engine started | dry_run={self.config.dry_run} "
                f"| ws_as_version={current_ws_as_version()}"
            ),
        )
        while self._running:
            if ENGINE_STOP_FILE.exists():
                ENGINE_STOP_FILE.unlink(missing_ok=True)
                logger.info("Stop file detected — shutting down WS pure engine.")
                break
            try:
                await self._run_cycle()
            except Exception:
                logger.exception("WS pure engine cycle failed")
            await asyncio.sleep(sample_interval_s)
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

    async def _run_cycle(self) -> None:
        config = BotConfig.load()
        self.config = config
        flags = WsFeatureFlags.from_config(config)
        self.alerts = TelegramAlerts(
            token=config.telegram_token,
            chat_id=config.telegram_chat_id,
            enabled=config.telegram_enabled,
        )
        await self._ensure_ws_stack()
        assert self._ws_feed is not None and self._adapter is not None
        connector = self.connector
        assert connector is not None

        state, bb, ba, mid = await self._refresh_book_state()
        if not is_trustworthy_rlusd_mid(mid, best_bid=bb, best_ask=ba):
            self.decision_log.add("book", "WS book not trustworthy — skip cycle.")
            if (
                config.trading_enabled
                and not config.dry_run
                and (config.bot_secret_key or "").strip()
            ):
                await self._sync_offers([], mid=mid, best_bid=bb, best_ask=ba)
            return
        self._last_valid_mid = mid
        if mid and flags.fill_quality:
            self._fill_quality.note_mid(mid)

        balance_xrp = await connector.get_xrp_balance()
        balance_rlusd = await connector.get_rlusd_balance()
        trust = await connector.get_rlusd_trust_line()
        portfolio = portfolio_value_xrp(balance_xrp, balance_rlusd, mid or 0.0)

        if self.kill_switch.is_active():
            await self._cancel_if_live(connector, config, "Kill switch active")
            await self._persist_cycle(
                config, mid, bb, ba, balance_xrp, balance_rlusd, portfolio, [], 0,
                execution=self.kill_switch.reason or "Kill switch active",
                engine_dec=None,
            )
            return

        portfolio, marked = self.drawdown_monitor.update_portfolio(
            balance_xrp, balance_rlusd, mid
        )
        drawdown_pct = self.drawdown_monitor.get_drawdown_percent()
        if (
            flags.drawdown_kill
            and marked
            and self.drawdown_monitor.is_kill_switch_triggered()
        ):
            reason = f"Daily portfolio drawdown {drawdown_pct:.2f}%"
            self.kill_switch.activate(reason)
            if config.telegram_enabled and flags.telegram_kill_alerts:
                self.alerts.send_kill_switch_alert(drawdown_pct, reason)
            return

        preflight = evaluate_preflight(
            config=config,
            xrp_balance=balance_xrp,
            rlusd_balance=balance_rlusd,
            trust_line_limit=trust.limit if trust.exists else None,
            has_trust_line=trust.exists,
            trust_line_no_ripple=trust.no_ripple if trust.exists else None,
            mid_price=mid,
            kill_switch_active=False,
            xrp_reserve=config.xrp_reserve,
            min_order_xrp=config.min_order_size_xrp,
        )
        if not preflight.ready:
            self.decision_log.add("preflight", preflight.summary)
            if (
                config.trading_enabled
                and not config.dry_run
                and (config.bot_secret_key or "").strip()
            ):
                await self._sync_offers([], mid=mid, best_bid=bb, best_ask=ba)
            return

        bb_before_intel, ba_before_intel = bb, ba
        comp_intel = await self._maybe_refresh_competitor_intel(config)
        fill_state = self._fill_quality.assess() if flags.fill_quality else None

        # Intel scrape + ledger RPC can take 30s+; refresh book again before quoting.
        state, bb, ba, mid = await self._refresh_book_state()
        if not is_trustworthy_rlusd_mid(mid, best_bid=bb, best_ask=ba):
            self.decision_log.add("book", "WS book not trustworthy before quote — skip cycle.")
            if (
                config.trading_enabled
                and not config.dry_run
                and (config.bot_secret_key or "").strip()
            ):
                await self._sync_offers([], mid=mid, best_bid=bb, best_ask=ba)
            return
        self._last_valid_mid = mid
        if mid and flags.fill_quality:
            self._fill_quality.note_mid(mid)
        self._last_ws_book_age_s = state.age_seconds()

        engine_dec = await self._adapter.compute_pure_as_decision(
            mid=mid or 0.0,
            best_bid=bb or 0.0,
            best_ask=ba or 0.0,
            xrp_bal=balance_xrp,
            rlusd_bal=balance_rlusd,
            target_ratio=config.inventory_target_xrp_ratio,
            ws_book_age_s=state.age_seconds(),
            fill_quality=fill_state,
            inventory_max_deviation=float(config.inventory_max_deviation),
            inventory_mode=str(config.inventory_mode or "market_make"),
            xrp_reserve=float(config.xrp_reserve),
            inventory_overshoot_slack=float(config.inventory_overshoot_slack),
            competitor_intel=comp_intel,
            g2_enabled=flags.g2_scaler,
            g4_enabled=flags.g4_peer_lane and flags.competitor_intel,
            competitor_pressure_enabled=flags.competitor_intel,
            session_buy_capture_xrp=self._last_session_buy_capture_xrp,
            session_sell_capture_xrp=self._last_session_sell_capture_xrp,
            recent_fill_records=tuple(self._session_fill_records[-12:]),
        )
        reservation = engine_dec.get("as_reservation")
        self._reservation_crossed_after_ws_sample = detect_stale_cross(
            reservation=reservation,
            best_bid_before=bb_before_intel,
            best_ask_before=ba_before_intel,
            best_bid_after=bb,
            best_ask_after=ba,
        )
        if self._reservation_crossed_after_ws_sample:
            self.decision_log.add(
                "book",
                "M3 stale-cross: reservation inside BBO pre-intel, outside post-refresh",
            )
        l1_from_dec = float(engine_dec.get("l1_xrp") or 0)
        if l1_from_dec > 0:
            self._last_our_lane_xrp = l1_from_dec
        bid_sz = float(engine_dec.get("bid_size") or engine_dec.get("bid_size_xrp") or 0)
        ask_sz = float(engine_dec.get("ask_size") or engine_dec.get("ask_size_xrp") or 0)
        lane_sz = max(bid_sz, ask_sz)
        if lane_sz > 0:
            self._last_our_lane_xrp = lane_sz
        would_quote = bool(engine_dec.get("would_quote"))
        intents = pure_intents_to_quote_intents(
            engine_dec.get("quote_intents") or [],
            would_quote=would_quote,
        )
        if would_quote:
            self._would_quote_cycles += 1
        self.decision_log.add("as_pure", engine_dec.get("quote_decision_summary", "")[:240])
        would_sync = len(intents) if would_quote else 0
        placed = 0
        cancelled = 0
        if (
            config.trading_enabled
            and not self.kill_switch.is_active()
            and not config.dry_run
            and (config.bot_secret_key or "").strip()
        ):
            sync_intents = intents if would_quote else []
            placed, cancelled = await self._sync_offers(
                sync_intents,
                mid=mid,
                best_bid=bb,
                best_ask=ba,
                peer_lane_empty=is_peer_lane_empty(comp_intel),
                solo_acquisition=bool(engine_dec.get("g7_solo_acquisition")),
                bid_allowed=bool(engine_dec.get("qd_bid_allowed")),
                ask_allowed=bool(engine_dec.get("qd_ask_allowed")),
            )

        await self._detect_fills(
            config,
            connector,
            balance_xrp,
            balance_rlusd,
            mid,
            best_bid=bb,
            best_ask=ba,
            engine_dec=engine_dec,
            competitor_intel=comp_intel,
        )

        execution = self._execution_summary(
            config, placed, cancelled=cancelled, would_sync=would_sync, would_quote=would_quote
        )
        offers_last = would_sync if config.dry_run else placed
        self._cycle_count += 1
        self.balance_logger.log_snapshot(
            cycle=self._cycle_count,
            network=config.network_name(),
            xrp_balance=balance_xrp,
            rlusd_balance=balance_rlusd,
            mid_rlusd_per_xrp=mid or 0.0,
            portfolio_xrp_equiv=portfolio,
            open_offers=len(await connector.get_open_offers()),
            dry_run=config.dry_run,
        )
        self._append_decision_file(
            cycle=self._cycle_count, mid=mid, execution=execution, would_quote=would_quote
        )
        hud_ladder = ladder_intents_for_hud(engine_dec.get("quote_intents") or [])
        await self._persist_cycle(
            config, mid, bb, ba, balance_xrp, balance_rlusd, portfolio, intents, offers_last,
            execution, engine_dec=engine_dec, hud_ladder_intents=hud_ladder,
        )

    async def _sync_offers(
        self,
        intents: List[QuoteIntent],
        *,
        mid: Optional[float],
        best_bid: Optional[float],
        best_ask: Optional[float],
        peer_lane_empty: bool = False,
        solo_acquisition: bool = False,
        bid_allowed: bool = True,
        ask_allowed: bool = True,
    ) -> tuple[int, int]:
        config = self.config
        connector = self.connector
        assert connector is not None
        if config.dry_run:
            self.decision_log.add(
                "execution",
                f"Dry-run: would sync {len(intents)} pure A-S quote(s).",
            )
            return 0, 0
        if not (config.bot_secret_key or "").strip():
            self.decision_log.add("execution", "No bot secret — cannot place offers.")
            return 0, 0

        open_offers = await connector.get_open_offers()
        max_worse = float(getattr(config, "max_quote_worse_than_touch_pct", 0.50))
        fq = self._fill_quality.assess()
        g2_active = fq.size_multiplier < 1.0 or fq.spread_multiplier > 1.0
        price_tol, preserve_touch = resolve_ws_sync_tolerances(
            mid=mid,
            last_sync_mid=self._last_sync_mid,
            toxic_ratio_30s=float(fq.toxic_ratio_30s),
            recent_fills=int(fq.recent_fills),
            g2_active=g2_active,
            base_price_tolerance_pct=float(
                getattr(config, "order_price_tolerance_pct", 0.08)
            ),
            peer_lane_empty=peer_lane_empty,
            solo_acquisition=solo_acquisition,
        )
        plan = plan_order_sync(
            intents,
            open_offers,
            price_tolerance_pct=price_tol,
            size_tolerance_xrp=float(getattr(config, "order_size_tolerance_xrp", 0.75)),
            best_bid=best_bid,
            best_ask=best_ask,
            max_worse_than_touch_pct=max_worse,
            preserve_queue_max_worse_pct=max_worse,
            max_improve_touch_pct=float(getattr(config, "max_quote_improve_touch_pct", 0.15)),
            preserve_touch_queue=preserve_touch,
        )
        now_utc = datetime.now(tz=timezone.utc)
        stale_decisions = stale_quote_cancel_decisions(
            open_offers,
            self._offer_age,
            now=now_utc,
            toxic_ratio_30s=float(fq.toxic_ratio_30s),
            mid=mid,
            last_sync_mid=self._last_sync_mid,
            mid_move_refresh_bps=WS_MID_MOVE_REFRESH_BPS,
            peer_lane_empty=peer_lane_empty,
        )
        cancel_sequences = list(plan.cancel_sequences)
        stale_seqs = {d.sequence for d in stale_decisions}
        for seq in stale_seqs:
            if seq not in cancel_sequences:
                cancel_sequences.append(seq)
        from experimental.ws_feed.ask_brake_cancel import side_brake_cancel_sequences

        for seq in side_brake_cancel_sequences(
            open_offers, bid_allowed=bid_allowed, ask_allowed=ask_allowed
        ):
            if seq not in cancel_sequences:
                cancel_sequences.append(seq)
                self.decision_log.add(
                    "execution",
                    f"QD side-brake: cancel seq {seq} (bid={bid_allowed} ask={ask_allowed})",
                )
        for decision in stale_decisions:
            self.decision_log.add(
                "execution",
                (
                    f"A3 stale-quote: cancel seq {decision.sequence} "
                    f"{decision.side} age={decision.age_seconds:.0f}s ({decision.reason})"
                ),
            )
        if not preserve_touch or price_tol < float(
            getattr(config, "order_price_tolerance_pct", 0.08)
        ):
            self.decision_log.add(
                "execution",
                f"WS refresh mode: tol={price_tol:.3f}% preserve_touch={preserve_touch}",
            )
        cancelled = 0
        for seq in cancel_sequences:
            self._offer_age.forget_sequence(seq)
            try:
                await connector.cancel_offer(seq)
                cancelled += 1
            except Exception as exc:
                self.decision_log.add("execution", f"Cancel seq {seq} failed: {exc}")
        placed = 0
        placed_intents: List[QuoteIntent] = []
        size_tol = float(getattr(config, "order_size_tolerance_xrp", 0.75))
        for intent in plan.place_intents:
            try:
                await connector.place_quote(intent)
                placed += 1
                placed_intents.append(intent)
            except Exception as exc:
                self.decision_log.add("execution", f"Place {intent.side} failed: {exc}")
        if placed_intents:
            try:
                refreshed_offers = await connector.get_open_offers()
            except Exception as exc:
                refreshed_offers = []
                self.decision_log.add("execution", f"Open offers refresh after place failed: {exc}")
            placed_utc = datetime.now(tz=timezone.utc)
            for intent in placed_intents:
                seq = find_offer_sequence_for_intent(
                    intent,
                    refreshed_offers,
                    price_tolerance_pct=price_tol,
                    size_tolerance_xrp=size_tol,
                )
                self._offer_age.record_place(
                    intent.side,
                    placed_utc=placed_utc,
                    sequence=seq,
                )
        self._offers_cancelled += cancelled
        self._offers_kept += plan.kept_count
        self.decision_log.add(
            "execution",
            f"WS pure sync: kept {plan.kept_count} cancel {cancelled} place {placed}",
        )
        if placed or cancelled:
            self.csv_logger.log_offer_refresh(
                network=config.network_name(),
                placed=placed,
                cancelled=cancelled,
                cycle=self._cycle_count + 1,
                dry_run=False,
            )
        if intents and mid and (placed or cancelled or plan.kept_count):
            self._last_sync_mid = mid
        return placed, cancelled

    def _cancel_per_fill_ratio(self) -> float:
        if self._session_fills <= 0:
            return float(self._offers_cancelled)
        return self._offers_cancelled / self._session_fills

    async def _detect_fills(
        self,
        config: BotConfig,
        connector: XRPLConnector,
        balance_xrp: float,
        balance_rlusd: float,
        mid: Optional[float],
        *,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None,
        engine_dec: Optional[Dict[str, Any]] = None,
        competitor_intel: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self._session_baseline_xrp is None and mid:
            self._session_baseline_xrp = balance_xrp
            self._session_baseline_rlusd = balance_rlusd
            self._session_baseline_mid = mid
        prev = getattr(self, "_prev_balances", None)
        self._prev_balances = (balance_xrp, balance_rlusd)
        if prev is None:
            return
        fill = detect_fill_from_balance_delta(
            prev_xrp=prev[0],
            prev_rlusd=prev[1],
            curr_xrp=balance_xrp,
            curr_rlusd=balance_rlusd,
            mid_price=mid,
        )
        if not fill:
            return
        mid_at_quote = self._last_sync_mid or self._last_valid_mid or mid
        reject = balance_delta_fill_reject_reason(
            fill,
            mid_at_quote,
            best_bid=best_bid,
            best_ask=best_ask,
        )
        if reject:
            self.decision_log.add("fill", reject)
            return
        side = str(fill["side"])
        fill_detected_utc = datetime.now(tz=timezone.utc)
        tracker_side = fill_side_to_offer_age_side(side)
        quote_age: Optional[float] = None
        offer_sequence: Optional[int] = None
        tracking = "none"
        if tracker_side:
            offer_sequence = self._offer_age.last_sequence_for_side(tracker_side)
            tracking = self._offer_age.tracking_label(tracker_side)
            quote_age = self._offer_age.effective_quote_age_at_fill_seconds(
                tracker_side,
                fill_detected_utc=fill_detected_utc,
                sequence=offer_sequence,
            )
            if quote_age is not None:
                self._last_fill_quote_age_seconds = quote_age
        xrp_amount = float(fill["xrp_amount"])
        rlusd_amount = float(fill["rlusd_amount"])
        price = float(fill["price_rlusd_per_xrp"])
        cap = estimate_spread_capture_xrp(
            side=side,
            xrp_amount=xrp_amount,
            fill_price_rlusd_per_xrp=price,
            mid_at_quote_rlusd_per_xrp=mid_at_quote,
        )
        mid_at_fill = mid if is_trustworthy_rlusd_mid(mid) else mid_at_quote
        self._session_fills += 1
        acq_ctx = extract_acquisition_fill_context(
            engine_dec, competitor_intel=competitor_intel
        )
        age_record = build_fill_quote_age_record(
            cycle=self._cycle_count + 1,
            side=side,
            offer_side=tracker_side or "",
            xrp_amount=xrp_amount,
            quote_age_seconds=quote_age,
            offer_sequence=offer_sequence,
            ws_as_version=current_ws_as_version(),
            fills_session=self._session_fills,
            capture_xrp=cap,
            tracking=tracking,
            acquisition=acq_ctx,
            fill_price_rlusd_per_xrp=price,
            mid_at_quote_rlusd_per_xrp=mid_at_quote,
        )
        age_record["ts_utc"] = fill_detected_utc.isoformat()
        append_fill_quote_age_record(age_record)
        self._session_fill_records.append(dict(age_record))
        self._recent_fill_quote_ages = push_recent_fill_age(
            self._recent_fill_quote_ages,
            age_record,
        )
        self._session_spread_capture += cap
        if mid_at_fill and WsFeatureFlags.from_config(config).fill_quality:
            self._fill_quality.note_fill(
                side=side,
                xrp_amount=xrp_amount,
                price=price,
                mid_at_fill=mid_at_fill,
                fill_source="ws_pure_balance_delta",
            )
        common = dict(
            network=config.network_name(),
            xrp_amount=xrp_amount,
            rlusd_amount=rlusd_amount,
            price_rlusd_per_xrp=price,
            profit_xrp_equiv=cap,
            cycle=self._cycle_count + 1,
            notes=(
                f"WS pure fill (balance delta); capture ~{cap:+.4f} XRP "
                f"@ mid {mid_at_quote or 'n/a'}"
                f"; inv={acq_ctx.get('inventory_label') or '?'}"
                + (
                    "; solo_acquire"
                    if acq_ctx.get("g7_solo_acquisition")
                    else ""
                )
                + (
                    f"; quote_age_m6={quote_age:.3f}s"
                    + (f" seq={offer_sequence}" if offer_sequence is not None else "")
                    + f" ({tracking})"
                    if quote_age is not None
                    else ""
                )
            ),
            balance_xrp_after=balance_xrp,
            balance_rlusd_after=balance_rlusd,
        )
        if side == "SELL":
            self.csv_logger.log_sell(**common)
        else:
            self.csv_logger.log_buy(**common)
        if tracker_side:
            if offer_sequence is not None:
                self._offer_age.forget_sequence(offer_sequence)
            else:
                self._offer_age.clear_side(tracker_side)

    async def _cancel_if_live(
        self, connector: XRPLConnector, config: BotConfig, reason: str
    ) -> None:
        if config.dry_run or not (config.bot_secret_key or "").strip():
            return
        try:
            n = await connector.cancel_all_offers()
            if n:
                self.decision_log.add("execution", f"Cancelled {n} offers — {reason}")
        except Exception as exc:
            self.decision_log.add("execution", f"Cancel-all failed: {exc}")

    def _execution_summary(
        self,
        config: BotConfig,
        placed: int,
        *,
        cancelled: int = 0,
        would_sync: int = 0,
        would_quote: bool = True,
    ) -> str:
        if self.kill_switch.is_active():
            return f"Kill switch: {self.kill_switch.reason}"
        if config.dry_run:
            if would_sync:
                return f"Dry-run: would sync {would_sync} pure A-S quote(s)."
            return "Dry-run: no quotes (would_quote=false or empty intents)."
        if not config.trading_enabled:
            return "Trading disabled."
        if cancelled and not placed:
            return f"Live WS pure: pulled {cancelled} offer(s) — A-S protected (no quote)."
        if placed and cancelled:
            return f"Live WS pure: placed {placed}, cancelled {cancelled} offer(s)."
        if placed:
            return f"Live WS pure: placed {placed} offer(s)."
        if not would_quote:
            return "Live WS pure: no quote this cycle (A-S protected)."
        return "Live WS pure: no placement this cycle."

    def _append_decision_file(
        self, *, cycle: int, mid: Optional[float], execution: str, would_quote: bool
    ) -> None:
        record = {
            "cycle": cycle,
            "mid_rlusd_per_xrp": mid,
            "execution": execution,
            "as_mode": "pure",
            "ws_as_version": current_ws_as_version(),
            "would_quote": bool(would_quote),
            "pid": os.getpid(),
            "events": [
                {"ts_utc": e.ts_utc, "category": e.category, "message": e.message}
                for e in self.decision_log.recent_newest_first(limit=6)
            ],
        }
        with self._decision_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    async def _persist_cycle(
        self,
        config: BotConfig,
        mid: Optional[float],
        bb: Optional[float],
        ba: Optional[float],
        balance_xrp: float,
        balance_rlusd: float,
        portfolio: float,
        intents: List[QuoteIntent],
        placed: int,
        execution: str,
        engine_dec: Optional[Dict[str, Any]] = None,
        hud_ladder_intents: Optional[List[QuoteIntent]] = None,
    ) -> None:
        flags = WsFeatureFlags.from_config(config)
        drawdown_pct = self.drawdown_monitor.get_drawdown_percent()
        open_offers = []
        enriched_offers: list = []
        quotes_at_touch = True
        worst_vs_touch_bps = 0.0
        quote_visibility_summary = ""
        if self.connector:
            try:
                offers = await self.connector.get_open_offers()
                open_offers = [o.__dict__ if hasattr(o, "__dict__") else o for o in offers]
                enriched_offers = enrich_open_offers(
                    open_offers, best_bid=bb, best_ask=ba
                )
                quotes_at_touch, worst_vs_touch_bps, quote_visibility_summary = quote_visibility(
                    enriched_offers
                )
            except Exception:
                open_offers = []
        ed = engine_dec or {}
        session_bal_pnl = 0.0
        if self._session_baseline_xrp is not None and mid:
            session_bal_pnl = session_pnl_balance_delta_xrp(
                balance_xrp=balance_xrp,
                balance_rlusd=balance_rlusd,
                baseline_xrp=self._session_baseline_xrp,
                baseline_rlusd=self._session_baseline_rlusd or 0.0,
                mid_rlusd_per_xrp=mid,
            )
        cycle_presence_pct = None
        if self._cycle_count > 0:
            cycle_presence_pct = round(100.0 * self._would_quote_cycles / self._cycle_count, 1)
        flags = WsFeatureFlags.from_config(config)
        fill_quality = self._fill_quality.assess() if flags.fill_quality else FillQualityState()
        bb_spread = ed.get("book_spread_pct")
        if bb_spread is None and mid and bb and ba:
            bb_spread = (ba - bb) / mid * 100.0 if mid > 0 else 0.0
        book_bids: List[Dict[str, Any]] = []
        book_asks: List[Dict[str, Any]] = []
        if self._ws_feed and hasattr(self._ws_feed, "state"):
            depth = self._ws_feed.state.depth_levels(25)
            book_bids = list(depth.get("bids") or [])
            book_asks = list(depth.get("asks") or [])
        if mid and mid > 0:
            self._price_history.append(float(mid))
            if len(self._price_history) > 200:
                self._price_history = self._price_history[-200:]
        decisions = [
            {"ts_utc": e.ts_utc, "category": e.category, "message": e.message}
            for e in self.decision_log.recent_newest_first(limit=60)
        ]
        cycle_s = int(self._sample_interval_s)
        comp_intel = self._last_comp_intel or {}
        append_runtime_sample(
            self._analysis_bundle,
            {
                "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
                "mid": mid,
                "best_bid": bb,
                "best_ask": ba,
                "book_spread_pct": float(bb_spread or 0.0),
                "as_optimal_spread_pct": ed.get("as_optimal_spread_pct"),
                "spread_gap_pct": (
                    float(bb_spread or 0.0) - float(ed.get("as_optimal_spread_pct") or 0.0)
                    if bb_spread is not None and ed.get("as_optimal_spread_pct") is not None
                    else None
                ),
                "as_reservation": ed.get("as_reservation"),
                "would_quote": bool(ed.get("would_quote", bool(intents))),
                "competitor_pressure": ed.get("competitor_pressure"),
                "competitor_observed_spread_pct": comp_intel.get("competitor_observed_spread_pct"),
                "volatility_pct": ed.get("volatility_pct"),
                "ws_book_age_s": (
                    self._last_ws_book_age_s
                    if self._last_ws_book_age_s is not None
                    else (self._ws_feed.age_seconds() if self._ws_feed else None)
                ),
                "inventory_label": ed.get("inventory_label"),
                "zero_quote_reason": ed.get("zero_quote_reason"),
                "inside_l1": ed.get("inside_l1"),
                "reservation_to_bbo_delta_bps": ed.get("reservation_to_bbo_delta_bps"),
                "reservation_crossed_after_ws_sample": self._reservation_crossed_after_ws_sample,
            },
        )
        presence_pct = self._analysis_bundle.get("as_presence_pct", cycle_presence_pct)
        peer_lane_empty = is_peer_lane_empty(comp_intel) if comp_intel else False
        runtime_for_acq: Dict[str, Any] = {
            "mid_price": mid,
            "balance_xrp": balance_xrp,
            "balance_rlusd": balance_rlusd,
            "session_baseline_xrp": self._session_baseline_xrp,
            "session_baseline_rlusd": self._session_baseline_rlusd,
            "session_baseline_mid": self._session_baseline_mid,
            "session_spread_capture_xrp": self._session_spread_capture,
            "session_boot_utc": self._session_boot_utc,
            "ws_as_version": current_ws_as_version(),
            "fills_session": self._session_fills,
        }
        runtime_for_acq.update(
            {k: v for k, v in compute_wealth_metrics(runtime_for_acq).items() if v is not None}
        )
        intel_cycles: List[Dict[str, Any]] = []
        if flags.intel_log:
            try:
                boot_dt = datetime.fromisoformat(
                    self._session_boot_utc.replace("Z", "+00:00")
                )
                if boot_dt.tzinfo is None:
                    boot_dt = boot_dt.replace(tzinfo=timezone.utc)
                ws_ver = current_ws_as_version()
                for row in tail_intel_records(limit=2000):
                    if row.get("kind") != "cycle":
                        continue
                    if ws_ver and str(row.get("ws_as_version") or "") not in ("", ws_ver):
                        continue
                    ts_raw = str(row.get("ts_utc") or "")
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if ts < boot_dt:
                            continue
                    except ValueError:
                        pass
                    intel_cycles.append(row)
            except (OSError, ValueError):
                intel_cycles = []
        acquisition_metrics = build_acquisition_metrics(
            runtime=runtime_for_acq,
            session_fills=self._session_fill_records,
            intel_cycles=intel_cycles,
        )
        buy_cap = (acquisition_metrics.get("inventory_growth_at_edge") or {}).get(
            "buy_capture_xrp"
        )
        if buy_cap is not None:
            self._last_session_buy_capture_xrp = float(buy_cap)
        sell_states = acquisition_metrics.get("sell_capture_by_state") or {}
        if sell_states:
            self._last_session_sell_capture_xrp = sum(
                float(v.get("cap") or 0) for v in sell_states.values()
            )
        state = RuntimeState(
            version=VERSION,
            network=config.network_name(),
            rpc_url=config.resolved_rpc_url(),
            dry_run=config.dry_run,
            trading_enabled=config.trading_enabled,
            kill_switch_active=self.kill_switch.is_active(),
            kill_switch_reason=self.kill_switch.reason or "",
            preflight_ready=True,
            portfolio_value_xrp=portfolio,
            drawdown_pct=drawdown_pct,
            active_profile="ws_pure",
            mid_price=mid,
            best_bid_rlusd_per_xrp=bb,
            best_ask_rlusd_per_xrp=ba,
            balance_xrp=balance_xrp,
            balance_rlusd=balance_rlusd,
            open_offers_count=len(open_offers),
            open_offers=open_offers,
            cycle_count=self._cycle_count,
            offers_placed_last_cycle=placed,
            last_execution_summary=execution,
            quote_intents=hud_ladder_intents if hud_ladder_intents else intents,
            recent_decisions=decisions,
            price_source="ws_book_feed",
            price_history=list(self._price_history),
            as_mode="pure",
            ws_as_version=current_ws_as_version(),
            as_protected=True,
            ws_book_age_s=(
                self._last_ws_book_age_s
                if self._last_ws_book_age_s is not None
                else (self._ws_feed.age_seconds() if self._ws_feed else None)
            ),
            ws_message_count=(
                int(self._ws_feed.state.message_count)
                if self._ws_feed and hasattr(self._ws_feed, "state")
                else 0
            ),
            fills_session=self._session_fills,
            offers_cancelled_session=self._offers_cancelled,
            offers_kept_session=self._offers_kept,
            cancel_per_fill=self._cancel_per_fill_ratio(),
            book_poll_interval_seconds=cycle_s,
            full_quote_refresh_seconds=cycle_s,
            last_cycle_full_refresh=True,
            market_edge_met=bool(ed.get("would_quote", bool(intents))),
            quote_decision_summary=str(ed.get("quote_decision_summary") or ""),
            quoting_policy_label=str(ed.get("quoting_policy_label") or "ws_pure_as"),
            inventory_label=str(ed.get("inventory_label") or ""),
            as_reservation=ed.get("as_reservation"),
            as_optimal_spread_pct=ed.get("as_optimal_spread_pct"),
            as_gamma=ed.get("as_gamma"),
            as_kappa=ed.get("as_kappa"),
            as_presence_pct=presence_pct,
            inside_l1=ed.get("inside_l1"),
            reservation_to_bbo_delta_bps=ed.get("reservation_to_bbo_delta_bps"),
            effective_quote_age_at_fill_seconds=self._last_fill_quote_age_seconds,
            recent_fill_quote_ages=list(self._recent_fill_quote_ages),
            reservation_crossed_after_ws_sample=self._reservation_crossed_after_ws_sample,
            zero_quote_reason=str(ed.get("zero_quote_reason") or ""),
            sample_history=list(self._analysis_bundle.get("sample_history") or []),
            sample_count=int(self._analysis_bundle.get("sample_count") or 0),
            presence_by_pressure=dict(self._analysis_bundle.get("presence_by_pressure") or {}),
            zero_quote_breakdown=dict(self._analysis_bundle.get("zero_quote_breakdown") or {}),
            soak_evaluation=dict(self._analysis_bundle.get("soak_evaluation") or {}),
            book_spread_pct=float(bb_spread or 0.0),
            volatility_pct=float(ed.get("volatility_pct") or ed.get("base_volatility_pct") or 0.0),
            session_baseline_xrp=self._session_baseline_xrp,
            session_baseline_rlusd=self._session_baseline_rlusd,
            session_baseline_mid=self._session_baseline_mid,
            session_pnl_balance_xrp=session_bal_pnl,
            session_spread_capture_xrp=float(self._session_spread_capture),
            session_pnl_xrp_estimate=session_bal_pnl,
            engine_pid=os.getpid(),
            inventory_mode=str(config.inventory_mode or "market_make"),
            edge_resolution_summary=str(ed.get("zero_quote_operator_note") or ed.get("zero_quote_reason") or ""),
            fill_quality_score=float(fill_quality.score),
            fill_quality_summary=str(fill_quality.summary),
            toxic_fill_ratio=float(fill_quality.toxic_ratio),
            toxic_fill_ratio_30s=float(fill_quality.toxic_ratio_30s),
            mean_markout_30s_pct=float(fill_quality.mean_markout_30s_pct),
            g2_size_mult=float(ed.get("g2_size_mult") or 1.0),
            g2_spread_mult=float(ed.get("g2_spread_mult") or 1.0),
            g2_grade=str(ed.get("g2_grade") or "neutral"),
            g2_active=bool(ed.get("g2_active")),
            g2_summary=str(ed.get("g2_summary") or ""),
            g4_size_mult=float(ed.get("g4_size_mult") or 1.0),
            g4_grade=str(ed.get("g4_grade") or "neutral"),
            g4_active=bool(ed.get("g4_active")),
            g4_summary=str(ed.get("g4_summary") or ""),
            competitor_intel=dict(self._last_comp_intel),
            g7_summary=str(ed.get("g7_summary") or ""),
            bid_touch_backoff_bps=float(ed.get("bid_touch_backoff_bps") or 0.0),
            ask_touch_backoff_bps=float(ed.get("ask_touch_backoff_bps") or 0.0),
            g7_bid_role=str(ed.get("g7_bid_role") or ""),
            g7_ask_role=str(ed.get("g7_ask_role") or ""),
            g7_scaler_label=str(ed.get("g7_scaler_label") or ""),
            g2_scaler_label=str(ed.get("g2_scaler_label") or ""),
            execution_brakes_summary=_execution_brakes_summary_with_queue(
                str(ed.get("execution_brakes_summary") or ""),
                quote_visibility_summary,
            ),
            quotes_at_touch=quotes_at_touch,
            worst_vs_touch_bps=float(worst_vs_touch_bps),
            quote_visibility_summary=str(quote_visibility_summary),
            book_bids=book_bids,
            book_asks=book_asks,
            session_boot_utc=self._session_boot_utc,
            g7_solo_acquisition=bool(ed.get("g7_solo_acquisition")),
            g7_ask_sell_defense=bool(ed.get("g7_ask_sell_defense")),
            peer_lane_empty=peer_lane_empty,
            solo_as_tighten=bool(ed.get("solo_as_tighten")),
            acquisition_metrics=acquisition_metrics,
            g4_peer_lane_count=int(ed.get("g4_peer_lane_count") or 0),
            qd_intent=str(ed.get("qd_intent") or ""),
            qd_bid_allowed=bool(ed.get("qd_bid_allowed")),
            qd_ask_allowed=bool(ed.get("qd_ask_allowed")),
            qd_would_quote=bool(ed.get("qd_would_quote")),
            qd_layer_summary=str(ed.get("qd_layer_summary") or ""),
            qd_bid_implied_bps=ed.get("qd_bid_implied_bps"),
            qd_ask_implied_bps=ed.get("qd_ask_implied_bps"),
            qd_bid_block_reason=str(ed.get("qd_bid_block_reason") or ""),
            qd_ask_block_reason=str(ed.get("qd_ask_block_reason") or ""),
            qd_bid_size_mult=float(ed.get("qd_bid_size_mult") or 0.0),
            qd_ask_size_mult=float(ed.get("qd_ask_size_mult") or 0.0),
        )
        self.state_store.save(state)
        if ed and flags.intel_log:
            try:
                append_intel_record(
                    build_cycle_intel_record(
                        cycle=self._cycle_count,
                        mid=mid,
                        balance_xrp=balance_xrp,
                        balance_rlusd=balance_rlusd,
                        portfolio_xrp=portfolio,
                        engine_dec=ed,
                        runtime_extras={
                            "inventory_target_xrp_ratio": float(
                                config.inventory_target_xrp_ratio
                            ),
                            "toxic_fill_ratio": float(fill_quality.toxic_ratio),
                            "toxic_fill_ratio_30s": float(fill_quality.toxic_ratio_30s),
                            "mean_markout_30s_pct": float(fill_quality.mean_markout_30s_pct),
                            "fills_session": self._session_fills,
                            "session_pnl_balance_xrp": session_bal_pnl,
                            "drawdown_pct": drawdown_pct,
                            "ws_as_version": current_ws_as_version(),
                            "peer_lane_empty": peer_lane_empty,
                            "worst_vs_touch_bps": float(worst_vs_touch_bps),
                        },
                    )
                )
            except OSError:
                pass
