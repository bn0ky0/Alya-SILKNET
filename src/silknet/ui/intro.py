"""Branded startup intro shown when Alya SILKNET opens."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from silknet import __version__
from silknet.config import AppSettings
from silknet.ui.assets import logo_pixmap
from silknet.ui.theme import theme_colors

INTRO_DURATION = 2000
OUTRO_DURATION = 180
_CORNER_RADIUS = 24
_SKIP_KEYS = frozenset(
    {
        Qt.Key.Key_Escape,
        Qt.Key.Key_Space,
        Qt.Key.Key_Return,
        Qt.Key.Key_Enter,
    }
)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _phase(progress: float, start: float, end: float) -> float:
    """Return an eased 0..1 value for the given slice of the timeline."""
    if end <= start:
        return 1.0 if progress >= end else 0.0
    value = _clamp((progress - start) / (end - start))
    return 1.0 - (1.0 - value) ** 3


def _with_alpha(color: QColor, alpha: float) -> QColor:
    result = QColor(color)
    result.setAlpha(round(max(0.0, min(255.0, alpha))))
    return result


@dataclass(frozen=True)
class _Metrics:
    """Layout values shared by the intro painters."""

    width: float
    height: float
    ui: float
    logo_size: float
    center_x: float
    logo_center_y: float
    title_y: float
    tagline_y: float
    line_y: float
    caption_y: float
    footer_y: float


class StartupIntro(QWidget):
    """A short branded curtain that reveals the workspace when it is ready."""

    finished = Signal()

    def __init__(
        self,
        settings: AppSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings or AppSettings()
        self._colors: dict[str, str] = {}
        self._title_font = QFont()
        self._tagline_font = QFont()
        self._caption_font = QFont()
        self._footer_font = QFont()
        self._logo_cache: tuple[tuple[int, float], QPixmap] | None = None
        self._progress = 0.0
        self._playing = False

        self.setObjectName("startupIntro")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Alya SILKNET is starting")
        self._refresh_style()

        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(INTRO_DURATION)
        self._animation.setEasingCurve(QEasingCurve.Type.Linear)
        self._animation.valueChanged.connect(self._set_progress)
        self._animation.finished.connect(self._complete)

        self._fade_effect = QGraphicsOpacityEffect(self)
        self._fade_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._fade_effect)
        self._fade = QPropertyAnimation(self._fade_effect, b"opacity", self)
        self._fade.setDuration(OUTRO_DURATION)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._complete)
        self.hide()

    @property
    def is_playing(self) -> bool:
        return self._playing

    def set_settings(self, settings: AppSettings) -> None:
        self._settings = settings
        self._refresh_style()
        self.update()

    def play(self) -> None:
        """Show the intro and start its timeline."""
        if self._playing:
            return
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self._playing = True
        self._progress = 0.0
        self._fade.stop()
        self._fade_effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._animation.stop()
        self._animation.start()

    def dismiss(self) -> None:
        """Skip the remaining timeline with a short fade."""
        if not self._playing:
            return
        self._animation.stop()
        self._fade.stop()
        self._fade.setStartValue(float(self._fade_effect.opacity()))
        self._fade.setEndValue(0.0)
        self._fade.start()

    def stop(self) -> None:
        """Stop without emitting :attr:`finished`, used when the window closes."""
        self._playing = False
        self._animation.stop()
        self._fade.stop()
        self._fade_effect.setOpacity(1.0)
        self._progress = 0.0
        self.hide()

    def _refresh_style(self) -> None:
        self._colors = theme_colors(self._settings)
        ui = max(0.75, min(1.25, self._settings.ui_scale))
        self._title_font = self._font(27.0 * ui, QFont.Weight.ExtraBold, 0.8 * ui)
        self._tagline_font = self._font(10.5 * ui, QFont.Weight.Medium)
        self._caption_font = self._font(8.5 * ui, QFont.Weight.Normal)
        self._footer_font = self._font(8.0 * ui, QFont.Weight.Normal)

    @staticmethod
    def _font(size: float, weight: QFont.Weight, spacing: float = 0.0) -> QFont:
        font = QFont("Sora")
        font.setPointSizeF(size)
        font.setWeight(weight)
        if spacing:
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        return font

    def _set_progress(self, value: object) -> None:
        self._progress = float(value)
        self.update()

    def _complete(self) -> None:
        if not self._playing:
            return
        self._playing = False
        self._animation.stop()
        self._fade.stop()
        self._fade_effect.setOpacity(1.0)
        self._progress = 0.0
        self.hide()
        self.finished.emit()

    def _metrics(self) -> _Metrics:
        width = float(self.width())
        height = float(self.height())
        ui = max(0.75, min(1.25, self._settings.ui_scale))
        logo_size = (102.0 if height < 640 else 128.0) * ui
        title_gap = 22.0 * ui
        title_height = 46.0 * ui
        tagline_height = 28.0 * ui
        line_gap = 30.0 * ui
        line_height = max(3.0, 4.0 * ui)
        caption_gap = 14.0 * ui
        caption_height = 20.0 * ui
        block = (
            logo_size
            + title_gap
            + title_height
            + tagline_height
            + line_gap
            + line_height
            + caption_gap
            + caption_height
        )
        top = max(48.0 * ui, (height - block) / 2.0 - 6.0 * ui)
        title_y = top + logo_size + title_gap
        tagline_y = title_y + title_height
        line_y = tagline_y + tagline_height + line_gap
        caption_y = line_y + line_height + caption_gap
        return _Metrics(
            width=width,
            height=height,
            ui=ui,
            logo_size=logo_size,
            center_x=width / 2.0,
            logo_center_y=top + logo_size / 2.0,
            title_y=title_y,
            tagline_y=tagline_y,
            line_y=line_y,
            caption_y=caption_y,
            footer_y=height - 34.0 * ui,
        )

    def _window_path(self, metrics: _Metrics) -> QPainterPath:
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        window = self.window()
        immersive = window is not None and (window.isMaximized() or window.isFullScreen())
        if immersive:
            path.addRect(rect)
        else:
            path.addRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)
        return path

    def _logo_pixmap(self, size: int) -> QPixmap:
        ratio = max(1.0, self.devicePixelRatioF())
        key = (size, round(ratio, 2))
        if self._logo_cache is None or self._logo_cache[0] != key:
            self._logo_cache = (key, logo_pixmap(size, device_ratio=ratio))
        return self._logo_cache[1]

    def paintEvent(self, _event: QPaintEvent) -> None:
        if self._progress <= 0.0 or self.width() <= 0 or self.height() <= 0:
            return
        progress = self._progress
        depart = 1.0 - _phase(progress, 0.86, 1.0)
        metrics = self._metrics()
        path = self._window_path(metrics)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._paint_background(painter, metrics, path, progress, depart)
        self._paint_portrait(painter, metrics, progress, depart)
        self._paint_copy(painter, metrics, progress, depart)
        self._paint_progress(painter, metrics, progress, depart)
        self._paint_footer(painter, metrics, progress, depart)
        painter.end()

    def _paint_background(
        self,
        painter: QPainter,
        metrics: _Metrics,
        path: QPainterPath,
        progress: float,
        depart: float,
    ) -> None:
        appear = _phase(progress, 0.0, 0.08)
        alpha = 255.0 * appear * depart
        if alpha <= 0.5:
            return
        backdrop = QLinearGradient(0.0, 0.0, 0.0, metrics.height)
        backdrop.setColorAt(0.0, _with_alpha(QColor(self._colors["window"]), alpha))
        backdrop.setColorAt(1.0, _with_alpha(QColor(self._colors["sidebar"]), alpha))
        painter.fillPath(path, backdrop)

        wash = 30.0 * _phase(progress, 0.1, 0.55) * depart
        if wash <= 0.5:
            return
        accent = QColor(self._colors["accent"])
        glow = QRadialGradient(
            QPointF(metrics.center_x, metrics.logo_center_y),
            metrics.width * 0.62,
        )
        glow.setColorAt(0.0, _with_alpha(accent, wash))
        glow.setColorAt(0.55, _with_alpha(accent, wash * 0.32))
        glow.setColorAt(1.0, _with_alpha(accent, 0.0))
        painter.save()
        painter.setClipPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRect(QRectF(0.0, 0.0, metrics.width, metrics.height))
        painter.restore()

    def _paint_portrait(
        self,
        painter: QPainter,
        metrics: _Metrics,
        progress: float,
        depart: float,
    ) -> None:
        reveal = _phase(progress, 0.03, 0.24)
        if reveal <= 0.01:
            return
        accent = QColor(self._colors["accent"])
        grow = _phase(progress, 0.05, 0.42)
        scale = (0.88 + 0.12 * grow) * (1.0 + 0.02 * _phase(progress, 0.84, 1.0))
        size = metrics.logo_size * scale
        rect = QRectF(
            metrics.center_x - size / 2.0,
            metrics.logo_center_y - size / 2.0,
            size,
            size,
        )

        glow_alpha = 72.0 * _phase(progress, 0.05, 0.48) * depart
        if glow_alpha > 0.5:
            radius = metrics.logo_size * 1.75
            glow = QRadialGradient(
                QPointF(metrics.center_x, metrics.logo_center_y),
                radius,
            )
            glow.setColorAt(0.0, _with_alpha(accent, glow_alpha))
            glow.setColorAt(0.55, _with_alpha(accent, glow_alpha * 0.28))
            glow.setColorAt(1.0, _with_alpha(accent, 0.0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(
                QRectF(
                    metrics.center_x - radius,
                    metrics.logo_center_y - radius,
                    radius * 2.0,
                    radius * 2.0,
                )
            )

        ring_reveal = _phase(progress, 0.1, 0.42) * depart
        if ring_reveal > 0.01:
            orbit_radius = metrics.logo_size * 0.72
            orbit = QRectF(
                metrics.center_x - orbit_radius,
                metrics.logo_center_y - orbit_radius,
                orbit_radius * 2.0,
                orbit_radius * 2.0,
            )
            track_pen = QPen(_with_alpha(QColor(self._colors["border"]), 110.0 * ring_reveal))
            track_pen.setWidthF(max(1.0, 1.2 * metrics.ui))
            painter.setPen(track_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(orbit)
            arc_pen = QPen(_with_alpha(accent, 190.0 * ring_reveal))
            arc_pen.setWidthF(max(1.4, 2.0 * metrics.ui))
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            start_angle = round((90.0 + 230.0 * progress) * 16)
            painter.drawArc(orbit, start_angle, 245 * 16)

        plate = _with_alpha(QColor(self._colors["surface"]), 210.0 * reveal * depart)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(plate)
        painter.drawEllipse(rect)

        painter.save()
        clip = QPainterPath()
        clip.addEllipse(rect)
        painter.setClipPath(clip)
        pixmap = self._logo_pixmap(max(1, round(metrics.logo_size * 1.2)))
        painter.setOpacity(reveal * depart)
        painter.drawPixmap(rect.toRect(), pixmap)
        painter.restore()

        border = QPen(_with_alpha(accent, 100.0 * reveal * depart))
        border.setWidthF(max(1.0, 1.2 * metrics.ui))
        painter.setPen(border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

    def _paint_copy(
        self,
        painter: QPainter,
        metrics: _Metrics,
        progress: float,
        depart: float,
    ) -> None:
        title_reveal = _phase(progress, 0.2, 0.46)
        title_opacity = title_reveal * depart
        if title_opacity > 0.01:
            slide = (1.0 - _phase(progress, 0.2, 0.5)) * 10.0 * metrics.ui
            painter.setFont(self._title_font)
            painter.setPen(_with_alpha(QColor(self._colors["text"]), 255.0 * title_opacity))
            painter.drawText(
                QRectF(0.0, metrics.title_y + slide, metrics.width, 50.0 * metrics.ui),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "Alya SILKNET",
            )

        tag_reveal = _phase(progress, 0.3, 0.54)
        tag_opacity = tag_reveal * depart
        if tag_opacity > 0.01:
            slide = (1.0 - _phase(progress, 0.3, 0.58)) * 8.0 * metrics.ui
            painter.setFont(self._tagline_font)
            painter.setPen(_with_alpha(QColor(self._colors["muted"]), 235.0 * tag_opacity))
            painter.drawText(
                QRectF(
                    0.0,
                    metrics.tagline_y + slide,
                    metrics.width,
                    26.0 * metrics.ui,
                ),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "Records & connections",
            )

    def _paint_progress(
        self,
        painter: QPainter,
        metrics: _Metrics,
        progress: float,
        depart: float,
    ) -> None:
        line_opacity = _phase(progress, 0.36, 0.5) * depart
        if line_opacity <= 0.01:
            return
        track_width = 210.0 * metrics.ui
        track_height = max(3.0, 4.0 * metrics.ui)
        left = metrics.center_x - track_width / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_with_alpha(QColor(self._colors["border"]), 165.0 * line_opacity))
        painter.drawRoundedRect(
            QRectF(left, metrics.line_y, track_width, track_height),
            track_height / 2.0,
            track_height / 2.0,
        )

        fill = track_width * _phase(progress, 0.38, 0.82)
        if fill > 0.5:
            accent = QColor(self._colors["accent"])
            accent_hover = QColor(self._colors["accent_hover"])
            fill_gradient = QLinearGradient(left, 0.0, left + track_width, 0.0)
            fill_gradient.setColorAt(0.0, _with_alpha(accent, 235.0 * line_opacity))
            fill_gradient.setColorAt(
                1.0,
                _with_alpha(accent_hover, 235.0 * line_opacity),
            )
            painter.setBrush(fill_gradient)
            painter.drawRoundedRect(
                QRectF(left, metrics.line_y, fill, track_height),
                track_height / 2.0,
                track_height / 2.0,
            )
            tip_radius = 2.4 * metrics.ui
            painter.setBrush(_with_alpha(accent_hover, 240.0 * line_opacity))
            painter.drawEllipse(
                QPointF(left + fill, metrics.line_y + track_height / 2.0),
                tip_radius,
                tip_radius,
            )

        caption_reveal = _phase(progress, 0.48, 0.62) * depart
        if caption_reveal > 0.01:
            painter.setFont(self._caption_font)
            painter.setPen(_with_alpha(QColor(self._colors["subtle"]), 210.0 * caption_reveal))
            painter.drawText(
                QRectF(
                    0.0,
                    metrics.caption_y,
                    metrics.width,
                    20.0 * metrics.ui,
                ),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "Opening your local workspace",
            )

    def _paint_footer(
        self,
        painter: QPainter,
        metrics: _Metrics,
        progress: float,
        depart: float,
    ) -> None:
        opacity = _phase(progress, 0.22, 0.44) * depart
        if opacity <= 0.01:
            return
        painter.setFont(self._footer_font)
        painter.setPen(_with_alpha(QColor(self._colors["subtle"]), 155.0 * opacity))
        painter.drawText(
            QRectF(
                0.0,
                metrics.footer_y,
                metrics.width - 24.0 * metrics.ui,
                20.0 * metrics.ui,
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "Click to skip",
        )
        painter.drawText(
            QRectF(
                24.0 * metrics.ui,
                metrics.footer_y,
                metrics.width - 48.0 * metrics.ui,
                20.0 * metrics.ui,
            ),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"v{__version__}  ·  Local workspace",
        )

    def event(self, event: QEvent) -> bool:
        # The main window owns an Escape shortcut for leaving full screen.
        # Accepting the shortcut override keeps that shortcut from swallowing
        # the skip key while this overlay has focus.
        if event.type() == QEvent.Type.ShortcutOverride and event.key() in _SKIP_KEYS:
            event.accept()
            return True
        return super().event(event)

    def mousePressEvent(self, event) -> None:
        self.dismiss()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() in _SKIP_KEYS:
            self.dismiss()
            event.accept()
            return
        super().keyPressEvent(event)
