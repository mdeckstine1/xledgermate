"""GUI module for XLedgerMate - Live tuning interface."""


def run_gui() -> None:
    from .streamlit_gui import run_gui as _run_gui

    _run_gui()


__all__ = ["run_gui"]
