"""Shared Intel + competitor scrape helpers for WS HUD (lab tester + production mirror)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from experimental.ws_feed.pair_books import RlusdXrpPair
from utils.env_secrets import resolve_intel_ai_config

logger = logging.getLogger(__name__)

INTEL_CONFIG_PATH = Path("logs/hud_intel_config.json")

try:
    from experimental.market_analysis.competitor_intel import CompetitorIntelProvider
except Exception:
    CompetitorIntelProvider = None  # type: ignore[misc, assignment]


def load_persisted_intel_config() -> Dict[str, Any]:
    """HUD Grok/API config saved from Config tab (survives ws-hud restart)."""
    if not INTEL_CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(INTEL_CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_persisted_intel_config(
    *,
    provider: str,
    key: str,
    model: str,
    enabled: bool,
) -> None:
    """Persist operator intel config (key at rest in logs/ — chmod 600 on VPS)."""
    key = (key or "").strip()
    if not key:
        return
    INTEL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "intel_ai_provider": (provider or "grok").strip() or "grok",
        "intel_ai_key": key,
        "intel_ai_model": (model or "grok-3").strip() or "grok-3",
        "intel_ai_enabled": bool(enabled),
    }
    INTEL_CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(INTEL_CONFIG_PATH, 0o600)
    except OSError:
        pass
    logger.info(
        "Saved HUD intel config (provider=%s model=%s key_len=%d)",
        payload["intel_ai_provider"],
        payload["intel_ai_model"],
        len(key),
    )


def build_connector(config: BotConfig) -> XRPLConnector:
    return XRPLConnector(
        account_address=(config.bot_account_address or "").strip(),
        secret=config.bot_secret_key or None,
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.resolved_rlusd_currency_code(),
        network=XRPLNetworkConfig(json_rpc_url=config.resolved_rpc_url()),
    )


def build_rlusd_pair(config: BotConfig) -> RlusdXrpPair:
    taker = (config.bot_account_address or "").strip()
    return RlusdXrpPair(
        rlusd_issuer=config.resolved_rlusd_issuer(),
        rlusd_currency=config.rlusd_currency,
        taker=taker or "rProductionHudXXXXXXXXXXXX",
    )


def resolve_hud_intel_fields(
    hud_state: Optional[Dict[str, Any]] = None,
    *,
    grok_enabled: bool = True,
) -> Dict[str, Any]:
    """
    Merge .env → persisted Config tab save → in-memory HUD state.

    Priority: in-memory (user just applied) > persisted file > .env.
    """
    prov, key, model = resolve_intel_ai_config()
    persisted = load_persisted_intel_config()
    p_key = (persisted.get("intel_ai_key") or "").strip()
    if p_key:
        key = p_key
        prov = str(persisted.get("intel_ai_provider") or prov or "grok")
        model = str(persisted.get("intel_ai_model") or model or "grok-3")

    hud_state = hud_state or {}
    user_key = (hud_state.get("intel_ai_key") or "").strip()
    if user_key:
        key = user_key
        prov = str(hud_state.get("intel_ai_provider") or prov or "grok")
        model = str(hud_state.get("intel_ai_model") or model or "grok-3")
        enabled = bool(hud_state.get("intel_ai_enabled", True))
    elif p_key:
        enabled = bool(persisted.get("intel_ai_enabled", True))
    else:
        enabled = bool(hud_state.get("intel_ai_enabled", True)) if "intel_ai_enabled" in hud_state else True

    if not grok_enabled:
        key = ""
        enabled = False

    if key and (not prov or prov == "stub"):
        prov = "grok"

    return {
        "intel_ai_provider": prov,
        "intel_ai_key": key,
        "intel_ai_model": model,
        "intel_ai_enabled": bool(enabled) and bool(key),
    }


def our_lane_xrp_from_runtime(runtime: Dict[str, Any], *, fallback_l1: float) -> float:
    from experimental.market_analysis.peer_lane import our_lane_from_runtime

    intents = runtime.get("quote_intents") or []
    normalized: list[dict[str, Any]] = []
    for row in intents:
        if hasattr(row, "__dict__"):
            row = row.__dict__
        if isinstance(row, dict):
            normalized.append(row)

    lane = our_lane_from_runtime(
        l1_xrp=runtime.get("l1_xrp"),
        bid_size_xrp=runtime.get("bid_size_xrp"),
        ask_size_xrp=runtime.get("ask_size_xrp"),
        quote_intents=normalized or None,
    )
    if lane > 0:
        return float(lane)

    # Posted on ledger (production: intents empty when A-S blocked but offers resting)
    offer_sizes: list[float] = []
    for row in runtime.get("open_offers") or []:
        if hasattr(row, "__dict__"):
            row = row.__dict__
        if not isinstance(row, dict):
            continue
        try:
            sz = float(row.get("size_xrp") or row.get("size") or 0)
        except (TypeError, ValueError):
            sz = 0.0
        if sz > 0:
            offer_sizes.append(sz)
    if offer_sizes:
        return max(offer_sizes)

    return float(fallback_l1)


async def fetch_competitor_quoting_intel(
    provider: Any,
    ws_feed: Any,
    *,
    our_lane_xrp: float,
    fallback_l1_xrp: float,
) -> Dict[str, Any]:
    """On-chain scrape with WS book for production ws-engine G4 quoting inputs."""
    state = ws_feed.state
    bb, ba = state.best_prices()
    book = state.to_order_book() if hasattr(state, "to_order_book") else {"bids": [], "asks": []}
    our_lane = our_lane_xrp if our_lane_xrp > 0 else float(fallback_l1_xrp)
    snap = await provider.fetch_snapshot(
        our_lane_xrp=our_lane,
        best_bid=bb,
        best_ask=ba,
        ws_bids=book.get("bids"),
        ws_asks=book.get("asks"),
    )
    return provider.to_hud_state(snap)


def competitor_fields_from_runtime(runtime: Dict[str, Any]) -> Dict[str, Any]:
    """Intelligence tab fields from ws-engine scrape (no duplicate HUD RPC)."""
    blob = runtime.get("competitor_intel")
    if isinstance(blob, dict) and blob:
        return dict(blob)
    return {}


def enrich_inventory_hud_fields(
    runtime: Dict[str, Any],
    *,
    config: Optional[BotConfig] = None,
    bot_address: str = "",
) -> Dict[str, Any]:
    """On-ledger bot inventory + funding plan vs risk_capital (for HUD Inventory tab)."""
    try:
        mid = float(runtime.get("mid_price") or runtime.get("mid") or 0)
    except (TypeError, ValueError):
        mid = 0.0
    try:
        bal_xrp = float(runtime.get("balance_xrp") or 0)
        bal_rlusd = float(runtime.get("balance_rlusd") or 0)
    except (TypeError, ValueError):
        bal_xrp, bal_rlusd = 0.0, 0.0
    try:
        portfolio = float(runtime.get("portfolio_value_xrp") or 0)
    except (TypeError, ValueError):
        portfolio = 0.0
    if portfolio <= 0 and mid > 0:
        portfolio = bal_xrp + bal_rlusd / mid

    target_ratio = 0.55
    risk_capital = 11254.0
    if config is not None:
        target_ratio = float(getattr(config, "inventory_target_xrp_ratio", 0.55))
        risk_capital = float(
            config.effective_risk_capital_xrp(mid) if mid > 0 else config.risk_capital_xrp
        )

    xrp_ratio = (bal_xrp / portfolio * 100.0) if portfolio > 0 else 0.0
    rlusd_xrp = (bal_rlusd / mid) if mid > 0 else 0.0
    deployed_pct = (portfolio / risk_capital * 100.0) if risk_capital > 0 else 0.0

    if deployed_pct < 5:
        funding_status = "pre_funding"
        funding_label = "Pre-funding — dev pilot only; operator capital stays in Xaman until dev complete"
    elif deployed_pct < 90:
        funding_status = "partial"
        funding_label = f"Partially funded ({deployed_pct:.0f}% of planned capital on bot ledger)"
    else:
        funding_status = "deployed"
        funding_label = "Planned capital deployed on bot ledger"

    addr = (bot_address or (getattr(config, "bot_account_address", "") if config else "") or "").strip()

    return {
        "bot_account_address": addr,
        "portfolio_value_xrp": round(portfolio, 4) if portfolio else None,
        "inventory_target_xrp_ratio": target_ratio,
        "inventory_xrp_ratio_pct": round(xrp_ratio, 1),
        "inventory_target_xrp_pct": round(target_ratio * 100.0, 1),
        "rlusd_xrp_equiv": round(rlusd_xrp, 4) if rlusd_xrp else None,
        "risk_capital_xrp": round(risk_capital, 2),
        "funding_deployed_xrp": round(portfolio, 2) if portfolio else 0.0,
        "funding_deployed_pct": round(deployed_pct, 1),
        "funding_status": funding_status,
        "funding_status_label": funding_label,
        "ledger_updated_utc": runtime.get("updated_utc"),
        "open_offers_count": int(runtime.get("open_offers_count") or 0),
    }
