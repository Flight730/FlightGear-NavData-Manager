"""Sidebar navigation: brand, grouped page links, FlightGear status.

Nav items are painted rather than styled so the hover / active / focus
states stay exact: muted gray by default, soft white on hover, and the
current page as a soft-blue outlined pill.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from flightgear_navdata_manager.infrastructure.fg_detect.macos_locator import FlightGearInstallation

from ..theme import brand, icons
from ..theme.tokens import COLORS, RADIUS

SIDEBAR_WIDTH = 232
_ITEM_HEIGHT = 36
_ICON = 18
_PAD = 12


class NavItem(QAbstractButton):
    """One page link: icon, label and an optional right-aligned count."""

    def __init__(self, icon_name: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._count: str = ""
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedHeight(_ITEM_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setAccessibleName(text)

    def count_text(self) -> str:
        return self._count

    def set_count(self, count: int | None) -> None:
        self._count = "" if count is None else f"{count:,}"
        self.setAccessibleDescription(f"{self._count} records" if self._count else "")
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(SIDEBAR_WIDTH - 24, _ITEM_HEIGHT)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        active = self.isChecked()
        hovered = self.underMouse()

        if active:
            p.setBrush(QColor(COLORS.focus_soft))
            border = QColor(COLORS.focus)
            border.setAlphaF(0.6)
            p.setPen(QPen(border, 1))
            p.drawRoundedRect(rect, RADIUS.md, RADIUS.md)
        elif hovered:
            p.setBrush(QColor(COLORS.surface_raised))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, RADIUS.md, RADIUS.md)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(COLORS.focus), 1.5))
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), RADIUS.md - 1, RADIUS.md - 1)

        fg = COLORS.text_primary if (active or hovered) else COLORS.text_secondary
        icon_y = (self.height() - _ICON) / 2
        p.drawPixmap(_PAD, int(icon_y), icons.pixmap(self._icon_name, fg, _ICON, 2))

        font = QFont(self.font())
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold if active else QFont.Weight.Normal)
        p.setFont(font)
        p.setPen(QColor(fg))
        text_left = _PAD + _ICON + 10
        count_width = 0
        if self._count:
            small = QFont(font)
            small.setPixelSize(12)
            small.setWeight(QFont.Weight.Medium)
            p.setFont(small)
            p.setPen(QColor(COLORS.text_secondary if active else COLORS.text_tertiary))
            count_width = p.fontMetrics().horizontalAdvance(self._count)
            p.drawText(
                QRectF(0, 0, self.width() - _PAD, self.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._count,
            )
            p.setFont(font)
            p.setPen(QColor(fg))
        p.drawText(
            QRectF(text_left, 0, self.width() - text_left - _PAD - count_width - 8, self.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )
        p.end()


class Sidebar(QFrame):
    """Emits pageRequested(index) when a nav item is clicked. Items are
    indexed in the order they were added with add_item()."""

    pageRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        self._items: list[NavItem] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.pageRequested)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 20, 12, 16)
        layout.setSpacing(2)
        layout.addWidget(self._build_brand())
        layout.addSpacing(20)
        self._nav_layout = layout
        self._footer = _StatusFooter()
        self._stretch_added = False

    # -- building --------------------------------------------------------
    def add_group(self, title: str) -> None:
        if self._items:
            self._nav_layout.addSpacing(14)
        label = QLabel(title)
        label.setProperty("role", "navGroup")
        self._nav_layout.addWidget(label)
        self._nav_layout.addSpacing(4)

    def add_item(self, icon_name: str, text: str) -> NavItem:
        item = NavItem(icon_name, text)
        self._group.addButton(item, len(self._items))
        self._items.append(item)
        self._nav_layout.addWidget(item)
        return item

    def finish(self) -> None:
        """Call once after the last item: pins the status footer to the bottom."""
        if not self._stretch_added:
            self._nav_layout.addStretch(1)
            self._nav_layout.addWidget(self._footer)
            self._stretch_added = True

    def _build_brand(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(4, 0, 0, 0)
        row.setSpacing(10)
        tile = QLabel()
        tile.setProperty("iconTile", "small")
        tile.setFixedSize(32, 32)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setPixmap(brand.mark_pixmap(22, 2))
        tile.setAccessibleName("NavData Manager")
        row.addWidget(tile)
        text = QVBoxLayout()
        text.setSpacing(0)
        title = QLabel("NavData Manager")
        title.setProperty("role", "brandTitle")
        subtitle = QLabel("for FlightGear")
        subtitle.setProperty("role", "brandSubtitle")
        text.addWidget(title)
        text.addWidget(subtitle)
        row.addLayout(text)
        row.addStretch(1)
        return box

    # -- state -------------------------------------------------------------
    def items(self) -> list[NavItem]:
        return list(self._items)

    def current_index(self) -> int:
        return self._group.checkedId()

    def set_current(self, index: int) -> None:
        self._items[index].setChecked(True)

    def set_count(self, index: int, count: int | None) -> None:
        self._items[index].set_count(count)

    def set_installation(self, installation: FlightGearInstallation) -> None:
        self._footer.set_installation(installation)

    def status_text(self) -> str:
        return self._footer.headline.text()


class _StatusFooter(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("SidebarFooter")
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 14, 4, 0)
        row.setSpacing(10)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        row.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.headline = QLabel()
        self.headline.setProperty("role", "footerTitle")
        self.detail = QLabel()
        self.detail.setProperty("role", "brandSubtitle")
        text.addWidget(self.headline)
        text.addWidget(self.detail)
        row.addLayout(text, 1)

    def set_installation(self, installation: FlightGearInstallation) -> None:
        if installation.found:
            version = installation.version or "version unknown"
            self.headline.setText(f"FlightGear {version}")
            self.detail.setText("Installation detected")
            self.dot.setProperty("statusDot", "ok")
            self.setToolTip(str(installation.app_bundle or installation.fgfs_binary or ""))
        else:
            self.headline.setText("FlightGear not found")
            self.detail.setText("See Dashboard for details")
            self.dot.setProperty("statusDot", "warn")
            self.setToolTip("")
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)
