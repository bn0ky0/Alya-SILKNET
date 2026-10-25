"""Interactive graph view for saved entities and relationship claims."""

from __future__ import annotations

from math import atan2, cos, hypot, pi, sin
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QMimeData,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsOpacityEffect,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from silknet.config import AppSettings
from silknet.core.enums import VerificationStatus
from silknet.core.exceptions import ValidationError
from silknet.core.models import Entity, GraphBoard, Relationship
from silknet.graph.model import InvestigationGraph
from silknet.services.container import ApplicationServices
from silknet.ui.assets import rounded_photo, screen_device_ratio
from silknet.ui.entity_manager import EntityRecordDialog
from silknet.ui.pages import PageHeader
from silknet.ui.platform_icons import paint_platform_badge, platform_badge_pixmap
from silknet.ui.source_widgets import SourcePicker
from silknet.ui.theme import graph_colors
from silknet.ui.widgets import (
    ON_GRAPH_ROLE,
    SUBTITLE_ROLE,
    ComboBox,
    EntityItemDelegate,
)

ENTITY_MIME_TYPE = "application/x-silknet-entity-id"
NODE_WIDTH = 214
NODE_HEIGHT = 84
ARROW_LENGTH = 10.0
ARROW_HALF_WIDTH = 4.4
ROLE_BADGE_GAP = 6.0

#: A deliberately huge scene keeps panning effectively infinite while still
#: giving QGraphicsView's scrollbars a stable coordinate system.
INFINITE_SCENE_RECT = QRectF(-100_000, -100_000, 200_000, 200_000)


class _CompactSplitter(QSplitter):
    """Splitter whose preferred height does not force the graph page to scroll."""

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        hint.setHeight(max(260, self.minimumSizeHint().height()))
        return hint


class GraphNodeItem(QGraphicsObject):
    position_committed = Signal(str, float, float)
    edit_requested = Signal(str)

    def __init__(self, entity: Entity, colors: dict[str, str], scale: float = 1.0) -> None:
        super().__init__()
        self.entity = entity
        self.colors = colors
        self.scale = 1.0
        self.text_scale = max(0.75, min(1.0, float(scale)))
        self.width = NODE_WIDTH * self.scale
        self.height = NODE_HEIGHT * self.scale
        self.padding = 12 * self.scale
        self.badge_size = 48 * self.scale
        self.edges: list[GraphEdgeItem] = []
        self.platform = str(entity.attributes.get("platform", "")).strip()
        self.is_social = entity.entity_type == "social_profile"
        self.role = (
            str(entity.attributes.get("role", "")).strip() if entity.entity_type == "person" else ""
        )
        self._hovered = False
        self.photo = self._load_photo()
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        type_label = entity.entity_type.replace("_", " ").title()
        if self.role:
            type_label = f"Person · {self.role}"
        tooltip = f"{entity.name}\n{type_label}"
        if self.platform:
            tooltip += f" · {self.platform}"
        if not self.photo.isNull():
            tooltip += "\nProfile photo attached"
        tooltip += (
            "\nDrag the dot on the right edge, Shift-drag, or middle-click and drag "
            "to another card to connect them."
        )
        self.setToolTip(tooltip)

    def _load_photo(self) -> QPixmap:
        image_path = str(self.entity.attributes.get("profile_image_path", ""))
        if not image_path:
            return QPixmap()
        source = QPixmap(image_path)
        if source.isNull():
            return QPixmap()
        # Keep three times the display resolution so photos stay sharp at the
        # graph's maximum zoom. The node always draws the source into a fixed
        # 48px badge with smooth transformation.
        return rounded_photo(
            source,
            max(1, round(self.badge_size * 3)),
            0.5,
            device_ratio=1.0,
        )

    def boundingRect(self) -> QRectF:
        badge = self.role_badge_rect()
        top = badge.top() if badge is not None else 0.0
        return QRectF(0, top, self.width, self.height - top)

    def _role_badge_font(self) -> QFont:
        font = QFont(QApplication.font())
        font.setBold(True)
        font.setPointSizeF(max(6.5, 7.4 * self.text_scale))
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8 * self.text_scale)
        return font

    def role_badge_rect(self) -> QRectF | None:
        """Return the floating role pill above a person card, if one is set."""
        if not self.role:
            return None
        metrics = QFontMetrics(self._role_badge_font())
        height = max(16.0, 20.0 * self.text_scale)
        text_width = metrics.horizontalAdvance(self.role.upper())
        width = min(
            self.width - 2 * self.padding,
            max(56.0 * self.text_scale, text_width + 30.0 * self.text_scale),
        )
        return QRectF(
            (self.width - width) / 2,
            -(height + ROLE_BADGE_GAP * self.text_scale),
            width,
            height,
        )

    def _paint_role_badge(self, painter: QPainter) -> None:
        badge = self.role_badge_rect()
        if badge is None:
            return
        accent = QColor(self.colors["accent"])
        fill = QColor(self.colors["accent_soft"])
        fill.setAlpha(242)
        painter.setPen(QPen(accent, 1.0))
        painter.setBrush(fill)
        painter.drawRoundedRect(badge, badge.height() / 2, badge.height() / 2)

        font = self._role_badge_font()
        painter.setFont(font)
        metrics = QFontMetrics(font)
        dot = max(1.7, 2.1 * self.text_scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawEllipse(
            QPointF(badge.left() + 10.0 * self.text_scale, badge.center().y()),
            dot,
            dot,
        )
        text_rect = badge.adjusted(18.0 * self.text_scale, 0, -8.0 * self.text_scale, 0)
        label = metrics.elidedText(
            self.role.upper(),
            Qt.TextElideMode.ElideRight,
            max(8, round(text_rect.width())),
        )
        painter.setPen(accent)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label,
        )

    def connection_port_rect(self) -> QRectF:
        size = 16 * self.scale
        return QRectF(self.width - size - 4 * self.scale, (self.height - size) / 2, size, size)

    def is_connection_port(self, point: QPointF) -> bool:
        return self.connection_port_rect().adjusted(-6, -6, 6, 6).contains(point)

    def _type_initials(self) -> str:
        words = self.entity.entity_type.replace("_", " ").split()
        return "".join(word[0] for word in words[:2]).upper() or "?"

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        bounds = QRectF(0, 0, self.width, self.height)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        fill = QColor(self.colors["selection"] if self.isSelected() else self.colors["surface"])
        border = QColor(self.colors["accent"] if self.isSelected() else self.colors["border"])
        radius = 12 * self.scale
        if self._hovered and not self.isSelected():
            glow = QColor(self.colors["accent"])
            glow.setAlpha(56)
            painter.setPen(QPen(glow, 5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bounds.adjusted(1, 1, -1, -1), radius, radius)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(border, 2.0 if self.isSelected() else 1.1))
        painter.drawRoundedRect(bounds.adjusted(1, 1, -1, -1), radius, radius)

        badge_rect = QRectF(
            self.padding,
            (self.height - self.badge_size) / 2,
            self.badge_size,
            self.badge_size,
        )
        if not self.photo.isNull():
            painter.drawPixmap(badge_rect, self.photo, QRectF(self.photo.rect()))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(self.colors["border"]), 1))
            painter.drawEllipse(badge_rect)
        elif self.is_social and self.platform:
            paint_platform_badge(painter, self.platform, badge_rect)
        else:
            painter.setBrush(QColor(self.colors["accent_soft"]))
            painter.setPen(QPen(QColor(self.colors["border"]), 1))
            painter.drawEllipse(badge_rect)
            font = painter.font()
            font.setBold(True)
            font.setPointSizeF(max(7.0, 11.0 * self.text_scale))
            painter.setFont(font)
            painter.setPen(QColor(self.colors["accent"]))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._type_initials())

        text_left = self.padding + self.badge_size + 11 * self.scale
        right = self.width - self.padding - 15 * self.scale
        if self.is_social and not self.photo.isNull():
            small = 20 * self.scale
            paint_platform_badge(
                painter,
                self.platform,
                QRectF(right - small, self.padding, small, small),
            )
            right -= small + 4 * self.scale
        name_width = max(20, round(right - text_left))
        font = painter.font()
        font.setBold(True)
        font.setPointSizeF(max(7.0, 10.0 * self.text_scale))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        name = metrics.elidedText(self.entity.name, Qt.TextElideMode.ElideRight, name_width)
        painter.setPen(QColor(self.colors["text"]))
        name_rect = QRectF(
            text_left,
            17 * self.scale,
            name_width,
            26 * self.scale,
        )
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, name)
        font.setBold(False)
        font.setPointSizeF(max(7.0, 8.5 * self.text_scale))
        painter.setFont(font)
        painter.setPen(QColor(self.colors["muted"]))
        type_text = (
            f"{self.platform} profile"
            if self.is_social and self.platform
            else self.entity.entity_type.replace("_", " ").title()
        )
        if self.entity.entity_type == "person":
            type_text = "Person"
        type_rect = QRectF(
            text_left,
            45 * self.scale,
            name_width,
            20 * self.scale,
        )
        painter.drawText(
            type_rect,
            Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(font).elidedText(type_text, Qt.TextElideMode.ElideRight, name_width),
        )

        port = self.connection_port_rect()
        port_fill = QColor(
            self.colors["accent"]
            if self._hovered or self.isSelected()
            else self.colors["surface_alt"]
        )
        port_border = QColor(self.colors["accent"])
        painter.setBrush(port_fill)
        painter.setPen(QPen(port_border, 1.4))
        painter.drawEllipse(port)
        plus = QColor(
            self.colors["accent_text"]
            if self._hovered or self.isSelected()
            else self.colors["accent"]
        )
        plus_pen = QPen(plus, max(1.3, 1.6 * self.scale))
        plus_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(plus_pen)
        center = port.center()
        arm = 3.2 * self.scale
        painter.drawLine(
            QPointF(center.x() - arm, center.y()),
            QPointF(center.x() + arm, center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - arm),
            QPointF(center.x(), center.y() + arm),
        )
        self._paint_role_badge(painter)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_path()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event) -> None:
        if self.is_connection_port(event.pos()):
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        position = self.pos()
        self.position_committed.emit(self.entity.id, position.x(), position.y())

    def mouseDoubleClickEvent(self, event) -> None:
        self.edit_requested.emit(self.entity.id)
        event.accept()


class GraphEdgeItem(QGraphicsPathItem):
    def __init__(
        self,
        relationship: Relationship,
        source: GraphNodeItem,
        target: GraphNodeItem,
        color: str,
        text_color: str,
        text_scale: float = 1.0,
    ) -> None:
        super().__init__()
        self.relationship = relationship
        self.source_node = source
        self.target_node = target
        self.color = QColor(color)
        self.text_color = QColor(text_color)
        self.text_scale = max(0.75, min(1.0, float(text_scale)))
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setToolTip(
            f"{source.entity.name} → {target.entity.name}\n{relationship.relationship_type}"
        )
        source.edges.append(self)
        target.edges.append(self)
        self.update_path()

    def update_path(self) -> None:
        source = self.source_node
        target = self.target_node
        start = source.pos() + QPointF(source.width / 2, source.height / 2)
        end = target.pos() + QPointF(target.width / 2, target.height / 2)
        dx, dy = end.x() - start.x(), end.y() - start.y()
        distance = hypot(dx, dy) or 1.0
        ux, uy = dx / distance, dy / distance
        source_inset = min(
            (source.width / 2) / max(abs(ux), 0.01),
            (source.height / 2) / max(abs(uy), 0.01),
        )
        target_inset = min(
            (target.width / 2) / max(abs(ux), 0.01),
            (target.height / 2) / max(abs(uy), 0.01),
        )
        start += QPointF(ux * source_inset, uy * source_inset)
        # Stop just before the target card so the arrowhead is not swallowed by
        # the card border. The gap is deliberately visible at every zoom level.
        arrow_gap = min(6.0, max(2.0, distance * 0.025))
        end -= QPointF(ux * (target_inset + arrow_gap), uy * (target_inset + arrow_gap))
        bend = min(42.0, distance * 0.10)
        nx, ny = -uy, ux
        path = QPainterPath(start)
        path.cubicTo(
            start + QPointF(nx * bend, ny * bend),
            end + QPointF(nx * bend, ny * bend),
            end,
        )
        self.setPath(path)
        self.update()

    def boundingRect(self) -> QRectF:
        return self.path().boundingRect().adjusted(-100, -50, 100, 40)

    def shape(self) -> QPainterPath:
        shape = QPainterPath()
        if self.path().isEmpty():
            return shape
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        shape.addPath(stroker.createStroke(self.path()))
        shape.addPolygon(self.arrow_polygon())
        midpoint = self.path().pointAtPercent(0.5)
        shape.addRect(QRectF(midpoint.x() - 90, midpoint.y() - 45, 180, 90))
        shape.setFillRule(Qt.FillRule.WindingFill)
        return shape

    def arrow_polygon(self) -> QPolygonF:
        """Return the visible arrowhead at the target end of this edge."""
        path = self.path()
        if path.isEmpty():
            return QPolygonF()
        end = path.pointAtPercent(1)
        tangent_start = path.pointAtPercent(0.95)
        angle = atan2(end.y() - tangent_start.y(), end.x() - tangent_start.x())
        ux, uy = cos(angle), sin(angle)
        nx, ny = -uy, ux
        return QPolygonF(
            [
                end,
                end
                - QPointF(
                    ux * ARROW_LENGTH - nx * ARROW_HALF_WIDTH,
                    uy * ARROW_LENGTH - ny * ARROW_HALF_WIDTH,
                ),
                end
                - QPointF(
                    ux * ARROW_LENGTH + nx * ARROW_HALF_WIDTH,
                    uy * ARROW_LENGTH + ny * ARROW_HALF_WIDTH,
                ),
            ]
        )

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        pen = QPen(self.color, 2.4 if self.isSelected() else 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = self.path()
        if path.isEmpty():
            painter.restore()
            return
        painter.drawPath(path)
        arrow = self.arrow_polygon()
        if not arrow.isEmpty():
            outline = QColor(self.text_color)
            # A status color can be the same muted tone as the label text. In
            # that case use the opposite ink so the head never disappears into
            # its own outline.
            if abs(outline.lightness() - self.color.lightness()) < 48:
                outline = QColor("#FFFFFF" if outline.lightness() > 128 else "#10141B")
            outline.setAlpha(200)
            arrow_pen = QPen(outline, 1.0)
            arrow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(arrow_pen)
            painter.setBrush(self.color)
            painter.drawPolygon(arrow)
        painter.restore()

    def _label_parts(self, painter: QPainter):
        """Return the label text, font, rectangle and background for this edge."""
        if not self.isVisible():
            return None
        path = self.path()
        if path.isEmpty():
            return None
        label = self.relationship.relationship_type
        font = painter.font()
        font.setPointSizeF(max(7.0, 8.5 * self.text_scale))
        font.setBold(True)
        metrics = QFontMetrics(font)
        label_width = metrics.horizontalAdvance(label) + 14
        label_height = max(18, metrics.height() + 5)
        anchor = path.pointAtPercent(0.5)
        before = path.pointAtPercent(0.47)
        after = path.pointAtPercent(0.53)
        dx, dy = after.x() - before.x(), after.y() - before.y()
        distance = hypot(dx, dy) or 1.0
        nx, ny = -dy / distance, dx / distance
        if ny > 0:
            nx, ny = -nx, -ny
        center = anchor + QPointF(nx * (label_height / 2 + 10), ny * (label_height / 2 + 10))
        label_rect = QRectF(
            center.x() - label_width / 2,
            center.y() - label_height / 2,
            label_width,
            label_height,
        )
        label_bg = (
            QColor(13, 29, 46, 212)
            if self.text_color.lightness() > 128
            else QColor(255, 255, 255, 235)
        )
        return label, font, label_rect, label_bg

    def label_rect(self, painter: QPainter) -> QRectF | None:
        """Public geometry used by the canvas to keep labels from colliding."""
        parts = self._label_parts(painter)
        return parts[2] if parts is not None else None

    def draw_label(self, painter: QPainter, offset: QPointF | None = None) -> None:
        """Draw the relationship label above cards, in viewport coordinates."""
        parts = self._label_parts(painter)
        if parts is None:
            return
        label, font, label_rect, label_bg = parts
        if offset is not None:
            label_rect = label_rect.translated(offset)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(font)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(label_bg))
        painter.drawRoundedRect(label_rect, 7, 7)
        painter.setPen(self.text_color)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()


class GraphCanvas(QGraphicsView):
    """Infinite graph viewport with pan, link and drag-out gestures."""

    entity_dropped = Signal(str, float, float)
    connection_requested = Signal(str, str)
    node_remove_requested = Signal(str)
    edit_selected_requested = Signal()
    delete_selected_requested = Signal()

    def __init__(
        self,
        scene: QGraphicsScene,
        colors: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(scene, parent)
        self.colors = colors
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumHeight(260)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.viewport().setMouseTracking(True)
        self._pan_origin: QPoint | None = None
        self._link_source: GraphNodeItem | None = None
        self._link_preview: QGraphicsPathItem | None = None
        self._connection_mode = False
        self._drag_node: GraphNodeItem | None = None
        self._drag_origin: QPointF | None = None
        self._drag_grab_offset: QPointF | None = None
        self._drag_out = False
        self._remove_hint_text = "Release outside the canvas to remove this card"
        self._drop_active = False
        self._drop_phase = 0.0
        self._fit_animation: QVariantAnimation | None = None
        self._center_animation: QVariantAnimation | None = None
        self._drop_timer = QTimer(self)
        self._drop_timer.setInterval(45)
        self._drop_timer.timeout.connect(self._pulse_drop_border)
        self._empty_hint = QLabel(self.viewport())
        self._empty_hint.setObjectName("graphEmptyHint")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._empty_hint.setWordWrap(True)
        self._empty_hint.hide()

        self._remove_hint = QLabel(self.viewport())
        self._remove_hint.setObjectName("graphRemoveHint")
        self._remove_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._remove_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._remove_hint.setWordWrap(True)
        self._remove_hint.hide()
        self._remove_effect = QGraphicsOpacityEffect(self._remove_hint)
        self._remove_effect.setOpacity(0.0)
        self._remove_hint.setGraphicsEffect(self._remove_effect)
        self._remove_animation = QPropertyAnimation(self._remove_effect, b"opacity", self)
        self._remove_animation.setDuration(140)
        self._remove_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._remove_animation.finished.connect(self._finish_remove_hint)

    def set_remove_hint_text(self, text: str) -> None:
        self._remove_hint_text = text.strip() or "Release outside the canvas"
        if self._remove_hint.isVisible():
            self._remove_hint.setText(self._remove_hint_text)
            self._position_remove_hint()

    def _pulse_drop_border(self) -> None:
        self._drop_phase = (self._drop_phase + 0.12) % 1.0
        self.viewport().update()

    def _show_remove_hint(self, visible: bool) -> None:
        self._remove_animation.stop()
        if visible:
            self._remove_hint.setText(self._remove_hint_text)
            self._remove_hint.adjustSize()
            self._position_remove_hint()
            self._remove_hint.show()
            self._remove_hint.raise_()
            self._remove_animation.setStartValue(self._remove_effect.opacity())
            self._remove_animation.setEndValue(1.0)
            self._remove_animation.start()
        else:
            self._remove_animation.setStartValue(self._remove_effect.opacity())
            self._remove_animation.setEndValue(0.0)
            self._remove_animation.start()

    def _finish_remove_hint(self) -> None:
        if self._remove_effect.opacity() <= 0.05:
            self._remove_hint.hide()

    def _position_remove_hint(self) -> None:
        if not hasattr(self, "_remove_hint"):
            return
        self._remove_hint.setFixedWidth(max(200, min(380, self.viewport().width() - 60)))
        self._remove_hint.adjustSize()
        self._remove_hint.move(
            (self.viewport().width() - self._remove_hint.width()) // 2,
            self.viewport().height() - self._remove_hint.height() - 26,
        )

    def set_empty_hint(self, message: str | None) -> None:
        if message:
            self._empty_hint.setText(message)
            self._size_empty_hint()
            self._empty_hint.show()
            self._empty_hint.raise_()
            self._position_empty_hint()
        else:
            self._empty_hint.hide()

    def _size_empty_hint(self) -> None:
        self._empty_hint.setFixedWidth(max(180, min(420, self.viewport().width() - 80)))
        self._empty_hint.adjustSize()

    def _position_empty_hint(self) -> None:
        if not hasattr(self, "_empty_hint") or self._empty_hint.isHidden():
            return
        self._empty_hint.move(
            (self.viewport().width() - self._empty_hint.width()) // 2,
            (self.viewport().height() - self._empty_hint.height()) // 2,
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The hint is often populated while its page is still hidden, when
        # ``isVisible`` is false. Re-centre it once the canvas is on screen.
        if hasattr(self, "_empty_hint") and not self._empty_hint.isHidden():
            self._size_empty_hint()
        self._position_empty_hint()
        self._position_remove_hint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_empty_hint") and not self._empty_hint.isHidden():
            self._size_empty_hint()
        self._position_empty_hint()
        self._position_remove_hint()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and hasattr(self, "_empty_hint"):
            self._size_empty_hint()
            self._position_empty_hint()

    def set_colors(self, colors: dict[str, str]) -> None:
        self.colors = colors
        self.viewport().update()

    def set_connection_mode(self, enabled: bool) -> None:
        self._connection_mode = enabled
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.RubberBandDrag
        )
        self.viewport().setCursor(
            Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        )

    def stop_view_animations(self) -> None:
        """Cancel a fit or centre glide before another view change takes over."""

        for attribute in ("_fit_animation", "_center_animation"):
            animation = getattr(self, attribute)
            if animation is not None:
                animation.stop()
                setattr(self, attribute, None)

    def wheelEvent(self, event) -> None:
        self.stop_view_animations()
        if event.angleDelta().y() == 0:
            super().wheelEvent(event)
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        current = self.transform().m11()
        if factor < 1 and current <= 0.22:
            event.accept()
            return
        target = max(0.22, min(3.0, current * factor))
        if abs(target - current) < 1e-6:
            event.accept()
            return
        self.scale(target / current, target / current)
        event.accept()

    def animate_fit(
        self,
        bounds: QRectF,
        *,
        max_scale: float = 1.0,
        duration: int = 240,
    ) -> None:
        """Glide to a fitted view instead of teleporting the transform."""

        viewport = self.viewport().rect()
        if bounds.width() <= 0 or bounds.height() <= 0:
            return
        target_scale = min(viewport.width() / bounds.width(), viewport.height() / bounds.height())
        target_scale = max(0.22, min(max_scale, target_scale))
        start_scale = self.transform().m11()
        start_center = self.mapToScene(viewport.center())
        end_center = bounds.center()
        self.stop_view_animations()
        if duration <= 0 or not self.isVisible():
            self.setTransform(QTransform.fromScale(target_scale, target_scale))
            self.centerOn(end_center)
            return
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def update(progress) -> None:
            factor = float(progress)
            scale = start_scale + (target_scale - start_scale) * factor
            center = start_center + (end_center - start_center) * factor
            self.setTransform(QTransform.fromScale(scale, scale))
            self.centerOn(center)

        animation.valueChanged.connect(update)
        animation.finished.connect(self._clear_fit_animation)
        self._fit_animation = animation
        animation.start()

    def _clear_fit_animation(self) -> None:
        self._fit_animation = None

    def _clear_center_animation(self) -> None:
        self._center_animation = None

    def animate_center_on(
        self,
        target: QPointF,
        *,
        duration: int = 200,
    ) -> None:
        """Glide the viewport to ``target`` without changing the zoom level."""

        start = self.mapToScene(self.viewport().rect().center())
        self.stop_view_animations()
        if duration <= 0 or not self.isVisible():
            self.centerOn(target)
            return
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def update(progress) -> None:
            factor = float(progress)
            self.centerOn(start + (target - start) * factor)

        animation.valueChanged.connect(update)
        animation.finished.connect(self._clear_center_animation)
        self._center_animation = animation
        animation.start()

    def _begin_pan(self, point: QPoint) -> None:
        self._pan_origin = point
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def _end_pan(self) -> None:
        self._pan_origin = None
        self.viewport().setCursor(
            Qt.CursorShape.CrossCursor if self._connection_mode else Qt.CursorShape.ArrowCursor
        )

    def _is_drag_outside(self, point: QPoint) -> bool:
        return not self.viewport().rect().adjusted(2, 2, -2, -2).contains(point)

    def _node_at(self, point: QPoint) -> GraphNodeItem | None:
        for item in self.scene().items(self.mapToScene(point)):
            if isinstance(item, GraphNodeItem):
                return item
        return None

    def _port_point(self, node: GraphNodeItem) -> QPointF:
        port = node.connection_port_rect()
        return node.pos() + port.center()

    def _start_link(self, node: GraphNodeItem) -> None:
        self._cancel_link()
        self._link_source = node
        preview = QGraphicsPathItem()
        pen = QPen(QColor(self.colors["accent"]), 2.2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        preview.setPen(pen)
        preview.setZValue(100)
        preview.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene().addItem(preview)
        self._link_preview = preview
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def _update_link_preview(self, point: QPoint) -> None:
        if self._link_source is None or self._link_preview is None:
            return
        end = self.mapToScene(point)
        path = QPainterPath(self._port_point(self._link_source))
        path.lineTo(end)
        self._link_preview.setPath(path)
        self.viewport().update()

    def _cancel_link(self) -> None:
        if self._link_preview is not None:
            if self._link_preview.scene() is not None:
                self.scene().removeItem(self._link_preview)
            self._link_preview = None
        self._link_source = None
        self.viewport().setCursor(
            Qt.CursorShape.CrossCursor if self._connection_mode else Qt.CursorShape.ArrowCursor
        )

    def _finish_link(self, point: QPoint) -> None:
        source = self._link_source
        target = self._node_at(point)
        self._cancel_link()
        if source is not None and target is not None and target is not source:
            self.connection_requested.emit(source.entity.id, target.entity.id)

    def mousePressEvent(self, event) -> None:
        button = event.button()
        point = event.position().toPoint()
        if button == Qt.MouseButton.RightButton:
            self._begin_pan(point)
            event.accept()
            return
        if button == Qt.MouseButton.MiddleButton:
            node = self._node_at(point)
            if node is not None:
                self._start_link(node)
                self._update_link_preview(point)
                event.accept()
                return
            self._begin_pan(point)
            event.accept()
            return
        self._drag_node = None
        self._drag_origin = None
        self._drag_grab_offset = None
        self._drag_out = False
        if button == Qt.MouseButton.LeftButton:
            node = self._node_at(point)
            if node is not None:
                scene_point = self.mapToScene(point)
                local_point = node.mapFromScene(scene_point)
                wants_link = (
                    self._connection_mode
                    or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    or node.is_connection_port(local_point)
                )
                if wants_link:
                    self._start_link(node)
                    self._update_link_preview(point)
                    event.accept()
                    return
                self._drag_node = node
                self._drag_origin = node.pos()
                self._drag_grab_offset = scene_point - node.pos()
                self._drag_out = False
                # Move the card ourselves so the drag-out gesture stays in
                # control even when the pointer leaves the viewport.
                node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        point = event.position().toPoint()
        if self._pan_origin is not None:
            delta = point - self._pan_origin
            self._pan_origin = point
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        if self._link_source is not None:
            self._update_link_preview(point)
            event.accept()
            return
        if self._drag_node is not None and event.buttons() & Qt.MouseButton.LeftButton:
            node = self._drag_node
            outside = self._is_drag_outside(point)
            if outside != self._drag_out:
                self._drag_out = outside
                self._show_remove_hint(outside)
            if outside:
                if self._drag_origin is not None:
                    node.setPos(self._drag_origin)
                node.setOpacity(0.35)
            else:
                node.setOpacity(1.0)
                if self._drag_origin is not None and self._drag_grab_offset is not None:
                    node.setPos(self.mapToScene(point) - self._drag_grab_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        button = event.button()
        if button in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            if self._pan_origin is not None:
                self._end_pan()
                event.accept()
                return
        if button in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            if self._link_source is not None:
                self._finish_link(event.position().toPoint())
                event.accept()
                return
        if button == Qt.MouseButton.LeftButton and self._drag_node is not None:
            node = self._drag_node
            # A fast drag can release outside without sending a final move
            # event, so also test the release point itself.
            dragged_out = self._drag_out or self._is_drag_outside(event.position().toPoint())
            origin = self._drag_origin
            self._drag_node = None
            self._drag_origin = None
            self._drag_grab_offset = None
            self._drag_out = False
            self._show_remove_hint(False)
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            node.setOpacity(1.0)
            if dragged_out and origin is not None:
                # Keep the saved layout untouched; the page removes the card
                # from this graph after the release.
                node.setPos(origin)
            super().mouseReleaseEvent(event)
            if dragged_out:
                self.node_remove_requested.emit(node.entity.id)
            event.accept()
            return
        if self._drag_node is not None:
            self._drag_node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            self._drag_node.setOpacity(1.0)
        self._drag_node = None
        self._drag_origin = None
        self._drag_grab_offset = None
        self._drag_out = False
        self._show_remove_hint(False)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._link_source is not None:
                self._cancel_link()
                event.accept()
                return
            if self._drag_node is not None:
                node = self._drag_node
                node.setOpacity(1.0)
                if self._drag_origin is not None:
                    node.setPos(self._drag_origin)
                node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                self._drag_node = None
                self._drag_origin = None
                self._drag_grab_offset = None
                self._drag_out = False
                self._show_remove_hint(False)
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected = self.scene().selectedItems()
            if any(isinstance(item, GraphEdgeItem) for item in selected):
                self.delete_selected_requested.emit()
                event.accept()
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if isinstance(item, GraphEdgeItem):
            if not item.isSelected():
                self.scene().clearSelection()
                item.setSelected(True)
            menu = QMenu(self)
            edit = menu.addAction("Edit claim…")
            delete = menu.addAction("Delete claim")
            chosen = menu.exec(event.globalPos())
            if chosen is edit:
                self.edit_selected_requested.emit()
            elif chosen is delete:
                self.delete_selected_requested.emit()
            event.accept()
            return
        if isinstance(item, GraphNodeItem):
            if not item.isSelected():
                self.scene().clearSelection()
                item.setSelected(True)
            menu = QMenu(self)
            edit = menu.addAction("Edit entity…")
            remove = menu.addAction("Remove from this graph")
            chosen = menu.exec(event.globalPos())
            if chosen is edit:
                self.edit_selected_requested.emit()
            elif chosen is remove:
                self.node_remove_requested.emit(item.entity.id)
            event.accept()
            return
        super().contextMenuEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(ENTITY_MIME_TYPE):
            self._drop_active = True
            self._drop_phase = 0.0
            self._drop_timer.start()
            self.viewport().update()
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(ENTITY_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self._drop_active = False
        self._drop_timer.stop()
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._drop_active = False
        self._drop_timer.stop()
        self.viewport().update()
        if not event.mimeData().hasFormat(ENTITY_MIME_TYPE):
            super().dropEvent(event)
            return
        entity_id = bytes(event.mimeData().data(ENTITY_MIME_TYPE)).decode("utf-8")
        scene_position = self.mapToScene(event.position().toPoint())
        self.entity_dropped.emit(entity_id, scene_position.x(), scene_position.y())
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        canvas = QColor(self.colors.get("canvas", "transparent"))
        if canvas.alpha() > 0:
            painter.fillRect(rect, canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        dot = QColor(self.colors.get("border", "#888888"))
        dot.setAlpha(70 if canvas.lightness() < 128 else 90)
        painter.setPen(QPen(dot, 1))
        spacing = 32
        left = int(rect.left()) - (int(rect.left()) % spacing)
        top = int(rect.top()) - (int(rect.top()) % spacing)
        points = [
            QPointF(x, y)
            for x in range(left, int(rect.right()) + spacing, spacing)
            for y in range(top, int(rect.bottom()) + spacing, spacing)
        ]
        if points:
            painter.drawPoints(QPolygonF(points))

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        scene = self.scene()
        if scene is None:
            return
        occupied = [
            item.sceneBoundingRect().adjusted(-6, -4, 6, 4)
            for item in scene.items()
            if isinstance(item, GraphNodeItem) and item.isVisible()
        ]
        labels: list[tuple[GraphEdgeItem, QRectF]] = []
        for item in scene.items():
            if not isinstance(item, GraphEdgeItem) or not item.isVisible():
                continue
            label_rect = item.label_rect(painter)
            if label_rect is not None:
                labels.append((item, label_rect))
        labels.sort(key=lambda pair: (pair[1].center().y(), pair[1].center().x()))
        if len(labels) > 120:
            # Dense maps are already visually busy; avoid an expensive
            # quadratic placement pass on every pan or zoom frame.
            for item, _label_rect in labels:
                item.draw_label(painter)
            return

        for item, label_rect in labels:
            step = label_rect.height() + 4
            chosen = label_rect
            for attempt in range(9):
                shift = (
                    0.0
                    if attempt == 0
                    else ((attempt + 1) // 2) * step * (-1 if attempt % 2 else 1)
                )
                candidate = label_rect.translated(0.0, shift)
                padded = candidate.adjusted(-3, -2, 3, 2)
                if not any(padded.intersects(other) for other in occupied):
                    chosen = candidate
                    break
            occupied.append(chosen.adjusted(-3, -2, 3, 2))
            item.draw_label(painter, QPointF(0.0, chosen.top() - label_rect.top()))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._drop_active:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pulse = (sin(self._drop_phase * 2 * pi) + 1) / 2
        accent = QColor(self.colors["accent"])
        accent.setAlpha(110 + round(pulse * 110))
        pen = QPen(accent, 2.2, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setDashOffset(-self._drop_phase * 24)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.viewport().rect().adjusted(4, 4, -4, -4), 12, 12)


class RelationshipRecordDialog(QDialog):
    def __init__(
        self,
        services: ApplicationServices,
        relationship: Relationship | None = None,
        parent: QWidget | None = None,
        domain: str = "general",
        allowed_entity_ids: set[str] | None = None,
        source_id: str | None = None,
        target_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.relationship = relationship
        self.domain = domain
        self.saved_relationship: Relationship | None = None
        self.deleted = False
        entities = services.entities.list()
        if allowed_entity_ids is not None:
            entities = [entity for entity in entities if entity.id in allowed_entity_ids]
        if domain == "family" or (
            relationship is not None and relationship.relationship_domain == "family"
        ):
            entities = [entity for entity in entities if entity.entity_type == "person"]
        self.setWindowTitle("Edit relationship" if relationship else "Add relationship")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.source_field = ComboBox()
        self.target_field = ComboBox()
        for entity in entities:
            label = f"{entity.name} · {entity.entity_type.replace('_', ' ')}"
            self.source_field.addItem(label, entity.id)
            self.target_field.addItem(label, entity.id)
        self.type_field = QLineEdit()
        self.type_field.setPlaceholderText("e.g. works with, owns, reported by")
        self.status_field = ComboBox()
        for status in VerificationStatus:
            self.status_field.addItem(status.value.replace("_", " ").title(), status.value)
        self.status_field.setCurrentIndex(
            self.status_field.findData(VerificationStatus.UNVERIFIED.value)
        )
        self.start_date_field = QLineEdit()
        self.start_date_field.setMaxLength(10)
        self.start_date_field.setPlaceholderText("YYYY-MM-DD (optional)")
        self.end_date_field = QLineEdit()
        self.end_date_field.setMaxLength(10)
        self.end_date_field.setPlaceholderText("YYYY-MM-DD (optional, or leave blank)")
        self.description_field = QLineEdit()
        self.confidence_field = QLineEdit()
        self.notes_field = QLineEdit()
        self.source_picker = SourcePicker(
            services.sources.list(), relationship.source_ids if relationship else ()
        )
        form.addRow("From", self.source_field)
        form.addRow("To", self.target_field)
        form.addRow("Relationship", self.type_field)
        form.addRow("Status", self.status_field)
        form.addRow("Start date", self.start_date_field)
        form.addRow("End date", self.end_date_field)
        form.addRow("Description", self.description_field)
        form.addRow("Confidence notes", self.confidence_field)
        form.addRow("Notes", self.notes_field)
        form.addRow("Evidence sources", self.source_picker)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        self.delete_button = None
        if relationship is not None:
            self.delete_button = self.buttons.addButton(
                "Delete claim",
                QDialogButtonBox.ButtonRole.DestructiveRole,
            )
            self.delete_button.setObjectName("dangerButton")
            self.delete_button.setToolTip("Delete this relationship claim")
            self.delete_button.clicked.connect(self._delete)
        layout.addWidget(self.buttons)
        if len(entities) < 2:
            self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        if relationship is not None:
            self.source_field.setCurrentIndex(
                self.source_field.findData(relationship.source_entity_id)
            )
            self.target_field.setCurrentIndex(
                self.target_field.findData(relationship.target_entity_id)
            )
            self.type_field.setText(relationship.relationship_type)
            self.status_field.setCurrentIndex(
                self.status_field.findData(relationship.verification_status.value)
            )
            self.start_date_field.setText(relationship.start_date or "")
            self.end_date_field.setText(relationship.end_date or "")
            self.description_field.setText(relationship.description)
            self.confidence_field.setText(relationship.confidence_notes)
            self.notes_field.setText(relationship.notes)
        else:
            if source_id:
                index = self.source_field.findData(source_id)
                if index >= 0:
                    self.source_field.setCurrentIndex(index)
            if target_id:
                index = self.target_field.findData(target_id)
                if index >= 0:
                    self.target_field.setCurrentIndex(index)
            if source_id is None and target_id is None and len(entities) > 1:
                self.target_field.setCurrentIndex(1)
            self.type_field.setFocus()
        # QLineEdit.setText moves its cursor to the end, which can leave long
        # prefilled notes scrolled out of view when the dialog opens.
        for field in (
            self.type_field,
            self.start_date_field,
            self.end_date_field,
            self.description_field,
            self.confidence_field,
            self.notes_field,
        ):
            field.setCursorPosition(0)

    def _confirm_delete(self) -> bool:
        claim = self.type_field.text().strip() or "relationship"
        source = self.source_field.currentText()
        target = self.target_field.currentText()
        answer = QMessageBox.question(
            self,
            "Delete relationship claim?",
            f"Delete the “{claim}” claim from {source} to {target}?\n\n"
            "The entities and evidence sources stay in the workspace.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _delete(self) -> None:
        relationship = self.relationship
        if relationship is None or not self._confirm_delete():
            return
        try:
            deleted = self.services.relationships.delete(relationship.id)
        except (LookupError, DatabaseError) as exc:
            QMessageBox.warning(self, "Relationship could not be deleted", str(exc))
            return
        if not deleted:
            QMessageBox.information(
                self,
                "Claim already removed",
                "That relationship claim was already deleted.",
            )
            return
        self.deleted = True
        self.saved_relationship = None
        self.accept()

    def _save(self) -> None:
        try:
            if self.relationship is None:
                create_relationship = (
                    self.services.family.create_relationship
                    if self.domain == "family"
                    else self.services.relationships.create
                )
                self.saved_relationship = create_relationship(
                    source_entity_id=self.source_field.currentData(),
                    target_entity_id=self.target_field.currentData(),
                    relationship_type=self.type_field.text(),
                    verification_status=self.status_field.currentData(),
                    description=self.description_field.text(),
                    start_date=self.start_date_field.text().strip() or None,
                    end_date=self.end_date_field.text().strip() or None,
                    confidence_notes=self.confidence_field.text(),
                    notes=self.notes_field.text(),
                    source_ids=self.source_picker.selected_ids(),
                    relationship_domain=self.domain,
                )
            else:
                old = self.relationship
                updated = Relationship(
                    id=old.id,
                    source_entity_id=self.source_field.currentData(),
                    target_entity_id=self.target_field.currentData(),
                    relationship_type=self.type_field.text(),
                    description=self.description_field.text(),
                    start_date=self.start_date_field.text().strip() or None,
                    end_date=self.end_date_field.text().strip() or None,
                    verification_status=self.status_field.currentData(),
                    confidence_notes=self.confidence_field.text(),
                    notes=self.notes_field.text(),
                    source_ids=self.source_picker.selected_ids(),
                    created_at=old.created_at,
                    relationship_domain=old.relationship_domain,
                )
                self.saved_relationship = self.services.relationships.update(updated)
        except (ValidationError, LookupError, ValueError, DatabaseError) as exc:
            QMessageBox.warning(self, "Relationship could not be saved", str(exc))
            return
        self.accept()


class GraphBoardDialog(QDialog):
    """Small, themed name prompt for creating or renaming a graph."""

    def __init__(
        self,
        title: str,
        name: str = "",
        submit_label: str = "Save graph",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.saved_name: str | None = None
        self.setWindowTitle(title)
        self.setMinimumWidth(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        copy = QLabel(
            "Give this graph a short name. Its layout and dragged entities stay separate."
        )
        copy.setObjectName("cardDescription")
        copy.setWordWrap(True)
        self.name_field = QLineEdit(name)
        self.name_field.setPlaceholderText("e.g. Alya's circle")
        self.name_field.setMaxLength(80)
        self.name_field.returnPressed.connect(self._save)
        layout.addWidget(heading)
        layout.addWidget(copy)
        layout.addWidget(self.name_field)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(submit_label)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name_field.selectAll()

    def _save(self) -> None:
        name = " ".join(self.name_field.text().split())
        if not name:
            QMessageBox.warning(self, "Graph name required", "Enter a name for this graph.")
            return
        if len(name) > 80:
            QMessageBox.warning(
                self, "Graph name too long", "Graph names must be 80 characters or fewer."
            )
            return
        self.saved_name = name
        self.accept()


class RestoreCardDialog(QDialog):
    """Choose whether a card brings its old claim lines back with it."""

    CARD_ONLY = "card"
    WITH_CONNECTIONS = "connections"

    def __init__(
        self,
        entity_name: str,
        connection_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.choice: str | None = None
        self.setWindowTitle("Restore card")
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(12)

        eyebrow = QLabel("RETURNING TO THIS GRAPH")
        eyebrow.setObjectName("pageEyebrow")
        heading = QLabel(f"Bring back “{entity_name}”?")
        heading.setObjectName("dialogHeading")
        heading.setWordWrap(True)
        connection_word = "connection" if connection_count == 1 else "connections"
        copy = QLabel(
            f"This card had {connection_count} saved {connection_word} on this graph. "
            "You can bring those lines back, or place just the card and keep the "
            "connections hidden. No relationship records will be deleted."
        )
        copy.setObjectName("cardDescription")
        copy.setWordWrap(True)
        privacy = QLabel("Card only is useful when you want a clean graph without the old context.")
        privacy.setObjectName("subtleText")
        privacy.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("quietButton")
        cancel.clicked.connect(self.reject)
        card_only = QPushButton("Card only")
        card_only.setObjectName("quietButton")
        card_only.setToolTip("Place the card without showing its previous connections.")
        card_only.clicked.connect(lambda: self._choose(self.CARD_ONLY))
        with_connections = QPushButton(f"Restore {connection_count} {connection_word}")
        with_connections.setObjectName("actionButton")
        with_connections.setToolTip("Place the card and show the connections it had before.")
        with_connections.clicked.connect(lambda: self._choose(self.WITH_CONNECTIONS))
        with_connections.setDefault(True)
        buttons.addWidget(cancel)
        buttons.addStretch(1)
        buttons.addWidget(card_only)
        buttons.addWidget(with_connections)

        layout.addWidget(eyebrow)
        layout.addWidget(heading)
        layout.addWidget(copy)
        layout.addWidget(privacy)
        layout.addSpacing(4)
        layout.addLayout(buttons)

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()


def _palette_icon(entity: Entity, colors: dict[str, str]) -> QIcon:
    image_path = str(entity.attributes.get("profile_image_path", "")).strip()
    if image_path:
        pixmap = rounded_photo(image_path, 30, 0.5)
        if not pixmap.isNull():
            return QIcon(pixmap)
    platform = str(entity.attributes.get("platform", "")).strip()
    if entity.entity_type == "social_profile" and platform:
        return QIcon(platform_badge_pixmap(platform, 30))
    ratio = max(1.0, screen_device_ratio())
    physical = max(1, round(30 * ratio))
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(ratio)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    size = 30.0
    painter.setBrush(QColor(colors["accent_soft"]))
    painter.setPen(QPen(QColor(colors["border"]), 1))
    painter.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    words = entity.entity_type.replace("_", " ").split()
    initials = "".join(word[0] for word in words[:2]).upper() or "?"
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(max(8, round(12 * ratio)))
    painter.setFont(font)
    painter.setPen(QColor(colors["accent"]))
    painter.drawText(
        QRectF(0, 0, size, size),
        Qt.AlignmentFlag.AlignCenter,
        initials,
    )
    painter.end()
    return QIcon(pixmap)


class EntityPaletteList(QListWidget):
    """Entity list that starts a copy drag for the graph canvas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setUniformItemSizes(False)

    def startDrag(self, supported_actions) -> None:
        item = self.currentItem()
        if item is None:
            return
        entity_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not entity_id:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(ENTITY_MIME_TYPE, entity_id.encode("utf-8"))
        drag.setMimeData(mime)
        icon = item.icon()
        if not icon.isNull():
            pixmap = icon.pixmap(QSize(38, 38))
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        drag.exec(Qt.DropAction.CopyAction)


class GraphPage(QWidget):
    navigate_requested = Signal(str)
    records_changed = Signal()
    message = Signal(str)

    def __init__(self, services: ApplicationServices, settings: AppSettings | None = None) -> None:
        super().__init__()
        self.services = services
        self.settings = settings or AppSettings()
        self.colors = graph_colors(self.settings)
        self._nodes: dict[str, GraphNodeItem] = {}
        self._edges: dict[str, GraphEdgeItem] = {}
        self._positions: dict[str, tuple[float, float]] = {}
        self._current_board_id = services.graph_layout.ensure_workspace().id
        self._has_rendered = False
        self._fit_pending = True
        self._reveal_animation: QVariantAnimation | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(
            PageHeader(
                "Workspace",
                "Investigation Graph",
                "Arrange separate maps, then drag entity cards from the right to build each one.",
                compact=True,
                inline=True,
            )
        )

        self.toolbar = QFrame()
        self.toolbar.setObjectName("graphToolbar")
        toolbar_layout = QVBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(9, 6, 9, 6)
        toolbar_layout.setSpacing(6)

        board_row = QHBoxLayout()
        board_row.setSpacing(6)
        self.board_selector = ComboBox()
        self.board_selector.setMinimumWidth(150)
        self.board_selector.setMaximumWidth(280)
        self.board_selector.setSizeAdjustPolicy(ComboBox.SizeAdjustPolicy.AdjustToContents)
        self.board_selector.setAccessibleName("Graph view")
        self.board_selector.setToolTip("Switch between independent graph views.")
        self.board_selector.currentIndexChanged.connect(self._board_changed)
        self.new_board_button = QPushButton("New")
        self.new_board_button.setObjectName("toolButton")
        self.new_board_button.setToolTip("Create a new empty graph view.")
        self.new_board_button.clicked.connect(self._new_board)
        self.rename_board_button = QPushButton("Rename")
        self.rename_board_button.setObjectName("toolButton")
        self.rename_board_button.setToolTip("Rename the current graph view.")
        self.rename_board_button.clicked.connect(self._rename_board)
        self.delete_board_button = QPushButton("Delete")
        self.delete_board_button.setObjectName("toolButton")
        self.delete_board_button.clicked.connect(self._delete_board)
        self.fit_button = QPushButton("Fit")
        self.fit_button.setObjectName("toolButton")
        self.fit_button.setToolTip("Fit every card into the canvas.")
        self.fit_button.clicked.connect(self.fit_graph)
        board_row.addWidget(self.board_selector)
        board_row.addWidget(self.new_board_button)
        board_row.addWidget(self.rename_board_button)
        board_row.addWidget(self.delete_board_button)
        board_row.addStretch(1)
        board_row.addWidget(self.fit_button)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.filter_field = QLineEdit()
        self.filter_field.setPlaceholderText("Filter cards…")
        self.filter_field.setClearButtonEnabled(True)
        self.filter_field.setToolTip("Filter this graph by name, type or platform.")
        self.filter_field.textChanged.connect(self._apply_filter)
        self.type_filter = ComboBox()
        self.type_filter.setMinimumWidth(108)
        self.type_filter.setMaximumWidth(155)
        self.type_filter.setAccessibleName("Entity type filter")
        self.type_filter.currentIndexChanged.connect(self._apply_filter)
        self.add_entity_button = QPushButton("Add entity")
        self.add_entity_button.setObjectName("toolAction")
        self.add_entity_button.clicked.connect(self._add_entity)
        self.add_relationship_button = QPushButton("Relationship")
        self.add_relationship_button.setObjectName("toolButton")
        self.add_relationship_button.setToolTip("Create a relationship claim between two cards.")
        self.add_relationship_button.clicked.connect(self._add_relationship)
        self.edit_button = QPushButton("Edit")
        self.edit_button.setObjectName("toolButton")
        self.edit_button.setEnabled(False)
        self.edit_button.setToolTip("Edit the selected card or relationship.")
        self.edit_button.clicked.connect(self._edit_selected)
        filter_row.addWidget(self.filter_field, 1)
        filter_row.addWidget(self.type_filter)
        filter_row.addWidget(self.add_entity_button)
        filter_row.addWidget(self.add_relationship_button)
        filter_row.addWidget(self.edit_button)

        toolbar_layout.addLayout(board_row)
        toolbar_layout.addLayout(filter_row)
        layout.addWidget(self.toolbar)

        splitter = _CompactSplitter(Qt.Orientation.Horizontal)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(INFINITE_SCENE_RECT)
        self.scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.scene.selectionChanged.connect(self._show_selection)
        self.canvas = GraphCanvas(self.scene, self.colors)
        self.canvas.setAccessibleName("Interactive investigation graph")
        self.canvas.setToolTip(
            "Drag cards to arrange them. Middle-click and drag card-to-card to connect, "
            "Shift-drag, or drag a right-edge dot. Right-drag to pan; wheel to zoom."
        )
        self.canvas.connection_requested.connect(self._connection_requested)
        self.canvas.entity_dropped.connect(self._entity_dropped)
        self.canvas.node_remove_requested.connect(self._remove_entity_from_graph)
        self.canvas.edit_selected_requested.connect(self._edit_selected)
        self.canvas.delete_selected_requested.connect(self._delete_selected_relationship)
        splitter.addWidget(self.canvas)

        right_column = _CompactSplitter(Qt.Orientation.Vertical)
        right_column.setChildrenCollapsible(False)
        right_column.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.palette = QFrame()
        self.palette.setObjectName("surfaceCard")
        self.palette.setMinimumHeight(120)
        palette_layout = QVBoxLayout(self.palette)
        palette_layout.setContentsMargins(14, 12, 14, 10)
        palette_layout.setSpacing(6)
        palette_heading = QHBoxLayout()
        palette_title = QLabel("Entities")
        palette_title.setObjectName("cardTitle")
        self.palette_count = QLabel()
        self.palette_count.setObjectName("subtleText")
        palette_heading.addWidget(palette_title)
        palette_heading.addStretch(1)
        palette_heading.addWidget(self.palette_count)
        self.palette_search = QLineEdit()
        self.palette_search.setPlaceholderText("Find an entity…")
        self.palette_search.setClearButtonEnabled(True)
        self.palette_search.setToolTip("Filter the entity palette. Drag a card onto the canvas.")
        self.palette_search.textChanged.connect(self._filter_palette)
        self.palette_list = EntityPaletteList()
        self.palette_list.setObjectName("graphPalette")
        self.palette_list.setAccessibleName("Entity palette for the graph")
        self.palette_list.setToolTip("Drag an entity onto the graph, or double-click to place it.")
        self.palette_list.setMouseTracking(True)
        self.palette_list.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.palette_list.setItemDelegate(
            EntityItemDelegate(self.palette_list, row_height=50, icon_size=32)
        )
        self.palette_list.itemDoubleClicked.connect(self._add_palette_item)
        self.graph_count = QLabel()
        self.graph_count.setObjectName("subtleText")
        self.graph_count.setWordWrap(True)
        palette_layout.addLayout(palette_heading)
        palette_layout.addWidget(self.palette_search)
        palette_layout.addWidget(self.palette_list, 1)
        palette_layout.addWidget(self.graph_count)

        self.details = QFrame()
        self.details.setObjectName("surfaceCard")
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(18, 16, 18, 16)
        detail_layout.setSpacing(6)
        self.detail_kind = QLabel("Selection")
        self.detail_kind.setObjectName("pageEyebrow")
        self.detail_title = QLabel("Nothing selected")
        self.detail_title.setObjectName("cardTitle")
        self.detail_copy = QLabel("Select a node or a relationship line to see its details.")
        self.detail_copy.setObjectName("cardDescription")
        self.detail_copy.setWordWrap(True)
        self.detail_copy.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.remove_node_button = QPushButton("Remove")
        self.remove_node_button.setObjectName("dangerButton")
        self.remove_node_button.setToolTip(
            "Remove this card from the current graph view. The entity stays in your workspace."
        )
        self.remove_node_button.hide()
        self.remove_node_button.clicked.connect(self._remove_selected_node)
        self.delete_claim_button = QPushButton("Delete claim")
        self.delete_claim_button.setObjectName("dangerButton")
        self.delete_claim_button.setToolTip(
            "Delete this relationship claim from the workspace. The entities and sources stay."
        )
        self.delete_claim_button.hide()
        self.delete_claim_button.clicked.connect(self._delete_selected_relationship)
        detail_heading = QHBoxLayout()
        detail_heading.setContentsMargins(0, 0, 0, 0)
        detail_heading.addWidget(self.detail_kind)
        detail_heading.addStretch(1)
        detail_heading.addWidget(self.remove_node_button)
        detail_heading.addWidget(self.delete_claim_button)
        detail_layout.addLayout(detail_heading)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_copy, 1)

        right_column.addWidget(self.palette)
        right_column.addWidget(self.details)
        right_column.setSizes([280, 104])
        right_column.setStretchFactor(0, 1)
        right_column.setStretchFactor(1, 0)
        self.right_column = right_column
        self.details.setMinimumHeight(104)
        right_column.setMinimumWidth(250)
        right_column.setMaximumWidth(330)
        splitter.addWidget(right_column)
        splitter.setSizes([900, 300])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        layout.addWidget(splitter, 1)

        self._refresh_boards()
        self.refresh_graph(fit=True)

    # ------------------------------------------------------------------ boards
    def _refresh_boards(self) -> None:
        boards = self.services.graph_layout.boards()
        if not boards:
            self.services.graph_layout.ensure_workspace()
            boards = self.services.graph_layout.boards()
        current = self._current_board_id
        self.board_selector.blockSignals(True)
        self.board_selector.clear()
        for board in boards:
            self.board_selector.addItem(board.name, board.id)
            index = self.board_selector.count() - 1
            self.board_selector.setItemData(
                index,
                "A saved graph workspace with its own entity cards and layout.",
                Qt.ItemDataRole.ToolTipRole,
            )
        index = self.board_selector.findData(current)
        if index < 0:
            index = 0
        self.board_selector.setCurrentIndex(index)
        self._current_board_id = self.board_selector.currentData()
        self.board_selector.blockSignals(False)
        self.delete_board_button.setEnabled(True)
        self.delete_board_button.setToolTip(
            "Delete this graph workspace. Entities and claims stay in the workspace."
        )

    def _current_board(self) -> GraphBoard:
        try:
            return self.services.graph_layout.get_board(self._current_board_id)
        except LookupError:
            board = self.services.graph_layout.ensure_workspace()
            self._current_board_id = board.id
            return board

    def _board_changed(self, _index: int) -> None:
        board_id = self.board_selector.currentData()
        if not board_id:
            return
        self._current_board_id = board_id
        self.refresh_graph(fit=True)

    def _new_board(self) -> None:
        dialog = GraphBoardDialog("New graph", submit_label="Create graph", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.saved_name:
            return
        try:
            board = self.services.graph_layout.create_board(dialog.saved_name)
        except (ValueError, OSError, DatabaseError) as exc:
            QMessageBox.warning(self, "Graph could not be created", str(exc))
            return
        self._current_board_id = board.id
        self._refresh_boards()
        self.refresh_graph(fit=True)

    def _rename_board(self) -> None:
        board = self._current_board()
        dialog = GraphBoardDialog("Rename graph", board.name, submit_label="Save name", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.saved_name:
            return
        try:
            self.services.graph_layout.rename_board(board.id, dialog.saved_name)
        except (ValueError, LookupError, OSError, DatabaseError) as exc:
            QMessageBox.warning(self, "Graph could not be renamed", str(exc))
            return
        self._refresh_boards()
        self.refresh_graph()

    def _delete_board(self) -> None:
        board = self._current_board()
        if not self._confirm_delete_board(board):
            return
        try:
            self.services.graph_layout.delete_board(board.id)
        except (ValueError, LookupError, OSError, DatabaseError) as exc:
            QMessageBox.warning(self, "Graph could not be deleted", str(exc))
            return
        self._current_board_id = self.services.graph_layout.ensure_workspace().id
        self._refresh_boards()
        self.refresh_graph(fit=True)
        self.message.emit(f"Graph “{board.name}” deleted")

    def _confirm_delete_board(self, board: GraphBoard) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Delete graph")
        box.setText(f"Delete “{board.name}”?")
        if len(self.services.graph_layout.boards()) == 1:
            box.setInformativeText(
                "Entities and relationship claims stay in the workspace. This is the last "
                "graph, so a new empty graph will be created automatically."
            )
        else:
            box.setInformativeText(
                "Entities and relationship claims stay in the workspace. Only this graph "
                "view and its saved layout are removed."
            )
        delete_button = box.addButton("Delete graph", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is delete_button

    # ------------------------------------------------------------------- render
    def set_theme(self, settings: AppSettings) -> None:
        self.settings = settings
        self.colors = graph_colors(settings)
        self.canvas.set_colors(self.colors)
        self.refresh_graph()

    def refresh_graph(self, *, fit: bool = False) -> None:
        board = self._current_board()
        all_entities = self.services.entities.list()
        hidden_relationship_ids = self.services.graph_layout.hidden_relationship_ids(board.id)
        member_ids = self.services.graph_layout.board_entity_ids(board.id)
        entities = [entity for entity in all_entities if entity.id in member_ids]
        member_ids = {entity.id for entity in entities}
        graph = InvestigationGraph.build(entities, self.services.relationships.list())
        self.canvas._cancel_link()
        self.canvas.stop_view_animations()
        if self._reveal_animation is not None:
            self._reveal_animation.stop()
            self._reveal_animation = None
        self.scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._positions = self.services.graph_layout.positions(board.id)

        types = sorted({node.entity.entity_type for node in graph.nodes})
        selected_type = self.type_filter.currentData()
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem("All types", "")
        for entity_type in types:
            self.type_filter.addItem(entity_type.replace("_", " ").title(), entity_type)
        index = self.type_filter.findData(selected_type)
        self.type_filter.setCurrentIndex(index if index >= 0 else 0)
        self.type_filter.blockSignals(False)

        missing_positions: list[tuple[str, float, float]] = []
        reveal_items: list[QGraphicsItem] = []
        for index, node in enumerate(graph.nodes):
            item = GraphNodeItem(node.entity, self.colors, self.settings.ui_scale)
            position = self._positions.get(node.entity.id)
            if position is None:
                position = self._auto_position(index, len(graph.nodes))
                missing_positions.append((node.entity.id, *position))
            item.setPos(*position)
            item.setOpacity(0.0)
            item.position_committed.connect(self._save_position)
            item.edit_requested.connect(self._edit_entity)
            self.scene.addItem(item)
            self._nodes[node.entity.id] = item
            reveal_items.append(item)

        # Persist one-time automatic placements so adding another card later
        # never makes previously placed cards jump to a new position.
        for entity_id, x, y in missing_positions:
            try:
                self.services.graph_layout.add_entity(board.id, entity_id, x, y)
            except (ValueError, LookupError, OSError, DatabaseError):
                pass

        status_colors = {
            VerificationStatus.VERIFIED: self.colors["verified"],
            VerificationStatus.DISPUTED: self.colors["disputed"],
            VerificationStatus.INFERRED: self.colors["inferred"],
        }
        for edge in graph.edges:
            relation = edge.relationship
            if relation.id in hidden_relationship_ids:
                continue
            source = self._nodes.get(relation.source_entity_id)
            target = self._nodes.get(relation.target_entity_id)
            if source is None or target is None:
                continue
            item = GraphEdgeItem(
                relation,
                source,
                target,
                status_colors.get(relation.verification_status, self.colors["muted"]),
                self.colors["muted"],
                self.settings.ui_scale,
            )
            item.setOpacity(0.0)
            self.scene.addItem(item)
            self._edges[relation.id] = item
            reveal_items.append(item)

        self._refresh_palette(all_entities, member_ids)
        self._apply_filter()
        self._animate_graph_reveal(reveal_items)
        self.canvas.set_remove_hint_text(
            "Release outside the canvas to remove this card. Its claim lines stay saved."
        )
        entity_word = "entity" if len(graph.nodes) == 1 else "entities"
        claim_word = "claim" if len(self._edges) == 1 else "claims"
        self.graph_count.setText(
            f"{board.name} · {len(graph.nodes)} {entity_word} · {len(self._edges)} {claim_word}"
        )
        self.delete_board_button.setEnabled(True)
        if graph.nodes:
            self.canvas.set_empty_hint(None)
            if fit or not self._has_rendered:
                self.fit_graph()
            self._show_selection()
            self._has_rendered = True
        else:
            self._has_rendered = False
            if not all_entities:
                self.canvas.set_empty_hint(
                    "Your workspace is empty.\nAdd an entity to start your graph."
                )
                self.detail_kind.setText("No records")
                self.detail_title.setText("Your workspace is empty")
                self.detail_copy.setText(
                    "Add entities from the Entities page or with the Add entity button."
                )
            else:
                self.canvas.set_empty_hint(
                    "This graph is empty.\nDrag an entity from the right to add it."
                )
                self.detail_kind.setText("Empty graph")
                self.detail_title.setText("Drag an entity here")
                self.detail_copy.setText(
                    "Use the entity palette on the right, or double-click an entity to place it."
                )
            self.detail_copy.setToolTip(self.detail_copy.text())
            self._set_detail_compact(False)
        self.remove_node_button.hide()
        self.delete_claim_button.hide()

    def _animate_graph_reveal(self, items: list[QGraphicsItem]) -> None:
        if not items:
            return
        animation = QVariantAnimation(self)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(220)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def update(progress) -> None:
            value = float(progress)
            for item in items:
                if item.scene() is not None:
                    item.setOpacity(value)

        animation.valueChanged.connect(update)
        animation.finished.connect(self._clear_reveal_animation)
        self._reveal_animation = animation
        animation.start()

    def _clear_reveal_animation(self) -> None:
        self._reveal_animation = None

    @staticmethod
    def _auto_position(index: int, total: int) -> tuple[float, float]:
        """Place new cards in a compact centred grid, not a wide spiral."""

        total = max(1, total)
        columns = 1 if total == 1 else 2 if total <= 4 else 3
        rows = max(1, (total + columns - 1) // columns)
        column = index % columns
        row = index // columns
        x = (column - (columns - 1) / 2) * 320.0
        y = (row - (rows - 1) / 2) * 180.0
        return x, y

    def _refresh_palette(self, entities, member_ids: set[str]) -> None:
        query = self.palette_search.text().strip().casefold()
        self.palette_list.blockSignals(True)
        self.palette_list.clear()
        for entity in entities:
            item = QListWidgetItem(_palette_icon(entity, self.colors), entity.name)
            item.setData(Qt.ItemDataRole.UserRole, entity.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, entity.entity_type)
            platform = str(entity.attributes.get("platform", "")).strip()
            on_graph = entity.id in member_ids
            detail = entity.entity_type.replace("_", " ").title()
            if platform:
                detail += f" · {platform}"
            item.setData(SUBTITLE_ROLE, detail)
            item.setData(ON_GRAPH_ROLE, on_graph)
            item.setToolTip(
                f"{entity.name}\n{detail}\n"
                + (
                    "On this graph — double-click to bring it into view."
                    if on_graph
                    else "Drag onto the canvas to add it to this graph."
                )
            )
            item.setSizeHint(QSize(0, 50))
            self.palette_list.addItem(item)
        self.palette_count.setText(f"{len(entities)} total")
        self.palette_list.blockSignals(False)
        self._filter_palette(query)

    def _filter_palette(self, _text=None) -> None:
        query = self.palette_search.text().strip().casefold()
        for row in range(self.palette_list.count()):
            item = self.palette_list.item(row)
            haystack = " ".join(
                [
                    item.text(),
                    str(item.data(Qt.ItemDataRole.UserRole + 1)),
                    item.toolTip(),
                ]
            ).casefold()
            item.setHidden(bool(query) and query not in haystack)

    def _add_palette_item(self, item: QListWidgetItem | None = None) -> None:
        item = item or self.palette_list.currentItem()
        if item is None:
            return
        entity_id = item.data(Qt.ItemDataRole.UserRole)
        if entity_id:
            self._add_entity_to_graph(str(entity_id))

    def _add_entity_to_graph(
        self,
        entity_id: str,
        position: QPointF | None = None,
        *,
        announce: bool = True,
    ) -> None:
        board = self._current_board()
        existing = self._nodes.get(entity_id)
        if existing is not None:
            self._clear_filters()
            self.scene.clearSelection()
            existing.setSelected(True)
            self.canvas.animate_center_on(
                existing.sceneBoundingRect().center(),
                duration=200,
            )
            return
        try:
            entity = self.services.entities.get(entity_id)
        except LookupError:
            QMessageBox.warning(
                self,
                "Entity not found",
                "That entity is no longer in this workspace.",
            )
            return
        saved_connections = self.services.graph_layout.removed_connection_ids(board.id, entity_id)
        restore_mode: str | None = None
        if saved_connections:
            restore_mode = self._ask_restore_choice(entity.name, len(saved_connections))
            if restore_mode is None:
                return
        if position is None:
            center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
            position = self._free_position(center - QPointF(NODE_WIDTH / 2, NODE_HEIGHT / 2))
        try:
            self.services.graph_layout.add_entity(board.id, entity_id, position.x(), position.y())
            if restore_mode == RestoreCardDialog.WITH_CONNECTIONS:
                self.services.graph_layout.restore_entity_connections(board.id, entity_id)
        except (ValueError, LookupError, OSError, DatabaseError) as exc:
            QMessageBox.warning(self, "Entity could not be added", str(exc))
            return
        self.refresh_graph()
        self._clear_filters()
        node = self._nodes.get(entity_id)
        if node is not None:
            self.scene.clearSelection()
            node.setSelected(True)
            self.canvas.animate_center_on(
                node.sceneBoundingRect().center(),
                duration=200,
            )
        if announce and restore_mode == RestoreCardDialog.WITH_CONNECTIONS:
            self.message.emit(f"“{entity.name}” restored with its old connections")
        elif announce and restore_mode == RestoreCardDialog.CARD_ONLY:
            self.message.emit(f"“{entity.name}” restored on its own")

    def _ask_restore_choice(self, entity_name: str, connection_count: int) -> str | None:
        dialog = RestoreCardDialog(entity_name, connection_count, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.choice

    def _entity_dropped(self, entity_id: str, x: float, y: float) -> None:
        self._add_entity_to_graph(entity_id, QPointF(x - NODE_WIDTH / 2, y - NODE_HEIGHT / 2))

    def _free_position(self, position: QPointF) -> QPointF:
        """Nudge a non-dropped card until it does not cover an existing card."""

        candidate = QPointF(position)
        for _ in range(24):
            rect = QRectF(candidate.x(), candidate.y(), NODE_WIDTH, NODE_HEIGHT)
            if not any(
                QRectF(node.pos().x(), node.pos().y(), node.width, node.height).intersects(rect)
                for node in self._nodes.values()
            ):
                return candidate
            candidate += QPointF(28, 28)
        return candidate

    def select_record(self, record_id: str) -> None:
        if record_id not in self._nodes and record_id not in self._edges:
            board = self._current_board()
            relationship = None
            try:
                relationship = self.services.relationships.get(record_id)
            except LookupError:
                pass

            if relationship is not None:
                # A claim can be absent from the current graph workspace. Add
                # both endpoint cards and reveal the claim in this workspace.
                for entity_id in (
                    relationship.source_entity_id,
                    relationship.target_entity_id,
                ):
                    try:
                        self.services.graph_layout.add_entity(board.id, entity_id)
                    except (ValueError, LookupError, OSError, DatabaseError):
                        pass
                try:
                    self.services.graph_layout.restore_relationship(board.id, relationship.id)
                except (ValueError, LookupError, OSError, DatabaseError):
                    pass
                self.refresh_graph(fit=True)
            elif record_id not in self._nodes:
                # The record may have been dragged out of this graph. Opening
                # it from search or another page is also a restore, so honor
                # the same connection choice.
                try:
                    self.services.entities.get(record_id)
                except LookupError:
                    pass
                else:
                    self._add_entity_to_graph(record_id, announce=False)
        self._clear_filters()
        item = self._nodes.get(record_id) or self._edges.get(record_id)
        if item is not None:
            self.scene.clearSelection()
            item.setSelected(True)
            self.canvas.animate_center_on(
                item.sceneBoundingRect().center(),
                duration=200,
            )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._fit_pending:
            self._fit_pending = False
            QTimer.singleShot(0, self.fit_graph)

    def fit_graph(self) -> None:
        if not self.isVisible() or self.canvas.viewport().width() < 120:
            self._fit_pending = True
            return
        self._fit_pending = False
        bounds = QRectF()
        for item in self.scene.items():
            if not item.isVisible():
                continue
            if isinstance(item, QGraphicsPathItem) and not isinstance(item, GraphEdgeItem):
                continue
            rect = item.sceneBoundingRect()
            bounds = rect if bounds.isNull() else bounds.united(rect)
        if bounds.isNull() or bounds.isEmpty():
            return
        bounds = bounds.adjusted(-90, -70, 90, 70)
        self.canvas.animate_fit(
            bounds,
            duration=240,
        )

    def _clear_filters(self) -> None:
        """Reveal a record that may be hidden by the current graph filters."""

        if self.filter_field.text():
            self.filter_field.clear()
        if self.type_filter.currentIndex() != 0:
            self.type_filter.setCurrentIndex(0)
        self._apply_filter()

    def _apply_filter(self, *_args) -> None:
        query = self.filter_field.text().strip().casefold()
        entity_type = self.type_filter.currentData()
        visible_ids: set[str] = set()
        for entity_id, item in self._nodes.items():
            entity = item.entity
            platform = str(entity.attributes.get("platform", "")).casefold()
            visible = (
                not query
                or query in entity.name.casefold()
                or query in entity.entity_type
                or query in platform
            ) and (not entity_type or entity.entity_type == entity_type)
            item.setVisible(visible)
            if visible:
                visible_ids.add(entity_id)
        for item in self._edges.values():
            item.setVisible(
                item.relationship.source_entity_id in visible_ids
                and item.relationship.target_entity_id in visible_ids
            )
        if any(not item.isVisible() for item in self.scene.selectedItems()):
            self.scene.clearSelection()

    def _save_position(self, entity_id: str, x: float, y: float) -> None:
        self._positions[entity_id] = (x, y)
        board = self._current_board()
        try:
            self.services.graph_layout.save(entity_id, x, y, board.id)
        except (OSError, ValueError, LookupError, DatabaseError) as exc:
            QMessageBox.warning(self, "Graph position not saved", str(exc))

    def _add_entity(self) -> None:
        dialog = EntityRecordDialog(
            self.services.entities,
            parent=self,
            image_service=self.services.profile_images,
            platform_service=self.services.platforms,
            source_service=self.services.sources,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.saved_entity is None:
            return
        self._add_entity_to_graph(dialog.saved_entity.id, announce=False)
        self._notify_change()

    def _add_relationship(self) -> None:
        if len(self._nodes) < 2:
            QMessageBox.information(
                self,
                "Two entities needed",
                "Add at least two entity cards to this graph before creating a relationship.",
            )
            return
        dialog = RelationshipRecordDialog(
            self.services,
            parent=self,
            allowed_entity_ids=set(self._nodes),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_relationship:
            self.refresh_graph()
            self._clear_filters()
            edge = self._edges.get(dialog.saved_relationship.id)
            if edge is not None:
                self.scene.clearSelection()
                edge.setSelected(True)
                self.canvas.animate_center_on(
                    edge.sceneBoundingRect().center(),
                    duration=200,
                )
            self._notify_change()

    def _connection_requested(self, source_id: str, target_id: str) -> None:
        if source_id == target_id:
            return
        dialog = RelationshipRecordDialog(
            self.services,
            parent=self,
            allowed_entity_ids=set(self._nodes),
            source_id=source_id,
            target_id=target_id,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_relationship:
            self.refresh_graph()
            self._clear_filters()
            edge = self._edges.get(dialog.saved_relationship.id)
            if edge is not None:
                self.scene.clearSelection()
                edge.setSelected(True)
                self.canvas.animate_center_on(
                    edge.sceneBoundingRect().center(),
                    duration=200,
                )
            self._notify_change()

    def _edit_entity(self, entity_id: str) -> None:
        try:
            entity = self.services.entities.get(entity_id)
        except LookupError:
            self.refresh_graph()
            return
        dialog = EntityRecordDialog(
            self.services.entities,
            entity,
            self,
            image_service=self.services.profile_images,
            platform_service=self.services.platforms,
            source_service=self.services.sources,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_entity:
            self.refresh_graph()
            node = self._nodes.get(dialog.saved_entity.id)
            if node is not None:
                self.scene.clearSelection()
                node.setSelected(True)
                self.canvas.animate_center_on(
                    node.sceneBoundingRect().center(),
                    duration=200,
                )
            self._notify_change()

    def _edit_selected(self) -> None:
        selected = self.scene.selectedItems()
        if not selected:
            return
        item = selected[0]
        if isinstance(item, GraphNodeItem):
            self._edit_entity(item.entity.id)
        elif isinstance(item, GraphEdgeItem):
            claim = item.relationship.relationship_type
            dialog = RelationshipRecordDialog(
                self.services,
                item.relationship,
                self,
                allowed_entity_ids=set(self._nodes),
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if dialog.deleted:
                self.refresh_graph()
                self._notify_change(
                    f"Claim “{claim}” deleted. Its entities and sources are still in the workspace."
                )
            elif dialog.saved_relationship:
                self.refresh_graph()
                edge = self._edges.get(dialog.saved_relationship.id)
                if edge is not None:
                    self.scene.clearSelection()
                    edge.setSelected(True)
                self._notify_change()

    def _remove_entity_from_graph(self, entity_id: str) -> None:
        board = self._current_board()
        node = self._nodes.get(entity_id)
        if node is None:
            return
        name = node.entity.name
        connection_ids = {
            relationship_id
            for relationship_id, edge in self._edges.items()
            if entity_id in (edge.relationship.source_entity_id, edge.relationship.target_entity_id)
        }
        try:
            self.services.graph_layout.remove_entity(board.id, entity_id, connection_ids)
        except (ValueError, LookupError, OSError, DatabaseError) as exc:
            QMessageBox.warning(self, "Entity could not be removed", str(exc))
            return
        self.refresh_graph()
        saved_connections = self.services.graph_layout.removed_connection_ids(board.id, entity_id)
        if saved_connections:
            self.message.emit(
                f"“{name}” removed. Its old connections are saved; bring it back to choose."
            )
        else:
            self.message.emit(
                f"“{name}” removed from this graph. Drag it back from the palette to restore it."
            )

    def _remove_selected_node(self) -> None:
        selected = self.scene.selectedItems()
        node = next((item for item in selected if isinstance(item, GraphNodeItem)), None)
        if node is None:
            return
        self._remove_entity_from_graph(node.entity.id)

    def _confirm_delete_relationship(self, relationship: Relationship) -> bool:
        source_node = self._nodes.get(relationship.source_entity_id)
        target_node = self._nodes.get(relationship.target_entity_id)
        source = source_node.entity.name if source_node else "Unknown"
        target = target_node.entity.name if target_node else "Unknown"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Delete relationship claim?")
        box.setText(f"Delete “{relationship.relationship_type}” between {source} and {target}?")
        box.setInformativeText(
            "The claim and its evidence links are removed from the workspace. "
            "The entities and sources themselves stay."
        )
        delete_button = box.addButton("Delete claim", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is delete_button

    def _delete_selected_relationship(self) -> None:
        selected = self.scene.selectedItems()
        edge = next((item for item in selected if isinstance(item, GraphEdgeItem)), None)
        if edge is None:
            return
        relationship = edge.relationship
        if not self._confirm_delete_relationship(relationship):
            return
        try:
            deleted = self.services.relationships.delete(relationship.id)
        except DatabaseError as exc:
            QMessageBox.warning(self, "Relationship could not be deleted", str(exc))
            return
        if not deleted:
            QMessageBox.warning(
                self,
                "Relationship not found",
                "This claim was already removed from the workspace.",
            )
            return
        self.refresh_graph()
        self._notify_change(
            f"Claim “{relationship.relationship_type}” deleted. "
            "Its entities and sources are still in the workspace."
        )

    def _notify_change(self, message: str | None = None) -> None:
        self.records_changed.emit()
        if message:
            self.message.emit(message)

    def _style_detail_title(self, large: bool) -> None:
        object_name = "graphDetailTitle" if large else "cardTitle"
        if self.detail_title.objectName() == object_name:
            return
        self.detail_title.setObjectName(object_name)
        self.detail_title.style().unpolish(self.detail_title)
        self.detail_title.style().polish(self.detail_title)

    def _set_detail_compact(self, compact: bool) -> None:
        """Hide the selection card when nothing is selected, freeing palette space."""

        self.detail_title.setVisible(True)
        self.detail_copy.setVisible(not compact)
        total = max(
            self.right_column.height(),
            self.palette.height() + self.details.height() + self.right_column.handleWidth(),
        )
        if compact and self._nodes:
            self.details.hide()
            if total > 120:
                self.right_column.setSizes([total, 0])
            return
        self.details.show()
        self.details.setMinimumHeight(150)
        if total <= 150:
            return
        # Give long claims and descriptions enough room instead of clipping
        # the lower metadata under the fixed splitter size.
        content_width = max(200, self.details.width() - 40)
        text_height = self.detail_copy.heightForWidth(content_width)
        desired_height = max(170, text_height + 108)
        detail_height = min(desired_height, max(150, total - 150), 240)
        self.right_column.setSizes([max(120, total - detail_height), detail_height])

    def _show_selection(self) -> None:
        selected = self.scene.selectedItems()
        item = selected[0] if selected else None
        self.edit_button.setEnabled(item is not None)
        self.remove_node_button.setVisible(isinstance(item, GraphNodeItem))
        self.delete_claim_button.setVisible(isinstance(item, GraphEdgeItem))
        if isinstance(item, GraphNodeItem):
            entity = item.entity
            self._style_detail_title(True)
            label = entity.entity_type.replace("_", " ").title()
            platform = str(entity.attributes.get("platform", "")).strip()
            role = str(entity.attributes.get("role", "")).strip()
            if entity.entity_type == "social_profile" and platform:
                label = f"{label} · {platform}"
            elif entity.entity_type == "person" and role:
                label = f"{label} · {role}"
            self.detail_kind.setText(label)
            self.detail_title.setText(entity.name)
            copy = entity.description or "No description recorded."
            if str(entity.attributes.get("profile_image_path", "")).strip():
                copy = f"Profile photo attached.\n{copy}"
            self.detail_copy.setText(copy)
            self.detail_copy.setToolTip(copy)
        elif isinstance(item, GraphEdgeItem):
            relation = item.relationship
            self._style_detail_title(True)
            source_node = self._nodes.get(relation.source_entity_id)
            target_node = self._nodes.get(relation.target_entity_id)
            source = source_node.entity.name if source_node else "Unknown"
            target = target_node.entity.name if target_node else "Unknown"
            self.detail_kind.setText("Relationship claim")
            self.detail_title.setText(relation.relationship_type)
            status = relation.verification_status.value.replace("_", " ")
            lines = [f"{source} → {target}", f"Status: {status}"]
            if relation.start_date or relation.end_date:
                start = relation.start_date or "not set"
                end = relation.end_date or "present"
                lines.append(f"Dates: {start} → {end}")
            if relation.description:
                lines.append(relation.description)
            copy = "\n".join(lines)
            tooltip = [copy]
            if relation.confidence_notes:
                tooltip.append(f"Confidence notes: {relation.confidence_notes}")
            if relation.notes:
                tooltip.append(f"Notes: {relation.notes}")
            self.detail_copy.setText(copy)
            self.detail_copy.setToolTip("\n\n".join(tooltip))
        elif item is None:
            self._style_detail_title(False)
            self.detail_kind.setText("Selection")
            self.detail_title.setText("Nothing selected")
            self.detail_copy.setText("Select a node or a relationship line to see its details.")
            self.detail_copy.setToolTip("")
        self._set_detail_compact(item is None)
