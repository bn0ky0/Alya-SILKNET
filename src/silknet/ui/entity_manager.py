"""Entity list and editing dialogs."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from silknet.core.enums import EntityType, VerificationStatus
from silknet.core.exceptions import ValidationError
from silknet.core.models import Entity
from silknet.services.entity_service import EntityService
from silknet.services.platform_service import BUILTIN_PLATFORMS, PlatformService
from silknet.services.profile_image_service import ProfileImageService
from silknet.services.source_service import SourceService
from silknet.ui.assets import rounded_photo
from silknet.ui.pages import PageHeader
from silknet.ui.platform_icons import platform_badge_pixmap, platform_icon
from silknet.ui.source_widgets import SourcePicker
from silknet.ui.theme import active_theme_colors
from silknet.ui.widgets import SUBTITLE_ROLE, ComboBox, EntityItemDelegate

_ENTITY_LABELS = {
    EntityType.PERSON.value: "Person",
    EntityType.SOCIAL_PROFILE.value: "Social profile",
    EntityType.ORGANIZATION.value: "Organization",
    EntityType.WEBSITE.value: "Website or domain",
    EntityType.EMAIL.value: "Email address",
    EntityType.PHONE.value: "Phone number",
    EntityType.LOCATION.value: "Location",
    EntityType.DOCUMENT.value: "Document",
}

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _image_path_from_mime(mime) -> Path | None:
    """Return the first local image file offered by a drag operation."""
    if not mime.hasUrls():
        return None
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        try:
            if path.is_file() and path.suffix.casefold() in _IMAGE_SUFFIXES:
                return path
        except OSError:
            continue
    return None


class ImageDropLabel(QLabel):
    """Picture control that accepts image files dragged from Explorer."""

    image_dropped = Signal(object)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._drop_active = False
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if _image_path_from_mime(event.mimeData()) is not None:
            self._drop_active = True
            self.update()
            event.acceptProposedAction()
        else:
            self._drop_active = False
            self.update()
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if _image_path_from_mime(event.mimeData()) is not None:
            self._drop_active = True
            self.update()
            event.acceptProposedAction()
        else:
            self._drop_active = False
            self.update()
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._drop_active = False
        self.update()
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API name
        path = _image_path_from_mime(event.mimeData())
        self._drop_active = False
        self.update()
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.image_dropped.emit(path)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().paintEvent(event)
        if not self._drop_active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(active_theme_colors().get("accent", "#2E7CF0"))
        fill = QColor(accent)
        fill.setAlpha(38)
        pen = QPen(accent, 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 13, 13)
        painter.end()


_TYPE_COLORS = {
    EntityType.PERSON.value: "#7C9CF5",
    EntityType.SOCIAL_PROFILE.value: "#56B6C2",
    EntityType.ORGANIZATION.value: "#E0A458",
    EntityType.WEBSITE.value: "#6FA8DC",
    EntityType.EMAIL.value: "#B48EAD",
    EntityType.PHONE.value: "#7FB77E",
    EntityType.LOCATION.value: "#E07A5F",
    EntityType.DOCUMENT.value: "#D4A373",
}


def _entity_type_icon(entity_type: str) -> QIcon:
    """Draw a soft type badge so photo-less rows keep the same alignment."""
    color = QColor(_TYPE_COLORS.get(entity_type, "#8A8792"))
    pixmap = QPixmap(72, 72)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(2.0)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(2.0, 2.0)
    background = QColor(color)
    background.setAlpha(38)
    border = QColor(color)
    border.setAlpha(105)
    painter.setPen(QPen(border, 1.1))
    painter.setBrush(background)
    painter.drawRoundedRect(QRectF(2.5, 2.5, 31, 31), 10, 10)

    painter.setPen(
        QPen(
            color,
            1.8,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if entity_type == EntityType.PERSON.value:
        painter.drawEllipse(QRectF(14, 9, 8, 8))
        path = QPainterPath()
        path.moveTo(8, 28)
        path.cubicTo(9, 21, 13, 19.5, 18, 19.5)
        path.cubicTo(23, 19.5, 27, 21, 28, 28)
        painter.drawPath(path)
    elif entity_type == EntityType.ORGANIZATION.value:
        painter.drawRoundedRect(QRectF(10, 8.5, 16, 19.5), 2, 2)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        for x in (13, 18, 23):
            for y in (13, 17.5):
                painter.drawRect(QRectF(x, y, 2.2, 2.2))
        painter.drawRoundedRect(QRectF(16.2, 23, 3.6, 5), 1, 1)
    elif entity_type in {EntityType.SOCIAL_PROFILE.value, EntityType.WEBSITE.value}:
        painter.drawEllipse(QRectF(8.5, 8.5, 19, 19))
        painter.drawEllipse(QRectF(13, 8.5, 10, 19))
        painter.drawLine(8, 18, 28, 18)
    elif entity_type == EntityType.EMAIL.value:
        painter.drawRoundedRect(QRectF(7.5, 11, 21, 15), 3, 3)
        path = QPainterPath()
        path.moveTo(8.5, 12.5)
        path.lineTo(18, 20)
        path.lineTo(27.5, 12.5)
        painter.drawPath(path)
    elif entity_type == EntityType.PHONE.value:
        painter.drawRoundedRect(QRectF(11.5, 7.5, 13, 21), 4, 4)
        painter.drawLine(15, 24, 21, 24)
        painter.drawEllipse(QRectF(17, 10.5, 2, 2))
    elif entity_type == EntityType.LOCATION.value:
        path = QPainterPath()
        path.moveTo(18, 28)
        path.cubicTo(13, 22, 9.5, 18.5, 9.5, 15)
        path.cubicTo(9.5, 10.3, 13.3, 7, 18, 7)
        path.cubicTo(22.7, 7, 26.5, 10.3, 26.5, 15)
        path.cubicTo(26.5, 18.5, 23, 22, 18, 28)
        painter.drawPath(path)
        painter.drawEllipse(QRectF(15, 12, 6, 6))
    elif entity_type == EntityType.DOCUMENT.value:
        path = QPainterPath()
        path.moveTo(11, 7)
        path.lineTo(21, 7)
        path.lineTo(26, 12)
        path.lineTo(26, 29)
        path.lineTo(11, 29)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(21, 7, 21, 12)
        painter.drawLine(21, 12, 26, 12)
        painter.drawLine(14, 17, 23, 17)
        painter.drawLine(14, 21, 23, 21)
        painter.drawLine(14, 25, 20, 25)
    else:
        path = QPainterPath()
        path.moveTo(18, 7.5)
        path.cubicTo(19.5, 14.5, 21.5, 16.5, 28.5, 18)
        path.cubicTo(21.5, 19.5, 19.5, 21.5, 18, 28.5)
        path.cubicTo(16.5, 21.5, 14.5, 19.5, 7.5, 18)
        path.cubicTo(14.5, 16.5, 16.5, 14.5, 18, 7.5)
        painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


class EntityRecordDialog(QDialog):
    def __init__(
        self,
        service: EntityService,
        entity: Entity | None = None,
        parent: QWidget | None = None,
        *,
        image_service: ProfileImageService | None = None,
        platform_service: PlatformService | None = None,
        source_service: SourceService | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.entity = entity
        self.image_service = image_service
        self.platform_service = platform_service
        self.source_service = source_service
        self.saved_entity: Entity | None = None
        self._selected_image_source: Path | None = None
        self._stored_image_path: Path | None = None
        self._remove_image = False
        self._existing_image_path = (
            str(entity.attributes.get("profile_image_path", "")) if entity else ""
        )
        self.setWindowTitle("Edit entity" if entity else "Add entity")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        heading = QLabel("Edit entity" if entity else "Add an entity")
        heading.setObjectName("dialogHeading")
        help_text = QLabel("Add the details you have. You can update this record later.")
        help_text.setObjectName("cardDescription")
        help_text.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(help_text)

        form_host = QWidget()
        form_host.setAutoFillBackground(False)
        form = QFormLayout(form_host)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(11)
        self.type_field = ComboBox()
        for key, label in _ENTITY_LABELS.items():
            self.type_field.addItem(label, key)
        for entity_type in self.service.list_custom_types():
            self.type_field.addItem(entity_type.display_name, entity_type.key)
        self.name_field = QLineEdit()
        self.name_field.setMaxLength(256)
        self.name_field.setPlaceholderText("Name or identifying label")
        self.role_field = QLineEdit()
        self.role_field.setMaxLength(128)
        self.role_field.setPlaceholderText("Optional, e.g. analyst, founder or witness")

        self.profile_image_preview = ImageDropLabel("No image")
        self.profile_image_preview.setObjectName("imagePreview")
        self.profile_image_preview.setFixedSize(84, 84)
        self.profile_image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.profile_image_preview.setWordWrap(True)
        self.profile_image_preview.setToolTip(
            "Drop a PNG, JPEG, WebP or BMP image here, or choose one. "
            "Images are copied to SILKNET's local data folder."
        )
        self.profile_image_preview.image_dropped.connect(self._use_dropped_image)
        self.choose_image_button = QPushButton("Choose image")
        self.choose_image_button.setObjectName("quietButton")
        self.choose_image_button.clicked.connect(self._choose_profile_image)
        self.remove_image_button = QPushButton("Remove")
        self.remove_image_button.setObjectName("quietButton")
        self.remove_image_button.clicked.connect(self._remove_profile_image)
        image_row = QHBoxLayout()
        image_row.addWidget(self.profile_image_preview)
        image_row.addWidget(self.choose_image_button)
        image_row.addWidget(self.remove_image_button)
        image_row.addStretch(1)
        image_widget = QWidget()
        image_widget.setLayout(image_row)

        self.social_profile_widget = QWidget()
        social_form = QFormLayout(self.social_profile_widget)
        social_form.setContentsMargins(0, 0, 0, 0)
        self.platform_field = ComboBox()
        self.platform_field.setPlaceholderText("Choose a platform")
        self.platform_field.addItem("Choose a platform", "")
        platform_options = (
            platform_service.list() if platform_service is not None else list(BUILTIN_PLATFORMS)
        )
        for option in platform_options:
            self.platform_field.addItem(option, option)
        self.platform_field.addItem("Other…", "__other__")
        self.custom_platform_field = QLineEdit()
        self.custom_platform_field.setPlaceholderText("Enter the platform name")
        self.custom_platform_field.setVisible(False)
        self.platform_mark = QLabel()
        self.platform_mark.setObjectName("platformMark")
        self.platform_mark.setFixedSize(36, 36)
        self.platform_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.platform_mark.setPixmap(platform_badge_pixmap("", 28))
        platform_row = QHBoxLayout()
        platform_row.addWidget(self.platform_field, 1)
        platform_row.addWidget(self.platform_mark)
        platform_widget = QWidget()
        platform_widget.setLayout(platform_row)
        self.profile_url_field = QLineEdit()
        self.profile_url_field.setPlaceholderText("https://...")
        self.username_field = QLineEdit()
        self.username_field.setPlaceholderText("Optional handle")
        self.profile_status_field = ComboBox()
        for status in VerificationStatus:
            self.profile_status_field.addItem(status.value.replace("_", " ").title(), status.value)
        self.profile_status_field.setCurrentIndex(
            self.profile_status_field.findData(VerificationStatus.UNVERIFIED.value)
        )
        self.open_profile_button = QPushButton("Open URL")
        self.open_profile_button.setObjectName("quietButton")
        self.open_profile_button.clicked.connect(self._open_profile_url)
        profile_url_row = QHBoxLayout()
        profile_url_row.addWidget(self.profile_url_field, 1)
        profile_url_row.addWidget(self.open_profile_button)
        profile_url_widget = QWidget()
        profile_url_widget.setLayout(profile_url_row)
        self.profile_identity_note = QLabel(
            "A valid URL does not confirm who controls the account."
        )
        self.profile_identity_note.setObjectName("subtleText")
        self.profile_identity_note.setWordWrap(True)
        social_form.addRow("Platform", platform_widget)
        social_form.addRow("Custom platform", self.custom_platform_field)
        self.custom_platform_label = social_form.labelForField(self.custom_platform_field)
        if self.custom_platform_label is not None:
            self.custom_platform_label.setVisible(False)
        social_form.addRow("Profile URL", profile_url_widget)
        social_form.addRow("Username", self.username_field)
        social_form.addRow("Verification", self.profile_status_field)
        social_form.addRow(self.profile_identity_note)
        self.aliases_field = QLineEdit()
        self.aliases_field.setPlaceholderText("Separate aliases with commas")
        self.tags_field = QLineEdit()
        self.tags_field.setPlaceholderText("Separate tags with commas")
        self.attributes_field = QTextEdit()
        self.attributes_field.setMaximumHeight(82)
        self.attributes_field.setPlaceholderText('{"field_name": "value"}')
        self.attributes_field.setPlainText("{}")
        self.description_field = QTextEdit()
        self.description_field.setMaximumHeight(78)
        self.notes_field = QTextEdit()
        self.notes_field.setMaximumHeight(92)
        self.source_picker = SourcePicker(
            source_service.list() if source_service is not None else [],
            entity.source_ids if entity is not None else (),
        )
        self.source_picker.setVisible(source_service is not None)
        form.addRow("Type", self.type_field)
        form.addRow("Name", self.name_field)
        form.addRow("Role", self.role_field)
        form.addRow("Profile image", image_widget)
        form.addRow("Social profile", self.social_profile_widget)
        self.role_label = form.labelForField(self.role_field)
        self.profile_image_label = form.labelForField(image_widget)
        self.social_profile_label = form.labelForField(self.social_profile_widget)
        form.addRow("Aliases", self.aliases_field)
        form.addRow("Tags", self.tags_field)
        form.addRow("Attributes (JSON)", self.attributes_field)
        form.addRow("Description", self.description_field)
        form.addRow("Notes", self.notes_field)
        form.addRow("Evidence sources", self.source_picker)
        source_label = form.labelForField(self.source_picker)
        if source_label is not None:
            source_label.setVisible(source_service is not None)
        self.form_scroll = QScrollArea()
        self.form_scroll.setObjectName("dialogFormScroll")
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.form_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.form_scroll.setMinimumHeight(220)
        self.form_scroll.viewport().setAutoFillBackground(False)
        self.form_scroll.setWidget(form_host)
        layout.addWidget(self.form_scroll, 1)
        self.type_field.currentIndexChanged.connect(self._update_type_fields)
        self.platform_field.currentIndexChanged.connect(self._update_platform_preview)
        self.custom_platform_field.textChanged.connect(self._update_platform_preview)
        self._update_type_fields()
        self._update_platform_preview()

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        if entity is not None:
            index = self.type_field.findData(entity.entity_type)
            if index >= 0:
                self.type_field.setCurrentIndex(index)
            self.name_field.setText(entity.name)
            self.aliases_field.setText(", ".join(entity.aliases))
            self.tags_field.setText(", ".join(entity.tags))
            visible_attributes = dict(entity.attributes)
            for key in (
                "profile_image_path",
                "platform",
                "profile_url",
                "username",
                "verification_status",
            ):
                visible_attributes.pop(key, None)
            attributes = entity.attributes
            if entity.entity_type == EntityType.PERSON.value:
                visible_attributes.pop("role", None)
                self.role_field.setText(str(attributes.get("role", "")))
            self.attributes_field.setPlainText(
                json.dumps(visible_attributes, ensure_ascii=False, indent=2)
            )
            self.description_field.setPlainText(entity.description)
            self.notes_field.setPlainText(entity.notes)
            self._select_platform(str(attributes.get("platform", "")))
            self.profile_url_field.setText(str(attributes.get("profile_url", "")))
            self.username_field.setText(str(attributes.get("username", "")))
            status = str(attributes.get("verification_status", "unverified"))
            status_index = self.profile_status_field.findData(status)
            if status_index < 0:
                status_index = self.profile_status_field.findText(status.replace("_", " ").title())
            if status_index >= 0:
                self.profile_status_field.setCurrentIndex(status_index)
            self._show_existing_image()
        self._update_type_fields()
        hint = self.sizeHint()
        screen = QApplication.primaryScreen()
        available_height = 680
        if screen is not None:
            available_height = max(420, screen.availableGeometry().height() - 80)
        target_width = max(560, min(800, hint.width() + 24))
        target_height = min(max(hint.height(), 660), available_height)
        self.resize(target_width, max(420, target_height))

    def _update_type_fields(self, *_args) -> None:
        entity_type = self.type_field.currentData()
        is_person = entity_type == EntityType.PERSON.value
        self.social_profile_widget.setVisible(entity_type == EntityType.SOCIAL_PROFILE.value)
        self.role_field.setVisible(is_person)
        social_label = getattr(self, "social_profile_label", None)
        if social_label is not None:
            social_label.setVisible(entity_type == EntityType.SOCIAL_PROFILE.value)
        role_label = getattr(self, "role_label", None)
        if role_label is not None:
            role_label.setVisible(is_person)

    def _select_platform(self, platform: str) -> None:
        cleaned = platform.strip()
        if not cleaned:
            self.platform_field.setCurrentIndex(0)
            return
        index = self.platform_field.findText(cleaned, Qt.MatchFlag.MatchFixedString)
        if index < 0:
            other_index = self.platform_field.findData("__other__")
            index = other_index if other_index >= 0 else self.platform_field.count()
            self.platform_field.insertItem(index, cleaned, cleaned)
        self.platform_field.setCurrentIndex(index)

    def _selected_platform(self) -> str:
        if self.platform_field.currentData() == "__other__":
            return self.custom_platform_field.text().strip()
        value = self.platform_field.currentData()
        return str(value).strip() if value else ""

    def _update_platform_preview(self, *_args) -> None:
        custom = self.platform_field.currentData() == "__other__"
        self.custom_platform_field.setVisible(custom)
        label = getattr(self, "custom_platform_label", None)
        if label is not None:
            label.setVisible(custom)
        self.platform_mark.setPixmap(platform_badge_pixmap(self._selected_platform(), 28))

    def _choose_profile_image(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose profile image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not filename:
            return
        self._use_dropped_image(Path(filename))

    def _use_dropped_image(self, image_file: Path) -> None:
        if self.image_service is None:
            QMessageBox.information(
                self, "Profile image storage unavailable", "Image storage is not configured."
            )
            return
        try:
            image = self.image_service.read_image(image_file)
        except ValidationError as exc:
            QMessageBox.warning(self, "Image could not be used", str(exc))
            return
        self._selected_image_source = image_file
        self._remove_image = False
        self._show_image(image)

    def _show_existing_image(self) -> None:
        if not self._existing_image_path or self.image_service is None:
            return
        try:
            image = self.image_service.read_image(Path(self._existing_image_path))
        except (OSError, ValidationError):
            return
        self._show_image(image)

    def _show_image(self, image) -> None:
        self.profile_image_preview.setText("")
        self.profile_image_preview.setPixmap(rounded_photo(image, 84, 0.30))

    def _remove_profile_image(self) -> None:
        self._selected_image_source = None
        self._remove_image = True
        self.profile_image_preview.setPixmap(QPixmap())
        self.profile_image_preview.setText("No image")

    def _open_profile_url(self) -> None:
        from silknet.core.validation import clean_url

        try:
            url = clean_url(self.profile_url_field.text())
        except ValidationError as exc:
            QMessageBox.warning(self, "Profile URL is not valid", str(exc))
            return
        if url and not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "Could not open URL", "Windows could not open this address.")

    def _save(self) -> None:
        try:
            attributes = json.loads(self.attributes_field.toPlainText() or "{}")
        except JSONDecodeError as exc:
            QMessageBox.warning(
                self,
                "Entity could not be saved",
                f"Attributes must be valid JSON: {exc.msg}.",
            )
            return
        if not isinstance(attributes, dict):
            QMessageBox.warning(
                self, "Entity could not be saved", "Attributes must be a JSON object."
            )
            return
        entity_type = self.type_field.currentData()
        if entity_type == EntityType.PERSON.value:
            role = self.role_field.text().strip()
            if role:
                attributes["role"] = role
            else:
                attributes.pop("role", None)
        if entity_type == EntityType.SOCIAL_PROFILE.value:
            platform = self._selected_platform()
            if not platform:
                QMessageBox.warning(
                    self,
                    "Platform is required",
                    "Choose a platform, or pick Other and enter its name.",
                )
                return
            attributes.update(
                {
                    "platform": platform,
                    "profile_url": self.profile_url_field.text(),
                    "username": self.username_field.text(),
                    "verification_status": self.profile_status_field.currentData(),
                }
            )
            if self.platform_service is not None:
                try:
                    self.platform_service.add(platform)
                except ValidationError as exc:
                    QMessageBox.warning(self, "Profile could not be saved", str(exc))
                    return
        else:
            for key in ("platform", "profile_url", "username", "verification_status"):
                attributes.pop(key, None)
        if self._selected_image_source is not None and self.image_service is not None:
            try:
                self._stored_image_path = self.image_service.store(self._selected_image_source)
                attributes["profile_image_path"] = str(self._stored_image_path)
            except ValidationError as exc:
                QMessageBox.warning(self, "Profile image could not be saved", str(exc))
                return
        elif self._remove_image:
            attributes.pop("profile_image_path", None)
        elif self._existing_image_path:
            attributes["profile_image_path"] = self._existing_image_path
        values = {
            "entity_type": entity_type,
            "name": self.name_field.text(),
            "aliases": _split_values(self.aliases_field.text()),
            "tags": _split_values(self.tags_field.text()),
            "attributes": attributes,
            "description": self.description_field.toPlainText(),
            "notes": self.notes_field.toPlainText(),
            "source_ids": (
                self.source_picker.selected_ids()
                if self.source_service is not None
                else (self.entity.source_ids if self.entity is not None else ())
            ),
        }
        try:
            if self.entity is None:
                self.saved_entity = self.service.create(**values)
            else:
                self.saved_entity = self.service.update(self.entity.id, **values)
        except (ValidationError, LookupError) as exc:
            if self._stored_image_path is not None and self.image_service is not None:
                self.image_service.discard(self._stored_image_path)
                self._stored_image_path = None
            QMessageBox.warning(self, "Entity could not be saved", str(exc))
            return
        except DatabaseError as exc:
            if self._stored_image_path is not None and self.image_service is not None:
                self.image_service.discard(self._stored_image_path)
                self._stored_image_path = None
            QMessageBox.critical(
                self,
                "Database error",
                f"The entity could not be saved to the local database: {exc}",
            )
            return
        if self.image_service is not None and self._existing_image_path and self.saved_entity:
            saved_image = str(self.saved_entity.attributes.get("profile_image_path", ""))
            if saved_image != self._existing_image_path:
                self.image_service.discard(Path(self._existing_image_path))
        self.accept()


class CustomEntityTypeDialog(QDialog):
    def __init__(self, service: EntityService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.saved_type = None
        self.setWindowTitle("Create custom entity type")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(13)
        heading = QLabel("Create a custom type")
        heading.setObjectName("dialogHeading")
        help_text = QLabel(
            "Define optional fields as a JSON array. Supported field types: text, number, date, "
            "boolean, and url."
        )
        help_text.setObjectName("cardDescription")
        help_text.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(help_text)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.key_field = QLineEdit()
        self.key_field.setPlaceholderText("vehicle")
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("Vehicle")
        self.fields_field = QTextEdit()
        self.fields_field.setMaximumHeight(160)
        self.fields_field.setPlainText(
            '[\n  {"key": "registration", "display_name": "Registration", '
            '"field_type": "text", "required": false}\n]'
        )
        form.addRow("Type key", self.key_field)
        form.addRow("Display name", self.name_field)
        form.addRow("Fields (JSON)", self.fields_field)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        try:
            fields = json.loads(self.fields_field.toPlainText() or "[]")
        except JSONDecodeError as exc:
            QMessageBox.warning(
                self,
                "Custom type could not be saved",
                f"Fields must be valid JSON: {exc.msg}.",
            )
            return
        if not isinstance(fields, list):
            QMessageBox.warning(
                self,
                "Custom type could not be saved",
                "Fields must be a JSON array.",
            )
            return
        try:
            self.saved_type = self.service.create_custom_type(
                key=self.key_field.text(),
                display_name=self.name_field.text(),
                fields=fields,
            )
        except (ValidationError, LookupError) as exc:
            QMessageBox.warning(self, "Custom type could not be saved", str(exc))
            return
        except DatabaseError as exc:
            QMessageBox.critical(
                self,
                "Database error",
                f"The custom type could not be saved to the local database: {exc}",
            )
            return
        self.accept()


class EntityManagerPage(QWidget):
    records_changed = Signal()
    message = Signal(str)

    def __init__(
        self,
        service: EntityService,
        image_service: ProfileImageService | None = None,
        platform_service: PlatformService | None = None,
        source_service: SourceService | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.image_service = image_service
        self.platform_service = platform_service
        self.source_service = source_service
        self._entities: dict[str, Entity] = {}
        self._type_labels = dict(_ENTITY_LABELS)
        self._details_animation: QPropertyAnimation | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(
            PageHeader(
                "Records",
                "Entities",
                "People, organizations, profiles and other records saved in this workspace.",
                compact=True,
                inline=True,
            )
        )

        toolbar = QHBoxLayout()
        self.count_label = QLabel("0 records")
        self.count_label.setObjectName("subtleText")
        toolbar.addWidget(self.count_label)
        toolbar.addStretch(1)
        self.edit_button = QPushButton("Edit")
        self.edit_button.setObjectName("quietButton")
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._delete_selected)
        self.add_type_button = QPushButton("New type")
        self.add_type_button.setObjectName("quietButton")
        self.add_type_button.clicked.connect(self._add_custom_type)
        self.add_button = QPushButton("Add record")
        self.add_button.setObjectName("actionButton")
        self.add_button.clicked.connect(self._add_entity)
        toolbar.addWidget(self.edit_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.add_type_button)
        toolbar.addWidget(self.add_button)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.entity_list = QListWidget()
        self.entity_list.setObjectName("entityList")
        self.entity_list.setAccessibleName("Entities in this workspace")
        self.entity_list.setMinimumWidth(300)
        self.entity_list.setIconSize(QSize(38, 38))
        self.entity_list.setSpacing(2)
        self.entity_list.setMouseTracking(True)
        self.entity_list.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.entity_list.setItemDelegate(
            EntityItemDelegate(self.entity_list, row_height=58, icon_size=38)
        )
        self.entity_list.currentItemChanged.connect(self._show_selected)
        self.entity_list.itemDoubleClicked.connect(lambda _item: self._edit_selected())

        self.empty_list = QWidget()
        empty_layout = QVBoxLayout(self.empty_list)
        empty_layout.setContentsMargins(18, 18, 18, 18)
        empty_layout.addStretch(1)
        empty_title = QLabel("No records yet")
        empty_title.setObjectName("emptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_copy = QLabel("Your records will appear here.")
        empty_copy.setObjectName("emptyDescription")
        empty_copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_add = QPushButton("Add your first record")
        empty_add.setObjectName("actionButton")
        empty_add.clicked.connect(self._add_entity)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_copy)
        empty_layout.addSpacing(12)
        empty_layout.addWidget(empty_add, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addStretch(1)

        self.entity_stack = QStackedWidget()
        self.entity_stack.setObjectName("entityStack")
        self.entity_stack.setMinimumWidth(300)
        self.entity_stack.addWidget(self.entity_list)
        self.entity_stack.addWidget(self.empty_list)
        splitter.addWidget(self.entity_stack)

        self.details = QFrame()
        self.details.setObjectName("entityDetails")
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(22, 18, 22, 18)
        detail_layout.setSpacing(10)
        self.detail_type = QLabel("Record")
        self.detail_type.setObjectName("detailChip")
        self.detail_type.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.detail_type.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.detail_name = QLabel("No entity selected")
        self.detail_name.setObjectName("entityDetailName")
        self.detail_name.setWordWrap(True)
        self.detail_avatar = ImageDropLabel()
        self.detail_avatar.setObjectName("detailAvatar")
        self.detail_avatar.setFixedSize(92, 92)
        self.detail_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_avatar.setToolTip("Drop a PNG, JPEG, WebP or BMP image to update this photo.")
        self.detail_avatar.setVisible(False)
        self.detail_avatar.image_dropped.connect(self._drop_avatar_image)
        self.detail_avatar.installEventFilter(self)
        self.detail_description = QLabel(
            "Choose a record from the list, or add one to get started."
        )
        self.detail_description.setObjectName("pageDescription")
        self.detail_description.setWordWrap(True)
        self.detail_social = QLabel("")
        self.detail_social.setObjectName("detailSocial")
        self.detail_social.setWordWrap(True)
        self.detail_social.setVisible(False)
        self.detail_aliases = QLabel("")
        self.detail_tags = QLabel("")
        self.detail_attributes = QLabel("")
        self.detail_notes = QLabel("")
        for label in (
            self.detail_aliases,
            self.detail_tags,
            self.detail_attributes,
            self.detail_notes,
        ):
            label.setObjectName("mutedText")
            label.setWordWrap(True)
        title_column = QVBoxLayout()
        title_column.setContentsMargins(0, 0, 0, 0)
        title_column.setSpacing(3)
        title_column.addWidget(self.detail_type, alignment=Qt.AlignmentFlag.AlignLeft)
        title_column.addWidget(self.detail_name)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(14)
        header_row.addWidget(self.detail_avatar, alignment=Qt.AlignmentFlag.AlignTop)
        header_row.addLayout(title_column, 1)
        detail_layout.addLayout(header_row)
        detail_layout.addWidget(self.detail_description)
        detail_layout.addWidget(self.detail_social)
        detail_layout.addWidget(self.detail_aliases)
        detail_layout.addWidget(self.detail_tags)
        detail_layout.addWidget(self.detail_attributes)
        detail_layout.addWidget(self.detail_notes)
        detail_layout.addStretch(1)
        splitter.addWidget(self.details)
        splitter.setSizes([360, 900])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self._detail_entity_id: str | None = None
        self.refresh_entities()

    def refresh_entities(self, selected_id: str | None = None) -> None:
        if selected_id is None:
            current = self.entity_list.currentItem()
            if current is not None:
                selected_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            entities = self.service.list()
            custom_types = self.service.list_custom_types()
        except DatabaseError as exc:
            QMessageBox.critical(
                self,
                "Database error",
                f"Entities could not be loaded from the local database: {exc}",
            )
            return
        self._entities = {entity.id: entity for entity in entities}
        self._type_labels = {
            **_ENTITY_LABELS,
            **{item.key: item.display_name for item in custom_types},
        }
        self.entity_list.clear()
        for entity in entities:
            item = QListWidgetItem(entity.name)
            item.setData(Qt.ItemDataRole.UserRole, entity.id)
            subtitle = self._entity_label(entity.entity_type)
            role = str(entity.attributes.get("role", "")).strip()
            if entity.entity_type == EntityType.PERSON.value and role:
                subtitle = f"Person · {role}"
            item.setData(SUBTITLE_ROLE, subtitle)
            icon = self._entity_icon(entity)
            if icon is not None:
                item.setIcon(icon)
            item.setToolTip(entity.name)
            item.setSizeHint(QSize(0, 58))
            self.entity_list.addItem(item)
        self.entity_stack.setCurrentWidget(self.entity_list if entities else self.empty_list)
        count = len(entities)
        custom_type_count = len(custom_types)
        self.count_label.setText(
            f"{count} record{'s' if count != 1 else ''}  ·  "
            f"{custom_type_count} custom type{'s' if custom_type_count != 1 else ''}"
        )
        if selected_id:
            for index in range(self.entity_list.count()):
                item = self.entity_list.item(index)
                if item.data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.entity_list.setCurrentItem(item)
                    self.entity_list.scrollToItem(item)
                    break
        if self.entity_list.currentItem() is None and self.entity_list.count():
            self.entity_list.setCurrentRow(0)
        elif not entities:
            self._show_empty()

    def select_entity(self, entity_id: str) -> None:
        for index in range(self.entity_list.count()):
            item = self.entity_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == entity_id:
                self.entity_list.setCurrentItem(item)
                return

    def _add_entity(self) -> None:
        dialog = EntityRecordDialog(
            self.service,
            parent=self,
            image_service=self.image_service,
            platform_service=self.platform_service,
            source_service=self.source_service,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_entity:
            self.refresh_entities(dialog.saved_entity.id)
            self._pulse_details()
            self.records_changed.emit()

    def _add_custom_type(self) -> None:
        dialog = CustomEntityTypeDialog(self.service, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_type:
            self.refresh_entities()
            self.records_changed.emit()

    def _edit_selected(self) -> None:
        entity = self._selected_entity()
        if entity is None:
            return
        dialog = EntityRecordDialog(
            self.service,
            entity,
            self,
            image_service=self.image_service,
            platform_service=self.platform_service,
            source_service=self.source_service,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_entity:
            self.refresh_entities(dialog.saved_entity.id)
            self._pulse_details()
            self.records_changed.emit()

    def _confirm_delete(self, entity: Entity) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Delete entity?")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            f"Delete '{entity.name}'? Relationships attached to this entity will also be removed."
        )
        delete_button = box.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_button)
        box.setEscapeButton(cancel_button)
        box.exec()
        return box.clickedButton() is delete_button

    def _delete_selected(self) -> None:
        entity = self._selected_entity()
        if entity is None:
            return
        if not self._confirm_delete(entity):
            return
        row = self.entity_list.currentRow()
        image_path = str(entity.attributes.get("profile_image_path", ""))
        try:
            deleted = self.service.delete(entity.id)
        except DatabaseError as exc:
            QMessageBox.critical(self, "Database error", f"The entity could not be deleted: {exc}")
            return
        if not deleted:
            QMessageBox.warning(
                self,
                "Record not found",
                "This record was already removed from the workspace.",
            )
            self.refresh_entities()
            return
        if image_path and self.image_service is not None:
            try:
                self.image_service.discard(Path(image_path))
            except OSError:
                pass
        self.refresh_entities()
        if self.entity_list.count():
            self.entity_list.setCurrentRow(min(row, self.entity_list.count() - 1))
        self._pulse_details()
        self.records_changed.emit()
        self.message.emit("Record deleted")

    def _entity_icon(self, entity: Entity) -> QIcon | None:
        image_path = str(entity.attributes.get("profile_image_path", ""))
        if image_path:
            pixmap = rounded_photo(Path(image_path), 36, 0.34)
            if not pixmap.isNull():
                return QIcon(pixmap)
        if entity.entity_type == EntityType.SOCIAL_PROFILE.value:
            return platform_icon(entity.attributes.get("platform", ""))
        return _entity_type_icon(entity.entity_type)

    def _pulse_details(self) -> None:
        if self._details_animation is not None:
            self._details_animation.stop()
            self._details_animation = None
        effect = QGraphicsOpacityEffect(self.details)
        effect.setOpacity(0.35)
        self.details.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(220)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def finish() -> None:
            self.details.setGraphicsEffect(None)
            self._details_animation = None

        animation.finished.connect(finish)
        self._details_animation = animation
        animation.start()

    def _show_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        entity_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        entity = self._entities.get(entity_id) if entity_id else None
        self.edit_button.setEnabled(entity is not None)
        self.delete_button.setEnabled(entity is not None)
        if entity is None:
            self._detail_entity_id = None
            self._show_empty()
            return
        changed = entity.id != self._detail_entity_id
        self._detail_entity_id = entity.id
        social = entity.entity_type == EntityType.SOCIAL_PROFILE.value
        platform = str(entity.attributes.get("platform", "")).strip()
        label = self._entity_label(entity.entity_type)
        role = str(entity.attributes.get("role", "")).strip()
        if social and platform:
            label = f"{label} · {platform}"
        elif entity.entity_type == EntityType.PERSON.value and role:
            label = f"{label} · {role}"
        self.detail_type.setText(label)
        self.detail_name.setText(entity.name)
        self.detail_description.setText(entity.description or "No description recorded.")
        self.detail_aliases.setText(
            f"Aliases: {', '.join(entity.aliases)}" if entity.aliases else ""
        )
        self.detail_tags.setText(f"Tags: {', '.join(entity.tags)}" if entity.tags else "")
        self.detail_aliases.setVisible(bool(entity.aliases))
        self.detail_tags.setVisible(bool(entity.tags))
        self._render_detail_avatar(entity)
        social_lines = []
        if social:
            if platform:
                social_lines.append(f"{platform} profile")
            username = str(entity.attributes.get("username", "")).strip()
            if username:
                social_lines.append(username)
            profile_url = str(entity.attributes.get("profile_url", "")).strip()
            if profile_url:
                social_lines.append(profile_url)
            status = str(entity.attributes.get("verification_status", "")).strip()
            if status:
                social_lines.append(status.replace("_", " ").title())
        self.detail_social.setText("\n".join(social_lines))
        self.detail_social.setVisible(bool(social_lines))
        hidden = {
            "profile_image_path",
            "platform",
            "username",
            "profile_url",
            "verification_status",
        }
        if entity.entity_type == EntityType.PERSON.value:
            hidden.add("role")
        attributes = " · ".join(
            f"{key.replace('_', ' ').title()}: {value}"
            for key, value in sorted(entity.attributes.items())
            if key not in hidden
        )
        self.detail_attributes.setText(f"Fields: {attributes}" if attributes else "")
        self.detail_notes.setText(f"Notes: {entity.notes}" if entity.notes else "")
        self.detail_attributes.setVisible(bool(attributes))
        self.detail_notes.setVisible(bool(entity.notes))
        if changed:
            QTimer.singleShot(0, self._pulse_details)

    def _render_detail_avatar(self, entity: Entity) -> None:
        target = max(24, self.detail_avatar.width())
        image_path = str(entity.attributes.get("profile_image_path", ""))
        avatar = QPixmap()
        if image_path:
            avatar = rounded_photo(Path(image_path), target, 0.30)
        elif entity.entity_type == EntityType.SOCIAL_PROFILE.value:
            platform = str(entity.attributes.get("platform", "")).strip()
            avatar = platform_badge_pixmap(platform or "?", target, device_ratio=None)
        if avatar.isNull():
            avatar = self._avatar_placeholder(target)
        self.detail_avatar.setPixmap(avatar)
        self.detail_avatar.setVisible(True)

    def _avatar_placeholder(self, size: int) -> QPixmap:
        """A quiet drop target shown when the selected record has no photo."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(active_theme_colors().get("accent", "#2E7CF0"))
        border = QColor(accent)
        border.setAlpha(120)
        pen = QPen(border, 1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(2, 2, size - 4, size - 4)
        painter.drawRoundedRect(rect, 16, 16)
        painter.setPen(QPen(accent, 2))
        center = rect.center()
        arm = max(5.0, size * 0.11)
        painter.drawLine(
            QPointF(center.x() - arm, center.y()),
            QPointF(center.x() + arm, center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - arm),
            QPointF(center.x(), center.y() + arm),
        )
        painter.end()
        return pixmap

    def _drop_avatar_image(self, image_file: Path) -> None:
        entity = self._selected_entity()
        if entity is None:
            return
        if self.image_service is None:
            QMessageBox.information(
                self, "Profile image storage unavailable", "Image storage is not configured."
            )
            return
        try:
            self.image_service.read_image(image_file)
            stored = self.image_service.store(image_file)
        except ValidationError as exc:
            QMessageBox.warning(self, "Image could not be used", str(exc))
            return
        previous = str(entity.attributes.get("profile_image_path", "")).strip()
        attributes = dict(entity.attributes)
        attributes["profile_image_path"] = str(stored)
        try:
            updated = self.service.update(entity.id, attributes=attributes)
        except (ValidationError, LookupError) as exc:
            self.image_service.discard(stored)
            QMessageBox.warning(self, "Profile image could not be saved", str(exc))
            return
        except DatabaseError as exc:
            self.image_service.discard(stored)
            QMessageBox.critical(
                self,
                "Database error",
                f"The profile image could not be saved to the local database: {exc}",
            )
            return
        if previous and previous != str(stored):
            self.image_service.discard(Path(previous))
        self.refresh_entities(updated.id)
        self.records_changed.emit()
        self.message.emit("Profile image updated")

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.detail_avatar
            and event.type() == QEvent.Type.Resize
            and self._selected_entity() is not None
        ):
            self._render_detail_avatar(self._selected_entity())
        return super().eventFilter(watched, event)

    def _show_empty(self) -> None:
        self.edit_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.detail_type.setText("Records")
        self.detail_name.setText("No records yet")
        self.detail_description.setText(
            "Add a person, organization, profile, or another record to begin."
        )
        self.detail_aliases.clear()
        self.detail_tags.clear()
        self.detail_attributes.clear()
        self.detail_notes.clear()
        self.detail_aliases.setVisible(False)
        self.detail_tags.setVisible(False)
        self.detail_attributes.setVisible(False)
        self.detail_notes.setVisible(False)
        self.detail_avatar.clear()
        self.detail_avatar.setVisible(False)
        self.detail_social.clear()
        self.detail_social.setVisible(False)

    def _selected_entity(self) -> Entity | None:
        item = self.entity_list.currentItem()
        if item is None:
            return None
        return self._entities.get(item.data(Qt.ItemDataRole.UserRole))

    def _entity_label(self, entity_type: str) -> str:
        return self._type_labels.get(entity_type, entity_type.replace("_", " ").title())


def _split_values(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())
