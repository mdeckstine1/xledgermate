"""Alpha operator HUD — FastAPI server reading logs/alpha_runtime_state.json."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_HUD_DIR = Path(__file__).resolve().parent
_INDEX = _HUD_DIR / "index.html"
_FAVICON = Path(__file__).resolve().parents[2] / "experimental" / "ws_feed" / "hud" / "favicon.png"
_RUNTIME = Path("logs/alpha_runtime_state.json")
_CONTROLS = Path("logs/alpha_controls.json")

try:
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
    import uvicorn
except ImportError:
    FastAPI = None  # type: ignore[misc, assignment]
    uvicorn = None  # type: ignore[misc, assignment]

app = FastAPI(title="xLedgerMate Alpha Operator HUD") if FastAPI else None


def _load_state() -> Dict[str, Any]:
    if not _RUNTIME.exists():
        return {
            "hud_kind": "alpha",
            "last_note": "Waiting for Alpha engine — start xledgermate-alpha.service",
            "alpha_version": "?",
            "updated_utc": None,
        }
    try:
        data = json.loads(_RUNTIME.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("alpha_hud_state_read_failed | %s", exc)
        return {"hud_kind": "alpha", "last_note": f"State read error: {exc}"}


if app is not None:

    @app.get("/", response_class=HTMLResponse)
    @app.get("/hud", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        if not _INDEX.is_file():
            return HTMLResponse("<h1>alpha/hud/index.html missing</h1>", status_code=500)
        html = _INDEX.read_text(encoding="utf-8")
        build = str(int(_INDEX.stat().st_mtime))
        html = html.replace("__HUD_BUILD__", build)
        resp = HTMLResponse(html)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/favicon.png")
    async def favicon() -> Response:
        if not _FAVICON.is_file():
            return Response(status_code=404)
        return FileResponse(_FAVICON, media_type="image/png")

    @app.get("/state")
    async def get_state() -> JSONResponse:
        return JSONResponse(_load_state())

    @app.post("/controls/{action}")
    async def controls(action: str) -> JSONResponse:
        from alpha.operator.controls import OperatorControlStore

        store = OperatorControlStore(path=_CONTROLS)
        if action == "pause":
            store.pause("HUD operator pause")
            return JSONResponse({"ok": True, "paused": True})
        if action == "resume":
            store.resume()
            return JSONResponse({"ok": True, "paused": False})
        return JSONResponse({"ok": False, "message": f"unknown action: {action}"}, status_code=400)

    @app.post("/engine/{action}")
    async def engine_control(action: str) -> JSONResponse:
        import subprocess

        allowed = {"start", "stop", "restart"}
        if action not in allowed:
            return JSONResponse({"ok": False, "message": f"Unknown action: {action}"})
        unit = Path("/etc/systemd/system/xledgermate-alpha.service")
        if not unit.is_file():
            return JSONResponse(
                {"ok": False, "message": "Engine control requires VPS systemd (xledgermate-alpha.service)."},
            )
        try:
            proc = subprocess.run(
                ["systemctl", action, "xledgermate-alpha"],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return JSONResponse({"ok": False, "message": str(exc)})
        active = subprocess.run(
            ["systemctl", "is-active", "xledgermate-alpha"],
            capture_output=True,
            text=True,
            check=False,
        )
        running = (active.stdout or "").strip() == "active"
        ok = proc.returncode == 0
        return JSONResponse(
            {
                "ok": ok,
                "running": running,
                "message": (proc.stderr or proc.stdout or "").strip() or action,
            }
        )


def run_alpha_hud(*, host: str = "127.0.0.1", port: int = 8765, background: bool = False) -> Optional[Any]:
    """Start Alpha HUD HTTP server."""
    if FastAPI is None or uvicorn is None:
        raise RuntimeError("Install fastapi and uvicorn: pip install fastapi uvicorn")

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    logger.info("alpha_hud_start | host=%s | port=%d", host, port)

    if background:
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        return server

    server.run()
    return server
