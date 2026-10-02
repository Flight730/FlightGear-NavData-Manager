"""Step 6 Manage Data rebuild: search / type / source filters with live
counts, footer, empty and no-results states, record identity under
filtering (toggle and delete always hit the record shown), painted
toggle/delete hit regions, keyboard, layout at both window sizes, a
~70,000-record dataset, and DataEvents / Dashboard / sidebar updates."""

import re
import time
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QScrollArea, QWidget

from flightgear_navdata_manager.application.navaid_service import build_dme, build_ndb, build_vor
from flightgear_navdata_manager.domain.models import DataSource, Fix
from flightgear_navdata_manager.infrastructure import config
from flightgear_navdata_manager.presentation.components.record_table import delete_rect, toggle_rect
from flightgear_navdata_manager.presentation.data_events import ChangeKind
from flightgear_navdata_manager.presentation.main_window import DASHBOARD, MANAGE_DATA
from flightgear_navdata_manager.presentation.theme.tokens import COLORS
from flightgear_navdata_manager.presentation.views.manage_data_view import (
    DELETE_COLUMN,
    ENABLED_COLUMN,
    ManageDataView,
)

IMPORTED = DataSource.IMPORTED


def _fix(ident, source=DataSource.CUSTOM):
    return Fix(id=None, source=source, enabled=True, created_at=datetime.now(timezone.utc),
               ident=ident, latitude=10.0, longitude=20.0)


@pytest.fixture
def seeded(gui_env):
    """Eight records across every kind and both sources."""
    fixes, navaids = gui_env["fix_repo"], gui_env["navaid_repo"]
    fixes.add(_fix("ALPHA"))
    fixes.add(_fix("BRAVO", IMPORTED))
    fixes.add(_fix("CHRLY", IMPORTED))
    navaids.add(build_ndb("ALP", "Alpine", 1, 2, 0, 375, 50))
    navaids.add(build_ndb("NDA", "Bravo Hill", 1, 3, 0, 380, 50, source=IMPORTED))
    navaids.add(build_vor("VRA", "Alpha Peak", 1, 4, 0, 113.2, 130, source=IMPORTED))
    navaids.add(build_vor("VCU", "Custom One", 1, 5, 0, 114.1, 130))
    navaids.add(build_dme("DMA", "Delta", 1, 6, 0, 115.3, 25, source=IMPORTED))
    gui_env["export_service"].regenerate()
    return gui_env


def _view(env, **kwargs):
    view = ManageDataView(env["waypoint_service"], env["navaid_service"], **kwargs)
    view.resize(1000, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    return view


def _idents(view):
    return [view._model.row(r)[1].ident for r in range(view._model.rowCount())]


def _filter(view, kind=0, source=0, text=""):
    view._kind_filter.setCurrentIndex(kind)
    view._source_filter.setCurrentIndex(source)
    view._search_edit.setText(text)
    view._apply_filters()            # what the debounce timer / Enter would do


def _click(view, row, column, at="center"):
    rect = view._table.visualRect(view._model.index(row, column))
    point = {"toggle": toggle_rect(rect).center(), "delete": delete_rect(rect).center(),
             "center": rect.center(), "edge": QPoint(rect.right() - 2, rect.center().y())}[at]
    QTest.mouseClick(view._table.viewport(), Qt.MouseButton.LeftButton, pos=point)


def _all_db_idents(env):
    return sorted([f.ident for f in env["waypoint_service"].list_all()]
                  + [n.ident for n in env["navaid_service"].list_all()])


def _yes(monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda p, t, text, *a, **k: (asked.append(text), QMessageBox.StandardButton.Yes)[1])
    return asked


# -- 1-8: filtering, counts, footer ------------------------------------------------

def test_all_records_with_total_footer_and_summary(seeded):
    view = _view(seeded)
    assert view._model.rowCount() == 8
    assert view._footer.text() == "Showing 8 of 8"
    assert view.summary_text() == "8 records · 8 enabled"
    assert view._kind_filter.itemText(0) == "All  8"


def test_type_filter(seeded):
    view = _view(seeded)
    _filter(view, kind=1)
    assert sorted(_idents(view)) == ["ALPHA", "BRAVO", "CHRLY"]
    _filter(view, kind=3)
    assert sorted(_idents(view)) == ["VCU", "VRA"]
    assert view._footer.text() == "Showing 2 of 8"


def test_source_filter(seeded):
    view = _view(seeded)
    _filter(view, source=1)
    assert sorted(_idents(view)) == ["ALP", "ALPHA", "VCU"]
    _filter(view, source=2)
    assert sorted(_idents(view)) == ["BRAVO", "CHRLY", "DMA", "NDA", "VRA"]


def test_search_by_ident_and_by_name_case_insensitive(seeded):
    view = _view(seeded)
    _filter(view, text="brav")
    assert sorted(_idents(view)) == ["BRAVO", "NDA"]          # ident BRAVO, name "Bravo Hill"
    _filter(view, text="ALPHA")
    assert sorted(_idents(view)) == ["ALPHA", "VRA"]          # ident ALPHA, name "Alpha Peak"
    _filter(view, text="  delta ")
    assert _idents(view) == ["DMA"]
    _filter(view, text="")
    assert view._model.rowCount() == 8


def test_search_combined_with_type_and_source(seeded):
    view = _view(seeded)
    _filter(view, kind=0, source=2, text="alp")               # imported + "alp"
    assert _idents(view) == ["VRA"]
    _filter(view, kind=2, source=1, text="alp")               # custom NDB + "alp"
    assert _idents(view) == ["ALP"]
    _filter(view, kind=1, source=1, text="alp")               # custom FIX + "alp"
    assert _idents(view) == ["ALPHA"]


def test_kind_counts_follow_source_and_search(seeded):
    view = _view(seeded)
    texts = lambda: [view._kind_filter.itemText(i) for i in range(5)]   # noqa: E731
    assert texts() == ["All  8", "Fixes  3", "NDB  2", "VOR  2", "DME  1"]
    _filter(view, source=2, text="")
    assert texts() == ["All  5", "Fixes  2", "NDB  1", "VOR  1", "DME  1"]
    _filter(view, source=0, text="alp")
    assert texts() == ["All  3", "Fixes  1", "NDB  1", "VOR  1", "DME  0"]   # ALPHA, ALP, VRA ("Alpha Peak")


def test_search_is_debounced_and_enter_or_escape_act_at_once(seeded):
    view = _view(seeded)
    QTest.keyClicks(view._search_edit, "delta")
    assert view._model.rowCount() == 8                        # not yet: debounced
    QTest.qWait(260)
    assert _idents(view) == ["DMA"]
    view._search_edit.setText("bravo")
    QTest.keyClick(view._search_edit, Qt.Key.Key_Return)
    assert sorted(_idents(view)) == ["BRAVO", "NDA"]          # NDA by its name, "Bravo Hill"
    QTest.keyClick(view._search_edit, Qt.Key.Key_Escape)
    assert view._search_edit.text() == "" and view._model.rowCount() == 8


# -- 9-12: identity under filtering ------------------------------------------------------

def test_toggling_a_filtered_row_changes_exactly_that_record(seeded):
    view = _view(seeded)
    _filter(view, kind=3, source=2)                           # imported VORs: only VRA
    assert _idents(view) == ["VRA"]
    _click(view, 0, ENABLED_COLUMN, at="toggle")
    states = {n.ident: n.enabled for n in seeded["navaid_service"].list_all()}
    assert states == {"ALP": True, "NDA": True, "VRA": False, "VCU": True, "DMA": True}
    assert all(f.enabled for f in seeded["waypoint_service"].list_all())
    assert " VRA " not in config.NAV_DAT_OUTPUT.read_text()
    assert view.summary_text() == "8 records · 7 enabled"


@pytest.mark.parametrize("filters, expected_visible, target", [
    (dict(kind=2, source=1), ["ALP"], "ALP"),                       # type + source
    (dict(text="bravo"), ["BRAVO", "NDA"], "NDA"),                  # search (2nd visible row)
    (dict(kind=0, source=2, text="a"), None, "DMA"),                # source + search
    (dict(kind=4, source=2, text="del"), ["DMA"], "DMA"),           # all three
])
def test_deleting_a_filtered_row_deletes_exactly_that_record(seeded, monkeypatch, filters, expected_visible, target):
    view = _view(seeded)
    _filter(view, **filters)
    if expected_visible is not None:
        assert sorted(_idents(view)) == sorted(expected_visible)
    row = _idents(view).index(target)
    asked = _yes(monkeypatch)
    before = _all_db_idents(seeded)
    _click(view, row, DELETE_COLUMN, at="delete")

    assert f"'{target}'" in asked[0]
    assert _all_db_idents(seeded) == sorted(i for i in before if i != target)
    assert target not in _idents(view)
    assert view._model.total_count() == 7
    assert view._footer.text() == f"Showing {view._model.rowCount()} of 7"
    output = config.FIX_DAT_OUTPUT.read_text() + config.NAV_DAT_OUTPUT.read_text()
    assert not re.search(rf"\b{target}\b", output)            # whole word: ALP must not match ALPHA


def test_delete_key_uses_the_current_row_with_confirmation(seeded, monkeypatch):
    view = _view(seeded)
    _filter(view, text="chrly")
    view._table.setCurrentIndex(view._model.index(0, 1))
    view._table.setFocus()
    asked = _yes(monkeypatch)
    QTest.keyClick(view._table, Qt.Key.Key_Delete)
    assert "'CHRLY'" in asked[0]
    assert "CHRLY" not in _all_db_idents(seeded)


# -- painted hit regions --------------------------------------------------------------------

def test_clicks_outside_the_switch_or_icon_only_select(seeded):
    view = _view(seeded)
    _click(view, 0, ENABLED_COLUMN, at="edge")
    _click(view, 0, DELETE_COLUMN, at="edge")       # the autouse guard fails on any dialog
    _click(view, 1, 2)                              # plain cell: selects
    assert all(n.enabled for n in seeded["navaid_service"].list_all())
    assert len(_all_db_idents(seeded)) == 8
    assert view._table.currentIndex().row() == 1


def test_delete_needs_press_and_release_on_the_icon(seeded):
    view = _view(seeded)
    rect = view._table.visualRect(view._model.index(0, DELETE_COLUMN))
    vp = view._table.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=delete_rect(rect).center())
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=QPoint(rect.left() + 2, rect.center().y()))
    assert len(_all_db_idents(seeded)) == 8          # dragged off: no dialog, nothing deleted


def test_row_painting(seeded, themed):
    view = _view(seeded)
    seeded["waypoint_service"].set_enabled(seeded["waypoint_service"].list_all()[0].id, False)
    view.refresh()
    QTest.qWait(20)
    image = view._table.viewport().grab().toImage()
    dpr = image.devicePixelRatio()

    def color_at(row, column, where):
        rect = view._table.visualRect(view._model.index(row, column))
        r = toggle_rect(rect) if where == "toggle" else delete_rect(rect)
        point = r.center() if where == "delete" else QPoint(r.left() + 5, r.center().y())
        return image.pixelColor(int(point.x() * dpr), int(point.y() * dpr))

    off_row = _idents(view).index("ALPHA")
    on_row = _idents(view).index("BRAVO")
    assert color_at(on_row, ENABLED_COLUMN, "toggle").name() == COLORS.accent        # on: teal track
    assert color_at(off_row, ENABLED_COLUMN, "toggle").name() != COLORS.accent       # off: dark track
    # Hovering the trash icon tints it red.
    rect = delete_rect(view._table.visualRect(view._model.index(0, DELETE_COLUMN)))
    view._table.hover_pos = rect.center()
    view._table.hover_row = 0
    hot = view._table.viewport().grab().toImage()
    red = [hot.pixelColor(int(x * dpr), int(rect.center().y() * dpr)) for x in range(rect.left(), rect.right())]
    assert any(c.red() > 180 and c.green() < 140 for c in red)
    # No widgets in cells.
    assert all(view._table.indexWidget(view._model.index(r, c)) is None
               for r in range(view._model.rowCount()) for c in range(8))
    assert view._table.verticalHeader().defaultSectionSize() == 36
    assert not view._table.showGrid() and not view._table.alternatingRowColors()


# -- 13-15: empty and no-results states --------------------------------------------------

def test_empty_database_state_offers_navigation(gui_env):
    targets = []
    view = _view(gui_env, on_navigate=targets.append)
    assert not view._empty_state_label.isHidden()
    assert view._table.isHidden() and view._no_results.isHidden() and view._toolbar.isHidden()
    labels = [b.text() for b in view._empty_state_label.buttons]
    assert labels == ["Import data", "Add waypoint"]
    for button in view._empty_state_label.buttons:
        button.click()
    assert targets == ["import", "add_waypoint"]


def test_no_results_state_is_distinct_and_clear_filters_restores(seeded):
    view = _view(seeded)
    _filter(view, kind=4, text="zzz")
    assert view._model.rowCount() == 0
    assert not view._no_results.isHidden()
    assert view._empty_state_label.isHidden()               # records do exist
    assert view._table.isHidden() and not view._toolbar.isHidden()
    assert view._footer.text() == "Showing 0 of 8"
    [clear] = view._no_results.buttons
    clear.click()
    assert view._model.rowCount() == 8 and view._search_edit.text() == ""
    assert view._kind_filter.currentIndex() == 0 and view._source_filter.currentIndex() == 0
    assert view._no_results.isHidden() and not view._table.isHidden()


# -- 16, 18-19, 21-22: in the window -----------------------------------------------------------

def test_command_f_focuses_search_only_on_this_page(make_window, seeded):
    window = make_window()
    window.show()
    QTest.qWaitForWindowExposed(window)
    QTest.qWait(10)
    window.set_current_page(MANAGE_DATA)
    QTest.qWait(10)
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert window.focusWidget() is window.manage_view._search_edit
    window.set_current_page(DASHBOARD)
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert window.focusWidget() is not window.manage_view._search_edit


def test_first_load_happens_after_the_window_is_built(make_window, seeded):
    window = make_window()
    assert window.manage_view._model.total_count() == 0          # not loaded during construction
    assert not window.manage_view._loading_label.isHidden()
    QTest.qWait(10)                                               # one event-loop pass
    assert window.manage_view._model.total_count() == 8
    assert window._pages[MANAGE_DATA].description_label.text() == "8 records · 8 enabled"


@pytest.mark.parametrize("size", ["minimum", "default"])
def test_layout_fits(make_window, seeded, themed, size):
    window = make_window()
    if size == "minimum":
        window.resize(window.minimumSize())
    window.show()
    QTest.qWaitForWindowExposed(window)
    window.set_current_page(MANAGE_DATA)
    QTest.qWait(30)
    view = window.manage_view
    viewport = window._pages[MANAGE_DATA].findChild(QScrollArea, "PageScroll").viewport()
    for widget in (view._search_edit, view._source_filter, view._refresh_btn, view._kind_filter,
                   view._table, view._footer):
        right = widget.mapTo(view, widget.rect().topRight()).x()
        assert right <= viewport.width(), widget
        assert not widget.visibleRegion().isEmpty(), widget
    header = view._table.horizontalHeader()
    assert header.sectionSize(2) >= 90                            # Name keeps usable room
    assert view._table.horizontalScrollBar().maximum() == 0       # no sideways scrolling


def test_toggle_and_delete_update_events_dashboard_and_sidebar(make_window, seeded, monkeypatch):
    window = make_window()
    window.show()
    QTest.qWaitForWindowExposed(window)
    window.set_current_page(MANAGE_DATA)
    QTest.qWait(20)
    view = window.manage_view
    kinds = []
    window.data_events.changed.connect(lambda c: kinds.append(c.kind))

    _filter(view, text="vcu")
    _click(view, 0, ENABLED_COLUMN, at="toggle")
    assert kinds == [ChangeKind.RECORD_TOGGLED]
    assert window.dashboard_view.stat_cards["records"].detail_text() == "7 enabled · 1 disabled"
    assert window._pages[MANAGE_DATA].description_label.text() == "8 records · 7 enabled"

    _yes(monkeypatch)
    _click(view, 0, DELETE_COLUMN, at="delete")
    assert kinds[-1] == ChangeKind.RECORD_DELETED
    assert window.sidebar.items()[MANAGE_DATA].count_text() == "7"
    assert window.dashboard_view.stat_cards["records"].value_text() == "7"
    assert window.dashboard_view.stat_cards["navaids"].detail_text().replace("\u00a0", " ") == \
        "NDB 2 · VOR 1 · DME 1"
    assert window._pages[MANAGE_DATA].description_label.text() == "7 records · 7 enabled"


# -- 20: ~70,000 records ------------------------------------------------------------------------

class _BigServices:
    """In-memory stand-ins for the two services with ~70,000 fixes, so the
    view is exercised at full FAA scale without a database."""

    def __init__(self, n):
        stamp = datetime.now(timezone.utc)
        self.fixes = [Fix(id=i + 1, source=IMPORTED, enabled=True, created_at=stamp,
                          ident=f"F{i:05d}", latitude=(i % 180) - 90.0, longitude=(i % 360) - 180.0)
                      for i in range(n)]
        self.deleted, self.toggled = [], []

    def list_all(self):
        return list(self.fixes)

    def set_enabled(self, record_id, enabled):
        self.toggled.append((record_id, enabled))

    def delete(self, record_id):
        self.deleted.append(record_id)
        self.fixes = [f for f in self.fixes if f.id != record_id]


class _NoNavaids:
    def list_all(self):
        return []


def test_seventy_thousand_records(qapp, monkeypatch):
    big = _BigServices(70_000)
    start = time.perf_counter()
    view = ManageDataView(big, _NoNavaids())
    load_s = time.perf_counter() - start
    view.resize(1000, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)

    assert view._model.total_count() == 70_000 and view._footer.text() == "Showing 70,000 of 70,000"
    # Painted, not built: the view owns a fixed handful of widgets, not one per row.
    assert len(view.findChildren(QWidget)) < 150
    assert view._table.indexWidget(view._model.index(69_999, ENABLED_COLUMN)) is None

    timings = []
    for text in ("F6", "F69", "F69999", "nomatch", ""):
        t = time.perf_counter()
        _filter(view, text=text)
        timings.append(time.perf_counter() - t)
    assert view._model.rowCount() == 70_000
    _filter(view, text="F69999")
    assert _idents(view) == ["F69999"]

    # Identity at scale: delete the one visible match; the right id goes.
    asked = _yes(monkeypatch)
    view._on_delete_row(0)
    assert "'F69999'" in asked[0] and big.deleted == [70_000]
    assert view._model.total_count() == 69_999
    _filter(view, text="F12345")
    view._model.setData(view._model.index(0, ENABLED_COLUMN), Qt.CheckState.Unchecked.value,
                        Qt.ItemDataRole.CheckStateRole)
    assert big.toggled == [(12_346, False)]

    # Generous bounds: catch accidental quadratic work, not machine speed.
    assert load_s < 5.0, load_s
    assert max(timings) < 1.0, timings


def test_states_without_the_table_keep_their_proportions(seeded, gui_env, themed):
    """Regressions: with the table hidden the type filter stretched to fill
    the page, and the empty state's wrapped text was clipped."""
    view = _view(seeded)
    _filter(view, kind=4, text="zzzz")
    QTest.qWait(20)
    seg = view._kind_filter
    assert seg.height() <= seg.sizeHint().height() + 2

    empty = ManageDataView(gui_env["waypoint_service"], gui_env["navaid_service"], on_navigate=lambda t: None)
    for record in gui_env["waypoint_service"].list_all():
        gui_env["waypoint_service"].delete(record.id)
    for record in gui_env["navaid_service"].list_all():
        gui_env["navaid_service"].delete(record.id)
    empty.refresh()
    empty.resize(1000, 600)
    empty.show()
    QTest.qWaitForWindowExposed(empty)
    QTest.qWait(20)
    label = empty._empty_state_label.text_label
    assert label.height() >= label.heightForWidth(label.width())
