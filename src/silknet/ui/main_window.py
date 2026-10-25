"""Main window, custom window chrome and navigation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from silknet.config import AppSettings, SettingsError, save_settings
from silknet.services.container import ApplicationServices
from silknet.ui.assets import ICON_FILE, app_icon
from silknet.ui.entity_manager import EntityManagerPage
from silknet.ui.evidence_view import EvidencePage
from silknet.ui.fonts import ensure_app_fonts
from silknet.ui.graph_view import GraphPage
from silknet.ui.intro import StartupIntro
from silknet.ui.mascot import MascotPet
from silknet.ui.navigation import NAV_ITEMS, NavigationSidebar
from silknet.ui.pages import (
    AboutPage,
    DashboardPage,
    PlaceholderPage,
    SettingsPage,
)
from silknet.ui.petals import PetalOverlay
from silknet.ui.search_view import SearchPage
from silknet.ui.theme import build_stylesheet, theme_colors
from silknet.ui.window_effects import apply_taskbar_icon, configure_native_window
from silknet.ui.window_frame import ResizeHandler

_PAGE_TITLES = {key: label for key, label in NAV_ITEMS}
_CORNER_RADIUS = 24


def _mix_color(start: QColor, end: QColor, progress: float) -> QColor:
    """Blend two colors, including alpha, for smooth hover transitions."""
    amount = max(0.0, min(1.0, progress))
    return QColor(
        round(start.red() + (end.red() - start.red()) * amount),
        round(start.green() + (end.green() - start.green()) * amount),
        round(start.blue() + (end.blue() - start.blue()) * amount),
        round(start.alpha() + (end.alpha() - start.alpha()) * amount),
    )


class _AnimatedHoverButton(QAbstractButton):
    """Small icon button with a soft, non-jarring hover response."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._hover_progress = 0.0
        self._hover_animation = QVariantAnimation(self)
        self._hover_animation.setDuration(140)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation.valueChanged.connect(self._set_hover_progress)

    def _set_hover_progress(self, value: object) -> None:
        self._hover_progress = float(value)
        self.update()

    def _animate_hover(self, target: float) -> None:
        self._hover_animation.stop()
        if abs(self._hover_progress - target) < 0.001:
            return
        self._hover_animation.setStartValue(self._hover_progress)
        self._hover_animation.setEndValue(target)
        self._hover_animation.start()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._animate_hover(1.0)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._animate_hover(0.0)


class WindowControlButton(_AnimatedHoverButton):
    """Crisp minimize, maximize and close controls for the custom title bar."""

    def __init__(self, kind: str, tooltip: str, parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._maximized = False
        self._icon_color = QColor("#A9AEB8")
        self._hover_icon = QColor("#FFFFFF")
        self._hover_surface = QColor("#262A30")
        self._close_hover = QColor("#D94F63")
        self.setToolTip(tooltip)
        self.setAccessibleName(f"{tooltip} window")
        self.setFixedSize(38, 30)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_colors(self, colors: dict[str, str]) -> None:
        self._icon_color = QColor(colors["muted"])
        self._hover_icon = QColor(colors["text"])
        self._hover_surface = QColor(colors["surface_alt"])
        self._close_hover = QColor("#D94F63")
        self.update()

    def set_maximized(self, maximized: bool) -> None:
        self._maximized = maximized
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        unit = min(self.width() / 38.0, self.height() / 30.0)
        rect = QRectF(self.rect()).adjusted(2 * unit, 2 * unit, -2 * unit, -2 * unit)
        hovered = max(self._hover_progress, 1.0 if self.isDown() else 0.0)
        close = self._kind == "close"

        base = QColor(self._hover_surface)
        base.setAlpha(92 if self._icon_color.lightness() < 128 else 150)
        target = QColor(self._close_hover if close else self._hover_surface)
        target.setAlpha(255)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_mix_color(base, target, hovered))
        painter.drawRoundedRect(rect, 9 * unit, 9 * unit)

        ink = _mix_color(self._icon_color, self._hover_icon, hovered)
        if close:
            ink = _mix_color(ink, QColor("#FFFFFF"), hovered)
        pen = QPen(
            ink,
            max(1.25, 1.6 * unit),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center = rect.center()
        if self._kind == "minimize":
            painter.drawLine(
                QPoint(round(center.x() - 6 * unit), round(center.y())),
                QPoint(round(center.x() + 6 * unit), round(center.y())),
            )
        elif self._kind == "maximize" and self._maximized:
            offset = 2.0 * unit
            painter.drawRoundedRect(
                QRectF(center.x() - 5.4 * unit, center.y() - 4.0 * unit, 9.4 * unit, 8.2 * unit),
                1.2 * unit,
                1.2 * unit,
            )
            painter.drawRoundedRect(
                QRectF(
                    center.x() - 3.8 * unit - offset,
                    center.y() - 5.8 * unit + offset,
                    9.4 * unit,
                    8.2 * unit,
                ),
                1.2 * unit,
                1.2 * unit,
            )
        elif self._kind == "maximize":
            painter.drawRoundedRect(
                QRectF(center.x() - 5.2 * unit, center.y() - 5.2 * unit, 10.4 * unit, 10.4 * unit),
                1.3 * unit,
                1.3 * unit,
            )
        else:
            extent = 5.6 * unit
            painter.drawLine(
                QPoint(round(center.x() - extent), round(center.y() - extent)),
                QPoint(round(center.x() + extent), round(center.y() + extent)),
            )
            painter.drawLine(
                QPoint(round(center.x() + extent), round(center.y() - extent)),
                QPoint(round(center.x() - extent), round(center.y() + extent)),
            )


class SidebarToggleButton(_AnimatedHoverButton):
    """Compact menu control for collapsing the left navigation rail."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._icon_color = QColor("#A9AEB8")
        self._hover_icon = QColor("#FFFFFF")
        self._hover_surface = QColor("#262A30")
        self._collapsed = False
        self.setToolTip("Hide navigation  ·  Ctrl+B")
        self.setAccessibleName("Hide navigation")
        self.setFixedSize(34, 30)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_colors(self, colors: dict[str, str]) -> None:
        self._icon_color = QColor(colors["muted"])
        self._hover_icon = QColor(colors["text"])
        self._hover_surface = QColor(colors["surface_alt"])
        self.update()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setToolTip("Show navigation  ·  Ctrl+B" if collapsed else "Hide navigation  ·  Ctrl+B")
        self.setAccessibleName("Show navigation" if collapsed else "Hide navigation")
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        unit = min(self.width() / 34.0, self.height() / 30.0)
        rect = QRectF(self.rect()).adjusted(2 * unit, 2 * unit, -2 * unit, -2 * unit)
        hovered = max(self._hover_progress, 1.0 if self.isDown() else 0.0)
        background = QColor(self._hover_surface)
        background.setAlpha(round((210 if self._icon_color.lightness() < 128 else 120) * hovered))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 9 * unit, 9 * unit)

        color = _mix_color(self._icon_color, self._hover_icon, hovered)
        pen = QPen(
            color,
            max(1.4, 1.8 * unit),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center = rect.center()
        if self._collapsed:
            chevron = 4.4 * unit
            painter.drawLine(
                QPoint(round(center.x() - chevron * 0.55), round(center.y() - chevron)),
                QPoint(round(center.x() + chevron * 0.45), round(center.y())),
            )
            painter.drawLine(
                QPoint(round(center.x() + chevron * 0.45), round(center.y())),
                QPoint(round(center.x() - chevron * 0.55), round(center.y() + chevron)),
            )
        else:
            half = 6.5 * unit
            for offset in (-4.2 * unit, 0.0, 4.2 * unit):
                painter.drawLine(
                    QPoint(round(center.x() - half), round(center.y() + offset)),
                    QPoint(round(center.x() + half), round(center.y() + offset)),
                )


class TopBar(QWidget):
    """Top bar that can also drag the frameless window."""

    maximize_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        # Like the navigation rail, this custom QWidget subclass needs an
        # explicit styled background or its theme background is skipped.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._drag_offset: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        window = self.window()
        handle = window.windowHandle()
        if handle is not None and handle.startSystemMove():
            event.accept()
            return
        self._drag_offset = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class Toast(QFrame):
    """Short-lived notification that replaces the old status strip."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label = QLabel()
        self.label.setObjectName("toastText")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 11, 18, 11)
        layout.setSpacing(0)
        layout.addWidget(self.label)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(190)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._finish_fade)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, duration: int = 4200) -> None:
        clean = " ".join(str(text).split())
        if not clean:
            return
        self.label.setText(clean)
        self._fit_to_text()
        self.reposition()
        self.show()
        self.raise_()
        self._hide_timer.start(max(1200, duration))
        self._fade.stop()
        self._fade.setDuration(190)
        self._fade.setStartValue(float(self._effect.opacity()))
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _fit_to_text(self) -> None:
        parent = self.parentWidget()
        available = max(240, (parent.width() if parent is not None else 700) - 64)
        metrics = self.label.fontMetrics()
        natural = metrics.horizontalAdvance(self.label.text()) + 4
        text_width = max(200, min(600, available, natural))
        self.label.setFixedWidth(text_width)
        label_height = max(metrics.height(), self.label.heightForWidth(text_width))
        self.label.setFixedHeight(label_height)
        self.setFixedSize(text_width + 36, label_height + 22)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self._fit_to_text()
        x = max(16, (parent.width() - self.width()) // 2)
        y = max(16, parent.height() - self.height() - 24)
        self.move(x, y)

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(float(self._effect.opacity()))
        self._fade.setEndValue(0.0)
        self._fade.setDuration(220)
        self._fade.start()

    def _finish_fade(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.hide()


class SilknetWindow(QMainWindow):
    def __init__(
        self,
        settings: AppSettings | None = None,
        settings_file: Path | None = None,
        services: ApplicationServices | None = None,
    ) -> None:
        super().__init__()
        self.app_settings = settings or AppSettings()
        self.settings_file = settings_file
        self.services = services
        self.entity_service = services.entities if services is not None else None
        self._current_page = "dashboard"
        self._page_fade: QPropertyAnimation | None = None
        self._page_slide: QPropertyAnimation | None = None
        self._transition_host: QWidget | None = None
        self._intro: StartupIntro | None = None
        self._intro_played = False
        self._sidebar_collapsed = False
        self._sidebar_animation: QVariantAnimation | None = None
        self._fullscreen_restore_maximized = False

        ensure_app_fonts()
        self.setWindowTitle("Alya SILKNET")
        self.setWindowIcon(app_icon())
        # The app draws its own rounded window chrome. The system hints still
        # give the taskbar a normal minimize/restore target while the custom
        # chrome stays frameless.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(960, 650)
        self._apply_stylesheet(self.app_settings)

        root = QWidget(self)
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.navigation = NavigationSidebar(root)
        self.navigation.page_requested.connect(self.navigate_to)
        root_layout.addWidget(self.navigation)

        main_area = QWidget(root)
        main_area.setObjectName("mainArea")
        self._main_area = main_area
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.top_bar = TopBar(main_area)
        self.top_bar.maximize_requested.connect(self._toggle_maximize)
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(18, 10, 12, 10)
        top_layout.setSpacing(12)
        self.sidebar_toggle = SidebarToggleButton(self.top_bar)
        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("pageTitle")
        self.search_field = QLineEdit(self.top_bar)
        self.search_field.setAccessibleName("Search SILKNET")
        self.search_field.setPlaceholderText("Search workspace  ·  Ctrl+K")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setMaximumWidth(420)
        self.search_field.setMinimumWidth(340)
        self.search_field.returnPressed.connect(self._open_search)
        local_status = QLabel("●  Local")
        local_status.setObjectName("localBadge")
        local_status.setToolTip("Records are stored in the local database.")
        self.minimize_button = WindowControlButton("minimize", "Minimize")
        self.maximize_button = WindowControlButton("maximize", "Maximize")
        self.close_button = WindowControlButton("close", "Close")
        self.minimize_button.clicked.connect(self.showMinimized)
        self.maximize_button.clicked.connect(self._toggle_maximize)
        self.close_button.clicked.connect(self.close)
        top_layout.addWidget(self.sidebar_toggle)
        top_layout.addWidget(self.page_title)
        top_layout.addStretch(1)
        top_layout.addWidget(self.search_field)
        top_layout.addWidget(local_status)
        top_layout.addSpacing(6)
        top_layout.addWidget(self.minimize_button)
        top_layout.addWidget(self.maximize_button)
        top_layout.addWidget(self.close_button)
        self._sync_control_colors()
        main_layout.addWidget(self.top_bar)

        self.pages = QStackedWidget(main_area)
        self.pages.setObjectName("workspacePages")
        self.page_widgets: dict[str, QWidget] = {}
        self._page_hosts: dict[str, QWidget] = {}
        self._build_pages()
        main_layout.addWidget(self.pages, 1)
        root_layout.addWidget(main_area, 1)
        self.setCentralWidget(root)

        self._petal_overlay = PetalOverlay(root)
        self._petal_overlay.setGeometry(root.rect())
        self._petal_overlay.hide()
        self._toast = Toast(root)
        self._intro = StartupIntro(self.app_settings, root)
        self._intro.hide()
        self._intro.finished.connect(self._on_intro_finished)

        self._size_and_center()
        self.mascot = MascotPet(self)

        self._sidebar_animation = QVariantAnimation(self)
        self._sidebar_animation.setDuration(220)
        self._sidebar_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._sidebar_animation.valueChanged.connect(self._set_sidebar_width)
        self._sidebar_animation.finished.connect(self._finish_sidebar_animation)

        self._resizer = ResizeHandler(self)
        self.navigation.set_current(self._current_page)
        self._install_shortcuts()
        self._sync_ambient()
        self._sync_window_state()
        QTimer.singleShot(0, self._refresh_native_window)

    @property
    def current_page(self) -> str:
        return self._current_page

    def play_intro(self) -> None:
        """Play the launch intro once, after the window has been shown."""
        intro = self._intro
        if intro is None or self._intro_played:
            return
        self._intro_played = True
        self._sync_overlay_geometry()
        intro.play()
        self._sync_ambient()

    def _on_intro_finished(self) -> None:
        self._sync_ambient()

    def navigate_to(self, page_key: str) -> None:
        page = self.page_widgets.get(page_key)
        host = self._page_hosts.get(page_key)
        if page is None or host is None:
            return
        previous_page = self._current_page
        changing = page_key != previous_page
        if page_key == "dashboard":
            self.dashboard.refresh_counts()
        self._current_page = page_key
        self.pages.setCurrentWidget(host)
        self.navigation.set_current(page_key)
        self.page_title.setText(_PAGE_TITLES[page_key])
        if changing:
            self._animate_page_change(host, self._page_direction(previous_page, page_key))

    def _build_pages(self) -> None:
        self.dashboard = DashboardPage(self.services)
        self.dashboard.navigate_requested.connect(self.navigate_to)
        self._add_page("dashboard", self.dashboard)

        if self.services is not None:
            self.graph_page = GraphPage(self.services, self.app_settings)
            self.graph_page.navigate_requested.connect(self.navigate_to)
            self._add_page("graph", self.graph_page)
        else:
            self.graph_page = PlaceholderPage("graph")
            self.graph_page.navigate_requested.connect(self.navigate_to)
            self._add_page("graph", self.graph_page)

        if self.entity_service is not None:
            self.entity_page = EntityManagerPage(
                self.entity_service,
                self.services.profile_images,
                self.services.platforms,
                self.services.sources,
            )
            self._add_page("entities", self.entity_page)
        else:
            self.entity_page = PlaceholderPage("entities")
            self._add_page("entities", self.entity_page)

        if self.services is not None:
            self.evidence_page = EvidencePage(self.services)
            self._add_page("evidence", self.evidence_page)
        else:
            self.evidence_page = PlaceholderPage("evidence")
            self.evidence_page.navigate_requested.connect(self.navigate_to)
            self._add_page("evidence", self.evidence_page)

        if self.services is not None:
            self.search_page = SearchPage(self.services)
            self.search_page.record_open_requested.connect(self._open_search_result)
            self._add_page("search", self.search_page)
        else:
            self.search_page = PlaceholderPage("search")
            self.search_page.navigate_requested.connect(self.navigate_to)
            self._add_page("search", self.search_page)

        settings_page = SettingsPage(
            self.app_settings,
            self.services.backups if self.services is not None else None,
        )
        settings_page.theme_requested.connect(self._change_theme)
        settings_page.settings_requested.connect(self._apply_settings)
        settings_page.workspace_restored.connect(self._refresh_workspace)
        self._add_page("settings", settings_page)
        self._settings_page = settings_page
        self._add_page("about", AboutPage())
        self._connect_data_signals()

    def _add_page(self, key: str, page: QWidget) -> None:
        host = QWidget(self.pages)
        host.setObjectName("pageHost")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        scroll = QScrollArea(host)
        scroll.setObjectName("pageScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(page)
        host_layout.addWidget(scroll)
        self.page_widgets[key] = page
        self._page_hosts[key] = host
        self.pages.addWidget(host)

    def _connect_data_signals(self) -> None:
        entity_page = self.page_widgets.get("entities")
        if isinstance(entity_page, EntityManagerPage):
            entity_page.records_changed.connect(lambda: self._refresh_related_data("entities"))
            entity_page.message.connect(self._show_status_message)
        graph_page = self.page_widgets.get("graph")
        if isinstance(graph_page, GraphPage):
            graph_page.records_changed.connect(lambda: self._refresh_related_data("graph"))
            graph_page.message.connect(self._show_status_message)
        evidence_page = self.page_widgets.get("evidence")
        if hasattr(evidence_page, "records_changed"):
            evidence_page.records_changed.connect(lambda: self._refresh_related_data("evidence"))
            evidence_page.message.connect(self._show_status_message)
        search_page = self.page_widgets.get("search")
        if hasattr(search_page, "records_changed"):
            search_page.records_changed.connect(lambda: self._refresh_related_data("search"))
            search_page.message.connect(self._show_status_message)

    def _refresh_related_data(self, source: str) -> None:
        self.dashboard.refresh_counts()
        if source != "entities" and isinstance(self.entity_page, EntityManagerPage):
            self.entity_page.refresh_entities()
        if source != "graph" and isinstance(self.graph_page, GraphPage):
            self.graph_page.refresh_graph()
        if source != "evidence" and hasattr(self.evidence_page, "refresh_sources"):
            self.evidence_page.refresh_sources()
        if source != "search" and hasattr(self.search_page, "refresh_results"):
            refresh_types = getattr(self.search_page, "refresh_entity_types", None)
            if refresh_types is not None:
                refresh_types()
            self.search_page.refresh_results()

    def _show_status_message(self, message: str) -> None:
        toast = getattr(self, "_toast", None)
        if toast is not None:
            toast.show_message(message)

    def _open_search(self) -> None:
        self.navigate_to("search")
        query = self.search_field.text().strip()
        search_page = self.page_widgets.get("search")
        if isinstance(search_page, SearchPage):
            search_page.set_query(query)

    def _open_search_result(self, page_key: str, record_id: str) -> None:
        self.navigate_to(page_key)
        page = self.page_widgets.get(page_key)
        selector = getattr(page, "select_record", None) or getattr(page, "select_entity", None)
        if selector:
            selector(record_id)

    def _refresh_workspace(self) -> None:
        self.dashboard.refresh_counts()
        refresh_types = getattr(self.search_page, "refresh_entity_types", None)
        if refresh_types is not None:
            refresh_types()
        for key, method_name in (
            ("entities", "refresh_entities"),
            ("graph", "refresh_graph"),
            ("evidence", "refresh_sources"),
            ("search", "refresh_results"),
        ):
            page = self.page_widgets.get(key)
            method = getattr(page, method_name, None)
            if method:
                method()
        refresh_types = getattr(self.search_page, "refresh_entity_types", None)
        if refresh_types is not None:
            refresh_types()

    def _change_theme(self, theme: str) -> None:
        self._apply_settings(self._settings_page.settings_for_theme(theme))

    def _apply_settings(self, updated: AppSettings) -> None:
        try:
            if self.settings_file is not None:
                save_settings(self.settings_file, updated)
        except SettingsError as exc:
            QMessageBox.warning(self, "Could not save appearance", str(exc))
            self._settings_page.set_settings(self.app_settings)
            return

        self.app_settings = updated
        self._apply_stylesheet(updated)
        self._settings_page.set_settings(updated)
        if isinstance(self.graph_page, GraphPage):
            self.graph_page.set_theme(updated)
        if isinstance(self.entity_page, EntityManagerPage):
            self.entity_page.refresh_entities()
        if self._intro is not None:
            self._intro.set_settings(updated)
        self._sync_ambient()
        self._refresh_native_window()
        self._sync_window_state()
        self.update()

    def _apply_stylesheet(self, settings: AppSettings) -> None:
        stylesheet = build_stylesheet(settings)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet)
        self.setStyleSheet(stylesheet)
        self._sync_control_colors()

    def _sync_control_colors(self) -> None:
        if not hasattr(self, "minimize_button"):
            return
        colors = theme_colors(self.app_settings)
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            button.set_colors(colors)
        self.sidebar_toggle.set_colors(colors)

    def _refresh_native_window(self) -> None:
        configure_native_window(self, dark=self.app_settings.theme not in {"light", "pink"})
        apply_taskbar_icon(self, ICON_FILE)

    def _toggle_maximize(self) -> None:
        if self.isFullScreen():
            self._restore_from_fullscreen()
            return
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._sync_window_state()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self._restore_from_fullscreen()
            return
        self._fullscreen_restore_maximized = self.isMaximized()
        self.showFullScreen()
        self._sync_window_state()

    def _restore_from_fullscreen(self) -> None:
        if self._fullscreen_restore_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        self._sync_window_state()

    def _sync_window_state(self) -> None:
        if not hasattr(self, "maximize_button"):
            return
        immersive = self.isMaximized() or self.isFullScreen()
        self.setProperty("immersive", immersive)
        for widget in (
            getattr(self, "navigation", None),
            getattr(self, "_main_area", None),
            getattr(self, "top_bar", None),
        ):
            if widget is None:
                continue
            widget.setProperty("immersive", immersive)
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()
        maximized = self.isMaximized() or self.isFullScreen()
        self.maximize_button.set_maximized(maximized)
        if self.isFullScreen():
            tooltip = "Exit full screen  ·  F11"
            accessible = "Exit full screen"
        elif maximized:
            tooltip = "Restore"
            accessible = "Restore window"
        else:
            tooltip = "Maximize  ·  F11 for full screen"
            accessible = "Maximize window"
        self.maximize_button.setToolTip(tooltip)
        self.maximize_button.setAccessibleName(accessible)
        if hasattr(self, "_resizer"):
            self._resizer.reload()
        self.update()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_window_state()
            self._sync_ambient()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_resizer"):
            self._resizer.reload()
        self._sync_overlay_geometry()
        self.update()

    def closeEvent(self, event) -> None:
        page = getattr(self, "_settings_page", None)
        if page is not None:
            page.flush_pending_settings()
        if self._intro is not None:
            self._intro.stop()
        self._petal_overlay.stop()
        pet = getattr(self, "mascot", None)
        if pet is not None:
            pet.set_active(False)
            pet.close()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:
        self._petal_overlay.stop()
        pet = getattr(self, "mascot", None)
        if pet is not None:
            pet.set_active(False)
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "_resizer"):
            self._resizer.reload()
        self._sync_overlay_geometry()
        self._sync_window_state()
        self._sync_ambient()
        QTimer.singleShot(0, self._refresh_native_window)

    def _sync_overlay_geometry(self) -> None:
        central = self.centralWidget()
        if central is None:
            return
        if hasattr(self, "_petal_overlay"):
            self._petal_overlay.setGeometry(central.rect())
            if self._petal_overlay.isVisible():
                self._petal_overlay.raise_()
        toast = getattr(self, "_toast", None)
        if toast is not None:
            toast.reposition()
            if toast.isVisible():
                toast.raise_()
        intro = getattr(self, "_intro", None)
        if intro is not None:
            intro.setGeometry(central.rect())
            if intro.isVisible():
                intro.raise_()

    def _size_and_center(self) -> None:
        """Open at a comfortable size, centred on the current monitor."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(1240, 760)
            return
        available = screen.availableGeometry()
        width = min(1440, max(1080, round(available.width() * 0.84)))
        height = min(920, max(700, round(available.height() * 0.87)))
        width = min(width, max(960, available.width() - 32))
        height = min(height, max(650, available.height() - 32))
        self.resize(width, height)
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def toggle_sidebar(self) -> None:
        """Animate the navigation rail out of the way, or bring it back."""
        collapsing = not self._sidebar_collapsed
        if self._sidebar_animation is None:
            self.navigation.setFixedWidth(0 if collapsing else 250)
            self.navigation.setVisible(not collapsing)
            self._sidebar_collapsed = collapsing
            self.sidebar_toggle.set_collapsed(collapsing)
            return

        self._sidebar_animation.stop()
        self._sidebar_collapsed = collapsing
        self.sidebar_toggle.set_collapsed(collapsing)
        if not collapsing:
            self.navigation.show()
        start = self.navigation.width()
        end = 0 if collapsing else 250
        self._sidebar_animation.setStartValue(float(start))
        self._sidebar_animation.setEndValue(float(end))
        self._sidebar_animation.start()

    def _set_sidebar_width(self, value: object) -> None:
        width = max(0, round(float(value)))
        self.navigation.setFixedWidth(width)

    def _finish_sidebar_animation(self) -> None:
        if self._sidebar_collapsed:
            self.navigation.setFixedWidth(0)
            self.navigation.hide()
        else:
            self.navigation.setFixedWidth(250)
            self.navigation.show()
            if isinstance(self.graph_page, GraphPage):
                self.graph_page.fit_graph()

    def _page_direction(self, previous: str, current: str) -> int:
        """Return 1 for a forward tab move and -1 for a backward one."""
        order = [key for key, _label in NAV_ITEMS]
        try:
            return 1 if order.index(current) >= order.index(previous) else -1
        except ValueError:
            return 1

    def _animate_page_change(self, host: QWidget, direction: int = 1) -> None:
        """Fade and slide the new page in from the side matching the tab order."""
        self._stop_page_animation()
        effect = QGraphicsOpacityEffect(host)
        effect.setOpacity(0.0)
        host.setGraphicsEffect(effect)
        offset = 26 * (1 if direction >= 0 else -1)
        host.move(offset, 0)
        fade = QPropertyAnimation(effect, b"opacity", host)
        fade.setDuration(200)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        slide = QPropertyAnimation(host, b"pos", host)
        slide.setDuration(200)
        slide.setStartValue(QPoint(offset, 0))
        slide.setEndValue(QPoint(0, 0))
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade.finished.connect(lambda: self._finish_page_animation(host, fade))
        self._page_fade = fade
        self._page_slide = slide
        self._transition_host = host
        fade.start()
        slide.start()

    def _finish_page_animation(self, host: QWidget, fade: QPropertyAnimation) -> None:
        if self._page_fade is not fade or self._transition_host is not host:
            return
        self._page_fade = None
        self._transition_host = None
        slide = self._page_slide
        self._page_slide = None
        if slide is not None:
            slide.stop()
            slide.deleteLater()
        host.setGraphicsEffect(None)
        host.move(0, 0)
        fade.deleteLater()

    def _stop_page_animation(self) -> None:
        fade = self._page_fade
        slide = self._page_slide
        host = self._transition_host
        self._page_fade = None
        self._page_slide = None
        self._transition_host = None
        if fade is not None:
            fade.stop()
            fade.deleteLater()
        if slide is not None:
            slide.stop()
            slide.deleteLater()
        if host is not None:
            host.setGraphicsEffect(None)
            host.move(0, 0)

    def _sync_ambient(self) -> None:
        intro_playing = self._intro is not None and self._intro.is_playing
        active = (
            self.app_settings.theme == "pink"
            and not intro_playing
            and self.isVisible()
            and not self.isMinimized()
        )
        self.mascot.set_active(active)
        if active:
            self._sync_overlay_geometry()
            self._petal_overlay.start()
            self._petal_overlay.raise_()
            self._toast.raise_()
        else:
            self._petal_overlay.stop()
        if self._intro is not None and self._intro.isVisible():
            self._intro.raise_()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        colors = theme_colors(self.app_settings)
        immersive = self.isMaximized() or self.isFullScreen()
        radius = 0 if immersive else _CORNER_RADIUS
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        if radius:
            path.addRoundedRect(rect, radius, radius)
        else:
            path.addRect(rect)
        painter.fillPath(path, QColor(colors["window"]))
        painter.setClipping(False)
        if not immersive:
            border = QColor(colors["border"])
            border.setAlpha(80)
            painter.setPen(QPen(border, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        painter.end()

    def _install_shortcuts(self) -> None:
        for index, (page_key, _label) in enumerate(NAV_ITEMS, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda key=page_key: self.navigate_to(key))

        focus_search = QShortcut(QKeySequence("Ctrl+K"), self)
        focus_search.activated.connect(self.search_field.setFocus)
        focus_search.activated.connect(self.search_field.selectAll)

        toggle_sidebar = QShortcut(QKeySequence("Ctrl+B"), self)
        toggle_sidebar.activated.connect(self.toggle_sidebar)

        toggle_fullscreen = QShortcut(QKeySequence("F11"), self)
        toggle_fullscreen.activated.connect(self._toggle_fullscreen)

        leave_fullscreen = QShortcut(QKeySequence("Escape"), self)
        leave_fullscreen.setContext(Qt.ShortcutContext.WindowShortcut)
        leave_fullscreen.activated.connect(self._leave_fullscreen_shortcut)
        self._escape_shortcut = leave_fullscreen

    def _leave_fullscreen_shortcut(self) -> None:
        if self.isFullScreen():
            self._restore_from_fullscreen()
