"""Application bootstrap: Qt app, dark palette, window, command-line files."""
from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME, __version__, icons
from .window import LumaWindow


def _dark_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(18, 20, 28))
    pal.setColor(QPalette.WindowText, QColor(236, 239, 247))
    pal.setColor(QPalette.Base, QColor(22, 24, 34))
    pal.setColor(QPalette.AlternateBase, QColor(28, 30, 42))
    pal.setColor(QPalette.Text, QColor(236, 239, 247))
    pal.setColor(QPalette.Button, QColor(30, 33, 46))
    pal.setColor(QPalette.ButtonText, QColor(236, 239, 247))
    pal.setColor(QPalette.Highlight, QColor(110, 123, 255))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.ToolTipBase, QColor(22, 24, 34))
    pal.setColor(QPalette.ToolTipText, QColor(236, 239, 247))
    return pal


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if any(a in ("-v", "--version") for a in argv[1:]):
        print(f"{APP_NAME} {__version__}")
        return 0

    if sys.platform.startswith("win"):
        # own taskbar icon/grouping instead of python.exe's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("luma")
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setWindowIcon(icons.logo_icon())
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)

    window = LumaWindow()
    window.show()
    if not window.start_engine():
        return 1

    files = [a for a in argv[1:] if not a.startswith("-")]
    if files:
        window.open_paths(files)
    return app.exec()
