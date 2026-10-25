"""Bundled Sora typeface loading."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONT_FILES = (
    "Sora-Regular.ttf",
    "Sora-SemiBold.ttf",
    "Sora-Bold.ttf",
    "Sora-ExtraBold.ttf",
)
_loaded = False


def ensure_app_fonts() -> str:
    """Register the bundled Sora weights once and return the family name."""
    global _loaded
    family = "Sora"
    if not _loaded and QApplication.instance() is not None:
        for name in _FONT_FILES:
            path = _FONT_DIR / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
        families = set(QFontDatabase.families())
        if family not in families:
            family = "Segoe UI Variable Text"
        app = QApplication.instance()
        if app is not None:
            app.setFont(QFont(family, 10))
        _loaded = True
    return family
