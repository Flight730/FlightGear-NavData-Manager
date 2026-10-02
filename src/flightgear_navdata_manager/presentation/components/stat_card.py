"""StatCard: a small card with an icon + label, a large value and a
muted detail line, e.g. "Records / 2,279 / 2,279 enabled · 0 disabled".
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..theme import icons
from ..theme.tokens import COLORS


class StatCard(QFrame):
    def __init__(self, icon_name: str, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("card", True)
        # Cards in a row share the tallest card's height.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(icons.pixmap(icon_name, COLORS.text_secondary, 16, 2))
        top.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.label = QLabel(label)
        self.label.setProperty("role", "statLabel")
        top.addWidget(self.label, 1)
        layout.addLayout(top)
        layout.addSpacing(6)

        self.value_label = QLabel("–")
        self.value_label.setProperty("role", "stat")
        layout.addWidget(self.value_label)
        self.detail_label = QLabel("")
        self.detail_label.setProperty("role", "small")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)
        layout.addStretch(1)

    def set_value(self, text: str, *, compact: bool = False) -> None:
        """compact: a word rather than a number ("Up to date"), set smaller."""
        self.value_label.setText(text)
        role = "statText" if compact else "stat"
        if self.value_label.property("role") != role:
            self.value_label.setProperty("role", role)
            self.value_label.style().unpolish(self.value_label)
            self.value_label.style().polish(self.value_label)

    def set_detail(self, text: str) -> None:
        self.detail_label.setText(text)

    def value_text(self) -> str:
        return self.value_label.text()

    def detail_text(self) -> str:
        return self.detail_label.text()
