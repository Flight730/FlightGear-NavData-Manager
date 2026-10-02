"""Status feedback widgets: StatusPill (a compact state tag) and
InlineBanner (an in-place message with an icon -- used instead of a
pop-up for results and errors that belong to one part of a page).

Tones: "success", "warning", "danger", "info", "neutral".
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from ..theme import icons
from ..theme.tokens import COLORS

TONES = ("success", "warning", "danger", "info", "neutral")

_TONE_ICON = {
    "success": ("circle-check", COLORS.accent),
    "warning": ("triangle-alert", COLORS.warning),
    "danger": ("circle-x", COLORS.danger),
    "info": ("info", COLORS.info),
    "neutral": ("info", COLORS.text_secondary),
}


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class StatusPill(QLabel):
    def __init__(self, text: str = "", tone: str = "neutral", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status(text, tone)

    def set_status(self, text: str, tone: str) -> None:
        assert tone in TONES, tone
        self.setText(text)
        self.setProperty("pill", tone)
        _repolish(self)

    def tone(self) -> str:
        return self.property("pill")


class InlineBanner(QFrame):
    """Hidden until show_message(); clear() hides it again. The message
    label is `text_label` (word-wrapped, selectable)."""

    def __init__(self, tone: str = "info", text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        self._icon = QLabel()
        self._icon.setFixedSize(16, 16)
        row.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        self.text_label = QLabel()
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.text_label, 1)
        if text:
            self.show_message(text, tone)
        else:
            self._set_tone(tone)
            self.setVisible(False)

    def show_message(self, text: str, tone: str) -> None:
        self._set_tone(tone)
        self.text_label.setText(text)
        self.setVisible(True)

    def clear(self) -> None:
        self.text_label.setText("")
        self.setVisible(False)

    def tone(self) -> str:
        return self.property("banner")

    def _set_tone(self, tone: str) -> None:
        assert tone in TONES, tone
        name, color = _TONE_ICON[tone]
        self._icon.setPixmap(icons.pixmap(name, color, 16, 2))
        self.setProperty("banner", tone)
        _repolish(self)


class Chip(QLabel):
    """A small, static outlined tag, e.g. a supported file format."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setProperty("chip", True)
        self.setIndent(0)   # a styled QLabel would otherwise indent its text
