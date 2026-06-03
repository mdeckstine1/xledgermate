"""Config must never wipe bot credentials on unrelated saves."""

from pathlib import Path

import yaml

from config.settings import BotConfig, patch_config_file


def test_save_preserves_existing_credentials(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "bot_account_address": "rBotAccount11111111111111111111",
                "bot_secret_key": "sSecret111111111111111111111111111",
                "testnet": False,
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )

    cfg = BotConfig.load(path)
    cfg.testnet = True
    cfg.bot_account_address = ""
    cfg.bot_secret_key = ""
    cfg.save(path)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["bot_account_address"] == "rBotAccount11111111111111111111"
    assert data["bot_secret_key"] == "sSecret111111111111111111111111111"
    assert data["testnet"] is True


def test_save_credentials_can_replace_when_explicit(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "bot_account_address": "rOld111111111111111111111111111",
                "bot_secret_key": "sOld111111111111111111111111111",
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )

    cfg = BotConfig.load(path)
    cfg.bot_account_address = "rNew222222222222222222222222222"
    cfg.bot_secret_key = "sNew222222222222222222222222222"
    cfg.save(path)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["bot_account_address"] == "rNew222222222222222222222222222"
    assert data["bot_secret_key"] == "sNew222222222222222222222222222"


def test_load_does_not_overwrite_on_parse_failure(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "testnet: false\ndry_run: false\nbot_account_address: rKeep111111111111111111111111111\n",
        encoding="utf-8",
    )
    cfg = BotConfig.load(path)
    assert cfg.testnet is False
    assert cfg.dry_run is False
    assert cfg.bot_account_address == "rKeep111111111111111111111111111"
    raw = path.read_text(encoding="utf-8")
    assert "testnet: false" in raw
    assert "dry_run: false" in raw


def test_load_adds_missing_keys_without_reverting_execution(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "testnet": False,
                "dry_run": False,
                "bot_account_address": "rBotAccount11111111111111111111",
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    cfg = BotConfig.load(path)
    assert cfg.testnet is False
    assert cfg.dry_run is False
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["testnet"] is False
    assert data["dry_run"] is False
    assert "tiered_refresh_enabled" in data


def test_sidecar_restores_credentials_after_config_wipe(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    sidecar = tmp_path / "credentials.local.yaml"
    path.write_text(
        yaml.dump(
            {
                "bot_account_address": "rBotAccount11111111111111111111",
                "bot_secret_key": "sSecret111111111111111111111111111",
                "testnet": False,
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    cfg = BotConfig.load(path)
    sidecar.write_text(
        yaml.dump(
            {
                "bot_account_address": cfg.bot_account_address,
                "bot_secret_key": cfg.bot_secret_key,
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    path.write_text(
        yaml.dump(
            {
                "bot_account_address": "",
                "bot_secret_key": "",
                "testnet": False,
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    restored = BotConfig.load(path)
    assert restored.bot_account_address == "rBotAccount11111111111111111111"
    assert restored.bot_secret_key == "sSecret111111111111111111111111111"


def test_patch_config_file_never_touches_credentials(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "bot_account_address": "rBotAccount11111111111111111111",
                "bot_secret_key": "sSecret111111111111111111111111111",
                "active_profile": "safe",
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    patch_config_file({"active_profile": "thin_liquidity"}, filepath=path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["active_profile"] == "thin_liquidity"
    assert data["bot_account_address"] == "rBotAccount11111111111111111111"
    assert data["bot_secret_key"] == "sSecret111111111111111111111111111"


def test_save_creates_backup(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("testnet: false\n", encoding="utf-8")
    cfg = BotConfig.load(path)
    cfg.dry_run = False
    cfg.save(path)
    backup = path.with_suffix(path.suffix + ".bak")
    assert backup.exists()
    assert "testnet: false" in backup.read_text(encoding="utf-8")
