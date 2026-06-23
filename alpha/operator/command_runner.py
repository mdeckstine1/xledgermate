"""Run queued HUD operator commands immediately (cancel / adjust)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from alpha.runtime.application import AlphaApplication

logger = logging.getLogger(__name__)


async def process_queued_commands(*, publish_hud: bool = True) -> Dict[str, Any]:
    """
    Drain ``logs/alpha_commands.json`` now and refresh HUD state.

    Used by the HUD cancel path so operators do not wait for the next trading cycle.
    """
    app, validation = AlphaApplication.from_config_file()
    if not validation.ok:
        return {"ok": False, "processed": 0, "message": validation.summary()}
    processed = 0
    try:
        if not app.runtime.has_pending_commands():
            return {"ok": True, "processed": 0, "message": "no_commands"}
        await app._sync_operator_runtime()  # noqa: SLF001
        processed = 1
        if publish_hud:
            snap, _validation, decision, orders = await app._gather_cycle_context()  # noqa: SLF001
            app._publish_hud_state(snap, decision, orders, None, "")  # noqa: SLF001
        return {"ok": True, "processed": processed, "message": "commands_processed"}
    except Exception as exc:
        logger.exception("operator_command_runner_failed | %s", exc)
        return {"ok": False, "processed": processed, "message": str(exc)}
    finally:
        await app.close()


def process_queued_commands_sync(*, publish_hud: bool = True) -> Dict[str, Any]:
    """Blocking wrapper for FastAPI ``run_in_executor``."""
    return asyncio.run(process_queued_commands(publish_hud=publish_hud))
