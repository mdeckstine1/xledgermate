"""Tests for Alpha HUD server auth wiring."""

from __future__ import annotations

import pytest

from alpha.hud.server import _require_auth_for_public_bind


def test_public_bind_requires_auth():
    with pytest.raises(RuntimeError, match="without auth"):
        _require_auth_for_public_bind("0.0.0.0", None)


def test_localhost_allows_no_auth():
    _require_auth_for_public_bind("127.0.0.1", None)


def test_public_bind_ok_with_auth_settings():
    from experimental.ws_feed.hud_auth import HudAuthSettings

    auth = HudAuthSettings(
        enabled=True,
        username="op",
        password="pw",
        session_secret=b"x" * 32,
    )
    _require_auth_for_public_bind("0.0.0.0", auth)
