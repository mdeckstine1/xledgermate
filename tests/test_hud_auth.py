"""Tests for HUD access control."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from experimental.ws_feed.hud_auth import (
    HudAuthSettings,
    resolve_hud_auth,
    verify_password,
    _sign_session,
    _verify_session,
)


def _settings() -> HudAuthSettings:
    return HudAuthSettings(
        enabled=True,
        username="operator",
        password="secret-pass",
        session_secret=b"test-secret-bytes-32chars-long!!",
    )


def test_verify_password_ok():
    s = _settings()
    assert verify_password(s, "operator", "secret-pass")
    assert not verify_password(s, "operator", "wrong")
    assert not verify_password(s, "other", "secret-pass")


def test_session_roundtrip():
    s = _settings()
    token = _sign_session(s, s.username)
    assert _verify_session(s, token)
    assert not _verify_session(s, token + "x")


def test_resolve_hud_auth_public_bind():
    cfg = SimpleNamespace(
        hud_auth_username="op",
        hud_auth_password="pw",
        hud_auth_enabled=False,
        hud_auth_rp_id="",
    )
    assert resolve_hud_auth(cfg, bind_host="0.0.0.0") is not None


def test_resolve_hud_auth_localhost_disabled_without_flag():
    cfg = SimpleNamespace(
        hud_auth_username="op",
        hud_auth_password="pw",
        hud_auth_enabled=False,
        hud_auth_rp_id="",
    )
    assert resolve_hud_auth(cfg, bind_host="127.0.0.1") is None


def test_resolve_hud_auth_localhost_explicit():
    cfg = SimpleNamespace(
        hud_auth_username="op",
        hud_auth_password="pw",
        hud_auth_enabled=True,
        hud_auth_rp_id="",
    )
    assert resolve_hud_auth(cfg, bind_host="127.0.0.1") is not None


def test_run_production_hud_rejects_public_bind_without_auth(monkeypatch):
    from experimental.ws_feed import ws_hud_production

    cfg = SimpleNamespace(
        hud_auth_username="",
        hud_auth_password="",
        hud_auth_enabled=False,
        hud_auth_rp_id="",
        hud_bind_host="0.0.0.0",
        ws_hud_enabled=True,
    )
    monkeypatch.setattr(ws_hud_production.BotConfig, "load", lambda: cfg)

    def _fail_run_hud(*args, **kwargs):
        raise AssertionError("run_hud must not bind a public unauthenticated HUD")

    monkeypatch.setattr(ws_hud_production, "run_hud", _fail_run_hud)

    with pytest.raises(RuntimeError, match="Refusing to start public HUD without authentication"):
        asyncio.run(ws_hud_production.run_production_hud(host="0.0.0.0"))
