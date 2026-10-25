"""Application bootstrap and dependency wiring."""

from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from silknet import __version__
from silknet.config import AppPaths, AppSettings, load_settings
from silknet.database.connection import initialize_database
from silknet.logging_config import configure_logging
from silknet.services.container import create_services
from silknet.ui.assets import app_icon
from silknet.ui.main_window import SilknetWindow

logger = logging.getLogger(__name__)


def _claim_taskbar_identity() -> None:
    """Give the process its own taskbar identity so the Alya icon is used.

    Without an explicit AppUserModelID Windows groups the process under
    ``pythonw.exe`` and shows the Python icon in the taskbar instead of the
    window icon.
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Alya.SILKNET.Desktop.1")
    except (AttributeError, OSError):
        pass


def create_application(
    argv: Sequence[str] | None = None,
    paths: AppPaths | None = None,
    settings: AppSettings | None = None,
    app: QApplication | None = None,
) -> tuple[QApplication, SilknetWindow]:
    app_paths = paths or AppPaths.from_environment()
    app_paths.ensure_directories()
    configure_logging(app_paths.log_file)
    app_settings = settings or load_settings(app_paths.settings_file)
    initialize_database(app_paths.database_file)
    services = create_services(app_paths.database_file)

    application = app or QApplication(list(sys.argv if argv is None else argv))
    _claim_taskbar_identity()
    application.setStyle("Fusion")
    application.setApplicationName("Alya SILKNET")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("SILKNET")
    application.setWindowIcon(app_icon())
    window = SilknetWindow(app_settings, app_paths.settings_file, services)
    logger.info("Alya SILKNET %s initialized", __version__)
    return application, window
