"""Single-instance coordination for the desktop application."""

from __future__ import annotations

import ctypes
import getpass
import hashlib
import sys
import time

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QWidget

_ACTIVATION_MESSAGE = b"ALYA-SILKNET-ACTIVATE"
_ACTIVATION_ACK = b"ALYA-SILKNET-ACTIVE"
_CONNECT_TIMEOUT_MS = 400
_ACK_TIMEOUT_SECONDS = 0.8


def server_name() -> str:
    """Return a per-user local server name shared by source and packaged runs."""
    try:
        user = getpass.getuser()
    except (OSError, KeyError):
        user = "default"
    user_key = hashlib.sha256(user.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"Alya.SILKNET.Desktop.{user_key}"


class SingleInstanceGuard(QObject):
    """Own a local server and notify the first instance when another one starts."""

    activation_requested = Signal()

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = name or server_name()
        self._server: QLocalServer | None = None
        self._sockets: set[QLocalSocket] = set()

    @property
    def name(self) -> str:
        return self._name

    def try_acquire(self) -> bool:
        """Become the primary instance, or ask the running one to come forward."""
        if self._notify_existing():
            return False

        # No live server answered. Remove a stale endpoint left by a crash and
        # claim it for this process.
        QLocalServer.removeServer(self._name)
        server = QLocalServer(self)
        server.newConnection.connect(self._accept_connections)
        if not server.listen(self._name):
            # A second process may have won the race between the probe and
            # listen(). Try once more to hand activation to it.
            if self._notify_existing():
                return False
            # Failing open is safer than making the application unusable.
            return True
        self._server = server
        return True

    def close(self) -> None:
        """Release the local endpoint during a normal application shutdown."""
        owns_server = self._server is not None
        if self._server is not None:
            self._server.close()
            self._server = None
        for socket in tuple(self._sockets):
            socket.abort()
        self._sockets.clear()
        if owns_server:
            QLocalServer.removeServer(self._name)

    def _notify_existing(self) -> bool:
        allow_foreground_activation()
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(_CONNECT_TIMEOUT_MS):
            return False
        socket.write(_ACTIVATION_MESSAGE)
        socket.flush()

        # Keep this short-lived process alive until the running instance has
        # read the message. Otherwise the socket can be destroyed before Qt
        # flushes the write, and the existing window never comes forward.
        deadline = time.monotonic() + _ACK_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            if socket.bytesAvailable():
                socket.readAll()
                break
            if socket.state() == QLocalSocket.LocalSocketState.UnconnectedState:
                break
            time.sleep(0.01)
        socket.disconnectFromServer()
        return True

    def _accept_connections(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            self._sockets.add(socket)
            socket.readyRead.connect(lambda current=socket: self._read_activation(current))
            socket.disconnected.connect(lambda current=socket: self._forget(current))
            # Data may already be buffered before readyRead is connected, so
            # inspect the socket immediately as well.
            self._read_activation(socket)

    def _read_activation(self, socket: QLocalSocket) -> None:
        data = bytes(socket.readAll())
        if _ACTIVATION_MESSAGE not in data:
            return
        if not socket.property("alyaActivationHandled"):
            socket.setProperty("alyaActivationHandled", True)
            self.activation_requested.emit()
        socket.write(_ACTIVATION_ACK)
        socket.flush()

    def _forget(self, socket: QLocalSocket) -> None:
        self._sockets.discard(socket)
        socket.deleteLater()


def activate_window(window: QWidget) -> None:
    """Bring the existing main window to the front on every supported desktop."""
    if window.isMinimized():
        window.showNormal()
    window.show()
    window.raise_()
    window.activateWindow()
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.SetForegroundWindow(int(window.winId()))
        except (AttributeError, OSError, TypeError, ValueError):
            pass


def allow_foreground_activation() -> None:
    """Let the already-running instance take focus from this short-lived launch."""
    if sys.platform != "win32":
        return
    try:
        # ASFW_ANY (-1) is valid here because this process was just launched by
        # the user and is about to exit without showing a window.
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
    except (AttributeError, OSError):
        pass
