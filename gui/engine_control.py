"""Start/stop the trading engine as a subprocess (avoids Streamlit asyncio conflicts)."""

from __future__ import annotations

import os
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


def _find_engine_pids() -> list[int]:
    """Find all python processes running main.py --mode engine."""
    pids: list[int] = []
    if sys.platform == "win32":
        script = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -like '*main.py*--mode*engine*' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(ROOT),
        )
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
    else:
        result = subprocess.run(
            ["pgrep", "-f", "main.py --mode engine"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
    return sorted(set(pids))


def _kill_pid(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        import signal

        os.kill(pid, signal.SIGTERM)


def stop_all_engines() -> tuple[int, str]:
    """Stop every running engine process (PID file + orphan scan)."""
    stopped: list[int] = []

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            _kill_pid(pid)
            stopped.append(pid)
        except ValueError:
            pass
        PID_FILE.unlink(missing_ok=True)

    for pid in _find_engine_pids():
        if pid not in stopped:
            _kill_pid(pid)
            stopped.append(pid)

    if not stopped:
        return 0, "No engine processes were running."
    return len(stopped), f"Stopped {len(stopped)} engine process(es): {stopped}"


def is_engine_running() -> bool:
    pids = _find_engine_pids()
    if pids:
        PID_FILE.write_text(str(pids[-1]), encoding="utf-8")
        return True
    PID_FILE.unlink(missing_ok=True)
    return False


def start_engine(*, force_restart: bool = True) -> tuple[bool, str]:
    if force_restart:
        stop_all_engines()

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
    count, msg = stop_all_engines()
    if count == 0:
        return False, "Engine is not running."
    return True, msg


def cancel_offers_on_ledger() -> tuple[bool, str]:
    result = subprocess.run(
        [_python_exe(), "main.py", "--mode", "cancel-offers"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown error").strip()
        return False, err[-2000:]
    return True, "All open offers cancelled on the ledger."


def clear_kill_switch() -> tuple[bool, str]:
    result = subprocess.run(
        [_python_exe(), "main.py", "--mode", "clear-kill"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown error").strip()
        return False, err[-2000:]
    return True, "Kill switch cleared."


def setup_trust_line() -> tuple[bool, str]:
    result = subprocess.run(
        [_python_exe(), "main.py", "--mode", "setup-trust"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown error").strip()
        return False, err[-2000:]
    for line in (result.stdout or "").splitlines():
        if "trust line submitted" in line.lower():
            return True, line.strip()
    return True, "RLUSD trust line created on the ledger."


def send_funds(destination: str, amount: float, asset: str = "XRP") -> tuple[bool, str]:
    """Send XRP or RLUSD from bot account via subprocess."""
    dest = (destination or "").strip()
    if not dest.startswith("r"):
        return False, "Destination must be a classic XRPL address (starts with r)."
    if amount <= 0:
        return False, "Amount must be greater than zero."

    result = subprocess.run(
        [
            _python_exe(),
            "main.py",
            "--mode",
            "send",
            "--to",
            dest,
            "--amount",
            str(amount),
            "--asset",
            asset.upper(),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown error").strip()
        return False, err[-2000:]
    for line in (result.stdout or "").splitlines():
        if "tx=" in line.lower() or "hash=" in line.lower():
            return True, line.strip()
    return True, f"Sent {amount} {asset.upper()} to {dest}."


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
