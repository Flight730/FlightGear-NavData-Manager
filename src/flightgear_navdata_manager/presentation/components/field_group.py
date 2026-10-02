"""FieldGroup: a form field with its label above it and optional muted
helper text below -- the layout every form in the app uses.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class FieldGroup(QWidget):
    def __init__(self, label: str, field: QWidget, helper: str | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.field = field
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.label = QLabel(label)
        self.label.setProperty("role", "fieldLabel")
        self.label.setBuddy(field)
        layout.addWidget(self.label)
        layout.addWidget(field)
        self.helper: QLabel | None = None
        if helper:
            self.helper = QLabel(helper)
            self.helper.setProperty("role", "helper")
            self.helper.setWordWrap(True)
            layout.addWidget(self.helper)


def section_title(text: str) -> QLabel:
    """A small heading that separates groups of fields inside a card."""
    label = QLabel(text)
    label.setProperty("role", "sectionTitle")
    # Its style-sheet margin counts as a frame, and a framed QLabel indents
    # its text automatically unless told otherwise.
    label.setIndent(0)
    return label
