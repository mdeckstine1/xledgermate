"""Alpha HUD config and wallet routes — account IDs, credentials, withdraw."""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

_COMMANDS = __import__("pathlib").Path("logs/alpha_commands.json")


def register_config_routes(app: Any) -> None:
    from fastapi import Body
    from fastapi.responses import JSONResponse

    from alpha.hud.account_config import (
        account_config_snapshot,
        apply_account_config_updates,
        is_alpha_engine_running,
        read_recent_transfers,
    )
    from alpha.operator.runtime import OperatorRuntimeStore
    from config.settings import patch_config_file

    def _runtime() -> OperatorRuntimeStore:
        return OperatorRuntimeStore(commands_path=_COMMANDS)

    @app.get("/operator/account-config")
    async def get_account_config() -> JSONResponse:
        snap = account_config_snapshot()
        snap["engine_running"] = is_alpha_engine_running()
        return JSONResponse({"ok": True, "account_config": snap})

    @app.patch("/operator/account-config")
    async def patch_account_config(body: Dict[str, Any] = Body(...)) -> JSONResponse:
        updates = body.get("updates") if isinstance(body.get("updates"), dict) else body
        if not isinstance(updates, dict) or not updates:
            return JSONResponse({"ok": False, "message": "updates object required"}, status_code=400)
        snap, errors = apply_account_config_updates(updates)
        if errors:
            return JSONResponse({"ok": False, "errors": errors}, status_code=400)
        _runtime().queue_command({"type": "config_reload"})
        return JSONResponse(
            {
                "ok": True,
                "account_config": snap,
                "queued": "config_reload",
            }
        )

    @app.get("/operator/transfers")
    async def get_transfers() -> JSONResponse:
        return JSONResponse({"ok": True, "transfers": read_recent_transfers()})

    @app.post("/operator/send-funds")
    async def post_send_funds(body: Dict[str, Any] = Body(...)) -> JSONResponse:
        destination = str(body.get("destination") or "").strip()
        asset = str(body.get("asset") or "XRP").strip().upper()
        try:
            amount = float(body.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        confirm_text = str(body.get("confirm_text") or "").strip().upper()
        confirm_engine_running = bool(body.get("confirm_engine_running"))

        if confirm_text != "SEND":
            return JSONResponse(
                {
                    "ok": False,
                    "message": 'Type SEND in the confirmation box to authorize withdrawal.',
                },
                status_code=400,
            )
        if not destination.startswith("r"):
            return JSONResponse(
                {"ok": False, "message": "Destination must be a classic XRPL address (r…)."},
                status_code=400,
            )
        if amount <= 0:
            return JSONResponse(
                {"ok": False, "message": "Amount must be greater than zero."},
                status_code=400,
            )
        if asset not in ("XRP", "RLUSD"):
            return JSONResponse(
                {"ok": False, "message": "Asset must be XRP or RLUSD."},
                status_code=400,
            )

        engine_up = is_alpha_engine_running()
        if engine_up and not confirm_engine_running:
            return JSONResponse(
                {
                    "ok": False,
                    "message": "Alpha engine is running — Pause trading and stop engine, or check the confirmation box.",
                    "engine_running": True,
                },
                status_code=400,
            )

        from config.settings import BotConfig

        config = BotConfig.load()
        if not (config.bot_account_address or "").strip():
            return JSONResponse(
                {"ok": False, "message": "bot_account_address is not configured."},
                status_code=400,
            )
        if not (config.bot_secret_key or "").strip():
            return JSONResponse(
                {
                    "ok": False,
                    "message": "bot_secret_key required — set in Config tab or credentials.local.yaml.",
                },
                status_code=400,
            )

        try:
            from utils.send_funds import send_from_bot_account

            tx_hash = await send_from_bot_account(
                destination=destination,
                amount=amount,
                asset=asset,
            )
        except Exception as exc:
            logger.warning("alpha_send_funds_failed | %s", exc)
            return JSONResponse({"ok": False, "message": str(exc)[:500]}, status_code=400)

        patch_config_file({"send_destination_default": destination})
        return JSONResponse(
            {
                "ok": True,
                "message": f"Sent {amount:g} {asset} to {destination}",
                "tx_hash": tx_hash,
                "transfers": read_recent_transfers(),
            }
        )

    logger.debug("alpha_hud_config_routes_registered")
