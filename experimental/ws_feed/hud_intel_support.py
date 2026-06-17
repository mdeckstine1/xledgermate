"""Shared Intel + competitor scrape helpers for WS HUD (lab tester + production mirror)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from config.settings import BotConfig
from connectors.xrpl_connector import XRPLConnector, XRPLNetworkConfig
from experimental.ws_feed.dynamic_sizing import DEFAULT_LADDER_SIZE_FRACS
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


def _normalize_quote_intents(runtime: Dict[str, Any]) -> list[dict[str, Any]]:
    intents = runtime.get("quote_intents") or []
    normalized: list[dict[str, Any]] = []
    for row in intents:
        if hasattr(row, "__dict__"):
            row = row.__dict__
        if isinstance(row, dict):
            normalized.append(row)
    return normalized


def lane_touch_xrp_from_intents(
    quote_intents: Optional[Sequence[Mapping[str, Any]]],
    level: int,
) -> float:
    """Max bid/ask size at ladder level (touch lane size for peer matching)."""
    if not quote_intents:
        return 0.0
    touch_sizes: list[float] = []
    for intent in quote_intents:
        if int(intent.get("level") or 0) != level:
            continue
        try:
            sz = float(intent.get("size_xrp") or 0)
        except (TypeError, ValueError):
            continue
        if sz > 0:
            touch_sizes.append(sz)
    return max(touch_sizes) if touch_sizes else 0.0


def _l1_touch_for_ladder(runtime: Dict[str, Any], *, fallback_l1: float = 0.0) -> float:
    lane = our_lane_xrp_from_runtime(runtime, fallback_l1=fallback_l1)
    if lane > 0:
        return lane
    for key in ("our_lane_xrp", "l1_xrp", "bid_size_xrp", "ask_size_xrp"):
        try:
            v = float(runtime.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v
    return 0.0


def planned_lane_touch_xrp(runtime: Dict[str, Any], level: int) -> float:
    """Derive planned L2/L3 touch from L1 when runtime only has active L1 intents."""
    if level <= 1:
        return 0.0
    l1 = _l1_touch_for_ladder(runtime)
    if l1 <= 0:
        return 0.0
    idx = level - 1
    configured = runtime.get("configured_order_sizes") or runtime.get("order_sizes")
    if configured and len(configured) >= level:
        try:
            raw = float(configured[idx])
        except (TypeError, ValueError):
            raw = 0.0
        if raw > 0:
            return raw
    if idx < len(DEFAULT_LADDER_SIZE_FRACS):
        return l1 * DEFAULT_LADDER_SIZE_FRACS[idx]
    return 0.0


def lane_ladder_hud_fields(runtime: Dict[str, Any]) -> Dict[str, Any]:
    """Planned L2/L3 touch sizes from quote ladder (L1 stays on our_lane_xrp from scrape)."""
    intents = _normalize_quote_intents(runtime)
    fields: Dict[str, Any] = {}
    for level, key in ((2, "our_lane_l2_xrp"), (3, "our_lane_l3_xrp")):
        touch = lane_touch_xrp_from_intents(intents, level)
        if touch <= 0:
            touch = planned_lane_touch_xrp(runtime, level)
        if touch > 0:
            fields[key] = round(touch, 2)
    return fields


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


def _accounts_match(query: str, row: Mapping[str, Any]) -> bool:
    """Match full or truncated r-address from scrape row."""
    q = (query or "").strip()
    if not q or len(q) < 8:
        return False
    full = str(row.get("account_full") or "").strip()
    short = str(row.get("account") or "").strip().replace("...", "")
    q_lower = q.lower()
    if full and (full.lower() == q_lower or full.lower().startswith(q_lower) or q_lower.startswith(full.lower())):
        return True
    if short and len(short) >= 8 and (q_lower.startswith(short.lower()) or short.lower().startswith(q_lower[:12])):
        return True
    return False


def find_competitor_profile(
    state: Mapping[str, Any],
    address: str,
) -> tuple[Optional[Dict[str, Any]], str]:
    """Return (profile row, source) where source is peer_lane | book_wide | none."""
    for row in state.get("top_peers") or []:
        if isinstance(row, dict) and _accounts_match(address, row):
            return dict(row), "peer_lane"
    for row in state.get("top_competitors") or []:
        if isinstance(row, dict) and _accounts_match(address, row):
            return dict(row), "book_wide"
    return None, "none"


def build_competitor_analysis_context(
    state: Mapping[str, Any],
    address: str,
    *,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assemble scrape-backed briefing for /analyze_competitor (HUD-only; no engine restart).

    Merges HUD _current_state with optional POST body fields from the browser.
    """
    from experimental.market_analysis.peer_lane import touch_in_peer_band

    merged: Dict[str, Any] = dict(state)
    if extra:
        for key, val in extra.items():
            if val is not None and val != "":
                merged[key] = val

    profile, source = find_competitor_profile(merged, address)
    if profile is None and isinstance(extra, Mapping):
        posted = extra.get("target_profile")
        if isinstance(posted, dict) and posted:
            profile = dict(posted)
            source = "peer_lane" if posted in list(merged.get("top_peers") or []) else "book_wide"
            if source == "book_wide" and any(
                _accounts_match(address, row) for row in (merged.get("top_peers") or []) if isinstance(row, dict)
            ):
                source = "peer_lane"
    try:
        our_lane = float(merged.get("our_lane_xrp") or 0)
    except (TypeError, ValueError):
        our_lane = 0.0
    try:
        band_low = float(merged.get("peer_lane_low_xrp") or (our_lane * 0.4 if our_lane > 0 else 0))
        band_high = float(merged.get("peer_lane_high_xrp") or (our_lane * 2.5 if our_lane > 0 else 0))
    except (TypeError, ValueError):
        band_low, band_high = 0.0, 0.0

    touch_xrp = 0.0
    if profile:
        try:
            touch_xrp = float(profile.get("touch_xrp") or 0)
        except (TypeError, ValueError):
            touch_xrp = 0.0

    in_peer_lane = source == "peer_lane"
    if profile and our_lane > 0 and touch_xrp > 0:
        in_peer_lane = touch_in_peer_band(touch_xrp, our_lane, allow_widen=True)

    fled_for_target: list[Dict[str, Any]] = []
    for ev in merged.get("peer_fled_events") or []:
        if not isinstance(ev, dict):
            continue
        if _accounts_match(address, ev):
            fled_for_target.append(ev)

    evidence_lines: list[str] = []
    if profile:
        evidence_lines.append(f"scrape_source={source}")
        evidence_lines.append(f"touch_xrp={touch_xrp:.2f}" if touch_xrp > 0 else "touch_xrp=unknown")
        evidence_lines.append(f"in_peer_lane={in_peer_lane}")
        if our_lane > 0:
            evidence_lines.append(f"our_lane_xrp={our_lane:.2f}")
            evidence_lines.append(f"peer_band={band_low:.1f}–{band_high:.1f} XRP")
        if profile.get("last_spread") is not None:
            evidence_lines.append(f"last_spread_pct={profile.get('last_spread')}")
        if profile.get("avg_spread") is not None:
            evidence_lines.append(f"avg_spread_pct={profile.get('avg_spread')}")
        if profile.get("activity") is not None:
            evidence_lines.append(f"offers_seen={profile.get('activity')}")
        if profile.get("cancels") is not None:
            evidence_lines.append(f"cancels_seen={profile.get('cancels')}")
        if profile.get("sides"):
            evidence_lines.append(f"sides={profile.get('sides')}")
        if profile.get("domain") and profile.get("domain") != "no-domain":
            evidence_lines.append(f"domain={profile.get('domain')}")
    else:
        evidence_lines.append("scrape_source=none (address not in last top_peers/top_competitors snapshot)")

    if fled_for_target:
        evidence_lines.append(f"fled_touch_events={len(fled_for_target)} recent")
        for ev in fled_for_target[:3]:
            evidence_lines.append(
                f"  fled: was {ev.get('previous_touch_xrp')} XRP at touch, {ev.get('age_s')}s ago"
            )

    # Live book / our posture
    for key, label, fmt in (
        ("competitor_pressure", "aggregate_pressure", lambda v: f"{float(v):.2f}"),
        ("competitor_observed_spread_pct", "observed_spread_pct", lambda v: f"{float(v):.3f}%"),
        ("competitor_depth_xrp", "book_depth_xrp", lambda v: f"{float(v):.1f}"),
        ("peer_lane_count", "peer_lane_count", str),
        ("inventory_label", "our_inventory", str),
        ("as_reservation", "our_as_reservation", lambda v: f"{float(v):.6f}"),
        ("as_optimal_spread_pct", "our_optimal_spread_pct", lambda v: f"{float(v):.3f}%"),
    ):
        val = merged.get(key)
        if val is not None and val != "":
            try:
                evidence_lines.append(f"{label}={fmt(val)}")
            except (TypeError, ValueError):
                evidence_lines.append(f"{label}={val}")

    if in_peer_lane:
        lane_note = "IN peer touch band — tactics may apply at our posted size."
    elif touch_xrp > 0 and our_lane > 0:
        lane_note = "OUT of peer touch band — macro/book context only; do not size tactics vs this touch."
    elif not profile:
        lane_note = "No scrape row — analysis must be explicitly speculative."
    else:
        lane_note = "Band status unknown — prefer aggregate peer-lane signals only."

    evidence_block = "\n".join(f"- {line}" for line in evidence_lines)
    prompt_block = (
        f"**Scraped on-chain facts for {address} (use as primary evidence; do not invent numbers):**\n"
        f"{evidence_block}\n\n"
        f"**Lane note:** {lane_note}\n\n"
        "If a behavior is not supported by the facts above, label it HYPOTHESIS and say what scrape field would confirm it."
    )

    if profile:
        header = (
            f"── Scrape evidence ({source.replace('_', ' ')}) ──\n"
            f"touch {touch_xrp:.1f} XRP · {'IN peer band' if in_peer_lane else 'OUT of band'} · "
            f"spread {profile.get('last_spread', '?')}% / avg {profile.get('avg_spread', '?')}% · "
            f"cancels {profile.get('cancels', '?')}\n"
            f"── Grok analysis (advisory) ──\n"
        )
    else:
        header = (
            "── No scrape row for this address (last ~15s snapshot) — Grok may speculate ──\n"
            "── Grok analysis (advisory) ──\n"
        )

    return {
        "profile": profile,
        "source": source,
        "in_peer_lane": in_peer_lane,
        "touch_xrp": touch_xrp,
        "our_lane_xrp": our_lane,
        "peer_band_low_xrp": band_low,
        "peer_band_high_xrp": band_high,
        "fled_events": fled_for_target,
        "evidence_lines": evidence_lines,
        "prompt_block": prompt_block,
        "evidence_header": header,
        "lane_note": lane_note,
    }


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
