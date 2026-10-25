"""Frameless window helpers: edge resizing and title-bar dragging.

SILKNET draws its own window chrome so it can show a truly transparent rounded
window on Windows. These helpers keep resizing and moving working without a
native frame: eight slim handles along the edges resize the window with plain
Qt geometry, and the top bar starts a system move.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QMainWindow, QWidget

_MARGIN = 5
_CORNER = 16

_POINTING = Qt.CursorShape.SizeFDiagCursor
_POINTING_REVERSE = Qt.CursorShape.SizeBDiagCursor
_VERTICAL = Qt.CursorShape.SizeVerCursor
_HORIZONTAL = Qt.CursorShape.SizeHorCursor

_HANDLE_SPECS: tuple[tuple[str, frozenset[str], Qt.CursorShape], ...] = (
    ("top-left", frozenset({"left", "top"}), _POINTING_REVERSE),
    ("top", frozenset({"top"}), _VERTICAL),
    ("top-right", frozenset({"right", "top"}), _POINTING),
    ("left", frozenset({"left"}), _HORIZONTAL),
    ("right", frozenset({"right"}), _HORIZONTAL),
    ("bottom-left", frozenset({"left", "bottom"}), _POINTING),
    ("bottom", frozenset({"bottom"}), _VERTICAL),
    ("bottom-right", frozenset({"right", "bottom"}), _POINTING_REVERSE),
)


class _ResizeHandle(QWidget):
    def __init__(
        self,
        window: QMainWindow,
        edges: frozenset[str],
        cursor: Qt.CursorShape,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._edges = edges
        self._start_geometry: QRect | None = None
        self._start_position: QPoint | None = None
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_geometry = self._window.frameGeometry()
            self._start_position = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._start_geometry is None or self._start_position is None:
            return
        delta = event.globalPosition().toPoint() - self._start_position
        geometry = QRect(self._start_geometry)
        minimum = self._window.minimumSize()
        left, top = geometry.left(), geometry.top()
        right, bottom = geometry.right(), geometry.bottom()
        if "left" in self._edges:
            left = min(left + delta.x(), right - minimum.width() + 1)
        if "right" in self._edges:
            right = max(right + delta.x(), left + minimum.width() - 1)
        if "top" in self._edges:
            top = min(top + delta.y(), bottom - minimum.height() + 1)
        if "bottom" in self._edges:
            bottom = max(bottom + delta.y(), top + minimum.height() - 1)
        self._window.setGeometry(QRect(QPoint(left, top), QPoint(right, bottom)))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._start_geometry = None
        self._start_position = None
        event.accept()


class ResizeHandler:
    """Owns the eight edge handles and keeps them aligned with the window."""

    def __init__(self, window: QMainWindow) -> None:
        self._window = window
        self._handles = {
            name: _ResizeHandle(window, edges, cursor) for name, edges, cursor in _HANDLE_SPECS
        }

    def reload(self) -> None:
        maximum = self._window.isMaximized() or self._window.isFullScreen()
        width, height = self._window.width(), self._window.height()
        geometry = {
            "top-left": QRect(0, 0, _CORNER, _CORNER),
            "top": QRect(_CORNER, 0, width - 2 * _CORNER, _MARGIN),
            "top-right": QRect(width - _CORNER, 0, _CORNER, _CORNER),
            "left": QRect(0, _CORNER, _MARGIN, height - 2 * _CORNER),
            "right": QRect(width - _MARGIN, _CORNER, _MARGIN, height - 2 * _CORNER),
            "bottom-left": QRect(0, height - _CORNER, _CORNER, _CORNER),
            "bottom": QRect(_CORNER, height - _MARGIN, width - 2 * _CORNER, _MARGIN),
            "bottom-right": QRect(width - _CORNER, height - _CORNER, _CORNER, _CORNER),
        }
        for name, handle in self._handles.items():
            handle.setGeometry(geometry[name])
            handle.setVisible(not maximum)
            if not maximum:
                handle.raise_()
