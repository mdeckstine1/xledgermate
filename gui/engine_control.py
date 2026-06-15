"""Start/stop the trading engine as a subprocess (avoids Streamlit asyncio conflicts)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / "logs" / "engine.pid"
PARENT_PID_FILE = ROOT / "logs" / "engine.parent.pid"
STOP_FILE = ROOT / "logs" / "engine.stop"
SYSTEMD_UNIT = Path("/etc/systemd/system/xledgermate.service")

# Production path (Ashigaru / Phase E). Legacy poll engine is deprecated.
ENGINE_MODE = "ws-engine"
LEGACY_ENGINE_MODE = "engine"


def _python_exe() -> str:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    venv_bin = ROOT / ".venv" / "bin" / "python"
    if venv_bin.exists():
        return str(venv_bin)
    return sys.executable


def _command_line_is_engine_mode(command_line: str | None) -> bool:
    """True for ws-engine (production) or legacy --mode engine."""
    return _command_line_is_trading_engine(command_line)


def _command_line_is_trading_engine(command_line: str | None) -> bool:
    if not command_line:
        return False
    lowered = command_line.lower()
    if "main.py" not in lowered or "--mode" not in lowered:
        return False
    if "--mode ws-engine" in lowered:
        return True
    return bool(re.search(r"--mode\s+engine(?:\s|$|\")", lowered))


def _command_line_is_legacy_engine(command_line: str | None) -> bool:
    if not command_line:
        return False
    lowered = command_line.lower()
    if "ws-engine" in lowered:
        return False
    return bool(re.search(r"--mode\s+engine(?:\s|$|\")", lowered)) and "main.py" in lowered


def _systemd_unit_available() -> bool:
    return sys.platform != "win32" and SYSTEMD_UNIT.is_file()


def _systemd_is_active() -> bool:
    if not _systemd_unit_available():
        return False
    result = subprocess.run(
        ["systemctl", "is-active", "xledgermate"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or "").strip() == "active"


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in (result.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pgrep_pattern(pattern: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: list[int] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _find_engine_pids() -> list[int]:
    """Find ws-engine (production) and legacy poll engine processes."""
    pids: list[int] = []
    if sys.platform == "win32":
        script = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -match '^(?i)python(3(\\.\\d+)?)?\\.exe$' "
            "-and $_.CommandLine -match 'main\\.py' "
            "-and ($_.CommandLine -match '--mode ws-engine' "
            "-or $_.CommandLine -match '--mode engine( |\\\")') } | "
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
        pids.extend(_pgrep_pattern("main.py --mode ws-engine"))
        pids.extend(_pgrep_pattern("main.py --mode engine"))
    return sorted(set(pids))


def _find_legacy_engine_pids() -> list[int]:
    if sys.platform == "win32":
        all_pids = _find_engine_pids()
        return [
            pid
            for pid in all_pids
            if _command_line_is_legacy_engine(_read_process_cmdline(pid))
        ]
    return _pgrep_pattern("main.py --mode engine")


def _read_process_cmdline(pid: int) -> str | None:
    if sys.platform == "win32":
        return None
    proc = Path(f"/proc/{pid}/cmdline")
    if not proc.exists():
        return None
    try:
        return proc.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace")
    except OSError:
        return None


def _kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        import signal

        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            os.kill(pid, signal.SIGTERM)


def _request_engine_stop() -> None:
    STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.write_text("stop", encoding="utf-8")


def _clear_stop_files() -> None:
    STOP_FILE.unlink(missing_ok=True)
    PID_FILE.unlink(missing_ok=True)
    PARENT_PID_FILE.unlink(missing_ok=True)


def stop_legacy_engines() -> tuple[int, str]:
    """Stop only the deprecated HTTP poll engine (--mode engine)."""
    targets = set(_find_legacy_engine_pids())
    stopped: list[int] = []
    for pid in sorted(targets, reverse=True):
        _kill_pid(pid)
        stopped.append(pid)
    if stopped:
        time.sleep(0.5)
    remaining = _find_legacy_engine_pids()
    if remaining:
        return len(stopped), f"Legacy engine may still run (pids {remaining})."
    if stopped:
        return len(stopped), f"Stopped legacy poll engine: {stopped}"
    return 0, "No legacy poll engine running."


def stop_all_engines() -> tuple[int, str]:
    """Stop every trading engine (systemd + ws-engine + legacy poll)."""
    _request_engine_stop()
    parts: list[str] = []

    if _systemd_unit_available() and _systemd_is_active():
        subprocess.run(
            ["systemctl", "stop", "xledgermate"],
            capture_output=True,
            check=False,
        )
        parts.append("systemd xledgermate stopped")
        time.sleep(1.0)

    targets: set[int] = set(_find_engine_pids())
    for path in (PID_FILE, PARENT_PID_FILE):
        if path.exists():
            try:
                targets.add(int(path.read_text(encoding="utf-8").strip()))
            except ValueError:
                pass

    stopped: list[int] = []
    for pid in sorted(targets, reverse=True):
        if pid in stopped:
            continue
        _kill_pid(pid)
        stopped.append(pid)

    time.sleep(0.75)

    for pid in _find_engine_pids():
        if pid not in stopped:
            _kill_pid(pid)
            stopped.append(pid)

    _clear_stop_files()

    if not stopped and not parts:
        return 0, "No engine processes were running."
    remaining = _find_engine_pids()
    base = " · ".join(parts) if parts else ""
    if remaining:
        msg = f"Stopped {len(stopped)} process(es) {stopped}, still running: {remaining}"
        return len(stopped), f"{base} — {msg}" if base else msg
    msg = f"Stopped {len(stopped)} engine process(es): {stopped}"
    return len(stopped), f"{base} — {msg}" if base else msg


def is_kill_switch_active() -> bool:
    """Read kill_switch.json directly (not stale runtime_state.json)."""
    from risk.kill_switch import KillSwitch

    return KillSwitch().is_active()


def kill_switch_reason() -> str:
    from risk.kill_switch import KillSwitch

    return KillSwitch().reason


def is_engine_running() -> bool:
    if _systemd_is_active():
        return True

    pids = _find_engine_pids()
    if pids:
        PID_FILE.write_text(str(pids[-1]), encoding="utf-8")
        return True

    for path in (PID_FILE, PARENT_PID_FILE):
        if not path.exists():
            continue
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            continue
        if _is_process_alive(pid):
            return True

    _clear_stop_files()
    return False


def is_ws_engine_running() -> bool:
    if _systemd_is_active():
        return True
    return any(
        not _command_line_is_legacy_engine(_read_process_cmdline(pid))
        for pid in _find_engine_pids()
    ) or bool(_pgrep_pattern("main.py --mode ws-engine"))


def engine_mode_label() -> str:
    """Human label for operator UI: ws-engine | legacy-poll | stopped."""
    if not is_engine_running():
        return "stopped"
    legacy = any(
        _command_line_is_legacy_engine(_read_process_cmdline(pid))
        for pid in _find_engine_pids()
    )
    if legacy and not is_ws_engine_running():
        return "legacy-poll"
    return "ws-engine"


def start_engine(*, force_restart: bool = True) -> tuple[bool, str]:
    if force_restart:
        stop_all_engines()

    if is_engine_running():
        pid = PID_FILE.read_text(encoding="utf-8").strip() if PID_FILE.exists() else "?"
        return False, f"Engine already running (pid {pid})."

    stop_legacy_engines()

    if _systemd_unit_available():
        result = subprocess.run(
            ["systemctl", "start", "xledgermate"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and _systemd_is_active():
            return True, "WS pure A-S engine started (systemd → main.py --mode ws-engine)."
        err = (result.stderr or result.stdout or "systemctl start failed").strip()
        return False, err[-2000:]

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    STOP_FILE.unlink(missing_ok=True)

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]

    proc = subprocess.Popen(
        [_python_exe(), "main.py", "--mode", ENGINE_MODE],
        cwd=str(ROOT),
        creationflags=creationflags,
    )
    PARENT_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    return True, f"WS pure A-S engine started (pid {proc.pid}, --mode {ENGINE_MODE})."


def stop_engine() -> tuple[bool, str]:
    count, msg = stop_all_engines()
    if count == 0 and "No engine" in msg:
        return False, "Engine is not running."
    return True, msg


def restart_engine(*, clear_kill: bool = True) -> tuple[bool, str]:
    """
    Stop all engine processes and start fresh.

    By default clears the persisted kill switch (survives ordinary restarts) and
    resets the in-memory toxic fill window on the new process.
    """
    parts: list[str] = []
    if clear_kill:
        ok_kill, kill_msg = clear_kill_switch()
        parts.append(kill_msg if ok_kill else f"Kill clear failed: {kill_msg}")
    stop_all_engines()
    time.sleep(0.5)
    ok, start_msg = start_engine(force_restart=False)
    parts.append(start_msg)
    return ok, " ".join(parts)


def cancel_offers_on_ledger() -> tuple[bool, str]:
    """Cancel via in-process XRPL (reliable credentials path) and refresh runtime_state."""
    import concurrent.futures

    from config.settings import BotConfig
    from utils.offer_cancel import cancel_all_offers_and_sync_sync

    def _run() -> tuple[bool, str, int, int]:
        return cancel_all_offers_and_sync_sync(BotConfig.load())

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            ok, msg, _cancelled, _remaining = pool.submit(_run).result(timeout=180)
    except concurrent.futures.TimeoutError:
        return False, "Cancel offers timed out after 180s."
    except ValueError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)[-2000:]
    return ok, msg


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


def disable_rlusd_rippling() -> tuple[bool, str]:
    result = subprocess.run(
        [_python_exe(), "main.py", "--mode", "trust-no-ripple"],
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
        lower = line.lower()
        if "rippling disabled" in lower or "already has rippling disabled" in lower:
            return True, line.strip()
    return True, "RLUSD rippling disabled (No Ripple) on the ledger."


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


def manual_rebalance_check() -> tuple[bool, str]:
    """Live balances + rebalance advice; updates runtime_state.json (in-process, no subprocess)."""
    import asyncio
    import concurrent.futures

    from config.settings import BotConfig
    from utils.manual_rebalance import run_manual_rebalance_check

    def _run_async() -> str:
        return asyncio.run(run_manual_rebalance_check(BotConfig.load()))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            message = pool.submit(_run_async).result(timeout=120)
        return True, message
    except concurrent.futures.TimeoutError:
        return False, "Rebalance check timed out after 120s."
    except Exception as exc:
        return False, str(exc)[-2000:]


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
