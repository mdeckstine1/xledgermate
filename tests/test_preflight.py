from utils.preflight import evaluate_preflight

from config.settings import BotConfig


def _cfg(**kwargs) -> BotConfig:
    c = BotConfig()
    c.bot_account_address = "rsLnfMsP5LzdLyR2Ume7fgyjwNfgwMjp8g"
    c.bot_secret_key = "sXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    c.dry_run = False
    c.fund_with_xrp_only = False
    c.order_sizes = [50.0, 0.0, 0.0]
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def test_preflight_warns_when_rippling_enabled() -> None:
    result = evaluate_preflight(
        config=_cfg(),
        xrp_balance=100.0,
        rlusd_balance=50.0,
        trust_line_limit=1_000_000.0,
        has_trust_line=True,
        trust_line_no_ripple=False,
        mid_price=1.32,
        kill_switch_active=False,
    )
    assert result.ready
    assert any("rippling enabled" in w.lower() for w in result.warnings)


def test_preflight_checks_no_ripple_when_disabled() -> None:
    result = evaluate_preflight(
        config=_cfg(),
        xrp_balance=100.0,
        rlusd_balance=50.0,
        trust_line_limit=1_000_000.0,
        has_trust_line=True,
        trust_line_no_ripple=True,
        mid_price=1.32,
        kill_switch_active=False,
    )
    assert any("rippling disabled" in c.lower() for c in result.checks)
