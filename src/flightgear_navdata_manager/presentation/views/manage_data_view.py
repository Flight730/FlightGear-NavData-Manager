"""Manage Data view: lists all Fix/NDB/VOR/DME records (custom and
imported), lets the user find them (search, type and source filters)
and enable/disable or delete individual records.

Enabling/disabling and deleting both trigger a regeneration of the
custom NavData output files via the injected services.

Implemented as a QTableView over a table model rather than a
QTableWidget with a checkbox and button widget per row: a full FAA
dataset is ~70,000 records, and per-row widgets took seconds and over a
gigabyte to build. Every cell is painted by a delegate
(components/record_table.py) -- the Enabled switch and the Delete trash
icon included -- so no row ever owns a widget.

Filtering lives inside RecordTableModel: it keeps every loaded record
and exposes the matching subset as its rows. A visible row maps to its
record *object* (which carries the database id), never to a position in
the database, so toggling or deleting a filtered row always acts on the
record shown.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from flightgear_navdata_manager.application.navaid_service import NavaidService
from flightgear_navdata_manager.application.waypoint_service import WaypointService
from flightgear_navdata_manager.domain.models import DataSource, Dme, Fix, Ndb, Vor

from ..components.empty_state import EmptyState
from ..components.record_table import (
    DeleteDelegate,
    KindDelegate,
    RecordTable,
    RowDelegate,
    SourceDelegate,
    ToggleDelegate,
)
from ..components.segmented import SegmentedControl
from ..theme import icons
from ..theme.dialogs import destructive_confirmation
from ..theme.tokens import COLORS, SPACING

_COLUMNS = ["Kind", "Ident", "Name", "Latitude", "Longitude", "Source", "Enabled", ""]
ENABLED_COLUMN = 6
DELETE_COLUMN = 7
# Fixed columns sized to their content; Name takes the rest (about 95 px at
# the 980 px minimum window width, more as the window grows).
_COLUMN_WIDTHS = {0: 64, 1: 88, 3: 100, 4: 108, 5: 96, ENABLED_COLUMN: 76, DELETE_COLUMN: 44}

KINDS = ["FIX", "NDB", "VOR", "DME"]
KIND_FILTER_LABELS = ["All", "Fixes", "NDB", "VOR", "DME"]     # segment order; None, then KINDS
SOURCE_FILTER_LABELS = ["All", "Custom", "Imported"]
SEARCH_DELAY_MS = 200


class _Entry:
    """One loaded record plus what filtering needs, computed once per load."""

    __slots__ = ("kind", "record", "source", "haystack")

    def __init__(self, kind: str, record):
        self.kind = kind
        self.record = record
        self.source = "Custom" if record.source == DataSource.CUSTOM else "Imported"
        name = "" if isinstance(record, Fix) else record.name
        self.haystack = f"{record.ident}\n{name}".lower()

    def matches(self, kind: str | None, source: str | None, text: str) -> bool:
        return ((kind is None or self.kind == kind)
                and (source is None or self.source == source)
                and (not text or text in self.haystack))


class RecordTableModel(QAbstractTableModel):
    def __init__(self, on_toggle: Callable[[str, object, bool], None], parent=None):
        super().__init__(parent)
        self._all: list[_Entry] = []       # every loaded record
        self._rows: list[_Entry] = []      # the ones matching the filter, in load order
        self._on_toggle = on_toggle
        self._kind: str | None = None
        self._source: str | None = None
        self._text = ""
        self._enabled = 0
        self._bold = QFont()
        self._bold.setPixelSize(13)
        self._bold.setWeight(QFont.Weight.DemiBold)
        self._digits = QFont()
        self._digits.setPixelSize(13)
        self._digits.setFeature(QFont.Tag("tnum"), 1)    # fixed-width digits line up

    # -- loading and filtering ----------------------------------------------------
    def set_rows(self, rows: list[tuple[str, object]]) -> None:
        self.beginResetModel()
        self._all = [_Entry(kind, record) for kind, record in rows]
        self._enabled = sum(1 for e in self._all if e.record.enabled)
        self._rows = self._matching()
        self.endResetModel()

    def set_filter(self, kind: str | None = None, source: str | None = None, text: str = "") -> None:
        text = text.strip().lower()
        if (kind, source, text) == (self._kind, self._source, self._text):
            return
        self._kind, self._source, self._text = kind, source, text
        self.beginResetModel()
        self._rows = self._matching()
        self.endResetModel()

    def filter_state(self) -> tuple[str | None, str | None, str]:
        return self._kind, self._source, self._text

    def _matching(self) -> list[_Entry]:
        kind, source, text = self._kind, self._source, self._text
        if kind is None and source is None and not text:
            return list(self._all)
        return [e for e in self._all if e.matches(kind, source, text)]

    # -- counts (in memory: one pass over the loaded records, no queries) --------
    def total_count(self) -> int:
        return len(self._all)

    def enabled_count(self) -> int:
        return self._enabled

    def kind_counts(self) -> dict[str | None, int]:
        """Matches per kind under the current source + search filters (what
        each type segment would show); None is the total across kinds."""
        counts = dict.fromkeys(KINDS, 0)
        source, text = self._source, self._text
        for e in self._all:
            if e.matches(None, source, text):
                counts[e.kind] += 1
        counts[None] = sum(counts.values())
        return counts

    # -- rows -----------------------------------------------------------------------
    def row(self, row: int) -> tuple[str, object]:
        entry = self._rows[row]
        return entry.kind, entry.record

    def remove(self, row: int) -> None:
        entry = self._rows[row]
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._rows[row]
        # By identity, never by position or equality: the visible row and
        # the full list are ordered differently whenever a filter is on.
        for i, candidate in enumerate(self._all):
            if candidate is entry:
                del self._all[i]
                break
        if entry.record.enabled:
            self._enabled -= 1
        self.endRemoveRows()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(_alignment(section))
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self._rows[index.row()]
        kind, record = entry.kind, entry.record
        column = index.column()
        if role == Qt.ItemDataRole.CheckStateRole and column == ENABLED_COLUMN:
            return Qt.CheckState.Checked if record.enabled else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.FontRole:
            return self._bold if column == 1 else self._digits if column in (3, 4) else None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(_alignment(column))
        if role == Qt.ItemDataRole.ToolTipRole and column == 2 and not isinstance(record, Fix):
            return record.name
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if column == 0:
            return kind
        if column == 1:
            return record.ident
        if column == 2:
            return "" if isinstance(record, Fix) else record.name
        if column == 3:
            return f"{record.latitude:.6f}"
        if column == 4:
            return f"{record.longitude:.6f}"
        if column == 5:
            return entry.source
        if column == DELETE_COLUMN:
            return "Delete"
        return None

    def flags(self, index: QModelIndex):
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == ENABLED_COLUMN:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if index.column() != ENABLED_COLUMN or role != Qt.ItemDataRole.CheckStateRole:
            return False
        entry = self._rows[index.row()]
        enabled = Qt.CheckState(value) == Qt.CheckState.Checked
        if enabled == entry.record.enabled:
            return True
        self._on_toggle(entry.kind, entry.record, enabled)   # writes now (service + export)
        entry.record.enabled = enabled
        self._enabled += 1 if enabled else -1
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        return True


def _alignment(column: int) -> Qt.AlignmentFlag:
    horizontal = Qt.AlignmentFlag.AlignRight if column in (3, 4) else Qt.AlignmentFlag.AlignLeft
    return horizontal | Qt.AlignmentFlag.AlignVCenter


class ManageDataView(QWidget):
    # "2,279 records · 2,279 enabled" -- MainWindow shows it as the page subtitle.
    summaryChanged = Signal(str)

    def __init__(
        self,
        waypoint_service: WaypointService,
        navaid_service: NavaidService,
        parent: QWidget | None = None,
        on_changed: Callable[[str], None] | None = None,
        on_navigate: Callable[[str], None] | None = None,
        load_now: bool = True,
    ):
        super().__init__(parent)
        self._waypoint_service = waypoint_service
        self._navaid_service = navaid_service
        # Called with "toggled" or "deleted" after a change made here.
        self._on_changed = on_changed
        # Called with "import" or "add_waypoint" by the empty-state buttons.
        self._on_navigate = on_navigate
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING.md)

        # -- toolbar ---------------------------------------------------------------------
        self._toolbar = QWidget()
        bar = QVBoxLayout(self._toolbar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(SPACING.md)
        top = QHBoxLayout()
        top.setSpacing(SPACING.md)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search identifier or name")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setAccessibleName("Search records")
        self._search_edit.addAction(QAction(icons.icon("search", COLORS.text_tertiary, 16), "", self),
                                    QLineEdit.ActionPosition.LeadingPosition)
        self._search_edit.setMinimumWidth(200)
        self._search_edit.setMaximumWidth(380)
        top.addWidget(self._search_edit, 1)
        top.addStretch(0)
        self._source_filter = SegmentedControl(SOURCE_FILTER_LABELS)
        top.addWidget(self._source_filter)
        self._refresh_btn = QPushButton()
        self._refresh_btn.setProperty("variant", "ghost")
        self._refresh_btn.setIcon(icons.icon("refresh-cw", COLORS.text_secondary, 16,
                                             active_color=COLORS.text_primary))
        self._refresh_btn.setToolTip("Reload from the database")
        self._refresh_btn.setAccessibleName("Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        top.addWidget(self._refresh_btn)
        bar.addLayout(top)
        kinds_row = QHBoxLayout()
        self._kind_filter = SegmentedControl(KIND_FILTER_LABELS)
        kinds_row.addWidget(self._kind_filter)
        kinds_row.addStretch(1)
        bar.addLayout(kinds_row)
        layout.addWidget(self._toolbar)

        # -- states shown instead of the table -------------------------------------------
        self._loading_label = QLabel("Loading records...")
        self._loading_label.setProperty("role", "secondary")
        layout.addWidget(self._loading_label)

        self._empty_state_label = EmptyState(
            "database", "No records yet",
            "Import a fix.dat / nav.dat file or a dataset, or create a waypoint or navaid by hand.",
        )
        if on_navigate is not None:
            self._empty_state_label.add_action("Import data", lambda: on_navigate("import"),
                                               primary=True, icon_name="download")
            self._empty_state_label.add_action("Add waypoint", lambda: on_navigate("add_waypoint"),
                                               icon_name="map-pin")
        layout.addWidget(self._empty_state_label, 1)     # takes the spare height when shown

        self._no_results = EmptyState(
            "search", "No records match your filters",
            "Try a different search, or clear the filters to see all records.",
        )
        self._no_results.add_action("Clear filters", self.clear_filters, icon_name="x")
        layout.addWidget(self._no_results, 1)

        # -- table -----------------------------------------------------------------------
        self._table = RecordTable()
        # Owned by the table, so Qt destroys it after the table has let go
        # of it. An unowned model can be garbage-collected while the table
        # still uses it, which crashes Qt.
        self._model = RecordTableModel(on_toggle=self._on_toggle, parent=self._table)
        self._table.setModel(self._model)
        self._model.dataChanged.connect(self._on_model_data_changed)
        self._row_delegate = RowDelegate(self._table)
        self._table.setItemDelegate(self._row_delegate)
        self._table.setItemDelegateForColumn(0, KindDelegate(self._table))
        self._table.setItemDelegateForColumn(5, SourceDelegate(self._table))
        self._table.setItemDelegateForColumn(ENABLED_COLUMN, ToggleDelegate(self._table))
        self._table.setItemDelegateForColumn(
            DELETE_COLUMN, DeleteDelegate(self._on_delete_row, self._table)
        )
        header = self._table.horizontalHeader()
        for column, width in _COLUMN_WIDTHS.items():
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.deleteRequested.connect(self._on_delete_row)
        layout.addWidget(self._table, 1)

        self._footer = QLabel()
        self._footer.setProperty("role", "small")
        layout.addWidget(self._footer)

        # -- wiring ----------------------------------------------------------------------
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DELAY_MS)
        self._search_timer.timeout.connect(self._apply_filters)
        self._search_edit.textChanged.connect(lambda _: self._search_timer.start())
        self._search_edit.returnPressed.connect(self._apply_filters)
        self._search_edit.installEventFilter(self)
        self._kind_filter.currentIndexChanged.connect(lambda _: self._apply_filters())
        self._source_filter.currentIndexChanged.connect(lambda _: self._apply_filters())
        self._find_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self)
        self._find_shortcut.activated.connect(self.focus_search)

        if load_now:
            self.refresh()
        else:
            self._show_state()

    # -- loading -------------------------------------------------------------------------
    def refresh(self) -> None:
        rows: list[tuple[str, object]] = [("FIX", fix) for fix in self._waypoint_service.list_all()]
        rows.extend(
            ({Ndb: "NDB", Vor: "VOR", Dme: "DME"}[type(navaid)], navaid)
            for navaid in self._navaid_service.list_all()
        )
        self._model.set_rows(rows)
        self._loaded = True
        self._after_change()

    # -- filters -------------------------------------------------------------------------
    def focus_search(self) -> None:
        self._search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search_edit.selectAll()

    def clear_filters(self) -> None:
        self._search_timer.stop()
        for control in (self._kind_filter, self._source_filter):
            control.blockSignals(True)
            control.setCurrentIndex(0)
            control.blockSignals(False)
        self._search_edit.blockSignals(True)
        self._search_edit.clear()
        self._search_edit.blockSignals(False)
        self._apply_filters()

    def _apply_filters(self) -> None:
        self._search_timer.stop()
        kind_index = self._kind_filter.currentIndex()
        source_index = self._source_filter.currentIndex()
        self._model.set_filter(
            kind=None if kind_index == 0 else KINDS[kind_index - 1],
            source=None if source_index == 0 else SOURCE_FILTER_LABELS[source_index],
            text=self._search_edit.text(),
        )
        self._after_change()

    def eventFilter(self, watched, event) -> bool:
        # Escape in the search field clears the search (and only then
        # leaves the key to anyone else).
        if (watched is self._search_edit and event.type() == event.Type.KeyPress
                and event.key() == Qt.Key.Key_Escape and self._search_edit.text()):
            self._search_edit.clear()
            self._apply_filters()
            return True
        return super().eventFilter(watched, event)

    # -- state ---------------------------------------------------------------------------
    def _after_change(self) -> None:
        """Counts, footer, subtitle and which state is shown -- all from the
        model's in-memory records, without touching the database."""
        model = self._model
        counts = model.kind_counts()
        for i, label in enumerate(KIND_FILTER_LABELS):
            count = counts[None if i == 0 else KINDS[i - 1]]
            self._kind_filter.setItemText(i, f"{label}  {count:,}")
        total, shown = model.total_count(), model.rowCount()
        self._footer.setText(f"Showing {shown:,} of {total:,}")
        self._show_state()
        if self._loaded:
            self.summaryChanged.emit(self.summary_text())

    def summary_text(self) -> str:
        return f"{self._model.total_count():,} records · {self._model.enabled_count():,} enabled"

    def _show_state(self) -> None:
        has_records = self._model.total_count() > 0
        has_matches = self._model.rowCount() > 0
        self._loading_label.setVisible(not self._loaded)
        self._empty_state_label.setVisible(self._loaded and not has_records)
        self._no_results.setVisible(self._loaded and has_records and not has_matches)
        self._toolbar.setVisible(self._loaded and has_records)
        self._footer.setVisible(self._loaded and has_records)
        self._table.setVisible(self._loaded and has_records and has_matches)

    # -- record actions --------------------------------------------------------------------
    def _on_toggle(self, kind: str, record, enabled: bool) -> None:
        if kind == "FIX":
            self._waypoint_service.set_enabled(record.id, enabled)
        else:
            self._navaid_service.set_enabled(record.id, enabled)
        if self._on_changed:
            self._on_changed("toggled")

    def _on_model_data_changed(self, top_left, bottom_right, roles) -> None:
        if Qt.ItemDataRole.CheckStateRole in roles:      # a toggle: the enabled count moved
            self.summaryChanged.emit(self.summary_text())

    def _on_delete_row(self, row: int) -> None:
        kind, record = self._model.row(row)
        with destructive_confirmation():
            reply = QMessageBox.question(
                self,
                "Delete record",
                f"Permanently delete {kind} '{record.ident}'? This cannot be undone. "
                f"(To keep it but exclude it from export, use the Enabled switch instead.)",
            )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if kind == "FIX":
            self._waypoint_service.delete(record.id)
        else:
            self._navaid_service.delete(record.id)
        # The row may have moved while the dialog was open only if the model
        # was reset; find it again by identity rather than trusting `row`.
        for visible in range(self._model.rowCount()):
            if self._model.row(visible)[1] is record:
                self._model.remove(visible)
                break
        self._after_change()
        if self._on_changed:
            self._on_changed("deleted")
