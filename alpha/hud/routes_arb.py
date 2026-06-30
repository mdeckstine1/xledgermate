"""Alpha HUD — read-only arb monitor routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from alpha.hud.arb_monitor import arb_snapshot_cached, refresh_arb_snapshot


def register_arb_routes(app: FastAPI) -> None:
    @app.get("/arb/state")
    async def arb_state() -> JSONResponse:
        snap = arb_snapshot_cached()
        return JSONResponse(snap)

    @app.post("/arb/refresh")
    async def arb_refresh() -> JSONResponse:
        """Manual poll — read-only RPC; does not touch Alpha orders."""
        snap = refresh_arb_snapshot()
        return JSONResponse({"ok": True, **snap})
