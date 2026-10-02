"""EmptyState: a centered icon, title, explanation and optional actions,
shown in place of content that doesn't exist yet (or matches nothing).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..theme import icons
from ..theme.tokens import COLORS


class EmptyState(QFrame):
    def __init__(self, icon_name: str, title: str, body: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 40, 32, 40)
        layout.setSpacing(10)
        # Centered with stretches, not layout alignment: an aligned layout
        # gives wrapped text its one-line height and clips it.
        layout.addStretch(1)

        tile = QLabel()
        tile.setProperty("iconTile", "page")
        tile.setFixedSize(44, 44)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setPixmap(icons.pixmap(icon_name, COLORS.text_secondary, 20, 2))
        layout.addWidget(tile, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "cardTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        self.text_label = QLabel(body)
        self.text_label.setProperty("role", "secondary")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        self.text_label.setMaximumWidth(460)
        text_row = QHBoxLayout()
        text_row.addStretch(1)
        text_row.addWidget(self.text_label, 100)
        text_row.addStretch(1)
        layout.addLayout(text_row)
        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        self._actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(6)
        layout.addLayout(self._actions)
        layout.addStretch(1)
        self.buttons: list[QPushButton] = []

    def add_action(self, text: str, callback: Callable[[], None], *, primary: bool = False,
                   icon_name: str | None = None) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setProperty("variant", "primary")
        if icon_name:
            icons.set_button_icon(button, icon_name, COLORS.text_on_accent if primary else COLORS.text_primary)
        button.clicked.connect(callback)
        self._actions.addWidget(button)
        self.buttons.append(button)
        return button
