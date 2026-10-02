"""PageScaffold: the frame every page sits in -- an icon tile, title and
one-line description, then the page's own content with consistent
margins. The content scrolls if the window is shorter than it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme import icons
from ..theme.tokens import COLORS, SPACING

PAGE_MARGIN_X = SPACING.xxl
PAGE_MARGIN_TOP = 28


class PageScaffold(QWidget):
    def __init__(self, icon_name: str, title: str, description: str, content: QWidget,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.content = content
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(PAGE_MARGIN_X, PAGE_MARGIN_TOP, PAGE_MARGIN_X, SPACING.xl)
        header_row.setSpacing(14)
        tile = QLabel()
        tile.setProperty("iconTile", "page")
        tile.setFixedSize(42, 42)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setPixmap(icons.pixmap(icon_name, COLORS.text_primary, 20, 2))
        header_row.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "pageTitle")
        self.description_label = QLabel(description)
        self.description_label.setProperty("role", "secondary")
        self.description_label.setWordWrap(True)
        text.addWidget(self.title_label)
        text.addWidget(self.description_label)
        header_row.addLayout(text, 1)
        outer.addWidget(header)

        divider = QFrame()
        divider.setObjectName("PageDivider")
        divider.setFixedHeight(1)
        outer.addWidget(divider)

        # The page's own margins are replaced by the scaffold's so every
        # page lines up with its header.
        if content.layout() is not None:
            content.layout().setContentsMargins(PAGE_MARGIN_X, SPACING.xl, PAGE_MARGIN_X, SPACING.xl)
        # Pages always fit the visible width (they scroll vertically only):
        # a long unwrapped line must never push the page past the window edge.
        policy = content.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        content.setSizePolicy(policy)
        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
