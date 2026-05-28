"""Start/stop the trading engine as a subprocess (avoids Streamlit asyncio conflicts)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / "logs" / "engine.pid"


def _python_exe() -> str:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def is_engine_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        PID_FILE.unlink(missing_ok=True)
        return False

    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        running = str(pid) in result.stdout
    else:
        import os

        try:
            os.kill(pid, 0)
            running = True
        except OSError:
            running = False

    if not running:
        PID_FILE.unlink(missing_ok=True)
    return running


def start_engine() -> tuple[bool, str]:
    if is_engine_running():
        pid = PID_FILE.read_text(encoding="utf-8").strip()
        return False, f"Engine already running (pid {pid})."

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]

    proc = subprocess.Popen(
        [_python_exe(), "main.py", "--mode", "engine"],
        cwd=str(ROOT),
        creationflags=creationflags,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    return True, f"Engine started in a new window (pid {proc.pid})."


def stop_engine() -> tuple[bool, str]:
    if not PID_FILE.exists():
        return False, "Engine is not running."

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        PID_FILE.unlink(missing_ok=True)
        return False, "Engine is not running."

    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        import os
        import signal

        os.kill(pid, signal.SIGTERM)

    PID_FILE.unlink(missing_ok=True)
    return True, f"Engine stopped (pid {pid})."


def run_single_cycle() -> tuple[bool, str]:
    """Run one market cycle in a subprocess (no asyncio inside Streamlit)."""
    result = subprocess.run(
        [_python_exe(), "main.py", "--mode", "once"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown error").strip()
        return False, err[-2000:]
    return True, "Single cycle completed. Refresh to see runtime snapshot."
