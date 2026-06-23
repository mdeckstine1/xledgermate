"""Alpha HUD operator API routes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_STATE_DIR = Path("logs")
_OVERRIDES = _STATE_DIR / "alpha_overrides.json"
_COMMANDS = _STATE_DIR / "alpha_commands.json"
_KILL = _STATE_DIR / "kill_switch.json"


def register_operator_routes(app: Any) -> None:
    """Attach operator control endpoints to the Alpha HUD FastAPI app."""
    from fastapi import Body
    from fastapi.responses import JSONResponse

    from alpha.operator.runtime import (
        OPERATOR_SLIDER_DEFAULTS,
        OperatorRuntimeStore,
        apply_overrides,
        effective_config_snapshot,
    )
    from config.settings import BotConfig
    from risk.kill_switch import KillSwitch

    def _runtime() -> OperatorRuntimeStore:
        return OperatorRuntimeStore(overrides_path=_OVERRIDES, commands_path=_COMMANDS)

    def _base_config() -> BotConfig:
        return BotConfig.load()

    def _effective() -> BotConfig:
        return apply_overrides(_base_config(), _runtime().load_overrides())

    @app.get("/operator/config")
    async def get_operator_config() -> JSONResponse:
        base = _base_config()
        overrides = _runtime().load_overrides()
        effective = apply_overrides(base, overrides)
        return JSONResponse(
            {
                "ok": True,
                "config_effective": effective_config_snapshot(effective),
                "config_base": effective_config_snapshot(base),
                "operator_overrides": overrides,
                "slider_defaults": OPERATOR_SLIDER_DEFAULTS,
            }
        )

    @app.patch("/operator/config")
    async def patch_operator_config(body: Dict[str, Any] = Body(...)) -> JSONResponse:
        updates = body.get("overrides") if isinstance(body.get("overrides"), dict) else body
        if not isinstance(updates, dict) or not updates:
            return JSONResponse({"ok": False, "message": "overrides object required"}, status_code=400)
        merged, errors = _runtime().patch_overrides(updates, base=_base_config())
        if errors:
            return JSONResponse({"ok": False, "errors": errors}, status_code=400)
        effective = apply_overrides(_base_config(), merged)
        return JSONResponse(
            {
                "ok": True,
                "operator_overrides": merged,
                "config_effective": effective_config_snapshot(effective),
            }
        )

    @app.post("/operator/config/reload")
    async def post_config_reload() -> JSONResponse:
        _runtime().queue_command({"type": "config_reload"})
        return JSONResponse({"ok": True, "queued": "config_reload"})

    @app.post("/operator/dry-run")
    async def post_dry_run(body: Dict[str, Any] = Body(...)) -> JSONResponse:
        dry_run = body.get("dry_run")
        confirm = str(body.get("confirm", ""))
        persist = bool(body.get("persist", False))
        if not isinstance(dry_run, bool):
            return JSONResponse({"ok": False, "message": "dry_run boolean required"}, status_code=400)
        if dry_run:
            if confirm != "ENABLE_DRY_RUN":
                return JSONResponse(
                    {"ok": False, "message": 'confirm must be "ENABLE_DRY_RUN"'},
                    status_code=400,
                )
        elif confirm != "ENABLE_LIVE":
            return JSONResponse(
                {"ok": False, "message": 'confirm must be "ENABLE_LIVE" for live trading'},
                status_code=400,
            )
        try:
            overrides = _runtime().set_dry_run(dry_run, persist_yaml=persist, base=_base_config())
        except ValueError as exc:
            return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)
        effective = apply_overrides(_base_config(), overrides)
        return JSONResponse(
            {
                "ok": True,
                "dry_run": effective.dry_run,
                "persisted": persist,
                "operator_overrides": overrides,
            }
        )

    @app.post("/controls/kill")
    async def controls_kill(body: Optional[Dict[str, Any]] = Body(default=None)) -> JSONResponse:
        reason = "Operator kill (HUD)"
        if body and body.get("reason"):
            reason = str(body["reason"])
        KillSwitch(path=_KILL).activate(reason)
        return JSONResponse({"ok": True, "kill_switch_active": True, "reason": reason})

    @app.post("/controls/clear-kill")
    async def controls_clear_kill() -> JSONResponse:
        KillSwitch(path=_KILL).clear("Operator cleared via HUD")
        return JSONResponse({"ok": True, "kill_switch_active": False})

    @app.post("/controls/cancel-all")
    async def controls_cancel_all(body: Dict[str, Any] = Body(...)) -> JSONResponse:
        if body.get("confirm") != "CANCEL_ALL":
            return JSONResponse(
                {"ok": False, "message": 'confirm must be "CANCEL_ALL"'},
                status_code=400,
            )
        _runtime().queue_command({"type": "cancel_all"})
        return JSONResponse({"ok": True, "queued": "cancel_all"})

    @app.post("/brackets/{bracket_id}/adjust")
    async def bracket_adjust(
        bracket_id: str,
        body: Dict[str, Any] = Body(...),
    ) -> JSONResponse:
        leg = str(body.get("leg", "")).lower()
        if leg not in ("tp", "sl", "entry"):
            return JSONResponse(
                {"ok": False, "message": 'leg must be "tp", "sl", or "entry"'},
                status_code=400,
            )
        try:
            price = float(body["price"])
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"ok": False, "message": "price float required"}, status_code=400)
        if price <= 0:
            return JSONResponse({"ok": False, "message": "price must be positive"}, status_code=400)
        _runtime().queue_command(
            {
                "type": "bracket_adjust",
                "bracket_id": bracket_id,
                "leg": leg,
                "new_price": price,
            }
        )
        return JSONResponse(
            {
                "ok": True,
                "queued": "bracket_adjust",
                "bracket_id": bracket_id,
                "leg": leg,
                "price": price,
            }
        )

    @app.post("/brackets/{bracket_id}/cancel")
    async def bracket_cancel(bracket_id: str) -> JSONResponse:
        _runtime().queue_command({"type": "bracket_cancel", "bracket_id": bracket_id})
        return JSONResponse(
            {"ok": True, "queued": "bracket_cancel", "bracket_id": bracket_id}
        )

    @app.post("/offers/{sequence}/cancel")
    async def offer_cancel(sequence: int) -> JSONResponse:
        _runtime().queue_command({"type": "offer_cancel", "sequence": sequence})
        return JSONResponse({"ok": True, "queued": "offer_cancel", "sequence": sequence})

    @app.post("/offers/{sequence}/adjust")
    async def offer_adjust(
        sequence: int,
        body: Dict[str, Any] = Body(...),
    ) -> JSONResponse:
        try:
            price = float(body["price"])
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"ok": False, "message": "price float required"}, status_code=400)
        if price <= 0:
            return JSONResponse({"ok": False, "message": "price must be positive"}, status_code=400)
        _runtime().queue_command(
            {"type": "offer_adjust", "sequence": sequence, "new_price": price}
        )
        return JSONResponse(
            {
                "ok": True,
                "queued": "offer_adjust",
                "sequence": sequence,
                "price": price,
            }
        )

    logger.debug("alpha_hud_operator_routes_registered")
