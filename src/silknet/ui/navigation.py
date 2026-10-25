"""Sidebar navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from silknet import __version__
from silknet.ui.assets import LogoBadge

NAV_ITEMS = (
    ("dashboard", "Dashboard"),
    ("graph", "Investigation Graph"),
    ("entities", "Entities"),
    ("evidence", "Evidence & Sources"),
    ("search", "Search"),
    ("settings", "Settings"),
    ("about", "About"),
)


class NavigationSidebar(QWidget):
    page_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        # Custom QWidget subclasses do not get a styled background by default;
        # without this the navigation rail would be painted transparent.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 14, 14)
        layout.setSpacing(4)

        brand = QWidget(self)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(2, 0, 0, 0)
        brand_layout.setSpacing(11)

        mark = LogoBadge(44, 0.27)
        mark.setObjectName("brandLogo")
        brand_layout.addWidget(mark)

        names = QVBoxLayout()
        names.setSpacing(1)
        name = QLabel("Alya SILKNET")
        name.setObjectName("brandName")
        caption = QLabel("Records & connections")
        caption.setObjectName("brandCaption")
        names.addWidget(name)
        names.addWidget(caption)
        brand_layout.addLayout(names)
        brand_layout.addStretch(1)
        layout.addWidget(brand)
        layout.addSpacing(24)

        section = QLabel("Workspace")
        section.setObjectName("workspaceCaption")
        section.setContentsMargins(11, 0, 0, 7)
        layout.addWidget(section)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for index, (key, label) in enumerate(NAV_ITEMS, start=1):
            button = QPushButton(label.replace("&", "&&"), self)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setAccessibleName(label)
            button.setToolTip(f"{label}  ·  Ctrl+{index}")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, page=key: self.page_requested.emit(page))
            self._group.addButton(button)
            self.buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        footer = QLabel(f"v{__version__}  ·  Local workspace")
        footer.setObjectName("sidebarFooter")
        footer.setContentsMargins(9, 0, 0, 2)
        layout.addWidget(footer)

    def set_current(self, key: str) -> None:
        button = self.buttons.get(key)
        if button is not None:
            button.setChecked(True)
