"""Brand-colored platform badges used in lists, forms and graph nodes."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from silknet.ui.assets import screen_device_ratio

_PLATFORM_MARKS = {
    "bluesky": "BS",
    "discord": "D",
    "facebook": "f",
    "github": "GH",
    "instagram": "IG",
    "linkedin": "in",
    "mastodon": "M",
    "pinterest": "P",
    "reddit": "r",
    "snapchat": "S",
    "telegram": "TG",
    "threads": "@",
    "tiktok": "TT",
    "twitch": "TW",
    "x": "X",
    "youtube": "YT",
}


@dataclass(frozen=True)
class PlatformStyle:
    """Colors and glyph used to draw one social platform badge."""

    label: str
    background: str
    foreground: str = "#FFFFFF"
    glyph: str = ""
    accent: str | None = None
    special: str = ""


_PLATFORM_STYLES = {
    "bluesky": PlatformStyle("Bluesky", "#1185FE", glyph="BS", special="bluesky"),
    "discord": PlatformStyle("Discord", "#5865F2", glyph="D", special="discord"),
    "facebook": PlatformStyle("Facebook", "#1877F2", glyph="f", special="facebook"),
    "github": PlatformStyle("GitHub", "#24292F", glyph="GH", special="github"),
    "instagram": PlatformStyle("Instagram", "#DD2A7B", glyph="IG", special="instagram"),
    "linkedin": PlatformStyle("LinkedIn", "#0A66C2", glyph="in", special="linkedin"),
    "mastodon": PlatformStyle("Mastodon", "#6364FF", glyph="M", special="mastodon"),
    "pinterest": PlatformStyle("Pinterest", "#E60023", glyph="P", special="pinterest"),
    "reddit": PlatformStyle("Reddit", "#FF4500", glyph="r", special="reddit"),
    "snapchat": PlatformStyle("Snapchat", "#FFFC00", "#FFFFFF", "S", special="snapchat"),
    "telegram": PlatformStyle("Telegram", "#229ED9", glyph="TG", special="telegram"),
    "threads": PlatformStyle("Threads", "#101010", glyph="@", special="threads"),
    "tiktok": PlatformStyle("TikTok", "#101010", glyph="TT", special="tiktok"),
    "twitch": PlatformStyle("Twitch", "#9146FF", glyph="TW", special="twitch"),
    "x": PlatformStyle("X", "#000000", glyph="X", special="x"),
    "youtube": PlatformStyle("YouTube", "#FF0033", glyph="YT", special="youtube"),
}
_GENERIC_STYLE = PlatformStyle("Platform", "#5B6B8C", "#FFFFFF", "?")


def platform_mark(platform: object) -> str:
    """Return a compact text mark for a platform name (kept for compatibility)."""
    name = platform.strip() if isinstance(platform, str) else ""
    mark = _PLATFORM_MARKS.get(name.casefold())
    if mark:
        return mark
    letters = "".join(word[0] for word in name.split()[:2] if word)
    return letters.upper() or "?"


def platform_style(platform: object) -> PlatformStyle:
    """Return brand colors and a glyph for the given platform name."""
    name = platform.strip() if isinstance(platform, str) else ""
    style = _PLATFORM_STYLES.get(name.casefold())
    if style is not None:
        return style
    if not name:
        return _GENERIC_STYLE
    return PlatformStyle(name, "#5B6B8C", "#FFFFFF", platform_mark(name))


def platform_color(platform: object) -> str:
    return platform_style(platform).background


def _text_glyph(
    painter: QPainter,
    rect: QRectF,
    text: str,
    color: QColor,
    *,
    ratio: float = 0.40,
    family: str = "Segoe UI Variable Display",
    italic: bool = False,
) -> None:
    size = min(rect.width(), rect.height())
    font = QFont(family, 1, QFont.Weight.Black)
    font.setPixelSize(max(8, round(size * ratio)))
    font.setItalic(italic)
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def _draw_platform_glyph(
    painter: QPainter,
    style: PlatformStyle,
    rect: QRectF,
) -> None:
    """Draw a recognisable vector mark for the common social platforms."""

    s = min(rect.width(), rect.height())
    cx, cy = rect.center().x(), rect.center().y()
    ink = QColor(style.foreground)
    background = QColor(style.background)
    # Small marks need a little more ink than large previews.
    stroke = max(1.4, s * 0.055)
    special = style.special

    if special == "instagram":
        pen = QPen(ink, stroke)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        camera = rect.adjusted(s * 0.2, s * 0.2, -s * 0.2, -s * 0.2)
        painter.drawRoundedRect(camera, s * 0.13, s * 0.13)
        painter.drawEllipse(camera.center(), s * 0.16, s * 0.16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawEllipse(
            QPointF(camera.right() - s * 0.09, camera.top() + s * 0.09),
            s * 0.045,
            s * 0.045,
        )
        return

    if special == "youtube":
        triangle = QPolygonF(
            [
                QPointF(cx - s * 0.13, cy - s * 0.2),
                QPointF(cx - s * 0.13, cy + s * 0.2),
                QPointF(cx + s * 0.21, cy),
            ]
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawPolygon(triangle)
        return

    if special == "telegram":
        plane = QPolygonF(
            [
                QPointF(rect.left() + s * 0.17, cy - s * 0.01),
                QPointF(rect.right() - s * 0.16, rect.top() + s * 0.22),
                QPointF(rect.right() - s * 0.28, rect.bottom() - s * 0.19),
                QPointF(cx + s * 0.02, cy + s * 0.08),
                QPointF(cx - s * 0.05, rect.bottom() - s * 0.27),
                QPointF(cx - s * 0.12, cy + s * 0.10),
            ]
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawPolygon(plane)
        return

    if special == "tiktok":

        def note(offset: float) -> QPainterPath:
            path = QPainterPath()
            path.moveTo(cx + s * (0.13 + offset), rect.top() + s * 0.24)
            path.cubicTo(
                cx + s * (0.15 + offset),
                rect.top() + s * 0.35,
                cx + s * (0.24 + offset),
                rect.top() + s * 0.41,
                cx + s * (0.33 + offset),
                rect.top() + s * 0.42,
            )
            path.moveTo(cx + s * (0.13 + offset), rect.top() + s * 0.24)
            path.lineTo(cx + s * (0.13 + offset), rect.top() + s * 0.66)
            path.cubicTo(
                cx + s * (0.12 + offset),
                rect.top() + s * 0.74,
                cx + s * (0.02 + offset),
                rect.top() + s * 0.78,
                cx - s * (0.06 - offset),
                rect.top() + s * 0.74,
            )
            path.cubicTo(
                cx - s * (0.12 - offset),
                rect.top() + s * 0.70,
                cx - s * (0.11 - offset),
                rect.top() + s * 0.62,
                cx - s * (0.04 - offset),
                rect.top() + s * 0.59,
            )
            path.cubicTo(
                cx + s * (0.01 + offset),
                rect.top() + s * 0.57,
                cx + s * (0.09 + offset),
                rect.top() + s * 0.58,
                cx + s * (0.13 + offset),
                rect.top() + s * 0.62,
            )
            return path

        pen = QPen(QColor("#25F4EE"), s * 0.09)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(note(-s * 0.025))
        pen.setColor(QColor("#FE2C55"))
        painter.setPen(pen)
        painter.drawPath(note(s * 0.025))
        pen.setColor(ink)
        painter.setPen(pen)
        painter.drawPath(note(0.0))
        return

    if special == "x":
        pen = QPen(ink, s * 0.125)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(
            QPointF(rect.left() + s * 0.2, rect.top() + s * 0.22),
            QPointF(rect.right() - s * 0.2, rect.bottom() - s * 0.22),
        )
        painter.drawLine(
            QPointF(rect.right() - s * 0.2, rect.top() + s * 0.22),
            QPointF(rect.left() + s * 0.2, rect.bottom() - s * 0.22),
        )
        return

    if special == "facebook":
        _text_glyph(painter, rect.adjusted(0, -s * 0.01, 0, 0), "f", ink, ratio=0.66)
        return

    if special == "linkedin":
        _text_glyph(painter, rect, "in", ink, ratio=0.40)
        return

    if special == "pinterest":
        _text_glyph(
            painter,
            rect.adjusted(0, -s * 0.01, 0, 0),
            "P",
            ink,
            ratio=0.56,
            family="Georgia",
            italic=True,
        )
        return

    if special == "threads":
        _text_glyph(painter, rect, "@", ink, ratio=0.48)
        return

    if special == "github":
        # Stylised cat head: two ears, round face and punched-out eyes.
        face = QPainterPath()
        face.addEllipse(QRectF(cx - s * 0.23, cy - s * 0.18, s * 0.46, s * 0.44))
        ear_left = QPolygonF(
            [
                QPointF(cx - s * 0.22, cy - s * 0.12),
                QPointF(cx - s * 0.22, cy - s * 0.32),
                QPointF(cx - s * 0.04, cy - s * 0.20),
            ]
        )
        ear_right = QPolygonF(
            [
                QPointF(cx + s * 0.22, cy - s * 0.12),
                QPointF(cx + s * 0.22, cy - s * 0.32),
                QPointF(cx + s * 0.04, cy - s * 0.20),
            ]
        )
        face.addPolygon(ear_left)
        face.addPolygon(ear_right)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawPath(face)
        painter.setBrush(background)
        painter.drawEllipse(QPointF(cx - s * 0.08, cy - s * 0.02), s * 0.035, s * 0.045)
        painter.drawEllipse(QPointF(cx + s * 0.08, cy - s * 0.02), s * 0.035, s * 0.045)
        return

    if special == "reddit":
        # Alien head with antennae, eyes and a small smile.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawEllipse(QPointF(cx, cy + s * 0.05), s * 0.23, s * 0.19)
        pen = QPen(ink, max(1.2, s * 0.035))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(
            QPointF(cx - s * 0.09, cy - s * 0.11),
            QPointF(cx - s * 0.15, cy - s * 0.22),
        )
        painter.drawLine(
            QPointF(cx + s * 0.09, cy - s * 0.11),
            QPointF(cx + s * 0.15, cy - s * 0.22),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawEllipse(QPointF(cx - s * 0.16, cy - s * 0.23), s * 0.025, s * 0.025)
        painter.drawEllipse(QPointF(cx + s * 0.16, cy - s * 0.23), s * 0.025, s * 0.025)
        painter.setBrush(background)
        painter.drawEllipse(QPointF(cx - s * 0.08, cy + s * 0.03), s * 0.035, s * 0.04)
        painter.drawEllipse(QPointF(cx + s * 0.08, cy + s * 0.03), s * 0.035, s * 0.04)
        pen = QPen(background, max(1.1, s * 0.03))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(
            QRectF(cx - s * 0.09, cy + s * 0.05, s * 0.18, s * 0.11),
            200 * 16,
            140 * 16,
        )
        return

    if special == "snapchat":
        ghost = QPainterPath()
        ghost.moveTo(cx - s * 0.15, rect.bottom() - s * 0.22)
        ghost.cubicTo(
            cx - s * 0.22,
            rect.bottom() - s * 0.25,
            cx - s * 0.20,
            rect.bottom() - s * 0.34,
            cx - s * 0.18,
            rect.bottom() - s * 0.40,
        )
        ghost.cubicTo(
            cx - s * 0.26,
            rect.bottom() - s * 0.43,
            cx - s * 0.25,
            rect.bottom() - s * 0.51,
            cx - s * 0.18,
            rect.bottom() - s * 0.53,
        )
        ghost.cubicTo(
            cx - s * 0.20,
            rect.top() + s * 0.36,
            cx - s * 0.11,
            rect.top() + s * 0.24,
            cx,
            rect.top() + s * 0.24,
        )
        ghost.cubicTo(
            cx + s * 0.11,
            rect.top() + s * 0.24,
            cx + s * 0.20,
            rect.top() + s * 0.36,
            cx + s * 0.18,
            rect.bottom() - s * 0.53,
        )
        ghost.cubicTo(
            cx + s * 0.25,
            rect.bottom() - s * 0.51,
            cx + s * 0.26,
            rect.bottom() - s * 0.43,
            cx + s * 0.18,
            rect.bottom() - s * 0.40,
        )
        ghost.cubicTo(
            cx + s * 0.20,
            rect.bottom() - s * 0.34,
            cx + s * 0.22,
            rect.bottom() - s * 0.25,
            cx + s * 0.15,
            rect.bottom() - s * 0.22,
        )
        ghost.cubicTo(
            cx + s * 0.11,
            rect.bottom() - s * 0.28,
            cx + s * 0.07,
            rect.bottom() - s * 0.28,
            cx + s * 0.05,
            rect.bottom() - s * 0.22,
        )
        ghost.cubicTo(
            cx + s * 0.01,
            rect.bottom() - s * 0.28,
            cx - s * 0.03,
            rect.bottom() - s * 0.28,
            cx - s * 0.06,
            rect.bottom() - s * 0.22,
        )
        ghost.cubicTo(
            cx - s * 0.10,
            rect.bottom() - s * 0.28,
            cx - s * 0.12,
            rect.bottom() - s * 0.26,
            cx - s * 0.15,
            rect.bottom() - s * 0.22,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawPath(ghost)
        return

    if special == "twitch":
        bubble = QPainterPath()
        bubble.moveTo(rect.left() + s * 0.18, rect.top() + s * 0.24)
        bubble.lineTo(rect.right() - s * 0.18, rect.top() + s * 0.24)
        bubble.lineTo(rect.right() - s * 0.18, rect.bottom() - s * 0.38)
        bubble.lineTo(rect.right() - s * 0.34, rect.bottom() - s * 0.22)
        bubble.lineTo(rect.left() + s * 0.44, rect.bottom() - s * 0.22)
        bubble.lineTo(rect.left() + s * 0.44, rect.bottom() - s * 0.38)
        bubble.lineTo(rect.left() + s * 0.18, rect.bottom() - s * 0.38)
        bubble.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawPath(bubble)
        painter.setBrush(background)
        painter.drawRoundedRect(
            QRectF(cx - s * 0.15, rect.top() + s * 0.37, s * 0.06, s * 0.18),
            s * 0.02,
            s * 0.02,
        )
        painter.drawRoundedRect(
            QRectF(cx + s * 0.09, rect.top() + s * 0.37, s * 0.06, s * 0.18),
            s * 0.02,
            s * 0.02,
        )
        return

    if special == "bluesky":
        wing_specs = (
            (-32.0, -s * 0.13, -s * 0.11, s * 0.32, s * 0.23),
            (22.0, -s * 0.12, s * 0.10, s * 0.24, s * 0.18),
            (-32.0, s * 0.13, -s * 0.11, s * 0.32, s * 0.23),
            (22.0, s * 0.12, s * 0.10, s * 0.24, s * 0.18),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        for angle, dx, dy, width, height in wing_specs:
            painter.save()
            painter.translate(cx + dx, cy + dy)
            painter.rotate(angle)
            painter.drawEllipse(QRectF(-width / 2, -height / 2, width, height))
            painter.restore()
        painter.drawEllipse(QRectF(cx - s * 0.018, cy - s * 0.16, s * 0.036, s * 0.32))
        return

    if special == "discord":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        face = QRectF(cx - s * 0.28, cy - s * 0.19, s * 0.56, s * 0.38)
        painter.drawRoundedRect(face, s * 0.16, s * 0.16)
        painter.setBrush(background)
        painter.drawEllipse(QPointF(cx - s * 0.10, cy - s * 0.01), s * 0.055, s * 0.075)
        painter.drawEllipse(QPointF(cx + s * 0.10, cy - s * 0.01), s * 0.055, s * 0.075)
        return

    if special == "mastodon":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawEllipse(QRectF(cx - s * 0.18, cy - s * 0.19, s * 0.36, s * 0.38))
        painter.drawEllipse(QRectF(cx - s * 0.32, cy - s * 0.13, s * 0.16, s * 0.25))
        painter.drawEllipse(QRectF(cx + s * 0.16, cy - s * 0.13, s * 0.16, s * 0.25))
        pen = QPen(ink, s * 0.065)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        trunk = QPainterPath()
        trunk.moveTo(cx - s * 0.03, cy + s * 0.12)
        trunk.cubicTo(
            cx - s * 0.04,
            cy + s * 0.25,
            cx - s * 0.08,
            cy + s * 0.29,
            cx - s * 0.15,
            cy + s * 0.26,
        )
        painter.drawPath(trunk)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawEllipse(QPointF(cx - s * 0.07, cy - s * 0.04), s * 0.026, s * 0.033)
        painter.drawEllipse(QPointF(cx + s * 0.07, cy - s * 0.04), s * 0.026, s * 0.033)
        return

    _text_glyph(painter, rect, style.glyph or platform_mark(style.label), ink)


def _paint_badge(painter: QPainter, style: PlatformStyle, rect: QRectF) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    size = min(rect.width(), rect.height())
    radius = size * 0.27
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    if style.special == "instagram":
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor("#FEDA75"))
        gradient.setColorAt(0.35, QColor("#FA7E1E"))
        gradient.setColorAt(0.68, QColor("#D62976"))
        gradient.setColorAt(1.0, QColor("#962FBF"))
        painter.fillPath(path, gradient)
    else:
        base = QColor(style.background)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, base.lighter(116))
        gradient.setColorAt(1.0, base)
        painter.fillPath(path, gradient)

    painter.save()
    painter.setClipPath(path)
    shine = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    shine.setColorAt(0.0, QColor(255, 255, 255, 62))
    shine.setColorAt(0.55, QColor(255, 255, 255, 0))
    painter.fillRect(rect, shine)
    painter.restore()

    light_badge = QColor(style.background).lightness() > 182
    border_color = QColor(0, 0, 0, 40) if light_badge else QColor(255, 255, 255, 62)
    border = QPen(border_color, max(1.0, size * 0.035))
    painter.setPen(border)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

    _draw_platform_glyph(painter, style, rect)
    painter.restore()


def paint_platform_badge(painter: QPainter, platform: object, rect: QRectF) -> None:
    """Draw a platform badge into an existing painter (used by graph nodes)."""
    _paint_badge(painter, platform_style(platform), rect)


def platform_badge_pixmap(
    platform: object,
    size: int = 30,
    *,
    device_ratio: float | None = None,
) -> QPixmap:
    """Render a crisp, high-DPI platform badge for labels and dialogs."""
    ratio = max(1.0, device_ratio if device_ratio is not None else screen_device_ratio())
    physical = max(1, round(size * ratio))
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    _paint_badge(painter, platform_style(platform), QRectF(0, 0, physical, physical))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def platform_icon(platform: object) -> QIcon:
    """Multi-size icon for list rows."""
    icon = QIcon()
    for size in (16, 20, 24, 28, 32, 40, 48, 64):
        icon.addPixmap(platform_badge_pixmap(platform, size, device_ratio=1.0))
    return icon
