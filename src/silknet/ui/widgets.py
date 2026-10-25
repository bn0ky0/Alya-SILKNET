"""Small shared controls used across the workspace pages."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QModelIndex,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QListView,
    QSlider,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
)

from silknet.ui.theme import active_theme_colors, combo_popup_stylesheet

#: Extra roles used by :class:`EntityItemDelegate`.
SUBTITLE_ROLE = int(Qt.ItemDataRole.UserRole) + 10
ON_GRAPH_ROLE = int(Qt.ItemDataRole.UserRole) + 11
ACCENT_ROLE = int(Qt.ItemDataRole.UserRole) + 12


class ComboItemDelegate(QStyledItemDelegate):
    """Rounded, theme-aware rows for the windowed combo popup."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._colors = active_theme_colors()

    def set_colors(self, colors: dict[str, str]) -> None:
        self._colors = dict(colors)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        font = option.font
        metrics = QFontMetrics(font)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        return QSize(metrics.horizontalAdvance(text) + 44, max(32, metrics.height() + 16))

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        colors = self._colors
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        row = QRectF(option.rect).adjusted(3, 2, -3, -2)
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors["selection"]))
            painter.drawRoundedRect(row, 8, 8)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors["surface"]))
            painter.drawRoundedRect(row, 8, 8)

        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        painter.setPen(QColor(colors["text"] if enabled else colors["subtle"]))
        font = QFont(option.font)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text_rect = option.rect.adjusted(14, 0, -12, 0)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(20, text_rect.width()))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.restore()


class ComboPopup(QFrame):
    """A themed, frameless popup owned by :class:`ComboBox`.

    Qt's built-in combo popup is a separate native window on Windows. Even when
    its list view is styled, the surrounding container can keep the default
    white palette and square frame. Owning the popup lets us paint the entire
    rounded surface ourselves, including the scrollbar and row hover states.
    """

    def __init__(self, combo: ComboBox) -> None:
        super().__init__(
            combo,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self._combo = combo
        self._colors = active_theme_colors()
        self._shadow = 1
        self._visible_rows = 1
        self._target_geometry = (0, 0, 0, 0)
        self.setObjectName("comboPopupPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(1.0)
        self._appear = QPropertyAnimation(self, b"windowOpacity", self)
        self._appear.setDuration(120)
        self._appear.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(self._shadow, self._shadow, self._shadow, self._shadow)
        self._layout.setSpacing(0)

        self.view = QListView(self)
        self.view.setObjectName("comboPopup")
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.view.viewport().setAutoFillBackground(False)
        self.view.viewport().setStyleSheet("background: transparent;")
        self.view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.view.setUniformItemSizes(True)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setMouseTracking(True)
        self.view.setSpacing(0)
        self.view.installEventFilter(self)
        self.view.clicked.connect(self._choose)
        self._layout.addWidget(self.view)

        self._delegate = ComboItemDelegate(self)
        self.view.setItemDelegate(self._delegate)
        self.apply_theme()

    def apply_theme(self) -> None:
        colors = active_theme_colors()
        self._colors = colors
        sheet = combo_popup_stylesheet(colors)
        self.setStyleSheet(sheet)
        self.view.setStyleSheet(sheet)
        self._delegate.set_colors(colors)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # Qt's translucent popup windows do not reliably paint a QSS background
        # on their own, especially on Windows. Paint the rounded surface here so
        # no native white frame can show through.
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pad = self._shadow
        panel = QRectF(self.rect()).adjusted(pad, pad, -pad, -pad)
        path = QPainterPath()
        path.addRoundedRect(panel, 13, 13)

        surface = QColor(self._colors["surface_alt"])
        fill = QLinearGradient(0, panel.top(), 0, panel.bottom())
        fill.setColorAt(0.0, surface.lighter(108))
        fill.setColorAt(1.0, surface)
        border = QColor(self._colors["border"])
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(border, 1.0))
        painter.drawPath(path)

        highlight = QColor(255, 255, 255)
        highlight.setAlpha(52 if QColor(self._colors["surface_alt"]).lightness() < 128 else 140)
        painter.setPen(QPen(highlight, 1))
        painter.drawLine(
            round(panel.left() + 14),
            round(panel.top() + 1),
            round(panel.right() - 14),
            round(panel.top() + 1),
        )

    def show_for_combo(self) -> None:
        """Open beneath the combo, flipping above or sideways at screen edges."""
        combo = self._combo
        if combo.count() == 0:
            return
        self.apply_theme()
        self.view.setFont(combo.font())
        self.view.setModel(combo.model())
        current_index = combo.model().index(combo.currentIndex(), 0)
        self.view.setCurrentIndex(current_index)

        screen = combo.screen()
        available = screen.availableGeometry()
        hint = self.view.sizeHintForColumn(0)
        panel_width = max(combo.width(), min(520, hint + 24))
        max_panel_width = max(80, available.width() - 12 - self._shadow * 2)
        panel_width = min(panel_width, max_panel_width)

        row_height = self.view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = max(32, self.fontMetrics().height() + 16)
        max_panel_height = max(row_height + 10, available.height() - 12 - self._shadow * 2)
        rows_by_space = max(1, (max_panel_height - 10) // row_height)
        self._visible_rows = max(
            1,
            min(combo.maxVisibleItems(), combo.count(), rows_by_space),
        )
        needs_scrollbar = combo.count() > self._visible_rows
        if needs_scrollbar:
            panel_width = min(
                panel_width + self.view.verticalScrollBar().sizeHint().width(),
                max_panel_width,
            )
        self.view.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if needs_scrollbar
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # The list's QSS padding is 5px top and bottom. Fixing the view to the
        # exact row height prevents a tall, mostly-empty surface and means the
        # scrollbar can never retain a stale offset from a previous opening.
        view_height = min(self._visible_rows * row_height + 10, max_panel_height)
        window_width = panel_width + self._shadow * 2
        window_height = view_height + self._shadow * 2
        self.view.setFixedSize(panel_width, view_height)
        self.view.verticalScrollBar().setValue(0)

        panel_left = combo.mapToGlobal(QPoint(0, 0)).x()
        panel_top = combo.mapToGlobal(QPoint(0, combo.height() + 6)).y()
        if panel_top + view_height > available.bottom() - 6:
            panel_top = combo.mapToGlobal(QPoint(0, -view_height - 6)).y()
        position = QPoint(panel_left - self._shadow, panel_top - self._shadow)
        position.setX(
            max(
                available.left() + 6,
                min(position.x(), available.right() - 6 - window_width),
            )
        )
        position.setY(
            max(
                available.top() + 6,
                min(position.y(), available.bottom() - 6 - window_height),
            )
        )

        self._target_geometry = (position.x(), position.y(), window_width, window_height)
        self.layout().activate()
        self.setGeometry(*self._target_geometry)
        self._appear.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self._appear.setStartValue(0.0)
        self._appear.setEndValue(1.0)
        self._appear.start()
        self.view.setFocus(Qt.FocusReason.PopupFocusReason)
        QTimer.singleShot(0, self._settle_view)

    def _settle_view(self) -> None:
        """Finish layout work only after the popup window has been shown."""
        if not self.isVisible():
            return
        # Windows can defer a top-level popup resize requested while it is
        # hidden and reinstate the previous larger geometry on show. Re-apply
        # the exact target once the window exists so shrinking the popup after
        # a long board list cannot leave a tall blank surface.
        current = self.geometry()
        current_geometry = (current.x(), current.y(), current.width(), current.height())
        if current_geometry != self._target_geometry:
            self.setGeometry(*self._target_geometry)
        self.layout().activate()
        self.view.doItemsLayout()
        scrollbar = self.view.verticalScrollBar()
        if self.view.model() is None:
            return
        if self.view.model().rowCount() <= self._visible_rows:
            scrollbar.setValue(scrollbar.minimum())
            self.view.scrollToTop()
        elif self.view.currentIndex().isValid():
            self.view.scrollTo(
                self.view.currentIndex(),
                QAbstractItemView.ScrollHint.EnsureVisible,
            )

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._appear.stop()
        self.setWindowOpacity(1.0)
        super().hideEvent(event)

    def _choose(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self.hide()
        self._combo.setCurrentIndex(index.row())
        self._combo.setFocus(Qt.FocusReason.OtherFocusReason)

    def _move_highlight(self, key: int) -> None:
        model = self.view.model()
        if model is None or model.rowCount() == 0:
            return
        row = self.view.currentIndex().row()
        if row < 0:
            row = 0
        page = max(1, self._visible_rows - 1)
        if key == Qt.Key.Key_Up:
            row -= 1
        elif key == Qt.Key.Key_Down:
            row += 1
        elif key == Qt.Key.Key_Home:
            row = 0
        elif key == Qt.Key.Key_End:
            row = model.rowCount() - 1
        elif key == Qt.Key.Key_PageUp:
            row -= page
        elif key == Qt.Key.Key_PageDown:
            row += page
        row = max(0, min(model.rowCount() - 1, row))
        index = model.index(row, 0)
        self.view.setCurrentIndex(index)
        self.view.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.view and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in {
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
                Qt.Key.Key_Home,
                Qt.Key.Key_End,
                Qt.Key.Key_PageUp,
                Qt.Key.Key_PageDown,
            }:
                self._move_highlight(key)
                return True
            if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
                self._choose(self.view.currentIndex())
                return True
            if key == Qt.Key.Key_Escape:
                self.hide()
                self._combo.setFocus(Qt.FocusReason.OtherFocusReason)
                return True
        return super().eventFilter(watched, event)


class ComboBox(QComboBox):
    """A combo box with a fully themed popup, sensible width and wheel safety.

    The popup is a custom translucent window, so it never inherits the native
    white combo frame on Windows. It sizes itself to the longest option, flips
    near screen edges and supports the usual arrow/Enter/Escape keys.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMaxVisibleItems(14)
        self._popup: ComboPopup | None = None
        # Keep a themed standard view attached as a safety net. Some native
        # popup paths (and keyboard activation on some platforms) can bypass
        # the custom popup override; this view still gives them readable rows
        # instead of the stock white list.
        fallback = QListView(self)
        fallback.setObjectName("comboPopupFallback")
        fallback.setFrameShape(QFrame.Shape.NoFrame)
        fallback.setUniformItemSizes(True)
        fallback.setMouseTracking(True)
        fallback.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        fallback.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        fallback.setItemDelegate(ComboItemDelegate(fallback))
        self.setView(fallback)

    @property
    def popup(self) -> ComboPopup | None:
        """The reusable popup, or ``None`` until the first open."""
        return self._popup

    def showPopup(self) -> None:  # noqa: N802 - Qt API name
        if self.isEditable():
            super().showPopup()
            self._theme_standard_popup()
            return
        if self._popup is None:
            self._popup = ComboPopup(self)
        self._popup.show_for_combo()

    def _theme_standard_popup(self) -> None:
        """Theme Qt's native popup container if the editable path uses it."""
        colors = active_theme_colors()
        view = self.view()
        view.setStyleSheet(
            f"""
            QListView#comboPopupFallback {{
                background: {colors["surface_alt"]};
                color: {colors["text"]};
                border: none;
                padding: 6px;
                outline: none;
                selection-background-color: {colors["selection"]};
                selection-color: {colors["text"]};
            }}
            """
        )
        container = view.window()
        if container is not view:
            container.setStyleSheet(
                f"""
                QFrame {{
                    background: {colors["surface_alt"]};
                    border: 1px solid {colors["border"]};
                    border-radius: 10px;
                }}
                QListView {{
                    background: transparent;
                    border: none;
                }}
                """
            )

    def hidePopup(self) -> None:  # noqa: N802 - Qt API name
        if self._popup is not None:
            self._popup.hide()
        if self.isEditable():
            super().hidePopup()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        popup = getattr(self, "_popup", None)
        if popup is not None:
            popup.hide()
        super().hideEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # Clicking the control while its popup is open should toggle it shut,
        # not let the popup close and immediately reopen underneath the cursor.
        if self._popup is not None and self._popup.isVisible():
            self.hidePopup()
            event.accept()
            return
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:
        # Scrolling a page must not silently rewrite a closed combo. The open
        # popup owns its own wheel events, so ignore this one either way.
        event.ignore()


class SmoothSlider(QSlider):
    """Six-step slider whose handle glides continuously between values.

    Qt only exposes integer slider positions. With six scale steps, animating
    the value would jump the handle in large blocks. This control paints the
    handle from a floating fraction while still updating the real QSlider value
    at every step, so labels and saved settings stay in sync.
    """

    _HANDLE_RADIUS = 10.0
    _HANDLE_OUTLINE = 3.0
    _FOCUS_HALO = 4.0
    _EDGE_MARGIN = _HANDLE_RADIUS + _FOCUS_HALO
    _TRACK_HEIGHT = 7.0

    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(32)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        palette = self.palette()
        self._accent = palette.highlight().color()
        self._groove = palette.mid().color()
        self._surface = palette.base().color()
        self._text = palette.text().color()
        self._display_fraction = self._fraction_for_value(self.value())
        self._dragging = False
        self._drag_offset = 0.0
        self._animating = False
        self._syncing = False
        self._hover = False
        self._glide = QVariantAnimation(self)
        self._glide.setDuration(260)
        self._glide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._glide.valueChanged.connect(self._on_glide_value)
        self._glide.finished.connect(self._on_glide_finished)
        self.valueChanged.connect(self._on_value_changed)
        self.rangeChanged.connect(self._on_range_changed)

    def set_track_colors(
        self,
        *,
        accent: str,
        groove: str,
        surface: str,
        text: str,
    ) -> None:
        """Keep the custom track in step with the active application theme."""

        self._accent = QColor(accent)
        self._groove = QColor(groove)
        self._surface = QColor(surface)
        self._text = QColor(text)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(280, 32)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(120, 32)

    # --------------------------------------------------------------- geometry
    def _track_span(self) -> tuple[float, float]:
        left = self._EDGE_MARGIN
        right = max(left, self.width() - self._EDGE_MARGIN)
        return left, right

    def _fraction_for_value(self, value: int) -> float:
        span = self.maximum() - self.minimum()
        if span <= 0:
            return 0.0
        return (value - self.minimum()) / span

    def _value_for_fraction(self, fraction: float) -> int:
        span = self.maximum() - self.minimum()
        if span <= 0:
            return self.minimum()
        return round(self.minimum() + fraction * span)

    def _fraction_at_x(self, x: float) -> float:
        left, right = self._track_span()
        if right <= left:
            return 0.0
        return max(0.0, min(1.0, (x - left) / (right - left)))

    def _handle_center_x(self) -> float:
        left, right = self._track_span()
        return left + self._display_fraction * (right - left)

    # ---------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self.orientation() != Qt.Orientation.Horizontal:
            super().paintEvent(event)
            return
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center_y = self.height() / 2
        track_top = center_y - self._TRACK_HEIGHT / 2
        handle_x = self._handle_center_x()
        enabled = self.isEnabled()

        groove = QColor(self._groove if enabled else self._text)
        if not enabled:
            groove.setAlpha(50)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(groove)
        painter.drawRoundedRect(
            QRectF(0, track_top, self.width(), self._TRACK_HEIGHT),
            self._TRACK_HEIGHT / 2,
            self._TRACK_HEIGHT / 2,
        )

        fill = QColor(self._accent if enabled else self._text)
        if not enabled:
            fill.setAlpha(90)
        painter.setBrush(fill)
        painter.drawRoundedRect(
            QRectF(0, track_top, max(0.0, handle_x), self._TRACK_HEIGHT),
            self._TRACK_HEIGHT / 2,
            self._TRACK_HEIGHT / 2,
        )

        hovered = self._hover or self._dragging
        if not enabled:
            handle_fill = QColor(self._text)
            handle_fill.setAlpha(75)
        elif hovered:
            handle_fill = QColor(self._accent).lighter(108)
        else:
            handle_fill = QColor(self._accent)
        if self.hasFocus():
            halo = QColor(self._accent)
            halo.setAlpha(46)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(
                QPointF(handle_x, center_y),
                self._HANDLE_RADIUS + self._FOCUS_HALO,
                self._HANDLE_RADIUS + self._FOCUS_HALO,
            )
        handle_rect = QRectF(
            handle_x - self._HANDLE_RADIUS,
            center_y - self._HANDLE_RADIUS,
            self._HANDLE_RADIUS * 2,
            self._HANDLE_RADIUS * 2,
        )
        painter.setPen(QPen(self._surface, self._HANDLE_OUTLINE))
        painter.setBrush(handle_fill)
        painter.drawEllipse(handle_rect)
        painter.end()

    # ---------------------------------------------------------------- animation
    def _stop_glide(self) -> None:
        if self._glide.state() == QAbstractAnimation.State.Running:
            self._glide.stop()
        self._animating = False

    def _glide_to_index(self, index: int, *, duration: int = 260) -> None:
        target = max(self.minimum(), min(self.maximum(), index))
        target_fraction = self._fraction_for_value(target)
        if abs(target_fraction - self._display_fraction) < 1e-5:
            self._display_fraction = target_fraction
            self.setValue(target)
            self.update()
            return
        self._glide.stop()
        self._animating = True
        self._glide.setStartValue(self._display_fraction)
        self._glide.setEndValue(target_fraction)
        self._glide.setDuration(duration)
        self._glide.start()

    def _on_glide_value(self, value) -> None:
        self._display_fraction = float(value)
        self._syncing = True
        try:
            self.setValue(self._value_for_fraction(self._display_fraction))
        finally:
            self._syncing = False
        self.update()

    def _on_glide_finished(self) -> None:
        self._animating = False
        self._display_fraction = self._glide.endValue()
        self._syncing = True
        try:
            self.setValue(self._value_for_fraction(self._display_fraction))
        finally:
            self._syncing = False
        self.update()

    def _on_value_changed(self, value: int) -> None:
        if self._animating or self._dragging or self._syncing:
            return
        self._display_fraction = self._fraction_for_value(value)
        self.update()

    def _on_range_changed(self, _minimum: int, _maximum: int) -> None:
        if not self._animating and not self._dragging:
            self._display_fraction = self._fraction_for_value(self.value())
            self.update()

    def setValue(self, value: int) -> None:  # noqa: N802 - Qt API name
        if not self._animating and not self._dragging and not self._syncing:
            self._stop_glide()
        super().setValue(value)
        if not self._animating and not self._dragging and not self._syncing:
            self._display_fraction = self._fraction_for_value(self.value())
            self.update()

    # ---------------------------------------------------------------- interaction
    def _handle_hit(self, point) -> bool:
        center_x = self._handle_center_x()
        center_y = self.height() / 2
        dx = point.x() - center_x
        dy = point.y() - center_y
        return dx * dx + dy * dy <= 16 * 16

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() != Qt.MouseButton.LeftButton or not self.isEnabled():
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        point = event.position()
        if self._handle_hit(point):
            self._stop_glide()
            self._dragging = True
            self._drag_offset = point.x() - self._handle_center_x()
        else:
            target = self._value_for_fraction(self._fraction_at_x(point.x()))
            self._glide_to_index(target)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            center = event.position().x() - self._drag_offset
            self._display_fraction = self._fraction_at_x(center)
            self._syncing = True
            try:
                self.setValue(self._value_for_fraction(self._display_fraction))
            finally:
                self._syncing = False
            self.update()
            event.accept()
            return
        hovered = self.rect().contains(event.position().toPoint())
        if hovered != self._hover:
            self._hover = hovered
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._glide_to_index(self.value(), duration=150)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._animating:
            # A groove click should keep gliding after the button is released.
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        key = event.key()
        delta = 0
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            delta = -1
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            delta = 1
        elif key == Qt.Key.Key_PageDown:
            delta = -self.pageStep()
        elif key == Qt.Key.Key_PageUp:
            delta = self.pageStep()
        elif key == Qt.Key.Key_Home:
            self._glide_to_index(self.minimum(), duration=180)
            event.accept()
            return
        elif key == Qt.Key.Key_End:
            self._glide_to_index(self.maximum(), duration=180)
            event.accept()
            return
        if delta:
            base = self.value()
            if self._animating:
                base = self._value_for_fraction(self._glide.endValue())
            self._glide_to_index(base + delta, duration=180)
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API name
        step = 1 if event.angleDelta().y() > 0 else -1
        base = self.value()
        if self._animating:
            base = self._value_for_fraction(self._glide.endValue())
        self._glide_to_index(base + step, duration=180)
        event.accept()


class EntityItemDelegate(QStyledItemDelegate):
    """Two-line card row with a large avatar and a quiet type subtitle."""

    def __init__(self, parent=None, *, row_height: int = 54, icon_size: int = 34) -> None:
        super().__init__(parent)
        self.row_height = row_height
        self.icon_size = icon_size

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        del option, index
        return QSize(0, self.row_height)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        palette = option.palette
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        row = QRectF(option.rect).adjusted(3, 2, -3, -2)
        accent = palette.color(QPalette.ColorRole.Highlight)

        if selected:
            fill = QColor(accent)
            fill.setAlpha(48)
            border = QColor(accent)
            painter.setPen(QPen(border, 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(row, 11, 11)
            marker = QRectF(row.left() + 1, row.top() + 8, 3, row.height() - 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawRoundedRect(marker, 1.5, 1.5)
        elif hovered:
            fill = palette.color(QPalette.ColorRole.WindowText)
            fill.setAlpha(12)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(row, 11, 11)

        icon_data = index.data(Qt.ItemDataRole.DecorationRole)
        icon_left = row.left() + 9
        icon_rect = QRect(
            round(icon_left),
            round(row.center().y() - self.icon_size / 2),
            self.icon_size,
            self.icon_size,
        )
        if isinstance(icon_data, QIcon) and not icon_data.isNull():
            icon_data.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)

        text_left = icon_rect.right() + 11
        badge_width = 0
        if bool(index.data(ON_GRAPH_ROLE)):
            badge_width = 9
        text_right = row.right() - 10 - badge_width
        name = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        subtitle = str(index.data(SUBTITLE_ROLE) or "")

        name_font = QFont(option.font)
        name_font.setBold(True)
        name_font.setPointSizeF(max(7.6, name_font.pointSizeF()))
        painter.setFont(name_font)
        metrics = QFontMetrics(name_font)
        elapsed = metrics.elidedText(
            name, Qt.TextElideMode.ElideRight, max(20, round(text_right - text_left))
        )
        name_rect = QRectF(text_left, row.top() + 7, text_right - text_left, 20)
        painter.setPen(palette.color(QPalette.ColorRole.WindowText))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter, elapsed)

        if subtitle:
            sub_font = QFont(option.font)
            sub_font.setBold(False)
            sub_font.setPointSizeF(max(7.0, sub_font.pointSizeF() - 0.9))
            painter.setFont(sub_font)
            sub_metrics = QFontMetrics(sub_font)
            sub_elapsed = sub_metrics.elidedText(
                subtitle,
                Qt.TextElideMode.ElideRight,
                max(20, round(text_right - text_left)),
            )
            sub_rect = QRectF(text_left, row.top() + 24, text_right - text_left, 18)
            muted = palette.color(QPalette.ColorRole.PlaceholderText)
            if not muted.isValid() or muted.alpha() == 0:
                muted = palette.color(QPalette.ColorRole.WindowText)
                muted.setAlpha(160)
            painter.setPen(muted)
            painter.drawText(sub_rect, Qt.AlignmentFlag.AlignVCenter, sub_elapsed)

        if badge_width:
            dot = QRectF(row.right() - 14, row.center().y() - 3, 6, 6)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(dot)

        painter.restore()
