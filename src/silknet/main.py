"""SILKNET command-line entry point."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from silknet.app import create_application
from silknet.single_instance import SingleInstanceGuard, activate_window

logger = logging.getLogger(__name__)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    guard = SingleInstanceGuard()
    if not guard.try_acquire():
        # The first instance received the activation message and is already
        # coming forward; this process has nothing else to do.
        return 0

    try:
        app, window = create_application(sys.argv, app=app)
    except Exception as exc:
        guard.close()
        logger.exception("Alya SILKNET could not start")
        QMessageBox.critical(
            None,
            "Alya SILKNET could not start",
            f"Alya SILKNET could not initialize its local workspace.\n\n{exc}",
        )
        return 1

    guard.activation_requested.connect(lambda: activate_window(window))
    app.aboutToQuit.connect(guard.close)
    window.show()
    window.play_intro()
    return app.exec()
