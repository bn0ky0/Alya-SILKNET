"""Local search results and validated workspace import/export controls."""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Error as DatabaseError

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from silknet.core.enums import EntityType, VerificationStatus
from silknet.core.exceptions import ValidationError
from silknet.services.container import ApplicationServices
from silknet.services.data_exchange_service import (
    DataExchangeService,
    ImportPreview,
    ImportSummary,
)
from silknet.services.integrations import IntegrationRegistry
from silknet.services.search_service import SearchResult, SearchService
from silknet.ui.pages import PageHeader
from silknet.ui.widgets import ComboBox


class ImportPreviewDialog(QDialog):
    def __init__(self, preview: ImportPreview, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Review {preview.file_type} import")
        self.setMinimumSize(460, 280)
        layout = QVBoxLayout(self)
        summary = QLabel(
            f"New entities: {preview.new_entities}\n"
            f"Duplicate entities to skip: {preview.duplicate_entities}\n"
            f"New sources: {preview.new_sources}\n"
            f"Duplicate sources to skip: {preview.duplicate_sources}\n"
            f"Relationship claims to check: {preview.relationships}"
        )
        summary.setObjectName("cardDescription")
        layout.addWidget(summary)
        if preview.errors:
            errors = QTextEdit()
            errors.setReadOnly(True)
            errors.setPlainText("\n".join(preview.errors))
            layout.addWidget(errors, 1)
        else:
            note = QLabel(
                "Matching entity names and types are treated as duplicates. Imported entities "
                "get new local IDs, and relationship links are remapped to those records."
            )
            note.setWordWrap(True)
            note.setObjectName("subtleText")
            layout.addWidget(note)
        buttons = QDialogButtonBox()
        if preview.can_import:
            self.import_button = buttons.addButton(
                "Import records", QDialogButtonBox.ButtonRole.AcceptRole
            )
            self.import_button.setObjectName("actionButton")
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SearchPage(QWidget):
    record_open_requested = Signal(str, str)
    records_changed = Signal()
    message = Signal(str)

    def __init__(self, services: ApplicationServices) -> None:
        super().__init__()
        self.services = services
        self.search_service = SearchService(
            services.entities, services.relationships, services.sources
        )
        self.exchange = DataExchangeService(services)
        self.integrations = IntegrationRegistry()
        self._results: dict[tuple[str, str], SearchResult] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 30)
        layout.setSpacing(16)
        layout.addWidget(
            PageHeader(
                "Workspace",
                "Search",
                "Search saved entities, claims and sources on this device.",
            )
        )
        self.query_field = QLineEdit()
        self.query_field.setPlaceholderText("Search names, notes, tags, URLs and claim text")
        self.query_field.textChanged.connect(self.refresh_results)
        query_row = QHBoxLayout()
        query_row.addWidget(self.query_field)
        layout.addLayout(query_row)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.kind_filter = ComboBox()
        self.kind_filter.addItem("All records", "all")
        self.kind_filter.addItem("Entities", "entity")
        self.kind_filter.addItem("Relationship claims", "relationship")
        self.kind_filter.addItem("Sources", "source")
        self.kind_filter.currentIndexChanged.connect(self.refresh_results)
        self.entity_type_filter = ComboBox()
        self.entity_type_filter.addItem("All entity types", "")
        for entity_type in EntityType:
            self.entity_type_filter.addItem(
                entity_type.value.replace("_", " ").title(), entity_type.value
            )
        for custom_type in services.entities.list_custom_types():
            self.entity_type_filter.addItem(custom_type.display_name, custom_type.key)
        self.entity_type_filter.currentIndexChanged.connect(self.refresh_results)
        self.status_filter = ComboBox()
        self.status_filter.addItem("Any status", "")
        for status in VerificationStatus:
            self.status_filter.addItem(status.value.replace("_", " ").title(), status.value)
        self.status_filter.currentIndexChanged.connect(self.refresh_results)
        self.tag_field = QLineEdit()
        self.tag_field.setPlaceholderText("Exact tag")
        self.tag_field.setMaximumWidth(180)
        self.tag_field.textChanged.connect(self.refresh_results)
        filters.addWidget(self.kind_filter)
        filters.addWidget(self.entity_type_filter)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.tag_field)
        filters.addStretch(1)
        layout.addLayout(filters)

        self.count_label = QLabel("Enter a search term or choose a filter.")
        self.count_label.setObjectName("subtleText")
        layout.addWidget(self.count_label)
        self.results_list = QListWidget()
        self.results_list.setObjectName("entityList")
        self.results_list.setAccessibleName("Local search results")
        self.results_list.currentItemChanged.connect(self._show_selected)
        self.results_list.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.results_list, 1)
        self.result_detail = QLabel("Search results will appear here.")
        self.result_detail.setObjectName("cardDescription")
        self.result_detail.setWordWrap(True)
        layout.addWidget(self.result_detail)

        actions = QHBoxLayout()
        self.integration_status = QLabel("No external providers are configured.")
        self.integration_status.setObjectName("subtleText")
        self.export_json_button = QPushButton("Export JSON")
        self.export_json_button.setObjectName("quietButton")
        self.export_json_button.clicked.connect(self._export_json)
        self.export_csv_button = QPushButton("Export entities CSV")
        self.export_csv_button.setObjectName("quietButton")
        self.export_csv_button.clicked.connect(self._export_csv)
        self.import_button = QPushButton("Import JSON or CSV")
        self.import_button.setObjectName("actionButton")
        self.import_button.clicked.connect(self._import_file)
        actions.addWidget(self.integration_status, 1)
        actions.addWidget(self.export_json_button)
        actions.addWidget(self.export_csv_button)
        actions.addWidget(self.import_button)
        layout.addLayout(actions)

    def set_query(self, query: str) -> None:
        self.query_field.setText(query)

    def refresh_entity_types(self) -> None:
        current = self.entity_type_filter.currentData()
        self.entity_type_filter.blockSignals(True)
        self.entity_type_filter.clear()
        self.entity_type_filter.addItem("All entity types", "")
        for entity_type in EntityType:
            self.entity_type_filter.addItem(
                entity_type.value.replace("_", " ").title(), entity_type.value
            )
        for custom_type in self.services.entities.list_custom_types():
            self.entity_type_filter.addItem(custom_type.display_name, custom_type.key)
        index = self.entity_type_filter.findData(current)
        self.entity_type_filter.setCurrentIndex(index if index >= 0 else 0)
        self.entity_type_filter.blockSignals(False)

    def refresh_results(self, *_args) -> None:
        results = self.search_service.search(
            self.query_field.text(),
            result_kind=self.kind_filter.currentData(),
            entity_type=self.entity_type_filter.currentData(),
            verification_status=self.status_filter.currentData(),
            tag=self.tag_field.text(),
        )
        self._results = {(item.kind, item.record_id): item for item in results}
        self.results_list.clear()
        self.result_detail.setText("Search results will appear here.")
        for result in results:
            item = QListWidgetItem(f"{result.title}\n{result.kind.title()} · {result.summary}")
            item.setData(Qt.ItemDataRole.UserRole, (result.kind, result.record_id))
            self.results_list.addItem(item)
        self.count_label.setText(
            f"{len(results)} result{'s' if len(results) != 1 else ''}"
            if results
            else "No matching records."
        )
        if not results:
            self.result_detail.setText("Try a shorter search term or clear one of the filters.")

    def _show_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        kind, record_id = current.data(Qt.ItemDataRole.UserRole)
        result = self._results.get((kind, record_id))
        if result:
            self.result_detail.setText(f"{result.kind.title()}\n{result.title}\n{result.summary}")

    def _open_selected(self, item: QListWidgetItem) -> None:
        kind, record_id = item.data(Qt.ItemDataRole.UserRole)
        page = {"entity": "entities", "relationship": "graph", "source": "evidence"}[kind]
        self.record_open_requested.emit(page, record_id)

    def _export_json(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export SILKNET workspace", "silknet-export.json", "JSON files (*.json)"
        )
        if not filename:
            return
        try:
            self.exchange.export_json(Path(filename))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export complete", f"Workspace exported to:\n{filename}")

    def _export_csv(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export entity records", "silknet-entities.csv", "CSV files (*.csv)"
        )
        if not filename:
            return
        try:
            self.exchange.export_csv(Path(filename))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export complete", f"Entity records exported to:\n{filename}")

    def _import_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import SILKNET data", "", "SILKNET exports (*.json *.csv)"
        )
        if not filename:
            return
        source = Path(filename)
        try:
            preview = (
                self.exchange.preview_json(source)
                if source.suffix.casefold() == ".json"
                else self.exchange.preview_csv(source)
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import preview failed", str(exc))
            return
        dialog = ImportPreviewDialog(preview, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            summary = (
                self.exchange.import_json(source)
                if source.suffix.casefold() == ".json"
                else self.exchange.import_csv(source)
            )
        except (ValidationError, OSError, DatabaseError, ValueError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.refresh_entity_types()
        self.refresh_results()
        self.records_changed.emit()
        self.message.emit("Workspace data imported")
        QMessageBox.information(self, "Import complete", _summary_text(summary))


def _summary_text(summary: ImportSummary) -> str:
    message = (
        f"Entities imported: {summary.imported_entities}\n"
        f"Entities skipped: {summary.skipped_entities}\n"
        f"Sources imported: {summary.imported_sources}\n"
        f"Sources skipped: {summary.skipped_sources}\n"
        f"Relationships imported: {summary.imported_relationships}\n"
        f"Relationships skipped: {summary.skipped_relationships}"
    )
    if summary.warnings:
        message += "\n\n" + "\n".join(summary.warnings)
    return message
