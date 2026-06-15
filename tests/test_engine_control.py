from gui.engine_control import (
    _command_line_is_engine_mode,
    _command_line_is_legacy_engine,
    _command_line_is_trading_engine,
)


def test_command_line_is_engine_mode() -> None:
    assert _command_line_is_engine_mode(
        r"C:\repo\.venv\Scripts\python.exe main.py --mode engine"
    )
    assert _command_line_is_engine_mode(
        r"C:\repo\.venv\Scripts\python.exe main.py --mode ws-engine"
    )
    assert _command_line_is_trading_engine("python main.py --mode ws-engine")
    assert not _command_line_is_legacy_engine("python main.py --mode ws-engine")
    assert _command_line_is_legacy_engine("python main.py --mode engine")
    assert not _command_line_is_engine_mode("python main.py --mode gui")
    assert not _command_line_is_engine_mode("python main.py --mode once")
    assert not _command_line_is_engine_mode(None)
    assert not _command_line_is_engine_mode("")
