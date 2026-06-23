from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, List, Optional, Union

import yaml

from alpha.decision.ta_config import AlphaTechnicalAnalysisConfig

CONFIG_FILE = Path(__file__).resolve().parent / "config.yaml"
CREDENTIALS_SIDECAR_NAME = "credentials.local.yaml"
_CREDENTIAL_FIELDS = ("bot_account_address", "bot_secret_key")


def credentials_sidecar_path(config_path: Optional[Union[str, Path]] = None) -> Path:
    path = Path(config_path) if config_path else CONFIG_FILE
    return path.parent / CREDENTIALS_SIDECAR_NAME


def _read_yaml_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _inject_preserved_credentials(data: dict, path: Path) -> None:
    """Restore credentials from sidecar, live file, or .bak when a save would blank them."""
    sidecar = _read_yaml_dict(credentials_sidecar_path(path))
    backup = _read_yaml_dict(path.with_suffix(path.suffix + ".bak"))
    existing = _read_yaml_dict(path)
    for source in (sidecar, existing, backup):
        if not source:
            continue
        for key in _CREDENTIAL_FIELDS:
            if str(data.get(key) or "").strip():
                continue
            old_val = str(source.get(key) or "").strip()
            if old_val:
                data[key] = source[key]


def _preserve_stored_credentials(config: "BotConfig", path: Path) -> None:
    """Never let a general settings save wipe credentials already on disk."""
    existing = _read_yaml_dict(path)
    sidecar = _read_yaml_dict(credentials_sidecar_path(path))
    for key in _CREDENTIAL_FIELDS:
        new_val = str(getattr(config, key, "") or "").strip()
        old_val = str(existing.get(key) or "").strip()
        side_val = str(sidecar.get(key) or "").strip()
        if not new_val and side_val:
            setattr(config, key, sidecar[key])
        elif not new_val and old_val:
            setattr(config, key, existing[key])


def _merge_credentials_into_config(config: "BotConfig", path: Path) -> None:
    """Load credentials from sidecar first, then config.yaml (sidecar wins)."""
    sidecar = _read_yaml_dict(credentials_sidecar_path(path))
    main = _read_yaml_dict(path)
    backup = _read_yaml_dict(path.with_suffix(path.suffix + ".bak"))
    for key in _CREDENTIAL_FIELDS:
        for source in (sidecar, main, backup):
            val = str(source.get(key) or "").strip()
            if val:
                setattr(config, key, source[key])
                break


def _write_credentials_sidecar(config: "BotConfig", path: Path) -> None:
    creds = {
        key: getattr(config, key)
        for key in _CREDENTIAL_FIELDS
        if str(getattr(config, key, "") or "").strip()
    }
    if not creds:
        return
    sidecar_path = credentials_sidecar_path(path)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    with sidecar_path.open("w", encoding="utf-8") as handle:
        yaml.dump(creds, handle, default_flow_style=False, sort_keys=False)


def _backup_config_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        pass


def _write_yaml_dict(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _inject_preserved_credentials(data, path)
    _backup_config_file(path)
    safe = {k: _yaml_safe_value(v) for k, v in data.items()}
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(safe, handle, default_flow_style=False, sort_keys=False)


def patch_config_file(updates: dict, filepath: Optional[Union[str, Path]] = None) -> None:
    """Update specific keys on disk without touching bot credentials."""
    path = Path(filepath) if filepath else CONFIG_FILE
    allowed = {item.name for item in fields(BotConfig)}
    data = _read_yaml_dict(path)
    _inject_preserved_credentials(data, path)
    for key, value in updates.items():
        if key in _CREDENTIAL_FIELDS or key not in allowed:
            continue
        data[key] = value
    _write_yaml_dict(path, data)


def _yaml_safe_value(value: Any) -> Any:
    """Convert dataclass/tuple values to YAML-safe plain Python types."""
    if is_dataclass(value):
        return _yaml_safe_value(asdict(value))
    if isinstance(value, dict):
        return {k: _yaml_safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_yaml_safe_value(v) for v in value]
    return value


def _config_from_dict(cls: type["BotConfig"], data: dict) -> "BotConfig":
    from alpha.decision.ta_config import AlphaTechnicalAnalysisConfig, merge_ta_config

    config = cls()
    allowed = {item.name for item in fields(cls)}
    for key, value in data.items():
        if key not in allowed:
            continue
        if key == "alpha_technical_analysis" and isinstance(value, dict):
            base = getattr(config, key)
            if isinstance(base, AlphaTechnicalAnalysisConfig):
                setattr(config, key, merge_ta_config(base, value))
            continue
        setattr(config, key, value)
    return config


@dataclass
class BotConfig:
    """Main configuration for XLedgerMate.
    All defaults are safe and ready-to-go for your 11,254 XRP Bot Account."""

    # === RISK CAPITAL (ONLY the rolled-in slice from Flare) ===
    risk_capital_xrp: float = 11254.0
    risk_capital_rlusd: float = 0.0  # used when risk_capital_unit is rlusd
    risk_capital_unit: str = "xrp"  # "xrp" | "rlusd" — GUI entry denomination
    bot_account_address: str = ""          # ← Fill this in (your Bot Account)
    bot_secret_key: str = ""               # ← NEVER commit this to git!

    # === TRADING PAIR ===
    trading_pair: str = "XRP-RLUSD"
    active_profile: str = "safe"
    rlusd_currency: str = "RLUSD"  # display name; on-ledger code is hex-encoded
    rlusd_issuer: str = ""  # optional override; empty = auto by network
    rlusd_issuer_testnet: str = "rQhWct2fv4Vc4KRjRgMrxa8xPN9Zx9iLKV"
    rlusd_issuer_mainnet: str = "rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De"

    # === ORDER BOOK STRATEGY (your 3-level layered brackets) ===
    order_levels: int = 3
    order_sizes: List[float] = field(default_factory=lambda: [150.0, 500.0, 1000.0])   # Level 1, 2, 3
    base_spread: float = 0.0010          # 0.10% base
    level_spread_increment: float = 0.0005  # +0.05% per level

    # === TIMING ===
    order_refresh_time_seconds: int = 60
    tiered_refresh_enabled: bool = True       # Profile-owned fast poll + full quote refresh
    rpc_failure_kill_streak: int = 6            # Consecutive cycle RPC failures → kill switch

    # === EXECUTION ===
    dry_run: bool = True
    trading_enabled: bool = True
    xrp_reserve: float = 12.0
    min_order_size_xrp: float = 1.0
    # Trading Bot Alpha — value accumulation (Phase 2+)
    alpha_ws_enabled: bool = True
    alpha_max_slippage_pct: float = 0.50
    alpha_weakness_deviation: float = 0.05
    alpha_strength_deviation: float = 0.05
    alpha_base_order_size_xrp: float = 50.0
    alpha_bid_offset_pct: float = 0.02
    alpha_ask_offset_pct: float = 0.02
    # Phase 4 entry — conservative mainnet defaults
    alpha_risk_per_trade_pct: float = 0.5  # Max XRP size as % of portfolio per entry
    alpha_min_edge_threshold_pct: float = 0.08  # Min edge (mid vs limit) for buy and sell entries
    alpha_buy_limit_offset_pct: float = 0.15  # Limit buy % below mid (also sets edge)
    alpha_sell_limit_offset_pct: float = 0.15  # Limit sell % above mid (symmetric to buy offset)
    alpha_max_inventory_imbalance_pct: float = 0.10  # Block buys when this far above target XRP ratio
    alpha_max_pending_buys: int = 1  # Max concurrent pending buy brackets
    alpha_max_pending_sells: int = 1  # Max concurrent strength-sell offers (non-bracket asks)
    alpha_cycle_interval_seconds: int = 60  # Trading loop sleep between cycles
    alpha_breakout_pct: float = 0.02  # Min % above entry/high for breakout trailing
    alpha_structure_lookback: int = 20  # Price samples for HTF structure
    alpha_structure_price_source: str = "ask"  # bid | ask | mid | last — directional default
    alpha_chart_price_source: str = "mid"  # Live HUD chart series (mid = fullest history)
    alpha_price_sample_interval_seconds: int = 15  # Sub-cycle book samples (0 = cycle only)
    alpha_gui_refresh_seconds: int = 30  # Streamlit auto-refresh hint
    alpha_gui_bind_host: str = ""  # Empty = use hud_bind_host; 0.0.0.0 for public VPS access
    alpha_hud_port: int = 8765  # Operator HUD (FastAPI) — replaces legacy ws-hud port
    alpha_technical_analysis: AlphaTechnicalAnalysisConfig = field(
        default_factory=AlphaTechnicalAnalysisConfig
    )
    # Fund the bot with XRP only at start; place sell-XRP (ask) quotes until you hold RLUSD.
    fund_with_xrp_only: bool = True

    # === BRACKET / OCO (Alpha value-accumulation — Phase 3) ===
    initial_stop_loss_pct: float = 0.015  # SL limit sell this % below entry (RLUSD/XRP)
    take_profit_pct: float = 0.03  # Fixed TP % above entry when take_profit_rr <= 0
    take_profit_rr: float = 2.0  # TP distance = SL distance * RR; preferred when > 0
    partial_fill_mode: str = "wait_full"  # wait_full | proportional
    min_fill_size_xrp_for_oco: float = 0.5  # Min leg fill before OCO cancels opposing bracket
    bracket_trailing_enabled: bool = False  # Enable SL/TP trailing after breakeven / breakout
    trailing_step_pct: float = 1.5  # % favorable move before ratcheting SL or TP (spec default 1.5)
    breakout_confirmation_tf: str = "15m"  # HTF lookback for breakout (15m, 1h, 4h, 1d)

    # === RISK MANAGEMENT (GUI-adjustable daily drawdown kill switch) ===
    # 5% is too tight for a market maker — normal inventory MTM and spread timing
    # cause false trips during testing; 10% is a realistic starting default.
    max_daily_drawdown_percent: float = 10.0
    min_drawdown_percent: float = 2.0
    max_drawdown_percent: float = 25.0
    inventory_target_xrp_ratio: float = 0.55   # Slightly XRP-heavy (supports your $27 thesis)
    inventory_mode: str = "market_make"        # market_make = two-sided spread capture; rebalance = pause side
    inventory_max_deviation: float = 0.12      # Rebalance mode: pause side beyond this (ratio points)
    inventory_hard_pause_deviation: float = 0.22  # Legacy YAML only; pause uses inventory_max_deviation
    max_leg_size_pct_of_capital: float = 0.12  # Cap one quote leg (~12% of risk capital)
    inventory_overshoot_slack: float = 0.03  # MM: max ratio beyond target one fill may reach
    min_edge_pct: float = 0.10                 # Legacy; migrated to edge_strictness on load
    edge_strictness: float = 1.0                 # Scales profile min edge: 0.85 low, 1.0 normal, 1.15 strict
    solo_edge_mult: float = 0.65                 # Solo L3 gate: pass if capture >= min_edge * this
    solo_edge_absolute_floor_pct: float = 0.012  # Solo L3 gate: pass if capture >= this (pct points)
    dynamic_min_edge_enabled: bool = True        # Adapt min edge to live book spread each cycle
    book_pressure_sensitivity: float = 1.0   # How strongly book depth imbalance steers quotes
    selective_order_refresh: bool = True     # Keep matching offers; cancel/replace only when quotes move
    order_price_tolerance_pct: float = 0.08    # Match open offer if within this % of planned price
    order_size_tolerance_xrp: float = 0.75     # Match open offer if size within this XRP
    spread_failure_kill_cycles: int = 8        # Consecutive live spread-check failures → kill switch (0=off)
    session_balance_loss_kill_xrp: float = 0.35  # Kill if session balance PnL below -this (0=off)
    session_balance_loss_kill_min_fills: int = 25  # Min fills before session balance kill applies
    toxic_fill_kill_enabled: bool = False      # False = pause/off-book only; no kill on markout ratio
    toxic_fill_ratio_kill_threshold: float = 0.75  # Kill if toxic/recent fills exceeds this (when enabled)
    toxic_fill_min_count: int = 12             # Minimum fills before toxic-ratio kill applies
    # Live spread guard: planned quotes must sit near book bid/ask (validated each cycle).
    max_quote_worse_than_touch_pct: float = 0.50   # Max % ask above best ask / bid below best bid
    competitive_off_touch_max_worse_pct: float = 0.12  # Cap distance from touch when not joining L1
    max_quote_improve_touch_pct: float = 0.15      # Max % allowed to cross/improve touch
    max_half_spread_from_mid_pct: float = 1.0      # Max distance from mid per quote leg
    require_spread_validation_for_live: bool = True
    auto_profile_switching: bool = False       # Auto-apply recommended profile when operator idle
    auto_profile_inactivity_minutes: int = 30
    auto_profile_confirm_cycles: int = 3       # Same recommendation N cycles before switching
    auto_profile_switch_cooldown_minutes: int = 45  # Min gap between auto switches

    # === MONITORING ===
    telegram_enabled: bool = False
    telegram_token: str = ""       # From @BotFather
    telegram_chat_id: str = ""     # Your chat ID (numeric, or @channel username)
    telegram_notify_each_cycle: bool = False
    telegram_hud_url: str = ""  # Optional public HUD URL for hourly Telegram (e.g. http://host:8765)
    telegram_quiet_hours_enabled: bool = False  # Skip hourly reports during quiet window (UTC)
    telegram_quiet_start_hour: int = 22  # Inclusive UTC hour (0–23)
    telegram_quiet_end_hour: int = 7  # Exclusive UTC hour (0–23); 22→7 = overnight
    hud_bind_host: str = "127.0.0.1"  # 0.0.0.0 for phone/browser without SSH tunnel (read-only HUD)
    hud_auth_enabled: bool = False  # Require login when username/password set (auto-on for public bind)
    hud_auth_username: str = ""
    hud_auth_password: str = ""  # Or XLG_HUD_PASSWORD in .env (gitignored)
    hud_auth_rp_id: str = ""  # WebAuthn rp_id override (default: request Host without port)

    # === WS ENGINE FEATURE SWITCHES (production ws-engine / ws-hud path) ===
    ws_competitor_intel_enabled: bool = True   # G1 on-chain scrape (~15s RPC) → G4 inputs
    ws_g2_scaler_enabled: bool = True          # Spread-quality brake on toxic markout
    ws_g4_peer_lane_enabled: bool = True       # Peer-lane size/side bias (needs intel)
    ws_drawdown_kill_enabled: bool = True      # Daily portfolio drawdown → kill file
    ws_intel_log_enabled: bool = True          # Append logs/intel_decisions.jsonl
    ws_fill_quality_enabled: bool = True       # Markout tracking (feeds G2 when enabled)
    ws_hud_enabled: bool = True                # Allow --mode ws-hud / systemd HUD unit
    ws_hud_metrics_enabled: bool = True        # G3/G6 grade panel (CSV walk; throttled in HUD)
    ws_hud_grok_enabled: bool = True           # HUD /analyze_competitor Grok calls
    telegram_hourly_report_enabled: bool = True  # Hourly soak script + timer
    telegram_kill_alerts_enabled: bool = True    # Immediate Telegram on drawdown kill

    # === OTHER ===
    testnet: bool = True                    # Start on testnet by default
    send_destination_default: str = ""      # Optional default withdraw / Mangie address
    private_node_url: Optional[str] = None  # e.g. your own node for no rate limits
    xrpl_testnet_rpc_url: str = "https://s.altnet.rippletest.net:51234"
    xrpl_mainnet_rpc_url: str = "https://s1.ripple.com:51234"

    def to_dict(self):
        return asdict(self)  # nested dataclasses (e.g. alpha_technical_analysis) serialize cleanly

    def risk_capital_unit_normalized(self) -> str:
        unit = (getattr(self, "risk_capital_unit", None) or "xrp").strip().lower()
        return "rlusd" if unit in ("rlusd", "usd") else "xrp"

    def effective_risk_capital_xrp(self, mid_rlusd_per_xrp: Optional[float] = None) -> float:
        """Quote-size cap in XRP equivalent (converts RLUSD capital when mid is known)."""
        if self.risk_capital_unit_normalized() == "rlusd":
            rlusd = float(getattr(self, "risk_capital_rlusd", 0) or 0)
            if mid_rlusd_per_xrp and float(mid_rlusd_per_xrp) > 0:
                return rlusd / float(mid_rlusd_per_xrp)
            return float(self.risk_capital_xrp)
        return float(self.risk_capital_xrp)

    def sync_risk_capital_pair(self, mid_rlusd_per_xrp: Optional[float]) -> None:
        """Keep XRP and RLUSD risk capital fields aligned when mid is available."""
        if not mid_rlusd_per_xrp or float(mid_rlusd_per_xrp) <= 0:
            return
        mid = float(mid_rlusd_per_xrp)
        if self.risk_capital_unit_normalized() == "rlusd":
            self.risk_capital_xrp = float(self.risk_capital_rlusd) / mid
        else:
            self.risk_capital_rlusd = float(self.risk_capital_xrp) * mid

    def network_name(self) -> str:
        return "testnet" if self.testnet else "mainnet"

    def resolved_rpc_url(self) -> str:
        if self.private_node_url:
            return self.private_node_url
        return self.xrpl_testnet_rpc_url if self.testnet else self.xrpl_mainnet_rpc_url

    def resolved_rlusd_issuer(self) -> str:
        from utils.xrpl_currency import RLUSD_ISSUER_MAINNET, RLUSD_ISSUER_TESTNET

        issuer_override = (self.rlusd_issuer or "").strip()
        if issuer_override:
            return issuer_override
        testnet_issuer = getattr(self, "rlusd_issuer_testnet", RLUSD_ISSUER_TESTNET)
        mainnet_issuer = getattr(self, "rlusd_issuer_mainnet", RLUSD_ISSUER_MAINNET)
        return testnet_issuer if self.testnet else mainnet_issuer

    def resolved_rlusd_currency_code(self) -> str:
        from utils.xrpl_currency import resolve_rlusd_currency_code

        return resolve_rlusd_currency_code(self.rlusd_currency)

    def save(self, filepath: Optional[Union[str, Path]] = None) -> None:
        """Save current config to YAML."""
        path = Path(filepath) if filepath else CONFIG_FILE
        _preserve_stored_credentials(self, path)
        data = self.to_dict()
        _inject_preserved_credentials(data, path)
        for key in _CREDENTIAL_FIELDS:
            val = str(data.get(key) or "").strip()
            if val:
                setattr(self, key, data[key])
        _write_credentials_sidecar(self, path)
        _write_yaml_dict(path, data)

    @classmethod
    def load(cls, filepath: Optional[Union[str, Path]] = None) -> "BotConfig":
        """Load from YAML, merging with defaults (never cls(**yaml) — avoids legacy key crashes)."""
        path = Path(filepath) if filepath else CONFIG_FILE

        if not path.exists():
            config = cls()
            config.save(filepath)
            return config

        raw = path.read_text(encoding="utf-8")
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError:
            parsed = None

        if parsed is None and raw.strip():
            # Corrupt file — do not overwrite operator settings with factory defaults.
            return _config_from_dict(cls, {})

        data = parsed if isinstance(parsed, dict) else {}
        if not data and raw.strip():
            return _config_from_dict(cls, {})

        allowed = {item.name for item in fields(cls)}
        merged = dict(data)
        updated = False

        config = _config_from_dict(cls, data)
        _merge_credentials_into_config(config, path)

        if config.testnet and config.rlusd_issuer == config.rlusd_issuer_mainnet:
            config.rlusd_issuer = ""
            if merged.get("rlusd_issuer") == config.rlusd_issuer_mainnet:
                merged["rlusd_issuer"] = ""
                updated = True

        if "edge_strictness" not in data and "min_edge_pct" in data:
            try:
                legacy = float(data["min_edge_pct"])
                config.edge_strictness = max(0.85, min(1.15, legacy / 0.10))
            except (TypeError, ValueError):
                config.edge_strictness = 1.0
            merged["edge_strictness"] = config.edge_strictness
            updated = True

        missing = allowed - set(data.keys())
        for key in missing:
            merged[key] = _yaml_safe_value(getattr(config, key))
            updated = True

        if "risk_capital_unit" not in data:
            merged["risk_capital_unit"] = "xrp"
            updated = True
        if "risk_capital_rlusd" not in data:
            merged["risk_capital_rlusd"] = 0.0
            updated = True

        if missing or updated:
            _inject_preserved_credentials(merged, path)
            _write_yaml_dict(path, merged)

        config = _config_from_dict(cls, _read_yaml_dict(path))
        _merge_credentials_into_config(config, path)
        if any(str(getattr(config, k, "") or "").strip() for k in _CREDENTIAL_FIELDS):
            _write_credentials_sidecar(config, path)
        return config


if __name__ == "__main__":
    config = BotConfig()
    config.save()
    print("Default config created at config/config.yaml")
