"""XLedgerMate Streamlit control panel — professional trading desk layout."""

from __future__ import annotations

import importlib
import json
import logging
import sys
from datetime import timedelta
from pathlib import Path

# Streamlit adds gui/ to sys.path; ensure repo root wins for config/, utils/, etc.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

import config.settings as settings_module
from config.settings import CONFIG_FILE, BotConfig
from core.market_conditions import assess_market_conditions, compute_book_spread_pct
from utils.profile_recommendation import normalize_profile_recommendation
from core.perception import BUILT_IN_PROFILES
from utils.gui_profile_presets import (
    apply_profile_gui_preset,
    preset_preview_lines,
    verify_profile_on_disk,
)
from core.runtime_state import QuoteIntent
from utils.gui_runtime_sync import patch_runtime_state_file
from utils.quote_validation import QuoteValidationResult, validate_quotes_against_book
from strategy.inventory_balance import assess_rebalance_need
from gui.formatters import (
    balance_value_shares,
    clean_decisions_table,
    fmt_balance_with_share,
    fmt_price as _fmt_price,
    fmt_rlusd_balance as _fmt_rlusd_balance,
    fmt_xrp_balance as _fmt_xrp_balance,
    inventory_ratio,
    portfolio_value_rlusd as _portfolio_value_rlusd,
    session_pnl_from_runtime as _session_pnl_from_runtime,
)
from gui.theme import alert_box, inject_theme, render_header_bar
from gui.engine_control import (
    cancel_offers_on_ledger,
    clear_kill_switch,
    is_engine_running,
    manual_rebalance_check,
    run_single_cycle,
    send_funds,
    disable_rlusd_rippling as run_disable_rlusd_rippling,
    setup_trust_line as run_setup_trust,
    start_engine,
    stop_engine,
)
from utils.auto_profile_state import clear_auto_profile_pending
from utils.profile_request import write_profile_request
from utils.wallet_credentials import secret_matches_address
from utils.xrpl_currency import RLUSD_ISSUER_TESTNET
import utils.operator_activity as _operator_activity

touch_operator_activity = _operator_activity.touch_operator_activity

logger = logging.getLogger(__name__)
RUNTIME_STATE_PATH = Path("logs/runtime_state.json")
LOGO_PATH = Path(__file__).resolve().parent.parent / "Xledermate.jpg"

_CREDENTIALS_FORM = "bot_account_credentials"

PROFILE_LABELS = {
    "safe": "Safe",
    "high_volatility": "High volatility",
    "thin_liquidity": "Thin liquidity",
    "tight_spread": "Tight spread",
    "profit_mode": "Profit mode",
}

PROFILE_SHORT = {
    "safe": "Safe",
    "high_volatility": "High vol",
    "thin_liquidity": "Thin liq",
    "tight_spread": "Tight",
    "profit_mode": "Profit",
}

try:
    _fragment = st.fragment
except AttributeError:  # pragma: no cover - older Streamlit

    def _fragment(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator


def _load_runtime_state() -> dict:
    if not RUNTIME_STATE_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _load_config(*, reload_modules: bool = False) -> BotConfig:
    """Load config.yaml. Avoid reload_modules in Streamlit — reload races with save/rerun."""
    if reload_modules:
        import core.perception as perception_module

        importlib.reload(perception_module)
        importlib.reload(settings_module)
    return settings_module.BotConfig.load()


def _order_size_slider_cap(config: BotConfig, mid: float) -> float:
    """Max L1/L2/L3 size from risk capital (XRP equivalent)."""
    raw = float(config.effective_risk_capital_xrp(mid if mid > 0 else None))
    floor = float(config.min_order_size_xrp or 1.0)
    return max(raw, floor)


def _clamp_order_sizes(config: BotConfig, size_cap: float) -> None:
    cap = max(float(size_cap), 0.0)
    for i in range(len(config.order_sizes)):
        config.order_sizes[i] = max(0.0, min(float(config.order_sizes[i]), cap))


def _ensure_page_config() -> None:
    if st.session_state.get("_xledgermate_page_config"):
        return
    st.set_page_config(
        page_title="XLedgerMate",
        page_icon=str(LOGO_PATH) if LOGO_PATH.is_file() else "chart",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    st.session_state._xledgermate_page_config = True


def _gui_clear_stale_panel_state() -> None:
    """Drop cached st.empty() handles — storing them causes white screens on rerun."""
    for key in (
        "_sidebar_wallet_panel",
        "_dash_live_panel",
        "_hist_live_panel",
        "_dash_config",
        "_hist_config",
    ):
        st.session_state.pop(key, None)


def _execute_gui_save(
    config: BotConfig,
    *,
    engine_running: bool,
    touch_save: bool = True,
    apply_profile: Optional[str] = None,
) -> tuple[bool, str]:
    runtime = _load_runtime_state()
    mid = float(runtime.get("mid_price") or 0) if runtime else 0.0
    _clamp_order_sizes(config, _order_size_slider_cap(config, mid))
    preset_note = ""
    if apply_profile:
        name = str(apply_profile).strip().lower()
        if name not in BUILT_IN_PROFILES:
            name = "safe"
        preset_note = apply_profile_gui_preset(config, name)
        write_profile_request(name)
        clear_auto_profile_pending()
    saved = _persist_config(config)
    _gui_sync_config_display(saved, engine_running=engine_running)
    if touch_save:
        touch_operator_activity("save_config")
    if apply_profile:
        label = PROFILE_LABELS.get(saved.active_profile, saved.active_profile)
        detail = f" ({preset_note})" if preset_note else ""
        if engine_running:
            refresh = max(30, int(saved.order_refresh_time_seconds))
            return (
                True,
                f"Profile **{label}** applied{detail} - GUI updated; engine uses it "
                f"within ~{refresh}s (next cycle).",
            )
        return True, f"Profile **{label}** applied{detail} - GUI updated now (engine stopped)."
    return True, "Config saved - settings are live in the GUI."


def _show_result(ok: bool, msg: str, *, fail: str = "error") -> None:
    """Show success/error without leaking Streamlit's DeltaGenerator return value."""
    if ok:
        st.success(msg)
    elif fail == "warning":
        st.warning(msg)
    else:
        st.error(msg)


def _merge_disk_credentials(config: BotConfig) -> None:
    """Never overwrite saved credentials with stale in-memory values from other tabs."""
    disk = _load_config()
    config.bot_account_address = disk.bot_account_address
    config.bot_secret_key = disk.bot_secret_key


def _save_credentials_to_disk(address: str, secret: str) -> tuple[bool, str]:
    address = (address or "").strip()
    secret = (secret or "").strip()
    match, detail = _credentials_match(address, secret)
    if not match:
        return False, detail
    cfg = _load_config()
    cfg.bot_account_address = address
    cfg.bot_secret_key = secret
    cfg.save()
    verify = _load_config()
    if verify.bot_account_address.strip() != address or verify.bot_secret_key != secret:
        return False, f"Write failed — check permissions on `{CONFIG_FILE}`."
    return True, f"Credentials saved to `{CONFIG_FILE.name}`."


def _persist_config(config: BotConfig) -> BotConfig:
    """Save non-credential settings without clobbering credentials on disk."""
    _merge_disk_credentials(config)
    config.active_profile = (config.active_profile or "safe").strip().lower()
    runtime = _load_runtime_state()
    mid = float(runtime.get("mid_price") or 0) if runtime else 0.0
    config.sync_risk_capital_pair(mid if mid > 0 else None)
    _clamp_order_sizes(config, _order_size_slider_cap(config, mid))
    config.save()
    return _load_config()


def _gui_clear_controls_widget_state() -> None:
    """Streamlit keys cache widget values — clear so the UI reloads from disk after save."""
    for key in (
        "controls_active_profile",
        "risk_capital_unit",
        "controls_base_spread_pct",
        "controls_level_spread_inc",
        "controls_refresh_sec",
        "controls_edge_strictness",
        "controls_dynamic_min_edge",
    ):
        st.session_state.pop(key, None)


def _copy_profile_fields_from_disk(config: BotConfig, disk: BotConfig) -> None:
    """Refresh in-memory config from disk for Controls fields tied to profiles."""
    config.active_profile = disk.active_profile
    config.base_spread = disk.base_spread
    config.level_spread_increment = disk.level_spread_increment
    config.edge_strictness = disk.edge_strictness
    config.book_pressure_sensitivity = disk.book_pressure_sensitivity
    config.dynamic_min_edge_enabled = disk.dynamic_min_edge_enabled
    config.order_refresh_time_seconds = disk.order_refresh_time_seconds


def _sync_controls_widgets_from_config(config: BotConfig) -> None:
    """Push saved config into widget session keys (Streamlit ignores value= when key exists)."""
    st.session_state["controls_active_profile"] = (config.active_profile or "safe").strip().lower()
    st.session_state["controls_base_spread_pct"] = float(config.base_spread) * 100.0
    st.session_state["controls_level_spread_inc"] = float(config.level_spread_increment) * 100.0
    st.session_state["controls_refresh_sec"] = int(config.order_refresh_time_seconds)
    strict = float(config.edge_strictness)
    for option in (0.85, 1.0, 1.15):
        if abs(option - strict) < 0.05:
            st.session_state["controls_edge_strictness"] = option
            break
    else:
        st.session_state["controls_edge_strictness"] = 1.0
    st.session_state["controls_dynamic_min_edge"] = bool(config.dynamic_min_edge_enabled)


def _make_apply_profile_callback(profile_name: Optional[str] = None):
    """Return a no-arg handler for st.button(on_click=...)."""

    def _handler() -> None:
        _apply_profile_callback(profile_name)

    return _handler


def _apply_profile_callback(profile_name: Optional[str] = None) -> None:
    """
    Streamlit on_click handler — runs at the start of the next rerun, before widgets.
    Writes profile presets directly to config.yaml (widgets cannot overwrite first).
    """
    name = (profile_name or st.session_state.get("controls_active_profile") or "safe").strip().lower()
    if name not in BUILT_IN_PROFILES:
        name = "safe"
    try:
        cfg = _load_config()
        note = apply_profile_gui_preset(cfg, name)
        write_profile_request(name)
        clear_auto_profile_pending()
        runtime = _load_runtime_state()
        mid = float(runtime.get("mid_price") or 0) if runtime else 0.0
        _clamp_order_sizes(cfg, _order_size_slider_cap(cfg, mid))
        cfg.save()
        verify = _load_config()
        ok, detail = verify_profile_on_disk(name, verify)
        if not ok:
            st.session_state["_gui_flash_message"] = (
                f"Apply profile failed — {detail}. "
                f"Check that `{CONFIG_FILE}` is writable."
            )
            st.session_state["_gui_flash_kind"] = "error"
        else:
            engine_running = bool(st.session_state.get("_gui_engine_running", False))
            _gui_sync_config_display(verify, engine_running=engine_running)
            label = PROFILE_LABELS.get(name, name)
            st.session_state["_gui_flash_message"] = (
                f"Profile **{label}** saved to config.yaml ({note})."
            )
            st.session_state["_gui_flash_kind"] = "success"
            st.session_state["_sync_controls_from_disk"] = True
    except Exception as exc:
        logging.getLogger(__name__).exception("Apply profile callback failed")
        st.session_state["_gui_flash_message"] = f"Apply profile failed: {exc}"
        st.session_state["_gui_flash_kind"] = "error"
    _gui_clear_controls_widget_state()


def _gui_sync_config_display(config: BotConfig, *, engine_running: bool) -> None:
    """Update runtime_state.json so market/header panels match config.yaml immediately."""
    profile = (config.active_profile or "safe").strip().lower()
    patch_runtime_state_file(
        {
            "active_profile": profile,
            "gui_config_profile": profile,
            "gui_config_synced": True,
        }
    )


def _gui_save_and_refresh(
    config: BotConfig,
    *,
    engine_running: bool,
    touch_save: bool = True,
    success_message: str = "Config saved - settings are live in the GUI.",
    apply_profile: Optional[str] = None,
) -> None:
    try:
        ok, msg = _execute_gui_save(
            config,
            engine_running=engine_running,
            touch_save=touch_save,
            apply_profile=apply_profile,
        )
        if ok and not apply_profile:
            msg = success_message
    except Exception as exc:
        logging.getLogger(__name__).exception("GUI config save failed")
        ok, msg = False, f"Config save failed: {exc}"
    st.session_state["_gui_flash_message"] = msg
    st.session_state["_gui_flash_kind"] = "success" if ok else "error"
    _gui_clear_controls_widget_state()
    _gui_clear_stale_panel_state()
    st.rerun()


def _gui_display_profile(config: BotConfig, runtime: dict, *, engine_running: bool) -> str:
    """Profile shown in the GUI — config on disk when stopped, else latest engine cycle."""
    disk = (_load_config().active_profile or "safe").strip().lower()
    if not engine_running:
        return disk
    engine_name = str(runtime.get("active_profile") or disk).strip().lower()
    return engine_name


def _profile_apply_hint(config: BotConfig, runtime: dict, *, engine_running: bool) -> None:
    """Explain config vs last-cycle profile when they differ."""
    disk = _load_config()
    config_name = (disk.active_profile or "safe").strip().lower()
    engine_name = str(runtime.get("active_profile") or config_name).strip().lower()
    if config_name == engine_name:
        return
    if not engine_running:
        st.caption(
            f"Config profile **{PROFILE_LABELS.get(config_name, config_name)}** — "
            "engine stopped (no cycle until you start)."
        )
        return
    refresh = max(30, int(config.order_refresh_time_seconds))
    st.info(
        f"**Config profile:** {PROFILE_LABELS.get(config_name, config_name)} · "
        f"**Last engine cycle:** {PROFILE_LABELS.get(engine_name, engine_name)} · "
        f"Engine catches up on the **next cycle** (within ~{refresh}s)."
    )


def _credentials_match(address: str, secret: str) -> tuple[bool, str]:
    return secret_matches_address(secret, address)


def _render_brand_logo(*, sidebar: bool = False) -> None:
    if not LOGO_PATH.is_file():
        if sidebar:
            st.markdown("### XLedgerMate")
        else:
            st.title("XLedgerMate")
        return
    if sidebar:
        st.image(str(LOGO_PATH), use_container_width=True)
    else:
        st.image(str(LOGO_PATH), width=480)


_SESSION_MTM_HELP = (
    "Mark-to-market since this engine run — matches cycle log portfolio "
    "(includes mid price moves on RLUSD)."
)
_SESSION_BALANCE_PNL_HELP = (
    "Wallet balance change only, both legs at current mid — fees and fills, "
    "not mid revaluation."
)
_SESSION_PNL_NOTE = "Since this engine run only — not Xaman all-time."
_PORTFOLIO_RLUSD_HELP = (
    "Total bot wallet in RLUSD: RLUSD balance plus XRP valued at the engine's book mid. "
    "Xaman may differ slightly (their price feed vs DEX mid)."
)


def _render_sidebar_wallet(runtime: dict) -> None:
    """Compact sidebar: one clear portfolio total + balance line."""
    port_rlusd = _portfolio_value_rlusd(runtime)
    mid = runtime.get("mid_price")

    if port_rlusd is not None:
        st.metric(
            "Portfolio",
            f"{port_rlusd:,.2f} RLUSD",
            help=_PORTFOLIO_RLUSD_HELP,
        )
        if mid is not None:
            st.caption(f"Book mid **{_fmt_price(mid)}** RLUSD/XRP")
    else:
        st.caption("Portfolio — waiting for engine balances…")

    xrp = runtime.get("balance_xrp")
    rlusd = runtime.get("balance_rlusd")
    if xrp is not None or rlusd is not None:
        parts = []
        if xrp is not None:
            parts.append(f"{_fmt_xrp_balance(xrp)} XRP")
        if rlusd is not None:
            parts.append(f"{_fmt_rlusd_balance(rlusd)} RLUSD")
        st.caption(" · ".join(parts))


def _runtime_updated_age_seconds(runtime: dict) -> Optional[float]:
    raw = runtime.get("updated_utc")
    if not raw:
        return None
    try:
        ts = pd.Timestamp(raw)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return (pd.Timestamp.now(tz="UTC") - ts).total_seconds()
    except (TypeError, ValueError):
        return None


def _runtime_stale_threshold_seconds(
    config: BotConfig, *, engine_running: bool
) -> float:
    """How old runtime_state may be before we warn — must exceed cycle sleep + RPC work."""
    if not engine_running:
        return 90.0
    refresh = max(30, int(config.order_refresh_time_seconds))
    return float(refresh + 45)


def _load_portfolio_snapshots(limit: int = 180) -> pd.DataFrame:
    path = Path("logs/portfolio_snapshots.csv")
    if not path.is_file():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError, ValueError):
        return pd.DataFrame()
    if df.empty or "portfolio_xrp_equiv" not in df.columns:
        return df
    return df.tail(limit)


def _quote_table(intents: List[dict]) -> pd.DataFrame:
    rows: Dict[int, dict] = {}
    for q in intents:
        level = int(q.get("level", 0))
        row = rows.setdefault(level, {"Level": f"L{level}"})
        side = str(q.get("side", "")).lower()
        price = float(q.get("price", 0))
        size = float(q.get("size_xrp", q.get("size", 0)))
        if side == "bid":
            row["Bid price"] = f"{price:.6f}"
            row["Bid size (XRP)"] = f"{size:.2f}"
        elif side == "ask":
            row["Ask price"] = f"{price:.6f}"
            row["Ask size (XRP)"] = f"{size:.2f}"
    if not rows:
        return pd.DataFrame(columns=["Level", "Bid price", "Bid size (XRP)", "Ask price", "Ask size (XRP)"])
    return pd.DataFrame([rows[k] for k in sorted(rows.keys())])


def _open_offers_table(offers: List[dict]) -> pd.DataFrame:
    columns = ["Side", "Price (RLUSD/XRP)", "Size (XRP)", "Offer seq"]
    if not offers:
        return pd.DataFrame(columns=columns)
    rows = []
    for offer in offers:
        rows.append(
            {
                "Side": str(offer.get("side", "")).upper(),
                "Price (RLUSD/XRP)": f"{float(offer.get('price', 0)):.6f}",
                "Size (XRP)": f"{float(offer.get('size_xrp', 0)):.2f}",
                "Offer seq": int(offer.get("sequence", 0)),
            }
        )
    return pd.DataFrame(rows)


def _show_dataframe(
    df: pd.DataFrame,
    *,
    height: int | None = None,
    alignment: str = "left",
) -> None:
    """Display a dataframe with consistent cell alignment (not right-justified numbers)."""
    kwargs: dict[str, Any] = {"use_container_width": True, "hide_index": True}
    if height is not None:
        kwargs["height"] = height
    if not df.empty and hasattr(st, "column_config"):
        kwargs["column_config"] = {
            str(col): st.column_config.Column(str(col), alignment=alignment)
            for col in df.columns
        }
    st.dataframe(df, **kwargs)


def _quote_intents_from_runtime(runtime: dict) -> List[QuoteIntent]:
    intents: List[QuoteIntent] = []
    for item in runtime.get("quote_intents") or []:
        if not isinstance(item, dict):
            continue
        intents.append(
            QuoteIntent(
                level=int(item.get("level", 0)),
                side=str(item.get("side", "")),
                price=float(item.get("price", 0)),
                size_xrp=float(item.get("size_xrp", 0)),
            )
        )
    return intents


def _engine_persisted_spread_check(runtime: dict) -> bool:
    return bool(runtime.get("spread_validation_summary")) or bool(
        runtime.get("spread_validation_lines")
    )


def _spread_validation_from_runtime(
    runtime: dict, config: BotConfig
) -> Optional[QuoteValidationResult]:
    """Prefer engine-persisted spread check; recompute only when missing."""
    summary = str(runtime.get("spread_validation_summary") or "").strip()
    if summary and int(runtime.get("cycle_count", 0)) > 0:
        return QuoteValidationResult(
            ok=bool(runtime.get("spread_validation_ok")),
            summary=summary,
            errors=list(runtime.get("spread_validation_errors") or []),
            lines=list(runtime.get("spread_validation_lines") or []),
        )
    return _compute_spread_validation(runtime, config)


def _compute_spread_validation(
    runtime: dict, config: BotConfig
) -> Optional[QuoteValidationResult]:
    """Validate planned quotes vs book from runtime snapshot (works even if engine is stale)."""
    mid = runtime.get("mid_price")
    if mid is None:
        return None
    return validate_quotes_against_book(
        _quote_intents_from_runtime(runtime),
        mid_price=float(mid),
        best_bid=runtime.get("best_bid_rlusd_per_xrp"),
        best_ask=runtime.get("best_ask_rlusd_per_xrp"),
        max_half_spread_from_mid_pct=float(
            getattr(config, "max_half_spread_from_mid_pct", 1.0)
        ),
        max_worse_than_touch_pct=float(
            getattr(config, "max_quote_worse_than_touch_pct", 0.50)
        ),
        max_improve_touch_pct=float(getattr(config, "max_quote_improve_touch_pct", 0.15)),
        require_intents_when_trading=bool(runtime.get("trading_enabled", True)),
    )


def _render_spread_check_panel(runtime: dict, config: BotConfig, *, compact: bool = False) -> None:
    cycles = int(runtime.get("cycle_count", 0))
    if cycles == 0 and not runtime.get("quote_intents"):
        st.caption("Run the engine to compare planned quotes to the live book.")
        return

    if not compact and cycles > 0 and not _engine_persisted_spread_check(runtime):
        st.warning(
            "Engine has not written spread-check results — **Stop Bot → Start Bot** after updates."
        )

    result = _spread_validation_from_runtime(runtime, config)
    if result is None:
        st.caption("Waiting for mid price and book from the next cycle…")
        return

    if result.ok:
        st.success(result.summary if not compact else "Spread check OK")
    else:
        st.error(result.summary)
    if not compact:
        for err in result.errors:
            st.error(err)
        for warn in result.warnings:
            st.warning(warn)
        if result.lines:
            _show_dataframe(pd.DataFrame(result.lines), height=220)


def _render_alert_strip(config: BotConfig, runtime: dict) -> None:
    """Critical alerts only — keep the main view calm."""
    runtime = _load_runtime_state() or runtime
    dry = bool(runtime.get("dry_run", config.dry_run))

    if runtime.get("kill_switch_active"):
        st.markdown(
            alert_box(
                f"Kill switch active — {runtime.get('kill_switch_reason', 'trading halted')}",
                "danger",
            ),
            unsafe_allow_html=True,
        )

    if not config.bot_account_address:
        st.markdown(
            alert_box("Set Bot Account credentials under <b>Advanced → Bot account</b>.", "warn"),
            unsafe_allow_html=True,
        )

    if not dry and not config.testnet:
        st.markdown(
            alert_box(
                "<b>Mainnet live</b> — real orders on the ledger. Spread check must pass each cycle.",
                "danger",
            ),
            unsafe_allow_html=True,
        )
    elif dry and not config.testnet:
        st.markdown(
            alert_box("Dry-run — quotes are planned only; nothing submits to mainnet.", "info"),
            unsafe_allow_html=True,
        )

    if not dry and config.testnet:
        st.markdown(
            alert_box("Live on testnet — real testnet orders (play money).", "warn"),
            unsafe_allow_html=True,
        )

    if not config.testnet and runtime.get("cycle_count", 0) > 0:
        spread = _spread_validation_from_runtime(runtime, config)
        if spread and not spread.ok:
            err = spread.errors[0] if spread.errors else spread.summary
            st.markdown(
                alert_box(f"<b>Spread check failed</b> — live orders blocked. {err}", "danger"),
                unsafe_allow_html=True,
            )


def _resolve_market_assessment(config: BotConfig, runtime: dict) -> dict:
    """Compute profile recommendation from latest book metrics (not stale runtime snapshot)."""
    if not runtime:
        return {}
    bid = runtime.get("best_bid_rlusd_per_xrp")
    ask = runtime.get("best_ask_rlusd_per_xrp")
    spread = float(runtime.get("book_spread_pct", 0)) or compute_book_spread_pct(bid, ask)
    assessment = assess_market_conditions(
        volatility_pct=float(runtime.get("volatility_pct", 0)),
        liquidity_score=float(runtime.get("liquidity_score", 0)),
        book_spread_pct=spread,
        active_profile=config.active_profile,
        previous_condition=runtime.get("market_condition"),
        previous_liquidity_level=runtime.get("liquidity_level"),
    )
    rec, reason = normalize_profile_recommendation(
        assessment.recommended_profile,
        assessment.recommendation_reason,
    )
    return {
        "recommended_profile": rec,
        "recommendation_reason": reason,
        "market_condition_label": assessment.condition_label,
    }


def _render_market_suggestion(config: BotConfig, runtime: dict, *, engine_running: bool) -> None:
    """Compact profile suggestion for Dashboard — not a full market panel."""
    if not runtime:
        return

    assessment = _resolve_market_assessment(config, runtime)
    rec = assessment.get("recommended_profile", "")
    rec_label = PROFILE_LABELS.get(str(rec), str(rec)) if rec else "—"
    active = _gui_display_profile(config, runtime, engine_running=engine_running)
    active_label = PROFILE_LABELS.get(str(active), str(active))
    reason = assessment.get("recommendation_reason", "")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        health = float(runtime.get("market_health_score", 0))
        cond_label = runtime.get("market_condition_label", "Neutral")
        vol = runtime.get("volatility_level", "—")
        liq = float(runtime.get("liquidity_score", 0))
        st.markdown(
            f"**Market:** {cond_label} · Health **{health:.0f}/100** · "
            f"Vol {vol} · Liq {liq:.2f} · Spread {runtime.get('book_spread_status', '—')}"
        )
        if rec and str(rec) == str(active):
            st.caption(f"Suggested profile **{rec_label}** — matches active. {reason}")
        elif rec:
            st.caption(f"Suggested **{rec_label}** (active: **{active_label}**). {reason}")
        else:
            st.caption("Profile suggestion appears after the engine runs.")
    with col_b:
        if rec and str(rec) != str(active):
            st.button(
                f"Apply {PROFILE_SHORT.get(str(rec), rec_label)}",
                key="apply_recommended_profile",
                on_click=_make_apply_profile_callback(str(rec)),
                use_container_width=True,
            )


def _render_session_statistics(
    runtime: dict,
    config: BotConfig,
    *,
    engine_running: bool,
    show_portfolio_chart: bool = False,
) -> None:
    """Live session metrics — same numbers as cycle log portfolio / engine state."""
    pnl_mtm, pnl_balance = _session_pnl_from_runtime(runtime)
    port = float(runtime.get("portfolio_value_xrp", 0))
    vol = float(runtime.get("volatility_pct", 0))
    liq = float(runtime.get("liquidity_score", 0))
    dd = float(runtime.get("drawdown_pct", 0))

    st.markdown("#### Session performance")
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    s1.metric(
        "Portfolio (XRP equiv.)",
        f"{port:.4f}",
        delta=f"{pnl_mtm:+.4f} MTM",
        help="Total book at mid — matches engine cycle log.",
    )
    s2.metric("Session MTM P&L", f"{pnl_mtm:+.4f}", help=_SESSION_MTM_HELP)
    s3.metric("Balance Δ P&L", f"{pnl_balance:+.4f}", help=_SESSION_BALANCE_PNL_HELP)
    s4.metric("Drawdown %", f"{dd:.3f}")
    s5.metric("Volatility %", f"{vol:.4f}")
    s6.metric("Liquidity score", f"{liq:.4f}")

    baseline_port = runtime.get("session_baseline_portfolio_xrp")
    if baseline_port is not None:
        st.caption(
            f"Session start portfolio: **{float(baseline_port):.4f}** XRP equiv. · "
            f"start mid **{runtime.get('session_baseline_mid', 'n/a')}** · "
            f"cycle **{int(runtime.get('cycle_count', 0))}**"
        )
    age = _runtime_updated_age_seconds(runtime)
    updated = runtime.get("updated_utc", "n/a")
    stale_after = _runtime_stale_threshold_seconds(config, engine_running=engine_running)
    if age is not None and age > stale_after:
        st.warning(f"Runtime state is **{int(age)}s** old ({updated}). Is the engine running?")
    else:
        st.caption(f"Engine state updated: **{updated}**")

    if vol == 0.0 and int(runtime.get("cycle_count", 0)) < 5:
        st.caption("Volatility stays 0% until the engine has enough mid samples in a cycle window.")

    if show_portfolio_chart:
        snaps = _load_portfolio_snapshots()
        if len(snaps) >= 2 and "timestamp_utc" in snaps.columns:
            chart_df = snaps.copy()
            chart_df["time"] = pd.to_datetime(chart_df["timestamp_utc"], utc=True)
            chart_df = chart_df.set_index("time")[["portfolio_xrp_equiv"]].apply(
                pd.to_numeric, errors="coerce"
            )
            chart_df = chart_df.dropna()
            if len(chart_df) >= 2:
                st.markdown("#### Portfolio value (running)")
                st.line_chart(chart_df, height=200)
                st.caption("From `logs/portfolio_snapshots.csv` — one point per engine cycle.")


def _update_live_dashboard(config: BotConfig, runtime: Optional[dict] = None) -> None:
    """Dashboard — at-a-glance overview for long monitoring sessions."""
    if runtime is None:
        runtime = _load_runtime_state()
    engine_running = is_engine_running()

    if not runtime:
        st.info("Start the bot or run one cycle to populate live data.")
        return

    _profile_apply_hint(config, runtime, engine_running=engine_running)

    pnl_mtm, pnl_balance = _session_pnl_from_runtime(runtime)
    port = float(runtime.get("portfolio_value_xrp", 0))
    dd = float(runtime.get("drawdown_pct", 0))
    dry = runtime.get("dry_run", config.dry_run)

    # ── Hero metrics ──
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Portfolio", f"{port:.4f} XRP", help="Total wallet at book mid.")
    m2.metric("Session P&L", f"{pnl_mtm:+.4f}", help=_SESSION_MTM_HELP)
    m3.metric("Balance Δ P&L", f"{pnl_balance:+.4f}", help=_SESSION_BALANCE_PNL_HELP)
    m4.metric("Drawdown", f"{dd:.3f}%")

    # ── Balances & activity ──
    b1, b2, b3 = st.columns(3)
    xrp = runtime.get("balance_xrp")
    rlusd = runtime.get("balance_rlusd")
    mid = float(runtime.get("mid_price") or 0)
    xrp_share, rlusd_share = balance_value_shares(runtime, mid=mid)
    b1.metric(
        "XRP balance",
        fmt_balance_with_share(
            _fmt_xrp_balance(xrp) if xrp is not None else "—",
            xrp_share,
        ),
        help="XRP held · share of total portfolio value at book mid.",
    )
    b2.metric(
        "RLUSD balance",
        fmt_balance_with_share(
            _fmt_rlusd_balance(rlusd) if rlusd is not None else "—",
            rlusd_share,
        ),
        help="RLUSD held · share of total portfolio value at book mid.",
    )
    b3.metric(
        "Open offers",
        int(runtime.get("open_offers_count", 0)),
        delta=f"cycle {int(runtime.get('cycle_count', 0))}",
    )

    st.caption(
        f"{'DRY-RUN' if dry else 'LIVE'} · "
        f"Placed last cycle: {int(runtime.get('offers_placed_last_cycle', 0))} · "
        f"{runtime.get('last_execution_summary', '') or 'Waiting for cycle…'}"
    )

    age = _runtime_updated_age_seconds(runtime)
    stale_after = _runtime_stale_threshold_seconds(config, engine_running=engine_running)
    if age is not None and age > stale_after:
        st.warning(f"Data is **{int(age)}s** old — check the engine.")
    else:
        st.caption(f"Updated {runtime.get('updated_utc', 'n/a')}")

    st.divider()
    _render_market_suggestion(config, runtime, engine_running=engine_running)

    # ── Recent decisions (clean) ──
    st.markdown("#### Recent activity")
    decisions_df = clean_decisions_table(runtime, limit=10)
    if not decisions_df.empty:
        _show_dataframe(decisions_df, height=240)
    else:
        st.caption("Decision log fills in after the first engine cycle.")

    if runtime.get("quote_decision_summary"):
        with st.expander("Why these quotes?", expanded=False):
            st.caption(runtime.get("quote_decision_summary"))
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Market edge", "OK" if runtime.get("market_edge_met", True) else "THIN")
            c2.metric("Fill quality", f"{float(runtime.get('fill_quality_score', 100)):.0f}")
            c3.metric("Pause bids", "YES" if runtime.get("pause_bids") else "no")
            c4.metric("Pause asks", "YES" if runtime.get("pause_asks") else "no")

    with st.expander("Quote ladder (this cycle)", expanded=False):
        intents = runtime.get("quote_intents", [])
        if intents:
            _show_dataframe(_quote_table(intents), height=180)
        else:
            st.caption("No quote intents yet.")


@_fragment(run_every=timedelta(seconds=5))
def _sidebar_wallet_live_fragment() -> None:
    if not st.session_state.get("auto_refresh", True):
        return
    runtime = _load_runtime_state()
    if runtime:
        _render_sidebar_wallet(runtime)


@_fragment(run_every=timedelta(seconds=5))
def _dashboard_live_fragment() -> None:
    if not st.session_state.get("auto_refresh", True):
        return
    runtime = _load_runtime_state()
    if not runtime:
        return
    try:
        cfg = _load_config()
    except TypeError:
        return
    _update_live_dashboard(cfg, runtime)


@_fragment(run_every=timedelta(seconds=5))
def _logs_live_fragment() -> None:
    if not st.session_state.get("auto_refresh", True):
        return
    runtime = _load_runtime_state()
    if not runtime:
        return
    try:
        cfg = _load_config()
    except TypeError:
        return
    _paint_logs_content(runtime, cfg)


@_fragment(run_every=timedelta(seconds=5))
def _inventory_live_fragment() -> None:
    if not st.session_state.get("auto_refresh", True):
        return
    runtime = _load_runtime_state()
    if not runtime:
        return
    try:
        cfg = _load_config()
    except TypeError:
        return
    _render_inventory_tab(cfg, runtime)


def _render_sidebar_commands(config: BotConfig) -> None:
    """Always-visible engine controls in the sidebar."""
    engine_running = is_engine_running()
    if st.button("▶ Start Bot", type="primary", disabled=engine_running, use_container_width=True):
        disk = _load_config()
        if disk.bot_account_address.strip() and _credentials_match(
            disk.bot_account_address, disk.bot_secret_key
        )[0]:
            _persist_config(config)
            ok, msg = start_engine(force_restart=True)
            _show_result(ok, msg, fail="warning")
            st.rerun()
        else:
            st.error("Save credentials under Advanced first.")
    if st.button("■ Stop Bot", disabled=not engine_running, use_container_width=True):
        ok, msg = stop_engine()
        _show_result(ok, msg, fail="warning")
        st.rerun()
    if st.button("Run One Cycle", use_container_width=True):
        with st.spinner("Running cycle..."):
            ok, msg = run_single_cycle()
        _show_result(ok, msg)


def _render_bot_controls(config: BotConfig) -> None:
    """Legacy hook — controls live in sidebar."""
    _render_sidebar_commands(config)


def _show_rebalance_status(
    config: BotConfig, runtime: dict, *, mid: float
) -> None:
    """Inventory mix from runtime snapshot or quick local estimate."""
    xrp = runtime.get("balance_xrp")
    rlusd = runtime.get("balance_rlusd")
    if xrp is None and rlusd is None:
        st.caption("Run **Check rebalance now** to load balances from the ledger.")
        return

    xrp_f = float(xrp or 0)
    rlusd_f = float(rlusd or 0)
    use_mid = mid if mid > 0 else float(runtime.get("mid_price") or 0)
    total = xrp_f + (rlusd_f / use_mid if use_mid > 0 else 0)
    ratio = (xrp_f / total) if total > 0 else 0.0
    target = float(config.inventory_target_xrp_ratio)
    st.caption(
        f"Current **{ratio:.0%} XRP** · target **{target:.0%} XRP** "
        f"({xrp_f:.2f} XRP, {rlusd_f:.2f} RLUSD)"
    )

    if use_mid > 0:
        spendable = max(0.0, xrp_f - float(config.xrp_reserve))
        advice = assess_rebalance_need(
            xrp_balance=xrp_f,
            rlusd_balance=rlusd_f,
            mid_price=use_mid,
            target_xrp_ratio=target,
            spendable_xrp=spendable,
            xrp_reserve=float(config.xrp_reserve),
            min_order_xrp=float(config.min_order_size_xrp),
            fund_with_xrp_only=bool(config.fund_with_xrp_only),
        )
        if runtime.get("rebalance_summary"):
            st.info(runtime["rebalance_summary"])
        elif advice.action != "hold":
            st.info(advice.summary)


def _render_controls_tab(
    config: BotConfig, *, engine_running: bool, runtime: Optional[dict] = None
) -> None:
    """Settings grouped in expanders — less overwhelming than one long scroll."""
    runtime = runtime or {}
    mid = float(runtime.get("mid_price") or 0)
    size_cap = _order_size_slider_cap(config, mid)
    _clamp_order_sizes(config, size_cap)
    disk_cfg = _load_config()

    if st.session_state.pop("_sync_controls_from_disk", False):
        _copy_profile_fields_from_disk(config, disk_cfg)
        _sync_controls_widgets_from_config(disk_cfg)

    st.caption(
        f"Saved on disk: **{PROFILE_LABELS.get(disk_cfg.active_profile, disk_cfg.active_profile)}** · "
        f"base **{disk_cfg.base_spread * 100:.2f}%** · edge **{disk_cfg.edge_strictness:.2f}**"
    )

    with st.expander("Profile & spreads", expanded=True):
        profile_names = list(BUILT_IN_PROFILES.keys())
        disk_profile = (disk_cfg.active_profile or "safe").strip().lower()
        if "controls_active_profile" not in st.session_state:
            st.session_state["controls_active_profile"] = disk_profile
        picked = st.selectbox(
            "Active profile",
            profile_names,
            format_func=lambda key: PROFILE_LABELS.get(key, key),
            key="controls_active_profile",
        )
        config.active_profile = picked
        preview = preset_preview_lines(picked)
        if preview:
            st.caption(preview)
        if picked != disk_profile:
            st.info("Profile changed — click **Apply profile now** to write presets to disk.")
        st.button(
            "Apply profile now",
            key="apply_controls_profile",
            use_container_width=True,
            type="primary",
            on_click=_make_apply_profile_callback(),
        )

        s1, s2, s3 = st.columns(3)
        with s1:
            config.base_spread = (
                st.number_input(
                    "Base spread (%)",
                    value=config.base_spread * 100,
                    step=0.01,
                    format="%.2f",
                    key="controls_base_spread_pct",
                )
                / 100
            )
            config.level_spread_increment = (
                st.number_input(
                    "Level spread step (%)",
                    value=config.level_spread_increment * 100,
                    step=0.01,
                    format="%.2f",
                    key="controls_level_spread_inc",
                )
                / 100
            )
        with s2:
            config.order_refresh_time_seconds = st.number_input(
                "Refresh interval (sec)",
                value=int(config.order_refresh_time_seconds),
                step=10,
                min_value=15,
                key="controls_refresh_sec",
            )
        with s3:
            _edge_strictness_labels = {0.85: "Low", 1.0: "Normal", 1.15: "Strict"}
            _current = float(getattr(config, "edge_strictness", 1.0))
            _key = min(_edge_strictness_labels.keys(), key=lambda k: abs(k - _current))
            _opts = list(_edge_strictness_labels.keys())
            config.edge_strictness = float(
                st.selectbox(
                    "Edge strictness",
                    options=_opts,
                    format_func=lambda k: f"{_edge_strictness_labels[k]} ({k}×)",
                    index=_opts.index(_key),
                    key="controls_edge_strictness",
                )
            )

    with st.expander("Order sizes (XRP)", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            config.order_sizes[0] = st.slider("Level 1", 0.0, size_cap, float(config.order_sizes[0]), 10.0)
        with c2:
            config.order_sizes[1] = st.slider("Level 2", 0.0, size_cap, float(config.order_sizes[1]), 25.0)
        with c3:
            config.order_sizes[2] = st.slider("Level 3", 0.0, size_cap, float(config.order_sizes[2]), 50.0)

    with st.expander("Risk capital & drawdown", expanded=False):
        r1, r2 = st.columns(2)
        with r1:
            unit_options = ["xrp", "rlusd"]
            unit_index = 1 if config.risk_capital_unit_normalized() == "rlusd" else 0
            picked_unit = st.radio(
                "Risk capital unit",
                unit_options,
                index=unit_index,
                format_func=lambda u: "XRP" if u == "xrp" else "RLUSD",
                horizontal=True,
                key="risk_capital_unit",
            )
            config.risk_capital_unit = picked_unit
            if picked_unit == "rlusd":
                default_rlusd = float(getattr(config, "risk_capital_rlusd", 0) or 0)
                if default_rlusd <= 0 and mid > 0:
                    default_rlusd = float(config.risk_capital_xrp) * mid
                config.risk_capital_rlusd = st.number_input(
                    "Risk capital (RLUSD)", min_value=0.0, value=default_rlusd, step=50.0
                )
                if mid > 0:
                    config.risk_capital_xrp = float(config.risk_capital_rlusd) / mid
            else:
                config.risk_capital_xrp = st.number_input(
                    "Risk capital (XRP)",
                    min_value=0.0,
                    value=float(config.risk_capital_xrp),
                    step=10.0,
                )
                if mid > 0:
                    config.risk_capital_rlusd = float(config.risk_capital_xrp) * mid
        with r2:
            config.max_daily_drawdown_percent = st.slider(
                "Max daily drawdown (%)",
                2.0,
                25.0,
                min(max(float(config.max_daily_drawdown_percent), 2.0), 25.0),
                0.5,
            )
            config.fund_with_xrp_only = st.toggle(
                "Fund with XRP only",
                value=getattr(config, "fund_with_xrp_only", True),
            )

    with st.expander("Execution mode", expanded=False):
        e1, e2 = st.columns(2)
        with e1:
            config.dry_run = st.toggle("Dry run (no ledger orders)", value=config.dry_run)
        with e2:
            config.trading_enabled = st.toggle("Trading enabled", value=config.trading_enabled)

    with st.expander("Defensive quoting & auto-profile", expanded=False):
        config.dynamic_min_edge_enabled = st.toggle(
            "Dynamic min edge from live book",
            value=bool(getattr(config, "dynamic_min_edge_enabled", False)),
            key="controls_dynamic_min_edge",
        )
        config.auto_profile_switching = st.toggle(
            "Auto profile switching",
            value=getattr(config, "auto_profile_switching", False),
        )
        a1, a2 = st.columns(2)
        with a1:
            config.auto_profile_inactivity_minutes = st.number_input(
                "Auto-switch after idle (min)",
                value=int(getattr(config, "auto_profile_inactivity_minutes", 30)),
                step=15,
                min_value=30,
            )
            config.auto_profile_confirm_cycles = st.number_input(
                "Confirm cycles",
                value=int(getattr(config, "auto_profile_confirm_cycles", 3)),
                min_value=1,
                max_value=10,
            )
        with a2:
            config.auto_profile_switch_cooldown_minutes = st.number_input(
                "Cooldown (min)",
                value=int(getattr(config, "auto_profile_switch_cooldown_minutes", 45)),
                step=5,
                min_value=0,
            )

    with st.expander("Live spread guard", expanded=False):
        g1, g2, g3 = st.columns(3)
        with g1:
            config.max_quote_worse_than_touch_pct = st.number_input(
                "Max worse than touch (%)",
                value=float(getattr(config, "max_quote_worse_than_touch_pct", 0.50)),
                min_value=0.05,
                max_value=5.0,
                step=0.05,
            )
        with g2:
            config.max_half_spread_from_mid_pct = st.number_input(
                "Max distance from mid (%)",
                value=float(getattr(config, "max_half_spread_from_mid_pct", 1.0)),
                min_value=0.05,
                max_value=5.0,
                step=0.05,
            )
        with g3:
            config.require_spread_validation_for_live = st.toggle(
                "Block live if check fails",
                value=getattr(config, "require_spread_validation_for_live", True),
            )

    if st.button("Save settings now", type="primary", key="save_controls_now", use_container_width=True):
        _gui_save_and_refresh(
            config,
            engine_running=engine_running,
            touch_save=True,
            success_message="Settings saved.",
        )


def _render_inventory_tab(config: BotConfig, runtime: dict) -> None:
    """Positions, inventory mix, open offers, and quote ladder."""
    if not runtime:
        st.info("Start the bot to load inventory data.")
        return

    mid = float(runtime.get("mid_price") or 0)
    target = float(config.inventory_target_xrp_ratio)
    ratio = inventory_ratio(runtime, mid=mid)

    i1, i2, i3, i4 = st.columns(4)
    i1.metric("XRP", _fmt_xrp_balance(runtime.get("balance_xrp")))
    i2.metric("RLUSD", _fmt_rlusd_balance(runtime.get("balance_rlusd")))
    if ratio is not None:
        i3.metric("XRP share", f"{ratio:.0%}", delta=f"target {target:.0%}")
    else:
        i3.metric("XRP share", "—")
    i4.metric("Inventory", runtime.get("inventory_label", "—"))

    _show_rebalance_status(config, runtime, mid=mid)
    if st.button("Check rebalance now", key="inv_rebalance_check", use_container_width=True):
        try:
            with st.spinner("Reading ledger..."):
                ok, msg = manual_rebalance_check()
            st.session_state["_gui_flash_message"] = msg or ("Done." if ok else "Failed.")
            st.session_state["_gui_flash_kind"] = "success" if ok else "warning"
        except Exception as exc:
            st.session_state["_gui_flash_message"] = str(exc)
            st.session_state["_gui_flash_kind"] = "warning"
        st.rerun()

    st.divider()
    st.markdown("#### Live book")
    p1, p2, p3 = st.columns(3)
    p1.metric("Best bid", _fmt_price(runtime.get("best_bid_rlusd_per_xrp"), 6))
    p2.metric("Mid", _fmt_price(runtime.get("mid_price"), 6))
    p3.metric("Best ask", _fmt_price(runtime.get("best_ask_rlusd_per_xrp"), 6))

    st.markdown("#### Open offers")
    ledger_offers = runtime.get("open_offers") or []
    if ledger_offers:
        _show_dataframe(_open_offers_table(ledger_offers), height=200)
    elif int(runtime.get("open_offers_count", 0)) > 0:
        st.caption(f"{runtime.get('open_offers_count')} offer(s) on ledger — detail on next cycle.")
    else:
        st.caption("No open offers.")

    st.markdown("#### Quote ladder (planned)")
    intents = runtime.get("quote_intents", [])
    if intents:
        _show_dataframe(_quote_table(intents), height=200)
    else:
        st.caption("No quote intents this cycle.")


def _render_account_tab(config: BotConfig, runtime: dict) -> None:
    disk = _load_config()
    config.bot_account_address = disk.bot_account_address
    config.bot_secret_key = disk.bot_secret_key

    st.markdown("### Bot account credentials")
    st.caption(
        "Family seed (`s...`, 29 chars) or Xaman encoded secret (`sn...`). "
        "Dedicated Bot Account only — never your main wallet."
    )

    disk_match, disk_detail = _credentials_match(disk.bot_account_address, disk.bot_secret_key)
    if disk.bot_account_address.strip():
        if disk_match:
            st.success(f"**On disk:** `{disk.bot_account_address}` — address and secret match.")
        else:
            st.error(f"**On disk:** `{disk.bot_account_address}` — {disk_detail}")
    else:
        st.warning("No bot address saved yet.")

    with st.form(_CREDENTIALS_FORM, clear_on_submit=False):
        address = st.text_input(
            "Bot account address (r...)",
            value=disk.bot_account_address,
            placeholder="rYourBotAccountAddress...",
        )
        secret = st.text_input(
            "Bot secret (never commit)",
            value=disk.bot_secret_key,
            type="password",
        )
        save_creds = st.form_submit_button("Save credentials", type="primary")

    if save_creds:
        ok, msg = _save_credentials_to_disk(address, secret)
        if ok:
            touch_operator_activity("save_credentials")
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    st.markdown("### Fund the bot")
    st.info(
        "Send **XRP** to the address below (testnet faucet or transfer). "
        "Use [tryrlusd.com](https://tryrlusd.com) with the **same** address for test RLUSD."
    )
    if config.bot_account_address:
        st.code(config.bot_account_address)
        f1, f2, f3, f4 = st.columns(4)
        if f2.button("Setup RLUSD trust line"):
            disk = _load_config()
            if not disk.bot_secret_key.strip():
                st.error("Click **Save credentials** first.")
            elif not _credentials_match(disk.bot_account_address, disk.bot_secret_key)[0]:
                st.error("On-disk credentials do not match — use **Save credentials**.")
            else:
                with st.spinner("Submitting TrustSet..."):
                    ok, msg = run_setup_trust()
                _show_result(ok, msg)
        if f3.button("Disable RLUSD rippling"):
            disk = _load_config()
            if not disk.bot_secret_key.strip():
                st.error("Click **Save credentials** first.")
            elif not _credentials_match(disk.bot_account_address, disk.bot_secret_key)[0]:
                st.error("On-disk credentials do not match — use **Save credentials**.")
            else:
                with st.spinner("Setting No Ripple on trust line..."):
                    ok, msg = run_disable_rlusd_rippling()
                _show_result(ok, msg)
        f4.link_button("Get testnet RLUSD", "https://tryrlusd.com/")

    trust_ok = any(
        "trust line exists" in str(c).lower()
        for c in (runtime.get("preflight_summary", ""), *(runtime.get("preflight_warnings") or []))
    ) or bool(runtime.get("preflight_ready"))
    if runtime.get("balance_rlusd") is not None or runtime:
        rlusd_bal = float(runtime.get("balance_rlusd", 0))
        if rlusd_bal > 0 or trust_ok:
            st.success(f"RLUSD on ledger: **{rlusd_bal:.4f}**")
        else:
            st.warning("RLUSD trust line may exist; balance still **0** until faucet pays you.")

    st.markdown("### Send / withdraw")
    send_dest = st.text_input(
        "Send to address",
        value=getattr(config, "send_destination_default", "") or "",
    )
    sc1, sc2 = st.columns(2)
    with sc1:
        send_amount = st.number_input("Amount", min_value=0.0, value=0.0, step=1.0)
    with sc2:
        send_asset = st.selectbox("Asset", ["XRP", "RLUSD"])
    send_ok = st.checkbox("Bot stopped & offers cancelled")
    if st.button("Send now", type="primary"):
        if not config.bot_secret_key.strip():
            st.error("Bot secret required.")
        elif is_engine_running() and not send_ok:
            st.error("Stop bot and confirm checkbox.")
        elif send_amount <= 0:
            st.error("Enter amount > 0.")
        else:
            config.send_destination_default = send_dest.strip()
            _persist_config(config)
            with st.spinner("Sending..."):
                ok, msg = send_funds(send_dest.strip(), send_amount, send_asset)
            _show_result(ok, msg)


def _render_advanced_tab(config: BotConfig, runtime: dict) -> None:
    with st.expander("Bot account & funding", expanded=not config.bot_account_address):
        _render_account_tab(config, runtime)

    with st.expander("Network & RPC", expanded=False):
        config.testnet = st.toggle("Use testnet", value=config.testnet)
        if not config.testnet:
            st.caption("Mainnet — use dry-run first; verify preflight before live trading.")
        config.xrpl_testnet_rpc_url = st.text_input(
            "Testnet RPC", value=config.xrpl_testnet_rpc_url
        )
        config.xrpl_mainnet_rpc_url = st.text_input(
            "Mainnet RPC", value=config.xrpl_mainnet_rpc_url
        )
        private = st.text_input("Private node (optional)", value=config.private_node_url or "")
        config.private_node_url = private or None
        config.rlusd_issuer = st.text_input(
            "RLUSD issuer override",
            value=config.rlusd_issuer or "",
            help=f"Default testnet: {RLUSD_ISSUER_TESTNET}",
        )
        st.caption(f"Active issuer: `{config.resolved_rlusd_issuer()}`")

    with st.expander("Telegram alerts", expanded=False):
        config.telegram_enabled = st.toggle("Enable Telegram", value=config.telegram_enabled)
        config.telegram_token = st.text_input(
            "Bot token", value=config.telegram_token, type="password"
        )
        config.telegram_chat_id = st.text_input("Chat ID", value=config.telegram_chat_id)
        config.telegram_notify_each_cycle = st.toggle(
            "Notify each cycle",
            value=getattr(config, "telegram_notify_each_cycle", False),
        )
        if st.button("Send Telegram test"):
            from monitoring.telegram_alerts import TelegramAlerts

            ok, msg = TelegramAlerts(
                token=config.telegram_token,
                chat_id=config.telegram_chat_id,
                enabled=True,
            ).send_test()
            _show_result(ok, msg)

    with st.expander("Safety & emergency", expanded=False):
        if runtime.get("kill_switch_active"):
            st.error(f"Kill switch active: {runtime.get('kill_switch_reason', '')}")
        else:
            st.success("Kill switch inactive")

        a1, a2, a3 = st.columns(3)
        if a1.button("Clear kill switch"):
            ok, msg = clear_kill_switch()
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
        if a2.button("Cancel all offers"):
            with st.spinner("Cancelling..."):
                ok, msg = cancel_offers_on_ledger()
            _show_result(ok, msg)
        if a3.button("Emergency stop"):
            from risk.kill_switch import KillSwitch

            KillSwitch().activate("GUI emergency stop")
            config.trading_enabled = False
            _persist_config(config)
            stop_engine()
            if not config.dry_run:
                cancel_offers_on_ledger()
            st.error("Emergency stop executed.")

    st.markdown("#### Log files")
    st.code(
        "logs/runtime_state.json\nlogs/portfolio_snapshots.csv\n"
        "logs/trades_YYYY-MM.csv\nlogs/decisions.jsonl",
        language=None,
    )


def _paint_logs_content(runtime: dict, config: BotConfig) -> None:
    """Logs tab — charts, spread check, full decision history."""
    if not runtime:
        st.warning("No runtime data yet. Start the bot or run one cycle.")
        return

    _render_session_statistics(
        runtime,
        config,
        engine_running=is_engine_running(),
        show_portfolio_chart=True,
    )

    st.markdown("### Price history")
    history = runtime.get("price_history") or []
    if len(history) >= 2:
        hist_df = pd.DataFrame(history)
        hist_df["time"] = pd.to_datetime(hist_df["ts_utc"], utc=True)
        mid_series = pd.to_numeric(hist_df["mid"], errors="coerce").dropna()
        if len(mid_series) >= 2:
            first_mid = float(mid_series.iloc[0])
            last_mid = float(mid_series.iloc[-1])
            delta_pct = ((last_mid - first_mid) / first_mid * 100.0) if first_mid else 0.0
            h1, h2, h3 = st.columns(3)
            h1.metric("Samples", len(mid_series))
            h2.metric("Latest mid", f"{last_mid:.6f}")
            h3.metric("Session move", f"{delta_pct:+.3f}%")
            chart_df = hist_df.set_index("time")[["mid"]].apply(pd.to_numeric, errors="coerce")
            chart_df = chart_df.dropna()
            if len(chart_df) >= 2:
                st.line_chart(chart_df, height=280)
                st.caption(
                    "Mid price (RLUSD per XRP) each engine cycle (~60s). "
                    "Moves look small because the axis auto-zooms to the session range."
                )
                with st.expander("Bid / ask (can look noisy)"):
                    ba_cols = [c for c in ("bid", "ask") if c in hist_df.columns]
                    if ba_cols:
                        ba_df = hist_df.set_index("time")[ba_cols].apply(
                            pd.to_numeric, errors="coerce"
                        )
                        st.line_chart(ba_df.dropna(how="all"), height=220)
            else:
                st.info("Collecting price samples — chart appears after a few cycles.")
        else:
            st.info("Collecting price samples — chart appears after a few cycles.")
    elif len(history) == 1:
        h0 = history[0]
        st.metric("Latest mid", _fmt_price(h0.get("mid"), 6))
        st.caption("Chart needs at least 2 engine cycles.")
    else:
        st.info("No price samples yet. Start the engine and wait for cycles.")

    st.markdown("### Quote ladder vs market")
    mid = runtime.get("mid_price")
    book_bid = runtime.get("best_bid_rlusd_per_xrp")
    book_ask = runtime.get("best_ask_rlusd_per_xrp")
    if mid:
        m = float(mid)
        st.caption(
            f"Book best bid **{_fmt_price(book_bid, 6)}** · mid **{_fmt_price(mid, 6)}** · "
            f"best ask **{_fmt_price(book_ask, 6)}** RLUSD/XRP"
        )
    _render_spread_check_panel(runtime, config, compact=False)

    st.markdown("#### Recent decisions")
    decisions_df = clean_decisions_table(runtime, limit=25)
    if not decisions_df.empty:
        _show_dataframe(decisions_df, height=320)
    elif runtime.get("recent_decisions"):
        _show_dataframe(pd.DataFrame(runtime.get("recent_decisions")), height=320)
    if runtime.get("last_error"):
        st.error(runtime["last_error"])


def _render_logs_tab(config: BotConfig, runtime: dict) -> None:
    if st.session_state.get("auto_refresh", True):
        _logs_live_fragment()
    else:
        _paint_logs_content(_load_runtime_state() or runtime, config)


def _render_inventory_tab_view(config: BotConfig, runtime: dict) -> None:
    if st.session_state.get("auto_refresh", True):
        _inventory_live_fragment()
    else:
        _render_inventory_tab(config, _load_runtime_state() or runtime)


def _render_history_tab(config: BotConfig, runtime: dict) -> None:
    _render_logs_tab(config, runtime)


def run_gui() -> None:
    _ensure_page_config()
    _gui_clear_stale_panel_state()

    try:
        config = _load_config()
    except TypeError as exc:
        st.error(f"Config load failed: {exc}")
        st.stop()
    except Exception as exc:
        st.error(f"Config load failed: {exc}")
        st.stop()

    runtime = _load_runtime_state() or {}
    mid_boot = float(runtime.get("mid_price") or 0) if runtime else 0.0
    _clamp_order_sizes(config, _order_size_slider_cap(config, mid_boot))
    engine_running = is_engine_running()
    st.session_state["_gui_engine_running"] = engine_running

    if not engine_running and runtime:
        disk = _load_config()
        disk_profile = (disk.active_profile or "safe").strip().lower()
        runtime_profile = str(runtime.get("active_profile") or "").strip().lower()
        if runtime_profile != disk_profile:
            _gui_sync_config_display(disk, engine_running=False)
            runtime = _load_runtime_state() or {}

    flash = st.session_state.pop("_gui_flash_message", None)
    flash_kind = st.session_state.pop("_gui_flash_kind", "success")
    if flash:
        if flash_kind == "warning":
            st.warning(flash)
        else:
            st.success(flash)

    with st.sidebar:
        st.markdown("##### Engine")
        _render_sidebar_commands(config)
        st.divider()
        save_config_clicked = st.button("Save Config", type="primary", use_container_width=True)
        st.divider()
        if st.session_state.get("auto_refresh", True):
            _sidebar_wallet_live_fragment()
        else:
            _render_sidebar_wallet(runtime)
        with st.expander("Display", expanded=False):
            auto_refresh = st.toggle(
                "Live refresh (5s)",
                value=st.session_state.get("auto_refresh", True),
            )
            st.session_state.auto_refresh = auto_refresh
            if st.button("Refresh now", use_container_width=True):
                _gui_clear_stale_panel_state()
                st.rerun()

    _render_alert_strip(config, runtime)

    pnl_mtm, pnl_balance = _session_pnl_from_runtime(runtime) if runtime else (0.0, 0.0)
    profile = _gui_display_profile(config, runtime, engine_running=engine_running)
    profile_label = PROFILE_LABELS.get(str(profile), str(profile))
    dry = bool(runtime.get("dry_run", config.dry_run)) if runtime else config.dry_run

    render_header_bar(
        engine_running=engine_running,
        dry_run=dry,
        testnet=config.testnet,
        profile_label=profile_label,
        market_label=str(runtime.get("market_condition_label", "—")),
        market_condition=str(runtime.get("market_condition", "neutral")),
        pnl_mtm=pnl_mtm,
        pnl_balance=pnl_balance,
        portfolio_xrp=float(runtime["portfolio_value_xrp"]) if runtime.get("portfolio_value_xrp") is not None else None,
        mid=runtime.get("mid_price"),
        network=config.network_name(),
    )

    tab_dash, tab_ctrl, tab_inv, tab_logs, tab_adv = st.tabs(
        ["Dashboard", "Controls", "Inventory", "Logs", "Advanced"]
    )

    with tab_dash:
        if st.session_state.get("auto_refresh", True):
            _dashboard_live_fragment()
        else:
            _update_live_dashboard(config, runtime)

    with tab_ctrl:
        _render_controls_tab(config, engine_running=engine_running, runtime=runtime)

    with tab_inv:
        _render_inventory_tab_view(config, runtime)

    with tab_logs:
        _render_logs_tab(config, runtime)

    with tab_adv:
        _render_advanced_tab(config, runtime)

    if save_config_clicked:
        _gui_save_and_refresh(
            config,
            engine_running=engine_running,
            touch_save=True,
            success_message="Config saved.",
        )


if __name__ == "__main__":
    try:
        run_gui()
    except Exception as exc:
        st.exception(exc)
