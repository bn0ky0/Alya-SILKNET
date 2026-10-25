"""Reusable source selector for entity and relationship forms."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from silknet.core.models import Source


class SourcePicker(QListWidget):
    def __init__(self, sources: list[Source], selected_ids: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.setAccessibleName("Evidence sources linked to this record")
        self.setMaximumHeight(112)
        self.setMinimumHeight(56)
        if not sources:
            item = QListWidgetItem("No sources yet. Add sources in Evidence & Sources.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.addItem(item)
            return
        selected = set(selected_ids)
        for source in sources:
            item = QListWidgetItem(source.title)
            item.setData(Qt.ItemDataRole.UserRole, source.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if source.id in selected else Qt.CheckState.Unchecked
            )
            self.addItem(item)

    def selected_ids(self) -> tuple[str, ...]:
        return tuple(
            item.data(Qt.ItemDataRole.UserRole)
            for index in range(self.count())
            if (item := self.item(index)).checkState() == Qt.CheckState.Checked
        )
