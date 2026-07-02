"""Alpha HUD operator API routes."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_STATE_DIR = Path("logs")
_OVERRIDES = _STATE_DIR / "alpha_overrides.json"
_COMMANDS = _STATE_DIR / "alpha_commands.json"
_KILL = _STATE_DIR / "kill_switch.json"
_COMMAND_EXECUTOR = ThreadPoolExecutor(max_workers=1)


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

    async def _queue_and_run(command: Dict[str, Any]) -> Dict[str, Any]:
        from alpha.operator.command_runner import process_queued_commands_sync

        _runtime().queue_command(command)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_COMMAND_EXECUTOR, process_queued_commands_sync)

    @app.get("/operator/config")
    async def get_operator_config() -> JSONResponse:
        base = _base_config()
        overrides = _runtime().load_overrides()
        effective = apply_overrides(base, overrides)
        return JSONResponse(
            {
                "ok": True,
                "config_effective": effective_config_snapshot(effective, overrides),
                "config_base": effective_config_snapshot(base, {}),
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
                "config_effective": effective_config_snapshot(effective, merged),
            }
        )

    @app.post("/operator/config/reload")
    async def post_config_reload() -> JSONResponse:
        _runtime().queue_command({"type": "config_reload"})
        return JSONResponse({"ok": True, "queued": "config_reload"})

    @app.post("/operator/walkaway")
    async def post_walkaway_preset() -> JSONResponse:
        """Apply walk-away bundle: trust-phase knobs + Agent Smith (not full SKYNET)."""
        from alpha.hud.skynet_agent import agent_status_payload, merge_agent_patch
        from alpha.hud.walkaway_preset import apply_walkaway_preset, walkaway_preset_payload

        base = _base_config()
        store = _runtime()
        merged, _agent, errors = apply_walkaway_preset(
            patch_overrides=lambda ov, base=base: store.patch_overrides(ov, base=base),
            merge_agent_patch=merge_agent_patch,
            base_config=base,
        )
        if errors:
            return JSONResponse({"ok": False, "errors": errors}, status_code=400)
        effective = apply_overrides(base, merged)
        return JSONResponse(
            {
                "ok": True,
                "message": walkaway_preset_payload()["description"],
                "operator_overrides": merged,
                "config_effective": effective_config_snapshot(effective, merged),
                "agent": agent_status_payload(),
            }
        )

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
        result = await _queue_and_run({"type": "cancel_all"})
        return JSONResponse({**result, "queued": "cancel_all"})

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
        result = await _queue_and_run(
            {
                "type": "bracket_adjust",
                "bracket_id": bracket_id,
                "leg": leg,
                "new_price": price,
            }
        )
        return JSONResponse(
            {
                **result,
                "queued": "bracket_adjust",
                "bracket_id": bracket_id,
                "leg": leg,
                "price": price,
            }
        )

    @app.post("/brackets/{bracket_id}/cancel")
    async def bracket_cancel(bracket_id: str) -> JSONResponse:
        result = await _queue_and_run({"type": "bracket_cancel", "bracket_id": bracket_id})
        return JSONResponse({**result, "queued": "bracket_cancel", "bracket_id": bracket_id})

    @app.post("/offers/{sequence}/cancel")
    async def offer_cancel(sequence: int) -> JSONResponse:
        result = await _queue_and_run({"type": "offer_cancel", "sequence": sequence})
        return JSONResponse({**result, "queued": "offer_cancel", "sequence": sequence})

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
        result = await _queue_and_run(
            {"type": "offer_adjust", "sequence": sequence, "new_price": price}
        )
        return JSONResponse(
            {
                **result,
                "queued": "offer_adjust",
                "sequence": sequence,
                "price": price,
            }
        )

    logger.debug("alpha_hud_operator_routes_registered")
