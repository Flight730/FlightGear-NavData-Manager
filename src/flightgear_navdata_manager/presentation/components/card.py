"""Card: a rounded, bordered surface with an optional header (icon tile,
title, subtitle, and right-aligned accessories such as a pill or
buttons). Put content in `card.body`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..theme import icons
from ..theme.tokens import COLORS, SPACING

CARD_PADDING = 20


class Card(QFrame):
    def __init__(self, title: str | None = None, icon_name: str | None = None,
                 subtitle: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("card", True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(CARD_PADDING, CARD_PADDING - 2, CARD_PADDING, CARD_PADDING)
        outer.setSpacing(SPACING.lg)

        self.header: QHBoxLayout | None = None
        self.title_label: QLabel | None = None
        if title is not None:
            self.header = QHBoxLayout()
            self.header.setSpacing(SPACING.md)
            if icon_name:
                tile = QLabel()
                tile.setProperty("iconTile", "small")
                tile.setFixedSize(32, 32)
                tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
                tile.setPixmap(icons.pixmap(icon_name, COLORS.text_secondary, 16, 2))
                self.header.addWidget(tile, 0, Qt.AlignmentFlag.AlignVCenter)
            text = QVBoxLayout()
            text.setSpacing(1)
            self.title_label = QLabel(title)
            self.title_label.setProperty("role", "cardTitle")
            text.addWidget(self.title_label)
            if subtitle:
                sub = QLabel(subtitle)
                sub.setProperty("role", "small")
                text.addWidget(sub)
            self.header.addLayout(text, 1)
            outer.addLayout(self.header)

        self.body = QVBoxLayout()
        self.body.setSpacing(SPACING.md)
        outer.addLayout(self.body)

    def add_header_widget(self, widget: QWidget) -> None:
        """Adds a right-aligned header accessory (pill, button...)."""
        assert self.header is not None, "card has no header"
        self.header.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
