"""Shared building blocks for the Add Waypoint / Add Navaid pages: the
form column (at most FORM_MAX_WIDTH wide) with an optional tip card
beside it when there is room, and the coordinate input.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ..theme.tokens import SPACING
from .card import Card

FORM_MAX_WIDTH = 600
ASIDE_WIDTH = 260


def coordinate_spin(minimum: float, maximum: float) -> QDoubleSpinBox:
    """Decimal degrees, 8 places, typed rather than stepped (no arrows)."""
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(8)
    spin.setSuffix("°")
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    spin.setProperty("arrows", "false")
    return spin


def tip_card(title: str, paragraphs: list[str]) -> Card:
    card = Card(title, "info")
    for text in paragraphs:
        label = QLabel(text)
        label.setProperty("role", "secondary")
        label.setWordWrap(True)
        card.body.addWidget(label)
    card.body.addStretch(1)
    return card


class FormColumns(QWidget):
    """The form card on the left (max FORM_MAX_WIDTH); the optional aside
    to its right, shown only when both fit."""

    def __init__(self, form: QWidget, aside: QWidget | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.form = form
        self.aside = aside
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING.lg)
        form.setMaximumWidth(FORM_MAX_WIDTH)
        row.addWidget(form, 1)
        if aside is not None:
            aside.setFixedWidth(ASIDE_WIDTH)
            row.addWidget(aside)
        row.addStretch(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.aside is not None:
            room = FORM_MAX_WIDTH + SPACING.lg + ASIDE_WIDTH
            self.aside.setVisible(event.size().width() >= room)
