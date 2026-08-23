"""Alpha operator HUD — FastAPI server reading logs/alpha_runtime_state.json."""

from __future__ import annotations

import json
import logging
import html
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from utils.env_secrets import load_dotenv_local

load_dotenv_local()

_HUD_DIR = Path(__file__).resolve().parent
_INDEX = _HUD_DIR / "index.html"
_FAVICON = Path(__file__).resolve().parents[2] / "experimental" / "ws_feed" / "hud" / "favicon.png"
_LOGO = Path(__file__).resolve().parents[2] / "Xledermate.jpg"
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
    from alpha.hud.routes_config import register_config_routes
    from alpha.hud.routes_operator import register_operator_routes
    from alpha.hud.routes_pro import register_pro_routes
    from alpha.hud.routes_skynet import register_skynet_routes
    from alpha.hud.routes_arb import register_arb_routes

    register_operator_routes(app)
    register_config_routes(app)
    register_pro_routes(app)
    register_skynet_routes(app)
    register_arb_routes(app)

    import time

    def _arb_monitor_background() -> None:
        from alpha.hud.arb_monitor import refresh_arb_snapshot

        # Stagger first poll so HUD startup is not blocked on amm_info RPC.
        time.sleep(12)
        while True:
            sleep_s = 60
            try:
                snap = refresh_arb_snapshot()
                # Burst ~12s when dislocation / fill+ / actionable; else ~60s.
                sleep_s = int(snap.get("poll_sleep_seconds") or 60)
                sleep_s = max(10, min(120, sleep_s))
            except Exception as exc:
                logger.warning("arb_monitor_background | %s", exc)
                sleep_s = 60
            time.sleep(sleep_s)

    threading.Thread(target=_arb_monitor_background, daemon=True, name="arb-monitor").start()

    def _skynet_agent_background() -> None:
        from alpha.hud.skynet_agent import maybe_run_agent_tick

        while True:
            time.sleep(25)
            try:
                maybe_run_agent_tick()
            except Exception as exc:
                logger.warning("skynet_agent_background | %s", exc)

    threading.Thread(target=_skynet_agent_background, daemon=True, name="skynet-agent").start()

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

    @app.get("/Xledermate.jpg")
    async def logo() -> Response:
        if not _LOGO.is_file():
            return Response(status_code=404)
        return FileResponse(_LOGO, media_type="image/jpeg")

    @app.get("/hud-health")
    async def hud_health() -> JSONResponse:
        """Tiny public heartbeat so a blank HUD can still be diagnosed."""
        from datetime import datetime, timezone

        state = _load_state()
        updated = state.get("updated_utc")
        age = None
        if updated:
            try:
                ts = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                age = round((datetime.now(tz=timezone.utc) - ts).total_seconds(), 1)
            except (TypeError, ValueError):
                age = None
        size = _RUNTIME.stat().st_size if _RUNTIME.is_file() else 0
        return JSONResponse(
            {
                "ok": True,
                "hud": "alpha",
                "updated_utc": updated,
                "state_age_seconds": age,
                "state_bytes": size,
                "has_xrp": state.get("xrp") is not None,
                "has_mid": state.get("mid") is not None,
                "chart_mids": len(((state.get("chart") or {}).get("mids") or [])),
            }
        )

    @app.get("/state")
    async def get_state() -> JSONResponse:
        from alpha.hud.state_export import refresh_live_metrics_in_state, sanitize_for_json

        state = refresh_live_metrics_in_state(_load_state(), logs_dir=_RUNTIME.parent)
        # Defense in depth: never serve unbounded chart ticks to the 1s poll.
        chart = state.get("chart")
        if isinstance(chart, dict):
            mids = chart.get("mids")
            if isinstance(mids, list) and len(mids) > 4000:
                chart = dict(chart)
                chart["mids"] = mids[-2500:]
                chart["mids_capped"] = True
                state = dict(state)
                state["chart"] = chart
        return JSONResponse(sanitize_for_json(state))

    @app.get("/reports/catalog")
    async def reports_catalog() -> JSONResponse:
        from alpha.hud.reports_support import list_reports

        return JSONResponse({"reports": list_reports()})

    @app.get("/reports/tax/periods")
    async def tax_periods() -> JSONResponse:
        from alpha.reporting.tax_ledger import tax_periods_payload

        return JSONResponse(tax_periods_payload(_RUNTIME.parent))

    @app.get("/report/{report_id}", response_class=HTMLResponse)
    async def report_view_html(
        report_id: str,
        month: str = "",
        year: str = "",
    ) -> HTMLResponse:
        from alpha.hud.reports_support import (
            generate_report_text,
            get_report_spec,
            wrap_report_html,
        )

        spec = get_report_spec(report_id)
        if spec is None:
            return HTMLResponse(
                f"<h1>Unknown report: {html.escape(report_id)}</h1>"
                f"<p><a href='/'>Back to HUD</a></p>",
                status_code=404,
            )
        year_val = int(year) if year.strip().isdigit() else None
        body = generate_report_text(
            report_id,
            logs_dir=_RUNTIME.parent,
            month=month.strip() or None,
            year=year_val,
        )
        subtitle = spec.subtitle
        if report_id == "alpha_trades_month" and month.strip():
            subtitle = f"Month {month.strip()}"
        if report_id == "alpha_tax_year" and year_val is not None:
            subtitle = f"Tax year {year_val}"
        page = wrap_report_html(
            report_id=report_id,
            title=spec.title,
            subtitle=subtitle,
            body_text=body,
            spec=spec,
        )
        resp = HTMLResponse(page)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return resp

    @app.get("/report/alpha_tax_year.csv")
    async def tax_year_csv_download(year: str = "") -> Response:
        from fastapi.responses import PlainTextResponse

        from alpha.reporting.tax_ledger import annual_csv_text
        from datetime import datetime, timezone

        y = int(year) if year.strip().isdigit() else datetime.now(tz=timezone.utc).year
        content = annual_csv_text(_RUNTIME.parent, y)
        resp = PlainTextResponse(content, media_type="text/csv")
        resp.headers["Content-Disposition"] = f'attachment; filename="trades_{y}_annual.csv"'
        return resp

    @app.get("/report/alpha_trades_month.csv")
    async def tax_month_csv_download(month: str = "") -> Response:
        from fastapi.responses import PlainTextResponse

        from alpha.reporting.tax_ledger import trades_path_for_month
        from datetime import datetime, timezone

        key = month.strip() or datetime.now(tz=timezone.utc).strftime("%Y-%m")
        path = trades_path_for_month(_RUNTIME.parent, key)
        if not path.is_file():
            return PlainTextResponse(f"Not found: logs/{path.name}\n", status_code=404)
        resp = PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/csv")
        resp.headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
        return resp

    @app.get("/report/{report_id}.txt")
    async def report_view_text(
        report_id: str,
        month: str = "",
        year: str = "",
    ) -> Response:
        from fastapi.responses import PlainTextResponse

        from alpha.hud.reports_support import generate_report_text, get_report_spec

        if get_report_spec(report_id) is None:
            return PlainTextResponse(f"Unknown report: {report_id}\n", status_code=404)
        year_val = int(year) if year.strip().isdigit() else None
        return PlainTextResponse(
            generate_report_text(
                report_id,
                logs_dir=_RUNTIME.parent,
                month=month.strip() or None,
                year=year_val,
            ),
        )

    @app.post("/controls/{action}")
    async def controls_legacy(action: str) -> JSONResponse:
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
    if app is None:
        raise RuntimeError("FastAPI app failed to initialize")

    from config.settings import BotConfig
    from experimental.ws_feed.hud_auth import attach_hud_auth, resolve_hud_auth

    config = BotConfig.load()
    bind_host = (host or "127.0.0.1").strip()
    auth = resolve_hud_auth(config, bind_host=bind_host)
    _require_auth_for_public_bind(bind_host, auth)
    attach_hud_auth(app, auth, bind_host=bind_host)
    if auth and auth.enabled:
        logger.info("alpha_hud_auth | enabled | user=%s | bind=%s", auth.username, bind_host)
    elif bind_host in ("127.0.0.1", "localhost", "::1"):
        logger.info("alpha_hud_auth | disabled | localhost bind only")

    config_uvicorn = uvicorn.Config(
        app,
        host=bind_host,
        port=port,
        log_level="warning",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    server = uvicorn.Server(config_uvicorn)
    logger.info("alpha_hud_start | host=%s | port=%d", bind_host, port)

    if background:
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        return server

    server.run()
    return server


def _require_auth_for_public_bind(host: str, auth: Optional[Any]) -> None:
    """Refuse public exposure without username/password (same policy as legacy WS HUD)."""
    public = host not in ("127.0.0.1", "localhost", "::1", "")
    if not public:
        return
    if auth is not None and getattr(auth, "enabled", False):
        return
    raise RuntimeError(
        "Alpha HUD cannot bind to a public interface without auth. "
        "Set hud_auth_username + hud_auth_password in config/config.yaml, or "
        "XLG_HUD_USERNAME + XLG_HUD_PASSWORD in .env (see config.example.yaml)."
    )
