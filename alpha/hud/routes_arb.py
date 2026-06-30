"""Alpha HUD — read-only arb monitor routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

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

    @app.get("/arb/report.txt")
    async def arb_report_text() -> Response:
        from fastapi.responses import PlainTextResponse

        from alpha.hud.arb_monitor import arb_soak_report_text

        return PlainTextResponse(arb_soak_report_text())
