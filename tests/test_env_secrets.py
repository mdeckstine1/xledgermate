"""Tests for .env secret loading."""

import os
from pathlib import Path

from utils.env_secrets import load_dotenv_local, resolve_grok_key, resolve_intel_ai_config


def test_resolve_intel_from_env(monkeypatch) -> None:
    monkeypatch.setenv("XLG_GROK_KEY", "xai-testkey")
    monkeypatch.setenv("XLG_GROK_MODEL", "grok-3")
    assert resolve_grok_key() == "xai-testkey"
    prov, key, model = resolve_intel_ai_config()
    assert prov == "grok"
    assert key == "xai-testkey"
    assert model == "grok-3"


def test_load_dotenv_local(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("XLG_GROK_KEY", raising=False)
    (tmp_path / ".env").write_text("XLG_GROK_KEY=xai-fromfile\n", encoding="utf-8")
    load_dotenv_local(repo_root=tmp_path)
    assert os.environ.get("XLG_GROK_KEY") == "xai-fromfile"
