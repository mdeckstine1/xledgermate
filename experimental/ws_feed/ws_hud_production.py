"""

Production WS + pure A-S HUD (:8765).



Mirrors the live tester HUD UI (`experimental/ws_feed/hud/index.html`) but reads

`logs/runtime_state.json` from `WsPureTradingEngine` and runs competitor intel +

Grok config for the Intelligence tab.



Run:

  python main.py --mode ws-hud

"""



from __future__ import annotations



import asyncio

import json

import logging

import time

from pathlib import Path

from typing import Any, Dict, Optional



from config.settings import BotConfig

from experimental.ws_feed.hud_intel_support import (
    CompetitorIntelProvider,
    build_connector,
    build_rlusd_pair,
    enrich_inventory_hud_fields,
    fetch_competitor_hud_fields,
    resolve_hud_intel_fields,
)

from experimental.ws_feed.live_pure_as_tester import _hud_market_payload

from experimental.ws_feed.intel_decisions_log import (
    append_intel_record,
    build_peer_scrape_intel_record,
)
from experimental.ws_feed.performance_metrics import build_performance_metrics
from experimental.ws_feed.pure_quote_path import WS_AS_VERSION

from experimental.ws_feed.real_time_as_hud import (

    get_hud_current_state,

    run_hud,

    update_state as hud_update_state,

)



logger = logging.getLogger(__name__)



RUNTIME_PATH = Path("logs/runtime_state.json")

POLL_INTERVAL_S = 1.0

COMP_SCRAPE_INTERVAL_S = 15.0





def _enrich_runtime_for_hud(runtime: Dict[str, Any]) -> Dict[str, Any]:

    """Map ws-engine RuntimeState export → HUD/live tester field names."""

    rt = dict(runtime)

  # Project VERSION (2.1.0) ≠ WS path WS_AS_VERSION (2.1.1); never conflate them.
    rt["ws_as_version"] = (str(rt.get("ws_as_version") or "").strip() or WS_AS_VERSION)

    rt.setdefault("sample_count", rt.get("cycle_count", 0))



    intents = rt.get("quote_intents") or []

    normalized: list[dict[str, Any]] = []

    for row in intents:

        if hasattr(row, "__dict__"):

            row = row.__dict__

        if not isinstance(row, dict):

            continue

        side = str(row.get("side") or "").lower()

        price = float(row.get("price") or 0)

        size = float(row.get("size_xrp") or row.get("size") or 0)

        level = int(row.get("level") or 1)

        normalized.append(

            {

                "level": level,

                "side": side,

                "price": price,

                "size_xrp": size,

                "active": level == 1 and price > 0 and size > 0,

            }

        )

        if level == 1 and price > 0:

            if side == "bid":

                rt.setdefault("suggested_bid", price)

                rt.setdefault("bid_size_xrp", size)

                rt.setdefault("l1_xrp", size)

            elif side == "ask":

                rt.setdefault("suggested_ask", price)

                rt.setdefault("ask_size_xrp", size)

                if not rt.get("l1_xrp"):

                    rt.setdefault("l1_xrp", size)

    if normalized:

        rt["quote_intents"] = normalized



    note = str(rt.get("edge_resolution_summary") or "")

    if note and not rt.get("zero_quote_reason"):

        rt["zero_quote_operator_note"] = note

    try:
        from scripts.ws_path_session_report import count_ws_fills_csv

        rt["ws_fills_csv"] = count_ws_fills_csv()
    except Exception:
        rt.setdefault("ws_fills_csv", int(rt.get("fills_session") or 0))

    return rt





def _load_runtime_snapshot() -> Dict[str, Any]:

    if not RUNTIME_PATH.exists():

        return {}

    try:

        return json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))

    except (OSError, json.JSONDecodeError) as exc:

        logger.warning("Could not read runtime_state.json: %s", exc)

        return {}





class ProductionHudMirror:

    """Poll ws-engine runtime + competitor intel → HUD /state."""



    def __init__(self, config: BotConfig) -> None:

        self.config = config

        self._comp_provider: Any = None

        self._last_comp_scrape = 0.0

        self._last_comp_fields: Dict[str, Any] = {}

        self._fallback_l1 = float(config.order_sizes[0]) if config.order_sizes else 15.0



    async def _ensure_competitor_provider(self) -> bool:

        if self._comp_provider is not None:

            return True

        if CompetitorIntelProvider is None:

            logger.warning("CompetitorIntelProvider unavailable — Intelligence scrape disabled")

            return False

        try:

            connector = build_connector(self.config)

            pair = build_rlusd_pair(self.config)

            self._comp_provider = CompetitorIntelProvider(connector, pair)

            logger.info("Production HUD: CompetitorIntelProvider active (on-chain scrape)")

            return True

        except Exception:

            logger.exception("Production HUD: failed to init CompetitorIntelProvider")

            return False



    async def _maybe_competitor_fields(self, enriched: Dict[str, Any]) -> Dict[str, Any]:

        now = time.monotonic()

        if now - self._last_comp_scrape < COMP_SCRAPE_INTERVAL_S and self._last_comp_fields:

            return dict(self._last_comp_fields)

        if not await self._ensure_competitor_provider():

            return {}

        try:

            fields = await fetch_competitor_hud_fields(

                self._comp_provider,

                enriched,

                fallback_l1_xrp=self._fallback_l1,

            )

            if fields.get("competitor_error"):

                return self._last_comp_fields

            self._last_comp_scrape = now

            self._last_comp_fields = fields

            return fields

        except Exception:

            logger.exception("Production HUD: competitor scrape failed")

            return self._last_comp_fields



    def _seed_intel_config(self) -> None:

        intel = resolve_hud_intel_fields(get_hud_current_state())

        hud_update_state(intel)

        if intel.get("intel_ai_key"):

            logger.info(

                "Production HUD: Grok intel configured (provider=%s model=%s key_len=%d)",

                intel.get("intel_ai_provider"),

                intel.get("intel_ai_model"),

                len(str(intel.get("intel_ai_key"))),

            )

        else:

            logger.warning(

                "Production HUD: no Grok key — set XLG_GROK_KEY in .env or Config tab Apply"

            )



    async def push_cycle(self, *, bot_address: str) -> None:

        runtime = _load_runtime_snapshot()

        if not runtime:

            return



        enriched = _enrich_runtime_for_hud(runtime)

        comp_fields = await self._maybe_competitor_fields(enriched)

        if comp_fields and not comp_fields.get("competitor_error"):
            try:
                append_intel_record(build_peer_scrape_intel_record(comp_fields))
            except OSError:
                pass

        enriched.update(comp_fields)

        enriched.update(
            enrich_inventory_hud_fields(
                enriched,
                config=self.config,
                bot_address=bot_address,
            )
        )

        intel = resolve_hud_intel_fields(get_hud_current_state())

        enriched.update(intel)

        enriched["performance_metrics"] = build_performance_metrics(runtime=enriched)

        hud_update_state(

            _hud_market_payload(

                enriched,

                bot_address=bot_address,

                production_source="ws-engine",

                dry_run=bool(enriched.get("dry_run")),

                engine_profile=enriched.get("active_profile"),

                active_profile=enriched.get("active_profile") or "ws_pure",

            )

        )





async def run_production_hud(*, host: str = "127.0.0.1", port: int = 8765) -> None:

    config = BotConfig.load()

    bot_address = (config.bot_account_address or "").strip() or "r... (set bot_account_address)"



    server = run_hud(host=host, port=port, background=True)

    if server is None:

        raise RuntimeError("HUD failed to start — pip install fastapi uvicorn")



    mirror = ProductionHudMirror(config)

    mirror._seed_intel_config()



    logger.info(

        "WS Pure A-S production HUD on http://%s:%s (ws-engine + competitor intel + Grok)",

        host,

        port,

    )



    while True:

        try:

            await mirror.push_cycle(bot_address=bot_address)

        except Exception:

            logger.exception("Production HUD poll failed")

        await asyncio.sleep(POLL_INTERVAL_S)





def main() -> None:

    logging.basicConfig(level=logging.INFO)

    asyncio.run(run_production_hud())





if __name__ == "__main__":

    main()


