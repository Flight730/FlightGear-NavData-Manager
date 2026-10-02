"""ElidedLabel: one line of text that is shortened in the middle to fit
("/Users/.../fgdata_2024_1") instead of widening its layout. text()
returns the full text; so does the tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setToolTip(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self) -> QSize:
        return QSize(40, super().minimumSizeHint().height())

    def elided_text(self) -> str:
        return self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideMiddle, self.contentsRect().width())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        painter.drawText(self.contentsRect(), int(self.alignment() | Qt.AlignmentFlag.AlignVCenter), self.elided_text())
        painter.end()
