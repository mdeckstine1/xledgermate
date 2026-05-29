from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import List, Optional, Union

import yaml

CONFIG_FILE = Path(__file__).resolve().parent / "config.yaml"


@dataclass
class BotConfig:
    """Main configuration for XLedgerMate.
    All defaults are safe and ready-to-go for your 11,254 XRP Bot Account."""

    # === RISK CAPITAL (ONLY the rolled-in slice from Flare) ===
    risk_capital_xrp: float = 11254.0
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

    # === EXECUTION ===
    dry_run: bool = True
    trading_enabled: bool = True
    xrp_reserve: float = 12.0
    min_order_size_xrp: float = 1.0
    # Fund the bot with XRP only at start; place sell-XRP (ask) quotes until you hold RLUSD.
    fund_with_xrp_only: bool = True

    # === RISK MANAGEMENT (GUI-adjustable daily drawdown kill switch) ===
    # 5% is too tight for a market maker — normal inventory MTM and spread timing
    # cause false trips during testing; 10% is a realistic starting default.
    max_daily_drawdown_percent: float = 10.0
    min_drawdown_percent: float = 2.0
    max_drawdown_percent: float = 25.0
    inventory_target_xrp_ratio: float = 0.55   # Slightly XRP-heavy (supports your $27 thesis)
    min_edge_pct: float = 0.10                 # Legacy; migrated to edge_strictness on load
    edge_strictness: float = 1.0                 # Scales profile min edge: 0.85 low, 1.0 normal, 1.15 strict
    dynamic_min_edge_enabled: bool = False       # Adapt min edge to live book spread each cycle
    book_pressure_sensitivity: float = 1.0   # How strongly book depth imbalance steers quotes
    # Live spread guard: planned quotes must sit near book bid/ask (validated each cycle).
    max_quote_worse_than_touch_pct: float = 0.50   # Max % ask above best ask / bid below best bid
    max_quote_improve_touch_pct: float = 0.15      # Max % allowed to cross/improve touch
    max_half_spread_from_mid_pct: float = 1.0      # Max distance from mid per quote leg
    require_spread_validation_for_live: bool = True
    auto_profile_switching: bool = False       # Auto-move to defensive profile when idle + stress
    auto_profile_inactivity_minutes: int = 120

    # === AUTO ROLLOVER (risk capital rule) ===
    auto_rollover_enabled: bool = True

    # === MONITORING ===
    telegram_enabled: bool = False
    telegram_token: str = ""       # From @BotFather
    telegram_chat_id: str = ""     # Your chat ID (numeric, or @channel username)
    telegram_notify_each_cycle: bool = False

    # === OTHER ===
    testnet: bool = True                    # Start on testnet by default
    send_destination_default: str = ""      # Optional default withdraw / Mangie address
    private_node_url: Optional[str] = None  # e.g. your own node for no rate limits
    xrpl_testnet_rpc_url: str = "https://s.altnet.rippletest.net:51234"
    xrpl_mainnet_rpc_url: str = "https://s1.ripple.com:51234"

    def to_dict(self):
        return asdict(self)

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
        from utils.xrpl_currency import RLUSD_CURRENCY_HEX, encode_currency_code

        if self.rlusd_currency.upper() in {"RLUSD", RLUSD_CURRENCY_HEX}:
            return RLUSD_CURRENCY_HEX
        return encode_currency_code(self.rlusd_currency)

    def save(self, filepath: Optional[Union[str, Path]] = None) -> None:
        """Save current config to YAML."""
        path = Path(filepath) if filepath else CONFIG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            yaml.dump(self.to_dict(), handle, default_flow_style=False, sort_keys=False)

    @classmethod
    def load(cls, filepath: Optional[Union[str, Path]] = None) -> "BotConfig":
        """Load from YAML, merging with defaults (never cls(**yaml) — avoids legacy key crashes)."""
        config = cls()
        path = Path(filepath) if filepath else CONFIG_FILE

        if not path.exists():
            config.save(filepath)
            return config

        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        if not isinstance(data, dict):
            data = {}

        allowed = {item.name for item in fields(cls)}
        updated = False

        for key, value in data.items():
            if key not in allowed:
                continue
            setattr(config, key, value)
            updated = True

        # Legacy configs used mainnet issuer while on testnet — prefer auto-select.
        if config.testnet and config.rlusd_issuer == config.rlusd_issuer_mainnet:
            config.rlusd_issuer = ""
            updated = True

        # Legacy min_edge_pct slider → edge_strictness (1.0 = old default 0.10%).
        if "edge_strictness" not in data and "min_edge_pct" in data:
            try:
                legacy = float(data["min_edge_pct"])
                config.edge_strictness = max(0.85, min(1.15, legacy / 0.10))
            except (TypeError, ValueError):
                config.edge_strictness = 1.0
            updated = True

        if allowed - set(data.keys()):
            config.save(filepath)
        elif updated:
            config.save(filepath)

        return config


if __name__ == "__main__":
    config = BotConfig()
    config.save()
    print("Default config created at config/config.yaml")
