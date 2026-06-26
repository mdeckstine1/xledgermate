"""Alpha HUD PRO routes — replay, defensive circuit, treasury placeholder."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_STATE_DIR = Path("logs")
_OVERRIDES = _STATE_DIR / "alpha_overrides.json"
_COMMANDS = _STATE_DIR / "alpha_commands.json"
_CIRCUIT = _STATE_DIR / "alpha_defensive_circuit.json"


def register_pro_routes(app: Any) -> None:
    from fastapi import Query
    from fastapi.responses import JSONResponse

    from alpha.operator.runtime import OperatorRuntimeStore
    from alpha.pro.circuit_breaker import DefensiveCircuit, defensive_status_snapshot
    from alpha.pro.replay import build_replay_report, format_replay_report_text
    from alpha.pro.treasury import treasury_placeholder_status
    from config.settings import BotConfig

    def _runtime() -> OperatorRuntimeStore:
        return OperatorRuntimeStore(overrides_path=_OVERRIDES, commands_path=_COMMANDS)

    def _circuit() -> DefensiveCircuit:
        return DefensiveCircuit(store=_runtime(), state_path=_CIRCUIT)

    @app.get("/operator/pro/status")
    async def get_pro_status() -> JSONResponse:
        cfg = BotConfig.load()
        status = defensive_status_snapshot(logs_dir=_STATE_DIR, config=cfg)
        status["treasury"] = treasury_placeholder_status(logs_dir=_STATE_DIR)
        return JSONResponse({"ok": True, **status})

    @app.get("/operator/pro/replay")
    async def get_pro_replay(hours: float = Query(168.0, ge=1.0, le=720.0)) -> JSONResponse:
        report = build_replay_report(logs_dir=_STATE_DIR, hours=hours)
        return JSONResponse(
            {
                "ok": True,
                "report": report,
                "text": format_replay_report_text(report),
            }
        )

    @app.post("/operator/pro/circuit/release")
    async def post_pro_circuit_release() -> JSONResponse:
        cfg = BotConfig.load()
        result = _circuit().release_manual(cfg)
        ok = result.get("event") == "released"
        return JSONResponse({"ok": ok, **result})

    @app.post("/operator/pro/circuit/evaluate")
    async def post_pro_circuit_evaluate() -> JSONResponse:
        """Force one defensive circuit evaluation (same logic as engine cycle)."""
        cfg = BotConfig.load()
        result = _circuit().tick(cfg, logs_dir=_STATE_DIR, force_evaluate=True)
        return JSONResponse({"ok": True, **result})
