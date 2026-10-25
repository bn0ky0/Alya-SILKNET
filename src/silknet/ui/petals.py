"""Kawaii blossom overlay used by the Alya pink theme."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import QWidget

_PETAL_COLORS = ("#FFC3D9", "#FFB2CE", "#FFD9E7", "#F7A5C3", "#FFE6F0", "#F490B4")


@dataclass
class _Petal:
    x: float
    y: float
    speed: float
    drift: float
    phase: float
    spin: float
    spin_speed: float
    color: QColor
    alpha: int
    path: QPainterPath


class PetalOverlay(QWidget):
    """Mouse-transparent layer of blossoms drifting across the window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._petals: list[_Petal] = []
        self._rng = random.Random(11)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance)

    # ------------------------------------------------------------------ state
    def start(self) -> None:
        width = max(self.width(), 320)
        height = max(self.height(), 240)
        if not self._petals:
            count = max(14, min(24, width // 70))
            self._petals = [self._spawn(width, height, spread=True) for _ in range(count)]
        if not self._timer.isActive():
            self._timer.start()
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        limit = max(0, self.width())
        for petal in self._petals:
            petal.x = min(petal.x, float(limit))
            petal.y = min(petal.y, float(max(0, self.height())))

    # ------------------------------------------------------------------ petals
    def _spawn(self, width: int, height: int, *, spread: bool = False) -> _Petal:
        rng = self._rng
        size = rng.uniform(5.0, 11.0)
        petal_width = size
        petal_height = size * 1.35
        path = QPainterPath()
        path.moveTo(0, -petal_height / 2)
        path.cubicTo(
            petal_width / 2,
            -petal_height / 4,
            petal_width / 2,
            petal_height / 3,
            0,
            petal_height / 2,
        )
        path.cubicTo(
            -petal_width / 2,
            petal_height / 3,
            -petal_width / 2,
            -petal_height / 4,
            0,
            -petal_height / 2,
        )
        return _Petal(
            x=rng.uniform(-10.0, float(width)),
            y=rng.uniform(0.0, float(height)) if spread else rng.uniform(-40.0, -8.0),
            speed=rng.uniform(0.55, 1.55),
            drift=rng.uniform(-0.22, 0.32),
            phase=rng.uniform(0.0, math.tau),
            spin=rng.uniform(0.0, 360.0),
            spin_speed=rng.uniform(-0.9, 0.9),
            color=QColor(rng.choice(_PETAL_COLORS)),
            alpha=rng.randint(120, 195),
            path=path,
        )

    def _advance(self) -> None:
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        for index, petal in enumerate(self._petals):
            petal.phase += 0.045
            petal.y += petal.speed
            petal.x += petal.drift + 0.42 * math.sin(petal.phase)
            petal.spin += petal.spin_speed
            if petal.y > height + 24:
                self._petals[index] = self._spawn(width, height)
        self.update()

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event: QPaintEvent) -> None:
        if not self._petals:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for petal in self._petals:
            painter.save()
            painter.translate(petal.x, petal.y)
            painter.rotate(petal.spin)
            color = QColor(petal.color)
            color.setAlpha(petal.alpha)
            painter.setBrush(color)
            painter.drawPath(petal.path)
            painter.restore()
        painter.end()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)
