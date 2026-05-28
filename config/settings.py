from dataclasses import dataclass, asdict, field
from typing import List, Optional
import yaml
from pathlib import Path


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

    # === RISK MANAGEMENT (GUI-adjustable 2%–5% drawdown) ===
    max_daily_drawdown_percent: float = 3.5   # Default (you can slide 2.0–5.0 in GUI)
    min_drawdown_percent: float = 2.0
    max_drawdown_percent: float = 5.0
    inventory_target_xrp_ratio: float = 0.55   # Slightly XRP-heavy (supports your $27 thesis)

    # === AUTO ROLLOVER (risk capital rule) ===
    auto_rollover_enabled: bool = True

    # === MONITORING ===
    telegram_enabled: bool = False
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # === OTHER ===
    testnet: bool = True                    # Start on testnet by default
    private_node_url: Optional[str] = None  # e.g. your own node for no rate limits
    xrpl_testnet_rpc_url: str = "https://s.altnet.rippletest.net:51234"
    xrpl_mainnet_rpc_url: str = "https://xrplcluster.com"

    def to_dict(self):
        return asdict(self)

    def network_name(self) -> str:
        return "testnet" if self.testnet else "mainnet"

    def resolved_rpc_url(self) -> str:
        if self.private_node_url:
            return self.private_node_url
        return self.xrpl_testnet_rpc_url if self.testnet else self.xrpl_mainnet_rpc_url

    def resolved_rlusd_issuer(self) -> str:
        if self.rlusd_issuer:
            return self.rlusd_issuer
        return self.rlusd_issuer_testnet if self.testnet else self.rlusd_issuer_mainnet

    def resolved_rlusd_currency_code(self) -> str:
        from utils.xrpl_currency import RLUSD_CURRENCY_HEX, encode_currency_code

        if self.rlusd_currency.upper() in {"RLUSD", RLUSD_CURRENCY_HEX}:
            return RLUSD_CURRENCY_HEX
        return encode_currency_code(self.rlusd_currency)

    def save(self, filepath: str = "config/config.yaml"):
        """Save current config to YAML"""
        Path("config").mkdir(exist_ok=True)
        with open(filepath, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

    @classmethod
    def load(cls, filepath: str = "config/config.yaml"):
        """Load from YAML or return defaults"""
        if Path(filepath).exists():
            with open(filepath, "r") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        config = cls()
        config.save()
        return config


if __name__ == "__main__":
    config = BotConfig()
    config.save()
    print("Default config created at config/config.yaml")
