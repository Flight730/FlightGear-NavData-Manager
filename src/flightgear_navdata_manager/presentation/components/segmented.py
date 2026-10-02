"""SegmentedControl: a row of mutually exclusive options (NDB | VOR | DME).

Deliberately QComboBox-compatible for the parts the app uses --
addItems(), count(), itemText(), currentIndex(), setCurrentIndex(),
currentText() and the currentIndexChanged(int) signal -- so it can
replace a combo box without changing the code (or tests) that drive it.
Left/Right arrow keys move the selection when it has keyboard focus.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton, QSizePolicy, QWidget


class SegmentedControl(QFrame):
    currentIndexChanged = Signal(int)

    def __init__(self, items: list[str] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        # Never taller than its buttons, whatever space the layout offers.
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(3, 3, 3, 3)
        self._row.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idToggled.connect(self._on_toggled)
        self._buttons: list[QPushButton] = []
        self._current = -1
        if items:
            self.addItems(items)

    # -- QComboBox-compatible API -------------------------------------------
    def addItems(self, items: list[str]) -> None:
        for text in items:
            self.addItem(text)

    def addItem(self, text: str) -> None:
        button = QPushButton(text)
        button.setCheckable(True)
        button.setProperty("segment", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.installEventFilter(self)
        self._group.addButton(button, len(self._buttons))
        self._buttons.append(button)
        self._row.addWidget(button, 1)
        if self._current == -1:
            self.setCurrentIndex(0)

    def count(self) -> int:
        return len(self._buttons)

    def itemText(self, index: int) -> str:
        return self._buttons[index].text()

    def setItemText(self, index: int, text: str) -> None:
        self._buttons[index].setText(text)

    def currentIndex(self) -> int:
        return self._current

    def currentText(self) -> str:
        return self.itemText(self._current) if self._current >= 0 else ""

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)   # emits via _on_toggled if it changed

    # -- internals ---------------------------------------------------------------
    def buttons(self) -> list[QPushButton]:
        return list(self._buttons)

    def _on_toggled(self, index: int, checked: bool) -> None:
        if checked and index != self._current:
            self._current = index
            self.currentIndexChanged.emit(index)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = -1 if event.key() == Qt.Key.Key_Left else 1
            index = max(0, min(len(self._buttons) - 1, self._current + step))
            self.setCurrentIndex(index)
            self._buttons[index].setFocus(Qt.FocusReason.TabFocusReason)
            return True
        return super().eventFilter(watched, event)
