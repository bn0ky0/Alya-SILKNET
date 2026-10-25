"""Bundled artwork helpers and branded image widgets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
LOGO_FILE = _ASSET_DIR / "alya-cutout.png"
ICON_FILE = _ASSET_DIR / "alya.ico"
_LOGO_SOURCE: QPixmap | None = None


def logo_path() -> Path:
    """Return the bundled transparent Alya artwork path."""
    return LOGO_FILE


def screen_device_ratio() -> float:
    """Return the screen ratio so artwork stays sharp at 125%/150% scaling."""
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return 1.0
    return max(1.0, float(screen.devicePixelRatio()))


def _logo_source() -> QPixmap:
    """Load the bundled logo once and reuse it for every rendered size."""
    global _LOGO_SOURCE
    if _LOGO_SOURCE is None:
        _LOGO_SOURCE = QPixmap(str(LOGO_FILE))
    return _LOGO_SOURCE


def _scaled_source(target: int) -> QPixmap:
    """Downscale the artwork in smooth halving steps to avoid aliasing."""
    source = _logo_source()
    if source.isNull():
        return source
    current = source
    while current.width() > target * 2 and current.height() > target * 2:
        current = current.scaled(
            max(1, current.width() // 2),
            max(1, current.height() // 2),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return current.scaled(
        target,
        target,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )


def _rounded_pixmap(source: QPixmap, size: int, radius_ratio: float, ratio: float) -> QPixmap:
    physical = max(1, round(size * max(1.0, ratio)))
    result = QPixmap(physical, physical)
    result.fill(Qt.GlobalColor.transparent)
    if source.isNull():
        result.setDevicePixelRatio(max(1.0, ratio))
        return result

    scaled = source.scaled(
        physical,
        physical,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    path = QPainterPath()
    radius = physical * max(0.0, min(0.5, radius_ratio))
    path.addRoundedRect(QRectF(0, 0, physical, physical), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(
        (physical - scaled.width()) // 2,
        (physical - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    result.setDevicePixelRatio(max(1.0, ratio))
    return result


def rounded_logo(
    size: int,
    radius_ratio: float = 0.30,
    *,
    device_ratio: float | None = None,
) -> QPixmap:
    """Return the artwork cropped to a rounded square of ``size`` logical pixels.

    The pixmap is rendered at the screen's device pixel ratio and tagged with it,
    so the logo is crisp instead of being upscaled by the compositor.
    """
    ratio = max(1.0, device_ratio if device_ratio is not None else screen_device_ratio())
    physical = max(1, round(size * ratio))
    scaled = _scaled_source(physical)
    return _rounded_pixmap(scaled, size, radius_ratio, ratio)


def logo_pixmap(
    size: int,
    *,
    device_ratio: float | None = None,
) -> QPixmap:
    """Render the transparent Alya cutout without adding a rounded plate."""
    ratio = max(1.0, device_ratio if device_ratio is not None else screen_device_ratio())
    physical = max(1, round(size * ratio))
    source = _scaled_source(physical)
    result = QPixmap(physical, physical)
    result.fill(Qt.GlobalColor.transparent)
    if source.isNull():
        result.setDevicePixelRatio(max(1.0, ratio))
        return result
    scaled = source.scaled(
        physical,
        physical,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(
        (physical - scaled.width()) // 2,
        (physical - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    result.setDevicePixelRatio(max(1.0, ratio))
    return result


def rounded_photo(
    source: QImage | QPixmap | str | Path,
    size: int,
    radius_ratio: float = 0.28,
    *,
    device_ratio: float | None = None,
) -> QPixmap:
    """Crop a user profile image into a high-DPI rounded square or circle."""
    if isinstance(source, QImage):
        pixmap = QPixmap.fromImage(source)
    elif isinstance(source, QPixmap):
        pixmap = source
    else:
        pixmap = QPixmap(str(source))
    ratio = max(1.0, device_ratio if device_ratio is not None else screen_device_ratio())
    return _rounded_pixmap(pixmap, size, radius_ratio, ratio)


class LogoBadge(QWidget):
    """Rounded Alya artwork that re-renders crisply when the UI scale changes."""

    def __init__(
        self,
        size: int = 44,
        radius_ratio: float = 0.27,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAccessibleName("Alya SILKNET logo")
        self.setToolTip("Alya SILKNET")
        self._radius_ratio = radius_ratio
        self._cache: QPixmap | None = None
        self._cache_key: tuple[int, float] | None = None

    def paintEvent(self, _event: QPaintEvent) -> None:
        size = max(1, min(self.width(), self.height()))
        ratio = max(1.0, self.devicePixelRatioF())
        key = (size, ratio)
        if self._cache is None or self._cache_key != key:
            self._cache = logo_pixmap(size, device_ratio=ratio)
            self._cache_key = key
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, self._cache)
        painter.end()


def app_icon() -> QIcon:
    """Load the bundled multi-resolution window and taskbar icon."""
    icon = QIcon(str(ICON_FILE))
    if not icon.isNull():
        return icon
    fallback = QIcon()
    for size in (16, 24, 32, 40, 48, 64, 128, 256):
        fallback.addPixmap(logo_pixmap(size, device_ratio=1.0))
    return fallback
