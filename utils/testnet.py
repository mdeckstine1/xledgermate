def is_testnet_mode() -> bool:
    """Returns True when config is set to XRPL Testnet (recommended for development)."""
    from config.settings import BotConfig

    return BotConfig.load().testnet
