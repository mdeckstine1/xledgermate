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
from typing import Any, Dict, List, Optional, Sequence

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig, is_trustworthy_rlusd_mid
from core import DecisionLog, VERSION
from core.runtime_state import QuoteIntent, RuntimeState, RuntimeStateStore
from engine.order_sync import plan_order_sync
from experimental.ws_feed.engine_adapter_example import WSBookFeedAdapter
from experimental.ws_feed.intel_decisions_log import (
    append_intel_record,
    build_cycle_intel_record,
    build_peer_scrape_intel_record,
)
from experimental.ws_feed.hud_intel_support import fetch_competitor_quoting_intel
from experimental.ws_feed.ws_feature_flags import WsFeatureFlags
from experimental.ws_feed.pure_quote_path import current_ws_as_version
from experimental.ws_feed.pair_books import RlusdXrpPair
from experimental.ws_feed.network_urls import rpc_url_to_websocket_url
from experimental.ws_feed.ws_book_feed import WsBookFeed
from monitoring.balance_logger import BalanceLogger
from monitoring.csv_logger import CSVLogger
from monitoring.fill_detection import detect_fill_from_balance_delta
from monitoring.fill_economics import estimate_spread_capture_xrp
from monitoring.telegram_alerts import TelegramAlerts
from risk.drawdown import DrawdownMonitor, portfolio_value_xrp, session_pnl_balance_delta_xrp
from risk.kill_switch import KillSwitch
from strategy.fill_quality import FillQualityState, FillQualityTracker
from utils.preflight import evaluate_preflight

logger = logging.getLogger(__name__)

ENGINE_STOP_FILE = Path("logs/engine.stop")
WS_STALE_REFRESH_S = 12.0
DEFAULT_SAMPLE_INTERVAL_S = 5.0
COMP_SCRAPE_INTERVAL_S = 15.0
WS_MID_MOVE_REFRESH_BPS = 4.0
WS_TOXIC_PRESERVE_OFF_RATIO = 0.35


def resolve_ws_sync_tolerances(
    *,
    mid: Optional[float],
    last_sync_mid: Optional[float],
    toxic_ratio_30s: float,
    recent_fills: int,
    g2_active: bool,
    base_price_tolerance_pct: float,
    mid_move_refresh_bps: float = WS_MID_MOVE_REFRESH_BPS,
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

    if mid and last_sync_mid and last_sync_mid > 0:
        move_bps = abs(mid - last_sync_mid) / last_sync_mid * 10_000.0
        if move_bps >= mid_move_refresh_bps:
            preserve_touch_queue = False
            price_tol = min(price_tol, 0.03)

    return price_tol, preserve_touch_queue


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
        side = str(row.get("side") or "").lower()
        if side not in ("bid", "ask"):
            continue
        price = float(row.get("price") or 0)
        size = float(row.get("size_xrp") or 0)
        level = int(row.get("level") or 1)
        if price <= 0 or size <= 0:
            continue
        out.append(QuoteIntent(level=level, side=side, price=price, size_xrp=size))
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
                return self._comp_intel_cache or None
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
            return self._comp_intel_cache or None

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

        await self._ws_feed.refresh_if_stale(WS_STALE_REFRESH_S)
        state = self._ws_feed.state
        bb, ba = state.best_prices()
        mid = (bb + ba) / 2.0 if bb and ba else None
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

        comp_intel = await self._maybe_refresh_competitor_intel(config)
        fill_state = self._fill_quality.assess() if flags.fill_quality else None

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
                sync_intents, mid=mid, best_bid=bb, best_ask=ba
            )

        await self._detect_fills(config, connector, balance_xrp, balance_rlusd, mid)

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
        self._append_decision_file(cycle=self._cycle_count, mid=mid, execution=execution)
        await self._persist_cycle(
            config, mid, bb, ba, balance_xrp, balance_rlusd, portfolio, intents, offers_last,
            execution, engine_dec=engine_dec,
        )

    async def _sync_offers(
        self,
        intents: List[QuoteIntent],
        *,
        mid: Optional[float],
        best_bid: Optional[float],
        best_ask: Optional[float],
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
        if not preserve_touch or price_tol < float(
            getattr(config, "order_price_tolerance_pct", 0.08)
        ):
            self.decision_log.add(
                "execution",
                f"WS refresh mode: tol={price_tol:.3f}% preserve_touch={preserve_touch}",
            )
        cancelled = 0
        for seq in plan.cancel_sequences:
            try:
                await connector.cancel_offer(seq)
                cancelled += 1
            except Exception as exc:
                self.decision_log.add("execution", f"Cancel seq {seq} failed: {exc}")
        placed = 0
        for intent in plan.place_intents:
            try:
                await connector.place_quote(intent)
                placed += 1
            except Exception as exc:
                self.decision_log.add("execution", f"Place {intent.side} failed: {exc}")
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
        side = str(fill["side"])
        xrp_amount = float(fill["xrp_amount"])
        rlusd_amount = float(fill["rlusd_amount"])
        price = float(fill["price_rlusd_per_xrp"])
        mid_at_quote = self._last_sync_mid or self._last_valid_mid or mid
        cap = estimate_spread_capture_xrp(
            side=side,
            xrp_amount=xrp_amount,
            fill_price_rlusd_per_xrp=price,
            mid_at_quote_rlusd_per_xrp=mid_at_quote,
        )
        mid_at_fill = mid if is_trustworthy_rlusd_mid(mid) else mid_at_quote
        self._session_fills += 1
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
            ),
            balance_xrp_after=balance_xrp,
            balance_rlusd_after=balance_rlusd,
        )
        if side == "SELL":
            self.csv_logger.log_sell(**common)
        else:
            self.csv_logger.log_buy(**common)

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

    def _append_decision_file(self, *, cycle: int, mid: Optional[float], execution: str) -> None:
        record = {
            "cycle": cycle,
            "mid_rlusd_per_xrp": mid,
            "execution": execution,
            "as_mode": "pure",
            "ws_as_version": current_ws_as_version(),
            "would_quote": "would sync" in execution.lower(),
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
    ) -> None:
        flags = WsFeatureFlags.from_config(config)
        drawdown_pct = self.drawdown_monitor.get_drawdown_percent()
        open_offers = []
        if self.connector:
            try:
                offers = await self.connector.get_open_offers()
                open_offers = [o.__dict__ if hasattr(o, "__dict__") else o for o in offers]
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
        presence_pct = None
        if self._cycle_count > 0:
            presence_pct = round(100.0 * self._would_quote_cycles / self._cycle_count, 1)
        flags = WsFeatureFlags.from_config(config)
        fill_quality = self._fill_quality.assess() if flags.fill_quality else FillQualityState()
        bb_spread = ed.get("book_spread_pct")
        if bb_spread is None and mid and bb and ba:
            bb_spread = (ba - bb) / mid * 100.0 if mid > 0 else 0.0
        if mid and mid > 0:
            self._price_history.append(float(mid))
            if len(self._price_history) > 200:
                self._price_history = self._price_history[-200:]
        decisions = [
            {"ts_utc": e.ts_utc, "category": e.category, "message": e.message}
            for e in self.decision_log.recent_newest_first(limit=60)
        ]
        cycle_s = int(self._sample_interval_s)
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
            quote_intents=intents,
            recent_decisions=decisions,
            price_source="ws_book_feed",
            price_history=list(self._price_history),
            as_mode="pure",
            ws_as_version=current_ws_as_version(),
            as_protected=True,
            ws_book_age_s=self._ws_feed.age_seconds() if self._ws_feed else None,
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
            pause_bids=bool(ed.get("pause_bids")),
            pause_asks=bool(ed.get("pause_asks")),
            as_reservation=ed.get("as_reservation"),
            as_optimal_spread_pct=ed.get("as_optimal_spread_pct"),
            as_gamma=ed.get("as_gamma"),
            as_kappa=ed.get("as_kappa"),
            as_presence_pct=presence_pct,
            book_spread_pct=float(bb_spread or 0.0),
            volatility_pct=float(ed.get("volatility_pct") or ed.get("base_volatility_pct") or 0.0),
            session_baseline_xrp=self._session_baseline_xrp,
            session_baseline_rlusd=self._session_baseline_rlusd,
            session_baseline_mid=self._session_baseline_mid,
            session_pnl_balance_xrp=session_bal_pnl,
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
                        },
                    )
                )
            except OSError:
                pass
