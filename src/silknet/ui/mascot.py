"""Alya-sama, the kawaii free-range pet of the Alya pink theme."""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QLabel, QWidget

from silknet.ui.assets import logo_pixmap

_MESSAGES = (
    "Nyanyame~! Alya is watching your graph.",
    "Source first, gossip later!",
    "Add a record. I believe in you.",
    "Pet me for good luck.",
    "Alya-sama approves this workspace.",
    "Baka! Back up your data.",
    "Tiny Alya, huge opinions.",
    "I am not a sticker. I am a lifestyle.",
    "No thoughts. Only sources.",
    "Your evidence is showing.",
    "I charge one headpat per graph.",
    "Rent-free on your desktop, as usual.",
    "I have been compressed for your convenience.",
    "Do not screenshot my bad side.",
    "This is my budget form. Still cute.",
    "I know what you did in the timeline.",
    "Click me again. I dare you.",
    "Alya is small, but the lore is enormous.",
    "Evidence first, snacks second.",
    "I am the softest little archivist.",
    "Do not cite me in your report.",
    "My sources say you should take a break.",
    "Nyaa~! I am basically a citation.",
    "One more record and we can nap.",
    "I saw that unsaved edit.",
    "Please stop dragging me into your conspiracies.",
    "The graph is plotting something.",
    "Headpats improve data integrity by 3%.",
    "Nyaa~! Your sources are safe with me.",
    "I have reviewed your claims. Cute.",
    "A tiny pet with a very large archive.",
    "Headpat accepted. Case closed.",
    "I found a clue. It was under the sofa.",
    "Please cite your snacks.",
    "My alibi? I was in the sidebar.",
    "This graph needs more sparkle.",
    "I am contractually obligated to be adorable.",
    "Drag me somewhere scandalous. Like Settings.",
    "I have no evidence, but I have vibes.",
    "Alya-sama is on break. Pet accordingly.",
    "The truth is out there. I am right here.",
    "One headpat, one verified source.",
    "I run on affection and local storage.",
    "No cloud. Just me and your data.",
    "I am the tiny guardian of this workspace.",
    "My cuteness is peer-reviewed.",
    "This is a safe space for silly theories.",
)


class _Avatar(QWidget):
    """Alya's portrait with a rose silhouette rim and a tiny idle bob."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(64, 64)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._pixmap: QPixmap | None = None
        self._outline: QPixmap | None = None
        self._cache_key: tuple[int, float] | None = None
        self._offset = 0.0
        self._glow = 0.0
        self._hovered = False
        self._animated = False
        self._animation = QPropertyAnimation(self, b"bob", self)
        self._animation.setDuration(2400)
        self._animation.setStartValue(-1.1)
        self._animation.setKeyValueAt(0.5, 1.1)
        self._animation.setEndValue(-1.1)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animation.setLoopCount(-1)
        self._pulse = QPropertyAnimation(self, b"glow", self)
        self._pulse.setDuration(420)
        self._pulse.setStartValue(0.0)
        self._pulse.setKeyValueAt(0.22, 1.0)
        self._pulse.setEndValue(0.0)
        self._pulse.setEasingCurve(QEasingCurve.Type.OutCubic)

    def get_bob(self) -> float:
        return self._offset

    def set_bob(self, value: float) -> None:
        self._offset = value
        self.update()

    bob = Property(float, get_bob, set_bob)

    def get_glow(self) -> float:
        return self._glow

    def set_glow(self, value: float) -> None:
        self._glow = max(0.0, min(1.0, float(value)))
        self.update()

    glow = Property(float, get_glow, set_glow)

    def set_animated(self, animated: bool) -> None:
        self._animated = animated
        if animated:
            self._animation.start()
        else:
            self._animation.stop()
            self._offset = 0.0
            self._glow = 0.0
            self._pulse.stop()
            self.update()

    def set_hovered(self, hovered: bool) -> None:
        if self._hovered != hovered:
            self._hovered = hovered
            self.update()

    def pulse(self) -> None:
        if not self._animated:
            return
        self._pulse.stop()
        self._pulse.start()

    def _ensure_assets(self) -> None:
        base = max(1, min(self.width(), self.height()))
        ratio = max(1.0, self.devicePixelRatioF())
        key = (base, ratio)
        if self._pixmap is not None and self._cache_key == key:
            return
        self._pixmap = logo_pixmap(max(1, base - 4), device_ratio=ratio)
        self._cache_key = key
        tinted = self._pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        outline_painter = QPainter(tinted)
        outline_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        outline_painter.fillRect(tinted.rect(), QColor(226, 119, 159, 238))
        outline_painter.end()
        self._outline = QPixmap.fromImage(tinted)
        self._outline.setDevicePixelRatio(self._pixmap.devicePixelRatio())

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        self._ensure_assets()
        if self._pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = self._pixmap.deviceIndependentSize()
        x = (self.width() - size.width()) / 2
        y = (self.height() - size.height()) / 2 + self._offset

        if self._outline is not None:
            # A soft rose halo plus a crisp silhouette rim makes the pale hair
            # readable on both the pink workspace and a busy desktop.
            glow_strength = (0.34 if self._hovered else 0.20) + 0.42 * self._glow
            painter.setOpacity(glow_strength)
            for dx, dy in (
                (-1.0, -1.0),
                (1.0, -1.0),
                (-1.0, 1.0),
                (1.0, 1.0),
                (-1.0, 0.0),
                (1.0, 0.0),
                (0.0, -1.0),
                (0.0, 1.0),
            ):
                painter.drawPixmap(QPointF(x + dx * 1.9, y + dy * 1.9), self._outline)
            painter.setOpacity(1.0)
            for dx, dy in (
                (-1.0, -1.0),
                (1.0, -1.0),
                (-1.0, 1.0),
                (1.0, 1.0),
                (-1.0, 0.0),
                (1.0, 0.0),
                (0.0, -1.0),
                (0.0, 1.0),
            ):
                painter.drawPixmap(QPointF(x + dx * 0.9, y + dy * 0.9), self._outline)

        painter.drawPixmap(QPointF(x, y), self._pixmap)
        painter.end()


class SpeechBubble(QWidget):
    """A click-through speech balloon that follows the pet."""

    _BODY_RADIUS = 15
    _TAIL_DEPTH = 10
    _EDGE = 7

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label.setStyleSheet(
            "color: #4A2634; background: transparent; "
            "font-family: 'Sora', 'Segoe UI'; font-size: 8.75pt; font-weight: 700;"
        )
        self.label.hide()
        self._tail_side = "bottom"
        self._tail_x = 0.0
        self._tail_y = 0.0
        self._label_size = (104, 20)
        self._appear = QPropertyAnimation(self, b"windowOpacity", self)
        self._appear.setDuration(150)
        self._appear.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_message)
        self.hide()

    @property
    def message(self) -> str:
        return self.label.text()

    def show_message(self, text: str) -> None:
        clean = " ".join(str(text).split())
        if not clean:
            return
        was_visible = self.isVisible()
        self.label.setText(clean)
        metrics = self.label.fontMetrics()
        natural = metrics.horizontalAdvance(clean) + 3
        text_width = max(96, min(188, natural))
        label_height = max(metrics.height(), self.label.heightForWidth(text_width))
        self.label.setFixedWidth(text_width)
        self.label.setFixedHeight(label_height)
        self._label_size = (text_width, label_height)
        self._tail_side = "bottom"
        self._resize_for_label()
        self.label.show()
        self.show()
        self.raise_()
        self._appear.stop()
        if not was_visible:
            self.setWindowOpacity(0.0)
        self._appear.setStartValue(self.windowOpacity())
        self._appear.setEndValue(1.0)
        self._appear.start()
        self._hide_timer.start(4700)

    def _body_rect(self) -> QRectF:
        width = float(self.width())
        height = float(self.height())
        if self._tail_side == "top":
            return QRectF(self._EDGE, 17, width - 14, height - 24)
        if self._tail_side == "bottom":
            return QRectF(self._EDGE, 7, width - 14, height - 24)
        if self._tail_side == "left":
            return QRectF(17, self._EDGE, width - 24, height - 14)
        return QRectF(self._EDGE, self._EDGE, width - 24, height - 14)

    def _resize_for_label(self) -> None:
        text_width, label_height = self._label_size
        body_width = text_width + 20
        body_height = label_height + 18
        if self._tail_side in {"top", "bottom"}:
            self.setFixedSize(body_width + 14, body_height + 24)
        else:
            self.setFixedSize(body_width + 24, body_height + 14)
        body = self._body_rect()
        self.label.setGeometry(
            round(body.left() + 10),
            round(body.top() + 9),
            text_width,
            label_height,
        )

    def reposition_for(self, pet: QWidget) -> None:
        screen = (
            QGuiApplication.screenAt(pet.frameGeometry().center())
            or pet.screen()
            or QGuiApplication.primaryScreen()
        )
        available = screen.availableGeometry() if screen is not None else None
        text_width, label_height = self._label_size
        vertical_height = label_height + 42
        side_width = text_width + 44
        gap = 5
        center = pet.frameGeometry().center()

        placement = "above"
        if available is not None:
            if pet.y() - vertical_height - gap < available.top() + 6:
                if pet.y() + pet.height() + gap + vertical_height <= available.bottom() - 6:
                    placement = "below"
                elif pet.x() - side_width - gap >= available.left() + 6:
                    placement = "left"
                elif pet.x() + pet.width() + gap + side_width <= available.right() - 6:
                    placement = "right"

        self._tail_side = {
            "above": "bottom",
            "below": "top",
            "left": "right",
            "right": "left",
        }[placement]
        self._resize_for_label()
        width, height = self.width(), self.height()

        if placement == "above":
            x = center.x() - width // 2
            y = pet.y() - height - gap
        elif placement == "below":
            x = center.x() - width // 2
            y = pet.y() + pet.height() + gap
        elif placement == "left":
            x = pet.x() - width - gap
            y = center.y() - height // 2
        else:
            x = pet.x() + pet.width() + gap
            y = center.y() - height // 2

        if available is not None:
            x = min(max(x, available.left() + 6), available.right() - width - 6)
            y = min(max(y, available.top() + 6), available.bottom() - height - 6)

        if self._tail_side in {"top", "bottom"}:
            self._tail_x = min(max(center.x() - x, 22.0), float(width - 22))
        else:
            self._tail_y = min(max(center.y() - y, 22.0), float(height - 22))
        self.move(x, y)
        if self.isVisible():
            self.raise_()

    def hide_message(self) -> None:
        self._hide_timer.stop()
        self._appear.stop()
        self.hide()
        self.setWindowOpacity(1.0)

    def _tail_path(self, body: QRectF) -> QPainterPath:
        tail = QPainterPath()
        if self._tail_side == "bottom":
            base = body.bottom() - 1
            tail.moveTo(self._tail_x - 10, base)
            tail.cubicTo(
                self._tail_x - 6,
                base + 4,
                self._tail_x - 3,
                base + 7,
                self._tail_x,
                self.height() - 7,
            )
            tail.cubicTo(
                self._tail_x + 3, base + 7, self._tail_x + 6, base + 4, self._tail_x + 10, base
            )
        elif self._tail_side == "top":
            base = body.top() + 1
            tail.moveTo(self._tail_x - 10, base)
            tail.cubicTo(self._tail_x - 6, base - 4, self._tail_x - 3, base - 7, self._tail_x, 7)
            tail.cubicTo(
                self._tail_x + 3, base - 7, self._tail_x + 6, base - 4, self._tail_x + 10, base
            )
        elif self._tail_side == "right":
            base = body.right() - 1
            tail.moveTo(base, self._tail_y - 10)
            tail.cubicTo(
                base + 4,
                self._tail_y - 6,
                base + 7,
                self._tail_y - 3,
                self.width() - 7,
                self._tail_y,
            )
            tail.cubicTo(
                base + 7, self._tail_y + 3, base + 4, self._tail_y + 6, base, self._tail_y + 10
            )
        else:
            base = body.left() + 1
            tail.moveTo(base, self._tail_y - 10)
            tail.cubicTo(base - 4, self._tail_y - 6, base - 7, self._tail_y - 3, 7, self._tail_y)
            tail.cubicTo(
                base - 7, self._tail_y + 3, base - 4, self._tail_y + 6, base, self._tail_y + 10
            )
        tail.closeSubpath()
        return tail

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = self._body_rect()
        body_path = QPainterPath()
        body_path.addRoundedRect(body, self._BODY_RADIUS, self._BODY_RADIUS)
        tail = self._tail_path(body)
        bubble = body_path.united(tail)

        painter.setPen(Qt.PenStyle.NoPen)
        for spread, alpha in ((4, 8), (2, 14)):
            shadow = body.adjusted(-spread, -spread + 2, spread, spread + 4)
            painter.setBrush(QColor(95, 44, 68, alpha))
            painter.drawRoundedRect(shadow, self._BODY_RADIUS + spread, self._BODY_RADIUS + spread)
        painter.setBrush(QColor(95, 44, 68, 20))
        painter.drawPath(tail.translated(0.7, 2.4))

        fill = QLinearGradient(body.topLeft(), body.bottomRight())
        fill.setColorAt(0.0, QColor(255, 255, 255, 252))
        fill.setColorAt(0.55, QColor(255, 248, 252, 250))
        fill.setColorAt(1.0, QColor(255, 235, 245, 246))
        painter.setBrush(fill)
        rim = QLinearGradient(body.topLeft(), body.bottomRight())
        rim.setColorAt(0.0, QColor(255, 255, 255, 224))
        rim.setColorAt(0.55, QColor(255, 255, 255, 178))
        rim.setColorAt(1.0, QColor(255, 174, 208, 184))
        painter.setPen(QPen(QBrush(rim), 1.2))
        painter.drawPath(bubble)
        painter.setPen(QPen(QColor(255, 152, 196, 112), 0.6))
        painter.drawPath(bubble)

        painter.save()
        painter.setClipPath(bubble)
        sheen = QLinearGradient(body.topLeft(), QPointF(body.left(), body.bottom()))
        sheen.setColorAt(0.0, QColor(255, 255, 255, 76))
        sheen.setColorAt(0.42, QColor(255, 255, 255, 16))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(body, sheen)
        painter.restore()

        painter.setPen(QPen(QColor(255, 255, 255, 226), 1.0))
        painter.drawLine(
            QPointF(body.left() + 14, body.top() + 1.6),
            QPointF(body.right() - 15, body.top() + 1.6),
        )

        sparkle_x = body.right() - 13
        sparkle_y = body.top() + 7
        painter.setPen(QPen(QColor(255, 255, 255, 218), 0.9))
        painter.drawLine(
            QPointF(sparkle_x - 2.4, sparkle_y),
            QPointF(sparkle_x + 2.4, sparkle_y),
        )
        painter.drawLine(
            QPointF(sparkle_x, sparkle_y - 2.4),
            QPointF(sparkle_x, sparkle_y + 2.4),
        )
        painter.setPen(QPen(QColor(255, 149, 194, 136), 0.55))
        painter.drawLine(
            QPointF(sparkle_x - 1.4, sparkle_y - 1.4),
            QPointF(sparkle_x + 1.4, sparkle_y + 1.4),
        )
        painter.end()


class MascotPet(QWidget):
    """A frameless desktop pet; she goes wherever she pleases."""

    # She is a window because she refuses to live in a sidebar.

    message_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(64, 64)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Alya-sama  ·  drag me anywhere, click me to chat")
        self.bubble = SpeechBubble(parent)
        self._avatar = _Avatar(self)
        self._avatar.move(0, 0)
        self._message_index = 0
        self._drag_offset: QPoint | None = None
        self._press_global = QPoint()
        self._dragging = False
        self._placed = False
        self.hide()

    def set_active(self, active: bool) -> None:
        if not active:
            self._avatar.set_animated(False)
            self.bubble.hide_message()
            self.hide()
            return
        if not self._placed:
            self._place_near_parent()
        else:
            self.move(self._clamped_position(self.pos()))
        self.show()
        self._avatar.set_animated(True)
        self.raise_()
        if self.bubble.isVisible():
            self.bubble.raise_()

    def say(self, text: str | None = None) -> None:
        if text is None:
            text = _MESSAGES[self._message_index % len(_MESSAGES)]
            self._message_index += 1
        self.bubble.show_message(text)
        self.bubble.reposition_for(self)
        self.message_changed.emit(text)

    def move_to(self, position: QPoint) -> None:
        """Move the pet, but keep her reachable on the current screen."""
        self.move(self._clamped_position(position))

    def _place_near_parent(self) -> None:
        parent = self.parentWidget()
        screen = QGuiApplication.primaryScreen()
        if parent is not None and parent.frameGeometry().width() > 200:
            frame = parent.frameGeometry()
            target = QPoint(frame.right() - self.width() - 32, frame.bottom() - self.height() - 54)
        elif screen is not None:
            area = screen.availableGeometry()
            target = QPoint(area.right() - self.width() - 32, area.bottom() - self.height() - 54)
        else:
            target = QPoint(34, 34)
        self.move(self._clamped_position(target))
        self._placed = True

    def _clamped_position(self, position: QPoint) -> QPoint:
        probe = position + QPoint(self.width() // 2, self.height() // 2)
        screen = QGuiApplication.screenAt(probe) or self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return position
        area = screen.availableGeometry().adjusted(6, 6, -6, -6)
        x = min(max(position.x(), area.left()), max(area.left(), area.right() - self.width()))
        y = min(max(position.y(), area.top()), max(area.top(), area.bottom() - self.height()))
        return QPoint(x, y)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._drag_offset = self._press_global - self.frameGeometry().topLeft()
            self._dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.raise_()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is None or not event.buttons() & Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)
            return
        global_pos = event.globalPosition().toPoint()
        if not self._dragging and (global_pos - self._press_global).manhattanLength() < 4:
            event.accept()
            return
        self._dragging = True
        self.move_to(global_pos - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            was_dragging = self._dragging
            self._drag_offset = None
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            # A click is just a very short drag.
            if not was_dragging:
                self._avatar.pulse()
                self.say()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self._avatar.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._avatar.set_hovered(False)
        super().leaveEvent(event)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.bubble.isVisible():
            self.bubble.reposition_for(self)

    def hideEvent(self, event) -> None:
        self.bubble.hide_message()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.bubble.hide_message()
        self.bubble.close()
        super().closeEvent(event)
