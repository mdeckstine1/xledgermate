from gui.engine_control import _command_line_is_engine_mode


def test_command_line_is_engine_mode() -> None:
    assert _command_line_is_engine_mode(
        r"C:\repo\.venv\Scripts\python.exe main.py --mode engine"
    )
    assert _command_line_is_engine_mode(
        '"C:\\Python312\\python.exe" main.py --mode engine'
    )
    assert not _command_line_is_engine_mode("python main.py --mode gui")
    assert not _command_line_is_engine_mode("python main.py --mode once")
    assert not _command_line_is_engine_mode(None)
    assert not _command_line_is_engine_mode("")
