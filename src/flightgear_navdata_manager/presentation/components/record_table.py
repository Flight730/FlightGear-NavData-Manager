"""The Manage Data table: a QTableView subclass plus painting delegates.

Everything here *paints* -- no cell ever gets a widget -- so the table
stays fast with tens of thousands of rows. RecordTable tracks the row
under the mouse so every delegate can draw a whole-row hover, and turns
the Delete/Backspace key into a deleteRequested(row) signal (the view
still asks for confirmation).

Hit regions are deliberately small: the Enabled toggle reacts only to
clicks on the switch itself, and Delete only to clicks on the trash icon
(press and release both inside it), so clicking elsewhere in those cells
just selects the row.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QModelIndex, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableView

from ..theme import icons
from ..theme.tokens import COLORS, RADIUS

ROW_HEIGHT = 36
TOGGLE_SIZE = (30, 16)
TOGGLE_LEFT = 10            # from the cell's left edge
DELETE_HIT = 28             # square hit area, centered in the cell


class RecordTable(QTableView):
    deleteRequested = Signal(int)   # visible row

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hover_row = -1
        self.hover_pos = None          # viewport position of the pointer, or None
        self.setMouseTracking(True)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.verticalHeader().setMinimumSectionSize(ROW_HEIGHT)
        self.horizontalHeader().setHighlightSections(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _set_hover_row(self, row: int) -> None:
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()

    def mouseMoveEvent(self, event) -> None:
        self.hover_pos = event.position().toPoint()
        self._set_hover_row(self.rowAt(self.hover_pos.y()))
        self.viewport().update()       # cheap: only visible rows repaint
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.hover_pos = None
        self._set_hover_row(-1)
        self.viewport().update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.currentIndex().isValid():
            self.deleteRequested.emit(self.currentIndex().row())
            return
        super().keyPressEvent(event)


def _hovered(option, index) -> bool:
    table = option.widget
    return isinstance(table, RecordTable) and table.hover_row == index.row()


class RowDelegate(QStyledItemDelegate):
    """Row background (hover / selection), a hairline row separator, then
    the cell's own content."""

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, QColor(COLORS.focus_soft))
        elif _hovered(option, index):
            painter.fillRect(rect, QColor(COLORS.surface_card))
        painter.setPen(QPen(QColor(COLORS.border_subtle), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.restore()
        self.paint_content(painter, option, index)

    def paint_content(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # The background is already drawn; let the style draw only the text.
        opt.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver
                       | QStyle.StateFlag.State_HasFocus)
        opt.backgroundBrush = Qt.BrushStyle.NoBrush
        opt.rect = option.rect.adjusted(10, 0, -10, 0)
        style = option.widget.style() if option.widget else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, option.widget)


class KindDelegate(RowDelegate):
    """FIX / NDB / VOR / DME as a small monochrome outline tag."""

    def paint_content(self, painter, option, index) -> None:
        text = index.data() or ""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(option.font)
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        width = painter.fontMetrics().horizontalAdvance(text) + 14
        tag = QRectF(option.rect.left() + 10, option.rect.center().y() - 9.5, width, 19)
        painter.setPen(QPen(QColor(COLORS.border_strong), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(tag.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS.sm, RADIUS.sm)
        painter.setPen(QColor(COLORS.text_secondary))
        painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class SourceDelegate(RowDelegate):
    """Muted source text; Custom gets a small teal dot."""

    def paint_content(self, painter, option, index) -> None:
        text = index.data() or ""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = option.rect.left() + 10
        cy = option.rect.center().y()
        if text == "Custom":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS.accent))
            painter.drawEllipse(QRectF(x, cy - 3, 6, 6))
            x += 12
        painter.setPen(QColor(COLORS.text_secondary))
        painter.setFont(option.font)
        painter.drawText(QRect(x, option.rect.top(), option.rect.right() - x, option.rect.height()),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)
        painter.restore()


def toggle_rect(cell: QRect) -> QRect:
    w, h = TOGGLE_SIZE
    return QRect(cell.left() + TOGGLE_LEFT, cell.center().y() - h // 2, w, h)


class ToggleDelegate(RowDelegate):
    """The Enabled checkbox painted as a switch. A click on the switch
    writes the new state immediately through the model's setData (the
    same path as the native checkbox); Space toggles the current row."""

    def paint_content(self, painter, option, index) -> None:
        on = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
        r = QRectF(toggle_rect(option.rect))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(COLORS.accent if on else COLORS.border_strong), 1))
        painter.setBrush(QColor(COLORS.accent if on else COLORS.surface_raised))
        radius = r.height() / 2
        painter.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        knob = r.height() - 6
        kx = r.right() - 3 - knob if on else r.left() + 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS.text_on_accent if on else COLORS.text_secondary))
        painter.drawEllipse(QRectF(kx, r.top() + 3, knob, knob))
        painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            # Swallow presses on the switch so a double click can't toggle twice.
            return toggle_rect(option.rect).adjusted(-4, -6, 4, 6).contains(event.position().toPoint())
        if event.type() == QEvent.Type.MouseButtonRelease:
            if (event.button() == Qt.MouseButton.LeftButton
                    and toggle_rect(option.rect).adjusted(-4, -6, 4, 6).contains(event.position().toPoint())):
                return self._flip(model, index)
            return False
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select):
            return self._flip(model, index)
        return False

    @staticmethod
    def _flip(model, index: QModelIndex) -> bool:
        current = index.data(Qt.ItemDataRole.CheckStateRole)
        new = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
        return model.setData(index, new.value, Qt.ItemDataRole.CheckStateRole)


def delete_rect(cell: QRect) -> QRect:
    return QRect(cell.center().x() - DELETE_HIT // 2, cell.center().y() - DELETE_HIT // 2,
                 DELETE_HIT, DELETE_HIT)


class DeleteDelegate(RowDelegate):
    """A trash icon; red with a soft red backdrop while the pointer is on
    it. Reports a click only when press and release are both on the icon."""

    def __init__(self, on_click: Callable[[int], None], parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self._pressed: tuple[int, int] | None = None

    def paint_content(self, painter, option, index) -> None:
        r = delete_rect(option.rect)
        table = option.widget
        hot = isinstance(table, RecordTable) and table.hover_pos is not None and r.contains(table.hover_pos)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if hot:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS.danger_soft))
            painter.drawRoundedRect(QRectF(r), RADIUS.sm, RADIUS.sm)
        color = COLORS.danger if hot else COLORS.text_tertiary
        size = 16
        painter.drawPixmap(r.center().x() - size // 2 + 1, r.center().y() - size // 2 + 1,
                           icons.pixmap("trash-2", color, size, 2))
        painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:
        etype = event.type()
        if etype not in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                         QEvent.Type.MouseButtonDblClick):
            return False
        on_icon = delete_rect(option.rect).contains(event.position().toPoint())
        if etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            self._pressed = (index.row(), index.column()) if on_icon else None
            return on_icon
        pressed, self._pressed = self._pressed, None
        if (event.button() == Qt.MouseButton.LeftButton and on_icon
                and pressed == (index.row(), index.column())):
            self._on_click(index.row())
            return True
        return False
