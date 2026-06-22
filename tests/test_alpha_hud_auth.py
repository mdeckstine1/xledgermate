"""Tests for Alpha HUD server auth wiring."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha.hud.server import _require_auth_for_public_bind
from experimental.ws_feed.hud_auth import (
    SESSION_COOKIE,
    HudAuthSettings,
    _sign_session,
    attach_hud_auth,
)


def _auth_settings() -> HudAuthSettings:
    return HudAuthSettings(
        enabled=True,
        username="op",
        password="pw",
        session_secret=b"x" * 32,
    )


def _auth_client() -> TestClient:
    app = FastAPI()

    @app.get("/")
    async def root():
        return {"ok": True}

    @app.get("/hud")
    async def hud():
        return {"hud": True}

    @app.get("/state")
    async def state():
        return {"state": True}

    attach_hud_auth(app, _auth_settings())
    return TestClient(app)


def test_public_bind_requires_auth():
    with pytest.raises(RuntimeError, match="without auth"):
        _require_auth_for_public_bind("0.0.0.0", None)


def test_localhost_allows_no_auth():
    _require_auth_for_public_bind("127.0.0.1", None)


def test_public_bind_ok_with_auth_settings():
    auth = _auth_settings()
    _require_auth_for_public_bind("0.0.0.0", auth)


def test_unauthenticated_get_root_redirects_to_login():
    client = _auth_client()
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login?next=/"


def test_unauthenticated_head_root_redirects_to_login():
    client = _auth_client()
    r = client.head("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login?next=/"


def test_unauthenticated_head_hud_redirects_to_login():
    client = _auth_client()
    r = client.head("/hud", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login?next=/hud"


def test_unauthenticated_state_returns_401():
    client = _auth_client()
    r = client.get("/state")
    assert r.status_code == 401
    assert r.json() == {"ok": False, "error": "unauthorized"}


def test_logout_clears_session_and_redirects():
    client = _auth_client()
    settings = _auth_settings()
    token = _sign_session(settings, settings.username)
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/state").status_code == 200

    r = client.get("/logout", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"
    assert SESSION_COOKIE not in r.cookies or not r.cookies.get(SESSION_COOKIE)

    client.cookies.clear()
    assert client.get("/state").status_code == 401
