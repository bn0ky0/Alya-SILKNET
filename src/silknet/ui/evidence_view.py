"""Source records and their links to entity and relationship claims."""

from __future__ import annotations

from sqlite3 import Error as DatabaseError

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from silknet.core.enums import SourceType
from silknet.core.exceptions import ValidationError
from silknet.core.models import Source
from silknet.services.container import ApplicationServices
from silknet.ui.pages import PageHeader
from silknet.ui.widgets import ComboBox


class SourceRecordDialog(QDialog):
    def __init__(
        self, service, source: Source | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.source = source
        self.saved_source: Source | None = None
        self.setWindowTitle("Edit source" if source else "Add source")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        heading = QLabel("Source record")
        heading.setObjectName("dialogHeading")
        description = QLabel(
            "Record where a claim came from. Saving a source does not confirm what it says."
        )
        description.setObjectName("cardDescription")
        description.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(description)
        form = QFormLayout()
        self.title_field = QLineEdit()
        self.title_field.setMaxLength(512)
        self.type_field = ComboBox()
        for source_type in SourceType:
            self.type_field.addItem(source_type.value.replace("_", " ").title(), source_type)
        self.url_field = QLineEdit()
        self.url_field.setPlaceholderText("https://...")
        self.path_field = QLineEdit()
        self.path_field.setPlaceholderText("Path to a local document")
        self.browse_button = QPushButton("Browse")
        self.browse_button.setObjectName("quietButton")
        self.browse_button.clicked.connect(self._browse_file)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_field, 1)
        path_row.addWidget(self.browse_button)
        path_widget = QWidget()
        path_widget.setLayout(path_row)
        self.observed_field = QLineEdit()
        self.observed_field.setPlaceholderText("YYYY-MM-DD")
        self.hash_field = QLineEdit()
        self.hash_field.setPlaceholderText("Optional integrity hash")
        self.notes_field = QTextEdit()
        self.notes_field.setMaximumHeight(100)
        form.addRow("Title", self.title_field)
        form.addRow("Source type", self.type_field)
        form.addRow("URL", self.url_field)
        form.addRow("Local file", path_widget)
        form.addRow("Observed date", self.observed_field)
        form.addRow("Content hash", self.hash_field)
        form.addRow("Notes", self.notes_field)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        if source is not None:
            self.title_field.setText(source.title)
            self.type_field.setCurrentIndex(self.type_field.findData(source.source_type))
            self.url_field.setText(source.url)
            self.path_field.setText(source.local_path)
            self.observed_field.setText(source.observed_at or "")
            self.hash_field.setText(source.content_hash)
            self.notes_field.setPlainText(source.notes)

    def _browse_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Select a document")
        if filename:
            self.path_field.setText(filename)
            self.type_field.setCurrentIndex(self.type_field.findData(SourceType.LOCAL_DOCUMENT))

    def _save(self) -> None:
        try:
            values = {
                "title": self.title_field.text(),
                "source_type": self.type_field.currentData(),
                "url": self.url_field.text(),
                "local_path": self.path_field.text(),
                "observed_at": self.observed_field.text() or None,
                "content_hash": self.hash_field.text(),
                "notes": self.notes_field.toPlainText(),
            }
            if self.source is None:
                self.saved_source = self.service.create(**values)
            else:
                self.saved_source = self.service.update(
                    Source(id=self.source.id, created_at=self.source.created_at, **values)
                )
        except (ValidationError, LookupError) as exc:
            QMessageBox.warning(self, "Source could not be saved", str(exc))
            return
        except DatabaseError as exc:
            QMessageBox.critical(self, "Database error", f"The source could not be saved: {exc}")
            return
        self.accept()


class EvidencePage(QWidget):
    records_changed = Signal()
    message = Signal(str)

    def __init__(self, services: ApplicationServices) -> None:
        super().__init__()
        self.services = services
        self._sources: dict[str, Source] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 30)
        layout.setSpacing(16)
        layout.addWidget(
            PageHeader(
                "Workspace",
                "Evidence & Sources",
                "Keep source details connected to the entities and claims they support.",
            )
        )
        toolbar = QHBoxLayout()
        self.count_label = QLabel("0 sources")
        self.count_label.setObjectName("subtleText")
        self.open_button = QPushButton("Open source")
        self.open_button.setObjectName("quietButton")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        self.edit_button = QPushButton("Edit")
        self.edit_button.setObjectName("quietButton")
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._delete_selected)
        self.add_button = QPushButton("Add source")
        self.add_button.setObjectName("actionButton")
        self.add_button.clicked.connect(self._add_source)
        toolbar.addWidget(self.count_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self.open_button)
        toolbar.addWidget(self.edit_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.add_button)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source_list = QListWidget()
        self.source_list.setObjectName("entityList")
        self.source_list.setAccessibleName("Sources in this workspace")
        self.source_list.setSpacing(2)
        self.source_list.currentItemChanged.connect(self._show_selected)
        self.source_list.itemDoubleClicked.connect(lambda _item: self._edit_selected())
        splitter.addWidget(self.source_list)
        self.details = QFrame()
        self.details.setObjectName("entityDetails")
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(20, 18, 20, 18)
        detail_layout.setSpacing(9)
        self.detail_type = QLabel("Source")
        self.detail_type.setObjectName("pageEyebrow")
        self.detail_title = QLabel("No source selected")
        self.detail_title.setObjectName("pageHeading")
        self.detail_copy = QLabel("Add a source to record the origin of an entity or claim.")
        self.detail_copy.setObjectName("pageDescription")
        self.detail_copy.setWordWrap(True)
        self.linked_records = QLabel()
        self.linked_records.setObjectName("cardDescription")
        self.linked_records.setWordWrap(True)
        self.detail_notes = QLabel()
        self.detail_notes.setObjectName("mutedText")
        self.detail_notes.setWordWrap(True)
        detail_layout.addWidget(self.detail_type)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_copy)
        detail_layout.addWidget(self.linked_records)
        detail_layout.addWidget(self.detail_notes)
        detail_layout.addStretch(1)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self.refresh_sources()

    def refresh_sources(self, selected_id: str | None = None) -> None:
        if selected_id is None:
            current = self.source_list.currentItem()
            if current is not None:
                selected_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            sources = self.services.sources.list()
        except DatabaseError as exc:
            QMessageBox.critical(self, "Database error", f"Sources could not be loaded: {exc}")
            return
        self._sources = {source.id: source for source in sources}
        self.source_list.clear()
        for source in sources:
            item = QListWidgetItem(
                f"{source.title}\n{source.source_type.value.replace('_', ' ').title()}"
            )
            item.setData(Qt.ItemDataRole.UserRole, source.id)
            item.setToolTip(source.title)
            self.source_list.addItem(item)
        self.count_label.setText(f"{len(sources)} source{'s' if len(sources) != 1 else ''}")
        if selected_id:
            for index in range(self.source_list.count()):
                item = self.source_list.item(index)
                if item.data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.source_list.setCurrentItem(item)
                    break
        if self.source_list.currentItem() is None and self.source_list.count():
            self.source_list.setCurrentRow(0)
        elif not sources:
            self._show_empty()

    def select_record(self, source_id: str) -> None:
        for index in range(self.source_list.count()):
            item = self.source_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == source_id:
                self.source_list.setCurrentItem(item)
                return

    def _selected_source(self) -> Source | None:
        item = self.source_list.currentItem()
        if item is None:
            return None
        return self._sources.get(item.data(Qt.ItemDataRole.UserRole))

    def _show_selected(self, current: QListWidgetItem | None, _previous) -> None:
        source = self._sources.get(current.data(Qt.ItemDataRole.UserRole)) if current else None
        self.edit_button.setEnabled(source is not None)
        self.delete_button.setEnabled(source is not None)
        self.open_button.setEnabled(source is not None and bool(source.url or source.local_path))
        if source is None:
            self._show_empty()
            return
        self.detail_type.setText(source.source_type.value.replace("_", " ").title())
        self.detail_title.setText(source.title)
        location = source.url or source.local_path or "No URL or local path recorded."
        observed = f"\nObserved: {source.observed_at}" if source.observed_at else ""
        content_hash = f"\nContent hash: {source.content_hash}" if source.content_hash else ""
        self.detail_copy.setText(f"{location}{observed}{content_hash}")
        entities = [
            entity.name
            for entity in self.services.entities.list()
            if source.id in entity.source_ids
        ]
        relationships = [
            relationship
            for relationship in self.services.relationships.list()
            if source.id in relationship.source_ids
        ]
        relationship_names = []
        for relationship in relationships:
            source_entity = self.services.entities.get(relationship.source_entity_id)
            target_entity = self.services.entities.get(relationship.target_entity_id)
            relationship_names.append(
                f"{source_entity.name} → {target_entity.name}: {relationship.relationship_type} "
                f"({relationship.verification_status.value.replace('_', ' ')})"
            )
        links = []
        if entities:
            links.append(f"Entities: {', '.join(entities)}")
        if relationship_names:
            links.append(f"Claims: {'; '.join(relationship_names)}")
        self.linked_records.setText(
            "\n".join(links) if links else "Not linked to a record or claim yet."
        )
        self.detail_notes.setText(source.notes or "")

    def _show_empty(self) -> None:
        self.detail_type.setText("Source")
        self.detail_title.setText("No source selected")
        self.detail_copy.setText("Add a source to record the origin of an entity or claim.")
        self.linked_records.setText("")
        self.detail_notes.setText("")

    def _add_source(self) -> None:
        dialog = SourceRecordDialog(self.services.sources, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_source:
            self.refresh_sources(dialog.saved_source.id)
            self.records_changed.emit()

    def _edit_selected(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        dialog = SourceRecordDialog(self.services.sources, source, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_source:
            self.refresh_sources(source.id)
            self.records_changed.emit()

    def _confirm_delete(self, source: Source) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Delete source?")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"Delete '{source.title}' and unlink it from any entities and claims?")
        delete_button = box.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_button)
        box.setEscapeButton(cancel_button)
        box.exec()
        return box.clickedButton() is delete_button

    def _delete_selected(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        if not self._confirm_delete(source):
            return
        row = self.source_list.currentRow()
        try:
            deleted = self.services.sources.delete(source.id)
        except DatabaseError as exc:
            QMessageBox.critical(self, "Database error", f"The source could not be deleted: {exc}")
            return
        if not deleted:
            QMessageBox.warning(
                self,
                "Source not found",
                "This source was already removed from the workspace.",
            )
        self.refresh_sources()
        if self.source_list.count():
            self.source_list.setCurrentRow(min(row, self.source_list.count() - 1))
        self.records_changed.emit()
        self.message.emit("Source deleted")

    def _open_selected(self) -> None:
        source = self._selected_source()
        if source is None:
            return
        target = source.url or (
            QUrl.fromLocalFile(source.local_path).toString() if source.local_path else ""
        )
        if target and not QDesktopServices.openUrl(QUrl(target)):
            QMessageBox.warning(
                self, "Could not open source", "Windows could not open this location."
            )
