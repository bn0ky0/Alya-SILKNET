"""Pages shown in the main workspace."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import (
    QRectF,
    QSignalBlocker,
    QSize,
    QStandardPaths,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath, QPen
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from silknet import __version__
from silknet.config import (
    DARK_ACCENTS,
    SUPPORTED_THEMES,
    UI_SCALE_OPTIONS,
    AppSettings,
    nearest_ui_scale,
)
from silknet.services.backup_service import BackupService
from silknet.services.container import ApplicationServices
from silknet.ui.assets import LogoBadge
from silknet.ui.theme import theme_colors
from silknet.ui.widgets import SmoothSlider
from silknet.updates import (
    LATEST_RELEASE_API,
    RELEASES_PAGE,
    UPDATE_TIMEOUT_MS,
    UPDATE_USER_AGENT,
    ReleaseInfo,
    is_newer,
    parse_release,
)

PAGE_DETAILS = {
    "graph": (
        "Investigation Graph",
        "Map the records and connections you add to Alya SILKNET.",
        "The graph view is still being built. You can add records in Entities in the meantime.",
    ),
    "evidence": (
        "Evidence & Sources",
        "Keep source material close to the claims it supports.",
        "Source management is not available in the interface yet.",
    ),
    "search": (
        "Search",
        "Find records saved in this workspace.",
        "Search is still being built. Open Entities to browse saved records.",
    ),
    "entities": (
        "Entities",
        "Manage people, organizations, profiles and other records.",
        "Entity storage is not connected in this window.",
    ),
}

THEME_OPTIONS = (
    ("dark", "Dark"),
    ("light", "Light"),
    ("pink", "Alya pink"),
    ("dark-red", "Dark red"),
    ("dark-purple", "Dark purple"),
    ("dark-green", "Dark green"),
)

#: Shows the accent color picker only where it applies.
_ACCENT_THEMES = {"dark", "light"}

_THEME_TIPS = {
    "dark": "Dark workspace that uses your chosen accent color.",
    "light": "Bright workspace that uses your chosen accent color.",
    "pink": "Kawaii pink workspace with Alya-sama and falling blossoms.",
    "dark-red": "Warm dark palette with a red accent.",
    "dark-purple": "Deep dark palette with a purple accent.",
    "dark-green": "Calm dark palette with a green accent.",
}

assert {theme for theme, _label in THEME_OPTIONS} == SUPPORTED_THEMES


class AccentSwatch(QAbstractButton):
    """Round, checkable color button used for the limited accent choices."""

    def __init__(self, color: str, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._name = name
        self.setCheckable(True)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)
        self.setAccessibleName(f"{name} accent color")

    def sizeHint(self) -> QSize:
        return QSize(34, 34)

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)

        if self.isChecked() or self.underMouse():
            ring = QColor(self._color)
            ring.setAlpha(255 if self.isChecked() else 110)
            painter.setPen(QPen(ring, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(-3, -3, 3, 3))

        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.setBrush(self._color)
        painter.drawEllipse(rect)

        if self.isChecked():
            ink = QColor("#FFFFFF") if self._color.lightness() < 165 else QColor("#10141B")
            pen = QPen(ink, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            check = QPainterPath()
            check.moveTo(rect.left() + 6, rect.center().y() + 1)
            check.lineTo(rect.center().x() - 0.5, rect.bottom() - 5.5)
            check.lineTo(rect.right() - 5, rect.top() + 5.5)
            painter.drawPath(check)


class PageHeader(QWidget):
    def __init__(
        self,
        eyebrow: str,
        title: str,
        description: str = "",
        *,
        compact: bool = False,
        inline: bool = False,
    ) -> None:
        super().__init__()
        title_label = QLabel(title)
        title_label.setObjectName("pageHeadingCompact" if compact else "pageHeading")
        description_label = QLabel(description) if description else None
        if description_label is not None:
            description_label.setObjectName(
                "pageDescriptionCompact" if compact else "pageDescription"
            )
            description_label.setWordWrap(True)

        if inline:
            # Title and description share one line on work-heavy pages. The
            # eyebrow is omitted there because the navigation rail already
            # names the current workspace.
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(14)
            layout.addWidget(title_label, 0, Qt.AlignmentFlag.AlignVCenter)
            if description_label is not None:
                layout.addWidget(description_label, 1, Qt.AlignmentFlag.AlignVCenter)
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3 if compact else 6)

        eyebrow_label = QLabel(eyebrow)
        eyebrow_label.setObjectName("pageEyebrow")
        layout.addWidget(eyebrow_label)
        layout.addWidget(title_label)
        if description_label is not None:
            layout.addWidget(description_label)


class EmptyWorkspace(QFrame):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        self.setObjectName("emptyCanvas")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        status = QLabel("In development")
        status.setObjectName("subtleText")
        heading = QLabel(title)
        heading.setObjectName("emptyTitle")
        copy = QLabel(description)
        copy.setObjectName("emptyDescription")
        copy.setWordWrap(True)
        copy.setMaximumWidth(520)
        self.open_entities = QPushButton("Open Entities")
        self.open_entities.setObjectName("quietButton")
        self.open_entities.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addWidget(status)
        layout.addWidget(heading)
        layout.addWidget(copy)
        layout.addSpacing(4)
        layout.addWidget(self.open_entities, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)


class PlaceholderPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, page_key: str) -> None:
        super().__init__()
        title, description, details = PAGE_DETAILS[page_key]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 30)
        layout.setSpacing(20)
        layout.addWidget(PageHeader("Workspace", title, description))

        empty_state = EmptyWorkspace(f"{title} is not ready yet", details)
        empty_state.open_entities.clicked.connect(lambda: self.navigate_requested.emit("entities"))
        layout.addWidget(empty_state, 1)


class DashboardPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, services: ApplicationServices | None = None) -> None:
        super().__init__()
        self.services = services
        self._count_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(20)
        layout.addWidget(
            PageHeader(
                "Overview",
                "Dashboard",
                "A place to keep people, organizations, sources and recorded connections together.",
            )
        )

        counts = QHBoxLayout()
        counts.setSpacing(12)
        for key, title in (
            ("entities", "Entities"),
            ("relationships", "Relationships"),
            ("sources", "Sources"),
        ):
            card = QFrame(self)
            card.setObjectName("surfaceCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 14, 18, 14)
            card_layout.setSpacing(3)
            value = QLabel("—")
            value.setObjectName("statValue")
            label = QLabel(title)
            label.setObjectName("statLabel")
            card_layout.addWidget(value)
            card_layout.addWidget(label)
            counts.addWidget(card, 1)
            self._count_labels[key] = value
        layout.addLayout(counts)

        section = QLabel("Get started")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        start_card = QFrame(self)
        start_card.setObjectName("surfaceCard")
        start_layout = QVBoxLayout(start_card)
        start_layout.setContentsMargins(20, 18, 20, 18)
        start_layout.setSpacing(14)

        start_title = QLabel("Add a record")
        start_title.setObjectName("cardTitle")
        start_description = QLabel(
            "Start with a person, organization, profile, or another entity. "
            "Then map the connections you can support with sources."
        )
        start_description.setObjectName("cardDescription")
        start_description.setWordWrap(True)
        start_layout.addWidget(start_title)
        start_layout.addWidget(start_description)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.open_entities = QPushButton("Add a record")
        self.open_entities.setObjectName("actionButton")
        self.open_entities.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_entities.clicked.connect(lambda: self.navigate_requested.emit("entities"))
        self.open_graph = QPushButton("Investigation Graph")
        self.open_graph.setObjectName("quietButton")
        self.open_graph.clicked.connect(lambda: self.navigate_requested.emit("graph"))
        self.open_search = QPushButton("Search workspace")
        self.open_search.setObjectName("quietButton")
        self.open_search.clicked.connect(lambda: self.navigate_requested.emit("search"))
        actions.addWidget(self.open_entities)
        actions.addWidget(self.open_graph)
        actions.addWidget(self.open_search)
        actions.addStretch(1)
        start_layout.addLayout(actions)

        shortcut_hint = QLabel("Ctrl+K search  ·  Ctrl+1–7 switch pages")
        shortcut_hint.setObjectName("subtleText")
        start_layout.addWidget(shortcut_hint)
        layout.addWidget(start_card)
        layout.addStretch(1)

        self.refresh_counts()

    def refresh_counts(self) -> None:
        if self.services is None:
            return

        services = {
            "entities": self.services.entities,
            "relationships": self.services.relationships,
            "sources": self.services.sources,
        }
        for key, service in services.items():
            self._count_labels[key].setText(str(len(service.list())))


class SettingsPage(QWidget):
    theme_requested = Signal(str)
    settings_requested = Signal(object)
    workspace_restored = Signal()

    def __init__(self, settings: AppSettings, backup_service: BackupService | None = None) -> None:
        super().__init__()
        self.backup_service = backup_service
        self._settings = settings

        self.setObjectName("settingsContent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 30)
        layout.setSpacing(18)
        layout.addWidget(
            PageHeader("Preferences", "Settings", "Choose how Alya SILKNET looks on this device.")
        )
        layout.addWidget(self._build_appearance_card())
        layout.addWidget(self._build_display_card())
        layout.addWidget(self._build_storage_card())
        layout.addStretch(1)

        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(180)
        self._settings_timer.timeout.connect(self._save_display_settings)

        self._sync_accent_buttons()
        self._sync_accent_block(settings.theme)
        self._show_scale_value()
        self._sync_slider_colors()

    # ------------------------------------------------------------------ cards

    def _build_appearance_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("surfaceCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(10)

        title = QLabel("Appearance")
        title.setObjectName("cardTitle")
        description = QLabel(
            "Pick a theme. Dark and Light follow your accent color; Alya pink adds Alya-sama "
            "and falling blossoms; every other theme keeps its own tuned palette."
        )
        description.setObjectName("cardDescription")
        description.setWordWrap(True)
        card_layout.addWidget(title)
        card_layout.addWidget(description)

        theme_group = QButtonGroup(self)
        theme_group.setExclusive(True)
        self.theme_buttons = {key: QRadioButton(label) for key, label in THEME_OPTIONS}
        self.dark_button = self.theme_buttons["dark"]
        self.light_button = self.theme_buttons["light"]
        self._button_themes = {button: key for key, button in self.theme_buttons.items()}
        choices = QGridLayout()
        choices.setHorizontalSpacing(22)
        choices.setVerticalSpacing(8)
        for index, (key, _label) in enumerate(THEME_OPTIONS):
            button = self.theme_buttons[key]
            button.setToolTip(_THEME_TIPS[key])
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            theme_group.addButton(button)
            button.toggled.connect(self._theme_toggled)
            choices.addWidget(button, index // 4, index % 4)
        current_button = self.theme_buttons[self._settings.theme]
        blocker = QSignalBlocker(current_button)
        current_button.setChecked(True)
        del blocker
        card_layout.addLayout(choices)

        self.accent_block = QWidget(card)
        accent_layout = QVBoxLayout(self.accent_block)
        accent_layout.setContentsMargins(0, 8, 0, 0)
        accent_layout.setSpacing(8)

        divider = QFrame(self.accent_block)
        divider.setObjectName("divider")
        divider.setFixedHeight(1)

        accent_header = QHBoxLayout()
        accent_header.setSpacing(8)
        accent_label = QLabel("Accent color")
        accent_label.setObjectName("mutedText")
        self.accent_value_label = QLabel("")
        self.accent_value_label.setObjectName("settingValue")
        accent_header.addWidget(accent_label)
        accent_header.addStretch(1)
        accent_header.addWidget(self.accent_value_label)

        swatches = QHBoxLayout()
        swatches.setSpacing(10)
        self.accent_group = QButtonGroup(self)
        self.accent_group.setExclusive(True)
        self.accent_buttons: dict[str, AccentSwatch] = {}
        for key, (name, color) in DARK_ACCENTS.items():
            swatch = AccentSwatch(color, name, self.accent_block)
            swatch.clicked.connect(
                lambda _checked=False, accent_key=key: self._accent_clicked(accent_key)
            )
            self.accent_group.addButton(swatch)
            self.accent_buttons[key] = swatch
            swatches.addWidget(swatch)
        swatches.addStretch(1)

        accent_layout.addWidget(divider)
        accent_layout.addLayout(accent_header)
        accent_layout.addLayout(swatches)
        card_layout.addWidget(self.accent_block)
        return card

    def _build_display_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("surfaceCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)

        title = QLabel("Display")
        title.setObjectName("cardTitle")
        description = QLabel(
            "Pick one of six fixed sizes for text and buttons. Window spacing and card "
            "sizes stay fixed, so the layout never grows or reflows."
        )
        description.setObjectName("cardDescription")
        description.setWordWrap(True)
        card_layout.addWidget(title)
        card_layout.addWidget(description)

        self.ui_scale_slider = SmoothSlider(Qt.Orientation.Horizontal)
        self.ui_scale_slider.setRange(0, len(UI_SCALE_OPTIONS) - 1)
        self.ui_scale_slider.setSingleStep(1)
        self.ui_scale_slider.setPageStep(1)
        self.ui_scale_slider.setValue(
            UI_SCALE_OPTIONS.index(nearest_ui_scale(self._settings.ui_scale))
        )
        self.ui_scale_slider.setAccessibleName("UI scale")
        self.ui_scale_slider.setToolTip("Six fixed steps: 75%, 80%, 85%, 90%, 95% and 100%")
        self.ui_scale_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.ui_scale_slider.setTickInterval(1)
        self.ui_scale_value = QLabel()
        self.ui_scale_value.setObjectName("settingValue")
        self.ui_scale_value.setMinimumWidth(64)
        self.ui_scale_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        scale_row = QHBoxLayout()
        scale_row.setSpacing(12)
        scale_caption = QLabel("UI scale")
        scale_caption.setObjectName("mutedText")
        scale_caption.setMinimumWidth(90)
        scale_row.addWidget(scale_caption)
        scale_row.addWidget(self.ui_scale_slider, 1)
        scale_row.addWidget(self.ui_scale_value)
        self.ui_scale_slider.valueChanged.connect(self._ui_scale_changed)
        card_layout.addLayout(scale_row)
        scale_hint = QLabel("75%  ·  80%  ·  85%  ·  90%  ·  95%  ·  100%")
        scale_hint.setObjectName("subtleText")
        scale_hint.setContentsMargins(102, 0, 76, 0)
        card_layout.addWidget(scale_hint)
        return card

    def _build_storage_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("surfaceCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(8)
        title = QLabel("Local files")
        title.setObjectName("cardTitle")
        copy = QLabel(
            "Workspace records, profile images, settings and logs stay in local files. "
            "Alya SILKNET does not use remote sync or analytics. Opening a URL or exporting "
            "a file is up to you. Local files are not encrypted by Alya SILKNET."
        )
        copy.setObjectName("cardDescription")
        copy.setWordWrap(True)
        card_layout.addWidget(title)
        card_layout.addWidget(copy)
        if self.backup_service is not None:
            backup_actions = QHBoxLayout()
            backup_actions.setSpacing(10)
            self.backup_button = QPushButton("Create backup")
            self.backup_button.setObjectName("quietButton")
            self.backup_button.clicked.connect(self._create_backup)
            self.restore_button = QPushButton("Restore backup")
            self.restore_button.setObjectName("quietButton")
            self.restore_button.clicked.connect(self._restore_backup)
            backup_actions.addWidget(self.backup_button)
            backup_actions.addWidget(self.restore_button)
            backup_actions.addStretch(1)
            card_layout.addLayout(backup_actions)
        return card

    # ------------------------------------------------------------- appearance

    def _theme_toggled(self, checked: bool) -> None:
        if not checked:
            return
        theme = self._button_themes.get(self.sender())
        if theme is None:
            return
        self._settings = self.settings_for_theme(theme)
        self._sync_accent_block(theme)
        self.theme_requested.emit(theme)

    def _accent_clicked(self, key: str) -> None:
        color = DARK_ACCENTS[key][1]
        self._settings = self._updated_settings(accent_color=color)
        self._sync_accent_buttons()
        self.settings_requested.emit(self._settings)

    def _sync_accent_block(self, theme: str) -> None:
        self.accent_block.setVisible(theme in _ACCENT_THEMES)

    def _sync_accent_buttons(self) -> None:
        current = self._settings.accent_color.upper()
        for key, button in self.accent_buttons.items():
            blocker = QSignalBlocker(button)
            button.setChecked(DARK_ACCENTS[key][1].upper() == current)
            del blocker
        name = next(
            (label for label, color in DARK_ACCENTS.values() if color.upper() == current),
            "Custom",
        )
        self.accent_value_label.setText(name)

    # ---------------------------------------------------------------- display

    def _ui_scale_changed(self, _value: int) -> None:
        self._show_scale_value()
        self._settings_timer.start()

    def _show_scale_value(self) -> None:
        self.ui_scale_value.setText(f"{self._scale_percent()}%")

    def _sync_slider_colors(self) -> None:
        colors = theme_colors(self._settings)
        self.ui_scale_slider.set_track_colors(
            accent=colors["accent"],
            groove=colors["border"],
            surface=colors["surface"],
            text=colors["text"],
        )

    def _scale_percent(self) -> int:
        index = max(0, min(self.ui_scale_slider.value(), len(UI_SCALE_OPTIONS) - 1))
        return round(UI_SCALE_OPTIONS[index] * 100)

    def _save_display_settings(self) -> None:
        self._settings = self._updated_settings()
        self.settings_requested.emit(self._settings)

    def flush_pending_settings(self) -> None:
        """Persist a slider change that is still inside the debounce window."""

        if not self._settings_timer.isActive():
            return
        self._settings_timer.stop()
        self._save_display_settings()

    def _updated_settings(self, **changes) -> AppSettings:
        index = max(0, min(self.ui_scale_slider.value(), len(UI_SCALE_OPTIONS) - 1))
        values = {
            "theme": self._settings.theme,
            "accent_color": self._settings.accent_color,
            "ui_scale": UI_SCALE_OPTIONS[index],
        }
        values.update(changes)
        return AppSettings(**values)

    def settings_for_theme(self, theme: str) -> AppSettings:
        return self._updated_settings(theme=theme)

    def set_theme(self, theme: str) -> None:
        self.set_settings(self.settings_for_theme(theme))

    def set_settings(self, settings: AppSettings) -> None:
        self._settings_timer.stop()
        self._settings = settings
        for theme, button in self.theme_buttons.items():
            blocker = QSignalBlocker(button)
            button.setChecked(theme == settings.theme)
            del blocker
        slider = self.ui_scale_slider
        blocker = QSignalBlocker(slider)
        slider.setValue(UI_SCALE_OPTIONS.index(nearest_ui_scale(settings.ui_scale)))
        del blocker
        self._show_scale_value()
        self._sync_accent_buttons()
        self._sync_accent_block(settings.theme)
        self._sync_slider_colors()

    # ---------------------------------------------------------------- backups

    def _create_backup(self) -> None:
        if self.backup_service is None:
            return
        documents = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        default_path = Path(documents) / f"Alya-SILKNET-backup-{stamp}.zip"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Create an Alya SILKNET backup",
            str(default_path),
            "Alya SILKNET backup (*.zip)",
        )
        if not filename:
            return
        try:
            self.backup_service.create_backup(Path(filename))
        except (OSError, ValueError, DatabaseError) as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))
            return
        QMessageBox.information(self, "Backup complete", f"Workspace backup saved to:\n{filename}")

    def _restore_backup(self) -> None:
        if self.backup_service is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Restore an Alya SILKNET backup", "", "Alya SILKNET backup (*.zip)"
        )
        if not filename:
            return
        answer = QMessageBox.question(
            self,
            "Restore workspace?",
            "This replaces the current workspace with the selected backup. "
            "Alya SILKNET saves a safety backup before replacing it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.backup_service.restore_backup(Path(filename))
        except (OSError, ValueError, DatabaseError) as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        self.workspace_restored.emit()
        QMessageBox.information(self, "Restore complete", "The workspace has been restored.")


class AboutPage(QWidget):
    """Product introduction, version details and a GitHub update check."""

    #: Tests and embedded builds can turn off the automatic request.
    auto_check_updates = True

    def __init__(self) -> None:
        super().__init__()
        self._update_manager = QNetworkAccessManager(self)
        self._update_reply: QNetworkReply | None = None
        self._latest_release: ReleaseInfo | None = None
        self._checked_for_updates = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 30)
        layout.setSpacing(20)
        layout.addWidget(PageHeader("About", "OSINT Investigations, Simplified."))

        card = QFrame(self)
        card.setObjectName("surfaceCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)

        identity = QHBoxLayout()
        identity.setSpacing(14)
        logo = LogoBadge(72, 0.27)
        logo.setObjectName("brandLogo")
        identity.addWidget(logo)
        identity_text = QVBoxLayout()
        identity_text.setSpacing(2)
        title = QLabel("Alya SILKNET")
        title.setObjectName("cardTitle")
        version = QLabel(f"Version {__version__}")
        version.setObjectName("subtleText")
        identity_text.addWidget(title)
        identity_text.addWidget(version)
        identity.addLayout(identity_text, 1)
        card_layout.addLayout(identity)

        description = QLabel(
            "A modern, lightweight, and easy-to-use OSINT investigation tool designed to help "
            "you organize information, connect the dots, and keep your investigations "
            "structured — all through a clean, interactive interface."
        )
        description.setObjectName("cardDescription")
        description.setWordWrap(True)
        card_layout.addWidget(description)

        update_row = QHBoxLayout()
        update_row.setSpacing(10)
        self.update_status = QLabel("Updates are checked against GitHub when this page opens.")
        self.update_status.setObjectName("subtleText")
        self.update_status.setWordWrap(True)
        update_row.addWidget(self.update_status, 1)

        self.release_button = QPushButton("Open release page")
        self.release_button.setObjectName("actionButton")
        self.release_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.release_button.clicked.connect(self._open_release_page)
        self.release_button.hide()
        update_row.addWidget(self.release_button)

        self.check_button = QPushButton("Check for updates")
        self.check_button.setObjectName("quietButton")
        self.check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_button.clicked.connect(self.check_for_updates)
        update_row.addWidget(self.check_button)
        card_layout.addLayout(update_row)

        layout.addWidget(card)
        layout.addStretch(1)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.auto_check_updates and not self._checked_for_updates:
            self._checked_for_updates = True
            QTimer.singleShot(0, self.check_for_updates)

    def check_for_updates(self) -> None:
        """Ask GitHub for the latest release without blocking the window."""
        if self._update_reply is not None:
            return
        self._checked_for_updates = True
        self.update_status.setToolTip("")
        self.update_status.setText("Checking GitHub Releases…")
        self.check_button.setEnabled(False)
        self.release_button.hide()

        request = QNetworkRequest(QUrl(LATEST_RELEASE_API))
        request.setTransferTimeout(UPDATE_TIMEOUT_MS)
        request.setRawHeader(b"User-Agent", UPDATE_USER_AGENT.encode("ascii"))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        self._update_reply = self._update_manager.get(request)
        self._update_reply.finished.connect(self._finish_update_check)

    def _finish_update_check(self) -> None:
        reply = self._update_reply
        if reply is None:
            return
        self._update_reply = None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError(reply.errorString())
            payload = json.loads(bytes(reply.readAll().data()).decode("utf-8"))
            release = parse_release(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._show_update_error(str(exc))
        else:
            self._show_update(release)
        finally:
            self.check_button.setEnabled(True)
            reply.deleteLater()

    def _show_update(self, release: ReleaseInfo) -> None:
        self._latest_release = release
        if is_newer(release.version, __version__):
            self.update_status.setText(f"Version {release.version} is available.")
            self.release_button.setText(f"Get {release.version}")
            self.release_button.show()
            return
        self.update_status.setText(f"You're up to date on version {__version__}.")
        self.release_button.hide()

    def _show_update_error(self, message: str) -> None:
        self._latest_release = None
        self.update_status.setText("Could not check for updates. Try again later.")
        self.update_status.setToolTip(message)
        self.release_button.hide()

    def _open_release_page(self) -> None:
        url = self._latest_release.url if self._latest_release is not None else RELEASES_PAGE
        QDesktopServices.openUrl(QUrl(url))
