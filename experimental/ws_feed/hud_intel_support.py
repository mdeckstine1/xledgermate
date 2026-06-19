"""Shared Intel + competitor scrape helpers for WS HUD (lab tester + production mirror)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

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


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_sides_string(sides: Any) -> tuple[int, int]:
    """Parse profile sides like 'b10/a5' into (bid_count, ask_count)."""
    text = str(sides or "").strip().lower()
    if not text:
        return 0, 0
    bid, ask = 0, 0
    for part in text.replace(" ", "").split("/"):
        if part.startswith("b") and part[1:].isdigit():
            bid += int(part[1:])
        elif part.startswith("a") and part[1:].isdigit():
            ask += int(part[1:])
    return bid, ask


def _rollup_sides_from_runtime(merged: Mapping[str, Any]) -> Dict[str, Any]:
    """Soak-safe fallback: roll up top_competitors sides when engine lacks I5 fields."""
    bid = int(merged.get("book_bid_offers") or 0)
    ask = int(merged.get("book_ask_offers") or 0)
    if bid or ask:
        return {}
    rows = list(merged.get("top_competitors") or []) + list(merged.get("top_peers") or [])
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("account_full") or row.get("account") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        b, a = _parse_sides_string(row.get("sides"))
        bid += b
        ask += a
    if not (bid or ask):
        return {}
    from experimental.market_analysis.competitor_intel import aggregate_book_side_skew, CompetitorProfile

    pseudo = [
        CompetitorProfile(account="_rollup", sides_quoted={"bid": bid, "ask": ask}),
    ]
    return aggregate_book_side_skew(pseudo)


def book_side_skew_hud_fields(runtime: Dict[str, Any]) -> Dict[str, Any]:
    """I5 — book-wide bid/ask offer skew from competitor scrape (HUD pill only)."""
    ci = competitor_fields_from_runtime(runtime)
    merged = {**runtime, **ci}
    rollup = _rollup_sides_from_runtime(merged)
    if rollup:
        merged = {**merged, **rollup}
    bid = int(merged.get("book_bid_offers") or 0)
    ask = int(merged.get("book_ask_offers") or 0)
    label = str(merged.get("book_side_skew_label") or "unknown")
    skew = _float_or_none(merged.get("book_side_skew"))
    ratio = _float_or_none(merged.get("book_side_skew_ratio"))
    display = "—"
    if bid or ask:
        display = f"b{bid}/a{ask}"
        if label != "unknown":
            display += f" · {label.replace('_', ' ')}"
    return {
        "book_bid_offers": bid or None,
        "book_ask_offers": ask or None,
        "book_side_skew": skew,
        "book_side_skew_ratio": ratio,
        "book_side_skew_label": label if (bid or ask) else None,
        "book_side_skew_display": display if (bid or ask) else "—",
    }


def structured_peer_briefing(
    ctx: Mapping[str, Any],
    *,
    address: str,
    state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """F3b — formal JSON briefing schema for Grok prompts and outcome tracking."""
    profile = ctx.get("profile")
    state = state or {}
    ci = competitor_fields_from_runtime(dict(state)) if state else {}
    merged = {**dict(state), **ci}
    prof_payload: Optional[Dict[str, Any]] = None
    if isinstance(profile, dict):
        prof_payload = {
            "account": profile.get("account_full") or profile.get("account"),
            "touch_xrp": profile.get("touch_xrp"),
            "last_spread_pct": profile.get("last_spread"),
            "avg_spread_pct": profile.get("avg_spread"),
            "offers_seen": profile.get("activity"),
            "cancels_seen": profile.get("cancels"),
            "sides": profile.get("sides"),
            "domain": profile.get("domain"),
        }
    return {
        "schema_version": 1,
        "address": address,
        "scrape_source": ctx.get("source"),
        "in_peer_lane": bool(ctx.get("in_peer_lane")),
        "touch_xrp": ctx.get("touch_xrp"),
        "our_lane_xrp": ctx.get("our_lane_xrp"),
        "peer_band": {
            "low_xrp": ctx.get("peer_band_low_xrp"),
            "high_xrp": ctx.get("peer_band_high_xrp"),
        },
        "profile": prof_payload,
        "macro": {
            "competitor_pressure": merged.get("competitor_pressure"),
            "book_regime_pressure": merged.get("book_regime_pressure") or merged.get("pressure_score"),
            "peer_pressure_score": merged.get("peer_pressure_score"),
            "peer_lane_count": merged.get("peer_lane_count"),
            "book_spread_pct": merged.get("book_spread_pct"),
            "book_side_skew": merged.get("book_side_skew"),
            "book_side_skew_label": merged.get("book_side_skew_label"),
            "inventory_label": merged.get("inventory_label"),
        },
        "fled_events": list(ctx.get("fled_events") or []),
        "evidence_lines": list(ctx.get("evidence_lines") or []),
        "lane_note": ctx.get("lane_note"),
        "is_our_bot": bool(ctx.get("is_our_bot")),
    }


def regime_intel_hud_fields(runtime: Dict[str, Any]) -> Dict[str, Any]:
    """
    I6 display split — peer lane pressure vs book-wide regime (HUD-only until JSONL ships).

    Does not change quoting inputs (`prepare_quoting_intel` neutralizes empty peer lane).
    """
    ci = competitor_fields_from_runtime(runtime)
    merged = {**runtime, **ci}
    peer_count = int(merged.get("peer_lane_count") or 0)
    peer_ps = _float_or_none(merged.get("peer_pressure_score"))
    book_ps = _float_or_none(
        merged.get("book_regime_pressure") or merged.get("pressure_score")
    )
    if book_ps is None and peer_count <= 0:
        book_ps = _float_or_none(merged.get("competitor_pressure"))
    peer_display = peer_ps if peer_count > 0 else None
    book_spread = _float_or_none(merged.get("book_spread_pct"))
    regime_spread = None
    if peer_count > 0:
        regime_spread = _float_or_none(merged.get("peer_observed_spread_pct"))
    if regime_spread is None:
        regime_spread = _float_or_none(merged.get("competitor_observed_spread_pct"))
    spread_regime_gap_bps = None
    if book_spread is not None and regime_spread is not None:
        spread_regime_gap_bps = round((regime_spread - book_spread) * 100.0, 1)
    return {
        "peer_pressure": peer_display,
        "book_regime_pressure": book_ps,
        "spread_regime_gap_bps": spread_regime_gap_bps,
        "regime_channel_active": bool(merged.get("regime_channel_active", False)),
        **book_side_skew_hud_fields(runtime),
    }


def _accounts_match(query: str, row: Mapping[str, Any]) -> bool:
    """Match full or truncated r-address from scrape row."""
    q = (query or "").strip()
    if not q or len(q) < 8:
        return False
    full = str(row.get("account_full") or row.get("account") or "").strip()
    short = str(row.get("account") or "").strip().replace("...", "")
    q_lower = q.lower()
    if full and (full.lower() == q_lower or full.lower().startswith(q_lower) or q_lower.startswith(full.lower())):
        return True
    if short and len(short) >= 8 and (q_lower.startswith(short.lower()) or short.lower().startswith(q_lower[:12])):
        return True
    return False


def bot_address_from_state(state: Mapping[str, Any]) -> str:
    """Configured bot ledger address on HUD runtime (if any)."""
    for key in ("bot_account_address", "bot_address"):
        val = str(state.get(key) or "").strip()
        if val.startswith("r") and len(val) >= 25:
            return val
    return ""


def is_own_bot_address(state: Mapping[str, Any], address: str) -> bool:
    bot = bot_address_from_state(state)
    if not bot:
        return False
    return _accounts_match(address, {"account_full": bot, "account": bot})


def build_self_bot_profile(state: Mapping[str, Any], address: str) -> Dict[str, Any]:
    """
    Synthetic scrape row for our own MM ledger.

    CompetitorIntelProvider excludes bot offers from top_peers/top_competitors by design.
    """
    try:
        our_lane = float(state.get("our_lane_xrp") or 0)
    except (TypeError, ValueError):
        our_lane = 0.0
    open_offers = int(state.get("open_offers_count") or 0)
    book_spread = state.get("book_spread_pct")
    if book_spread is None:
        book_spread = state.get("as_optimal_spread_pct")
    intents = state.get("quote_intents") or []
    bid_n = sum(1 for i in intents if isinstance(i, dict) and i.get("side") == "bid")
    ask_n = sum(1 for i in intents if isinstance(i, dict) and i.get("side") == "ask")
    if bid_n or ask_n:
        sides = f"b{bid_n}/a{ask_n}"
    elif state.get("pause_bids") or state.get("pause_asks"):
        parts = []
        if state.get("pause_bids"):
            parts.append("bid paused")
        if state.get("pause_asks"):
            parts.append("ask paused")
        sides = ", ".join(parts)
    else:
        sides = f"live×{open_offers}" if open_offers else "—"
    short = address[:12] + "..." if len(address) > 15 else address
    return {
        "account": short,
        "account_full": address,
        "touch_xrp": our_lane,
        "last_spread": book_spread,
        "avg_spread": state.get("as_optimal_spread_pct"),
        "activity": open_offers,
        "cancels": state.get("cancel_per_fill"),
        "sides": sides,
        "domain": "our-bot",
        "is_self": True,
        "g7_summary": state.get("g7_summary"),
        "worst_vs_touch_bps": state.get("worst_vs_touch_bps"),
        "quote_visibility_summary": state.get("quote_visibility_summary"),
    }


def find_competitor_profile(
    state: Mapping[str, Any],
    address: str,
) -> tuple[Optional[Dict[str, Any]], str]:
    """Return (profile row, source) where source is peer_lane | book_wide | none."""
    for row in state.get("top_peers") or []:
        if isinstance(row, dict) and _accounts_match(address, row):
            return dict(row), "peer_lane"
    for row in state.get("shadow_top_peers") or []:
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
    is_our_bot = False
    if profile is None and is_own_bot_address(merged, address):
        bot = bot_address_from_state(merged) or address
        profile = build_self_bot_profile(merged, bot)
        source = "our_bot"
        is_our_bot = True
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

    in_peer_lane = source in ("peer_lane", "our_bot")
    if profile and our_lane > 0 and touch_xrp > 0 and source != "our_bot":
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
        if is_our_bot:
            evidence_lines.append("target_role=our_bot (excluded from competitor scrape by design)")
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
        if profile.get("g7_summary"):
            evidence_lines.append(f"g7_summary={profile.get('g7_summary')}")
        if profile.get("worst_vs_touch_bps") is not None:
            evidence_lines.append(f"worst_vs_touch_bps={profile.get('worst_vs_touch_bps')}")
        if profile.get("quote_visibility_summary"):
            evidence_lines.append(f"quote_visibility={profile.get('quote_visibility_summary')}")
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

    if is_our_bot:
        lane_note = (
            "OUR bot ledger — self-audit only (queue visibility, vs-touch, inventory). "
            "Not a competitor; do not recommend tactics to trade against ourselves."
        )
    elif str(merged.get("analysis_context") or "") == "shadow_e3_calibration":
        if in_peer_lane:
            lane_note = (
                "SHADOW E3 calibration (11k equiv · 55/45 — not live posting size). "
                "IN shadow peer touch band — queue tactics may apply at scaled touch."
            )
        else:
            lane_note = (
                "SHADOW E3 calibration — OUT of shadow band at E3 ruler; book context only."
            )
        evidence_lines.insert(
            0,
            "calibration_mode=shadow_e3 (11k XRP-equiv · 55% XRP · balanced — advisory only)",
        )
    elif in_peer_lane:
        lane_note = "IN peer touch band — tactics may apply at our posted size."
    elif touch_xrp > 0 and our_lane > 0:
        lane_note = "OUT of peer touch band — macro/book context only; do not size tactics vs this touch."
    elif not profile:
        lane_note = "No scrape row — analysis must be explicitly speculative."
    else:
        lane_note = "Band status unknown — prefer aggregate peer-lane signals only."

    evidence_block = "\n".join(f"- {line}" for line in evidence_lines)
    if is_our_bot:
        prompt_block = (
            f"**Target is OUR market-making bot** ({address}). Runtime facts (not competitor scrape):\n"
            f"{evidence_block}\n\n"
            f"**Lane note:** {lane_note}\n\n"
            "Advise on quote posture, touch distance, visibility, and inventory alignment — not exploitative tactics vs this address."
        )
    else:
        prompt_block = (
            f"**Scraped on-chain facts for {address} (use as primary evidence; do not invent numbers):**\n"
            f"{evidence_block}\n\n"
            f"**Lane note:** {lane_note}\n\n"
            "If a behavior is not supported by the facts above, label it HYPOTHESIS and say what scrape field would confirm it."
        )

    if profile:
        label = "our bot (self-audit)" if is_our_bot else source.replace("_", " ")
        header = (
            f"── Scrape evidence ({label}) ──\n"
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

    structured = structured_peer_briefing(
        {
            "profile": profile,
            "source": source,
            "in_peer_lane": in_peer_lane,
            "touch_xrp": touch_xrp,
            "our_lane_xrp": our_lane,
            "peer_band_low_xrp": band_low,
            "peer_band_high_xrp": band_high,
            "fled_events": fled_for_target,
            "evidence_lines": evidence_lines,
            "lane_note": lane_note,
            "is_our_bot": is_our_bot,
        },
        address=address,
        state=merged,
    )

    return {
        "profile": profile,
        "source": source,
        "in_peer_lane": in_peer_lane,
        "is_our_bot": is_our_bot,
        "touch_xrp": touch_xrp,
        "our_lane_xrp": our_lane,
        "peer_band_low_xrp": band_low,
        "peer_band_high_xrp": band_high,
        "fled_events": fled_for_target,
        "evidence_lines": evidence_lines,
        "prompt_block": prompt_block,
        "evidence_header": header,
        "lane_note": lane_note,
        "structured_briefing": structured,
        "peer_lane_count": int(merged.get("peer_lane_count") or 0),
    }


def strip_grok_json_echo(text: str) -> str:
    """Remove echoed ```json blocks; flag JSON-only replies."""
    import re

    cleaned = re.sub(r"```json\s*[\s\S]*?```", "", text or "", flags=re.IGNORECASE).strip()
    if not cleaned:
        return "(Grok echoed structured JSON only — expand “Input briefing” below for machine-readable fields.)"
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            import json as _json

            _json.loads(cleaned)
            return "(Grok returned JSON only — expand “Input briefing” below for machine-readable fields.)"
        except ValueError:
            pass
    return cleaned


def _fmt_pct(val: Any, places: int = 3) -> str:
    try:
        return f"{float(val):.{places}f}%"
    except (TypeError, ValueError):
        return str(val)


def format_intel_analysis_report(briefing: Mapping[str, Any]) -> str:
    """Operator-facing prose report from briefing facts (always shown above Grok commentary)."""
    is_our_bot = bool(briefing.get("is_our_bot"))
    profile = briefing.get("profile") if isinstance(briefing.get("profile"), dict) else {}
    source = str(briefing.get("source") or "none")
    touch = briefing.get("touch_xrp")
    our_lane = briefing.get("our_lane_xrp")
    band_lo = briefing.get("peer_band_low_xrp")
    band_hi = briefing.get("peer_band_high_xrp")
    in_lane = briefing.get("in_peer_lane")
    peer_count = int(briefing.get("peer_lane_count") or 0)

    # Parse evidence key=value pairs once (macro fields not duplicated in header).
    macro: Dict[str, str] = {}
    for ev in briefing.get("evidence_lines") or []:
        text = str(ev)
        if "=" not in text:
            continue
        key, _, val = text.partition("=")
        macro[key.strip()] = val.strip()

    lines: List[str] = []
    if is_our_bot:
        lines.append("=== Our bot — self-audit report ===")
    else:
        lines.append("=== Competitor analysis report ===")
    lines.append("")

    if profile:
        acct = profile.get("account_full") or profile.get("account") or "—"
        lines.append(f"Address: {acct}")
        lines.append(f"Source: {source.replace('_', ' ')}")
        if touch is not None:
            lines.append(f"Posted touch: {float(touch):.2f} XRP")
        if our_lane is not None:
            lines.append(f"Our lane (L1 size): {float(our_lane):.2f} XRP")
        if band_lo is not None and band_hi is not None:
            lines.append(f"Peer band: {float(band_lo):.1f}–{float(band_hi):.1f} XRP")
        if is_our_bot:
            if peer_count <= 0:
                lines.append("Band status: OUR quotes in lane · no peer makers at touch right now")
            elif in_lane:
                lines.append(f"Band status: IN peer touch band · {peer_count} peer(s) at touch")
            else:
                lines.append("Band status: OUT of peer touch band")
        else:
            lane_txt = "IN peer touch band" if in_lane else "OUT of peer touch band"
            lines.append(f"Band status: {lane_txt}")
        if profile.get("last_spread") is not None:
            avg = profile.get("avg_spread")
            avg_txt = _fmt_pct(avg) if avg is not None else "—"
            lines.append(f"Book spread: {_fmt_pct(profile.get('last_spread'))} · our optimal: {avg_txt}")
        if profile.get("activity") is not None:
            lines.append(f"Open offers on ledger: {profile.get('activity')}")
        if profile.get("sides"):
            lines.append(f"Quote intents (levels): {profile.get('sides')}")
        if profile.get("cancels") is not None:
            lines.append(f"Cancel/fill (session): {profile.get('cancels')}")
        if profile.get("g7_summary"):
            lines.append(f"G7: {profile.get('g7_summary')}")
        if profile.get("worst_vs_touch_bps") is not None:
            lines.append(f"Worst vs touch: {float(profile.get('worst_vs_touch_bps')):.1f} bps")
        if profile.get("quote_visibility_summary"):
            lines.append(f"Visibility: {profile.get('quote_visibility_summary')}")
    else:
        lines.append("No scrape profile — address absent from last peer/book snapshot.")

    macro_keys = (
        ("our_inventory", "Inventory"),
        ("aggregate_pressure", "Book pressure"),
        ("observed_spread_pct", "Observed L1 spread"),
        ("book_depth_xrp", "Book depth"),
        ("peer_lane_count", "Peers at touch"),
        ("our_as_reservation", "A-S reservation"),
        ("our_optimal_spread_pct", "A-S optimal spread"),
    )
    macro_lines: List[str] = []
    for key, label in macro_keys:
        if key in macro and macro[key]:
            macro_lines.append(f"  · {label}: {macro[key]}")
    if macro_lines:
        lines.append("")
        lines.append("Regime")
        lines.extend(macro_lines)

    fled = briefing.get("fled_events") or []
    if fled:
        lines.append("")
        lines.append(f"Recent fled-touch events: {len(fled)}")
        for ev in fled[:3]:
            if isinstance(ev, dict):
                lines.append(
                    f"  · was {ev.get('previous_touch_xrp')} XRP, {ev.get('age_s')}s ago"
                )

    if briefing.get("lane_note"):
        lines.append("")
        lines.append(str(briefing.get("lane_note")))

    return "\n".join(lines)


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


# --- P4–P6 shadow E3 peer-lane calibration (HUD-only; does not affect quoting) ---

SHADOW_E3_PORTFOLIO_XRP_EQUIV = 11000.0
SHADOW_E3_XRP_SHARE = 0.55
SHADOW_E3_ASSUMPTION = "11000_xrp_equiv_55_45_balanced"
PEER_LANE_CALIBRATION_PATH = Path("logs/peer_lane_calibration.jsonl")


def compute_shadow_e3_lane_xrp(
    *,
    configured_l1_xrp: float = 11254.0,
    min_order_size_xrp: float = 1.0,
) -> float:
    """Representative L1 touch for E3 thesis: 11k XRP-equiv · 55% XRP · balanced skew."""
    from experimental.ws_feed.dynamic_sizing import compute_pure_l1_sizes

    xrp_balance = SHADOW_E3_PORTFOLIO_XRP_EQUIV * SHADOW_E3_XRP_SHARE
    sizes = compute_pure_l1_sizes(
        xrp_balance=xrp_balance,
        configured_l1_xrp=max(float(configured_l1_xrp), xrp_balance * 0.07),
        min_order_size_xrp=min_order_size_xrp,
        inventory_label="balanced",
        inventory_skew=0.0,
        pressure_size_mult=1.0,
    )
    return round(max(sizes.l1_xrp, sizes.bid_size_xrp, sizes.ask_size_xrp), 2)


def _dedupe_profile_rows(rows: Sequence[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        acct = str(row.get("account_full") or row.get("account") or "").strip()
        if not acct or acct in seen:
            continue
        seen.add(acct)
        out.append(dict(row))
    return out


def shadow_peer_lane_hud_fields(
    runtime: Mapping[str, Any],
    *,
    config: Optional[BotConfig] = None,
) -> Dict[str, Any]:
    """
    Counterfactual peer band at E3 touch size — for Peer Cal tab / calibration JSONL.

    Uses top_peers + top_competitors from the last engine scrape (partial; not full book).
    """
    from experimental.market_analysis.peer_lane import (
        aggregate_peer_pressure,
        select_peer_lane,
    )

    cfg = config or BotConfig.load()
    configured_l1 = float(cfg.order_sizes[0]) if cfg.order_sizes else 150.0
    configured_l1 = max(configured_l1, float(getattr(cfg, "risk_capital_xrp", 11254) or 11254))
    shadow_lane = compute_shadow_e3_lane_xrp(configured_l1_xrp=configured_l1)

    profiles = _dedupe_profile_rows(
        list(runtime.get("top_peers") or []) + list(runtime.get("top_competitors") or [])
    )
    touch_by_account: Dict[str, float] = {}
    profiles_by_acct: Dict[str, Dict[str, Any]] = {}
    for row in profiles:
        acct = str(row.get("account_full") or row.get("account") or "").strip()
        if not acct:
            continue
        try:
            touch = float(row.get("touch_xrp") or 0)
        except (TypeError, ValueError):
            touch = 0.0
        if touch > 0:
            touch_by_account[acct] = max(touch_by_account.get(acct, 0.0), touch)
            profiles_by_acct[acct] = row

    peer_result = select_peer_lane(touch_by_account, shadow_lane)
    shadow_peers: List[Dict[str, Any]] = []
    for acct in peer_result.peer_accounts:
        if acct in profiles_by_acct:
            shadow_peers.append(dict(profiles_by_acct[acct]))
        else:
            touch = float(touch_by_account.get(acct) or 0)
            short = acct[:12] + "..." if len(acct) > 15 else acct
            shadow_peers.append(
                {
                    "account": short,
                    "account_full": acct,
                    "touch_xrp": round(touch, 2),
                    "last_spread": None,
                    "avg_spread": None,
                    "activity": None,
                    "cancels": None,
                    "sides": "—",
                    "domain": "touch-only",
                }
            )

    peer_spreads = [
        float(p.get("last_spread") or 0)
        for p in shadow_peers
        if p.get("last_spread") is not None and float(p.get("last_spread") or 0) > 0
    ]
    try:
        global_spread = float(runtime.get("competitor_observed_spread_pct") or runtime.get("book_spread_pct") or 0)
    except (TypeError, ValueError):
        global_spread = 0.0
    peer_cancel_rate = 0.0
    offers = sum(int(p.get("activity") or 0) for p in shadow_peers)
    cancels = sum(int(p.get("cancels") or 0) for p in shadow_peers)
    if offers > 0:
        peer_cancel_rate = cancels / offers

    shadow_pressure = aggregate_peer_pressure(
        peer_spreads=peer_spreads,
        global_spread=global_spread,
        peer_count=peer_result.peer_lane_count,
        fled_in_lane_count=0,
        cancel_proxy_rate=peer_cancel_rate,
    )

    live_count = int(runtime.get("peer_lane_count") or 0)
    live_lane = float(runtime.get("our_lane_xrp") or 0)
    shadow_g4_active = peer_result.peer_lane_count > 0 and not peer_result.empty
    live_g4_active = live_count > 0 and not bool(runtime.get("peer_lane_empty"))

    return {
        "shadow_e3_assumption": SHADOW_E3_ASSUMPTION,
        "shadow_e3_lane_xrp": shadow_lane,
        "shadow_peer_lane_low_xrp": round(peer_result.peer_low_xrp, 2),
        "shadow_peer_lane_high_xrp": round(peer_result.peer_high_xrp, 2),
        "shadow_peer_lane_count": peer_result.peer_lane_count,
        "shadow_peer_lane_empty": peer_result.empty,
        "shadow_peer_lane_widened": peer_result.widened,
        "shadow_peer_pressure_score": shadow_pressure,
        "shadow_top_peers": shadow_peers[:10],
        "shadow_g4_would_activate": shadow_g4_active,
        "live_vs_shadow_delta_peers": peer_result.peer_lane_count - live_count,
        "shadow_peer_lane_partial": True,
        "shadow_peer_lane_note": (
            "Shadow peers from last scrape top lists only — full touch map at P1 engine pass."
        ),
        "live_g4_active": live_g4_active,
        "live_our_lane_xrp": round(live_lane, 2) if live_lane > 0 else None,
    }


def append_peer_lane_calibration_record(
    fields: Mapping[str, Any],
    *,
    path: Path = PEER_LANE_CALIBRATION_PATH,
) -> None:
    """Append one calibration snapshot (HUD mirror; soak-safe)."""
    import json
    from datetime import datetime, timezone

    row = {
        "kind": "peer_lane_shadow",
        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
        "assumption": fields.get("shadow_e3_assumption"),
        "mid": fields.get("mid") or fields.get("mid_price"),
        "live": {
            "our_lane_xrp": fields.get("live_our_lane_xrp") or fields.get("our_lane_xrp"),
            "peer_lane_count": fields.get("peer_lane_count"),
            "peer_lane_empty": fields.get("peer_lane_empty"),
            "peer_pressure_score": fields.get("peer_pressure_score"),
            "g4_active": fields.get("live_g4_active"),
        },
        "shadow_e3": {
            "lane_xrp": fields.get("shadow_e3_lane_xrp"),
            "peer_lane_count": fields.get("shadow_peer_lane_count"),
            "peer_lane_low_xrp": fields.get("shadow_peer_lane_low_xrp"),
            "peer_lane_high_xrp": fields.get("shadow_peer_lane_high_xrp"),
            "peer_lane_empty": fields.get("shadow_peer_lane_empty"),
            "peer_pressure_score": fields.get("shadow_peer_pressure_score"),
            "g4_would_activate": fields.get("shadow_g4_would_activate"),
        },
        "delta_peers": fields.get("live_vs_shadow_delta_peers"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
