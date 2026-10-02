"""Verifies the Manage Data table's Enabled checkbox and Delete button
actually drive the correct service calls with the correct record id --
the earlier smoke test only confirmed these didn't crash, not that
toggling them produces the correct effect.

Clicks are real mouse events on the table (the table is a model/view
with a painted Delete button, see manage_data_view.py).
"""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QStyle, QStyleOptionViewItem

from flightgear_navdata_manager.infrastructure import config
from flightgear_navdata_manager.presentation.views.manage_data_view import (
    DELETE_COLUMN,
    ENABLED_COLUMN,
    ManageDataView,
)


def _shown(view):
    view.resize(900, 400)
    view.show()
    QTest.qWaitForWindowExposed(view)
    return view


def _text(view, row, column):
    return view._model.index(row, column).data()


def _checked(view, row):
    return view._model.index(row, ENABLED_COLUMN).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked


def _click_checkbox(view, row):
    table = view._table
    index = view._model.index(row, ENABLED_COLUMN)
    option = QStyleOptionViewItem()
    table.initViewItemOption(option)
    option.rect = table.visualRect(index)
    option.features |= QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
    box = table.style().subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, table)
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=box.center())


def _click_delete(view, row):
    rect = view._table.visualRect(view._model.index(row, DELETE_COLUMN))
    QTest.mouseClick(view._table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())


def test_checkbox_toggle_calls_set_enabled_and_updates_export(gui_env):
    ws = gui_env["waypoint_service"]
    ws.create("CHKBX", 10.0, 20.0)

    view = _shown(ManageDataView(ws, gui_env["navaid_service"]))
    assert view._model.rowCount() == 1
    assert _text(view, 0, 1) == "CHKBX"
    assert _checked(view, 0) is True
    assert "CHKBX" in config.FIX_DAT_OUTPUT.read_text()

    _click_checkbox(view, 0)  # the real user click
    assert _checked(view, 0) is False
    assert "CHKBX" not in config.FIX_DAT_OUTPUT.read_text()
    assert ws.list_all()[0].enabled is False

    _click_checkbox(view, 0)
    assert "CHKBX" in config.FIX_DAT_OUTPUT.read_text()
    assert ws.list_all()[0].enabled is True


def test_delete_button_asks_for_confirmation_and_deletes_on_yes(gui_env, monkeypatch):
    ws = gui_env["waypoint_service"]
    ws.create("DELME", 1.0, 1.0)
    ws.create("KEEP1", 2.0, 2.0)

    view = _shown(ManageDataView(ws, gui_env["navaid_service"]))
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda parent, title, text, *a, **k: (asked.append(text), QMessageBox.StandardButton.Yes)[1],
    )
    _click_delete(view, 0)

    assert "DELME" in asked[0]
    assert view._model.rowCount() == 1
    assert _text(view, 0, 1) == "KEEP1"
    assert [f.ident for f in ws.list_all()] == ["KEEP1"]
    assert "DELME" not in config.FIX_DAT_OUTPUT.read_text()


def test_delete_button_does_nothing_on_cancel(gui_env, monkeypatch):
    ws = gui_env["waypoint_service"]
    ws.create("KEEPME", 1.0, 1.0)

    view = _shown(ManageDataView(ws, gui_env["navaid_service"]))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    _click_delete(view, 0)

    assert view._model.rowCount() == 1
    assert len(ws.list_all()) == 1
    assert "KEEPME" in config.FIX_DAT_OUTPUT.read_text()


def test_deleting_last_record_shows_empty_state(gui_env, monkeypatch):
    ws = gui_env["waypoint_service"]
    ws.create("LAST1", 1.0, 1.0)
    view = _shown(ManageDataView(ws, gui_env["navaid_service"]))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    _click_delete(view, 0)
    assert view._empty_state_label.isHidden() is False
    assert view._table.isHidden() is True


def test_empty_state_shown_when_no_records_and_hidden_once_one_exists(gui_env):
    # NOTE: QWidget.isVisible() reflects on-screen visibility, which
    # requires the whole ancestor chain (including a shown top-level
    # window) to be visible -- always False for a widget that's never
    # been shown, regardless of setVisible() calls. isHidden() reflects
    # the widget's own explicit visibility flag directly, which is what
    # we actually want to assert here.
    view = ManageDataView(gui_env["waypoint_service"], gui_env["navaid_service"])
    assert view._empty_state_label.isHidden() is False
    assert view._table.isHidden() is True

    gui_env["waypoint_service"].create("ANY01", 1.0, 1.0)
    view.refresh()
    assert view._empty_state_label.isHidden() is True
    assert view._table.isHidden() is False


def test_navaid_rows_show_correct_kind_label(gui_env):
    ns = gui_env["navaid_service"]
    ns.create_ndb("NDB1", "N", 0.0, 0.0, 0, 362, 50)
    ns.create_vor("VOR1", "V", 0.0, 0.0, 0, 110.0, 100)
    ns.create_dme("DME1", "D", 0.0, 0.0, 0, 110.0, 25)

    view = ManageDataView(gui_env["waypoint_service"], ns)
    kinds = {_text(view, row, 1): _text(view, row, 0) for row in range(view._model.rowCount())}
    assert kinds == {"NDB1": "NDB", "VOR1": "VOR", "DME1": "DME"}


def test_row_columns(gui_env):
    gui_env["navaid_service"].create_vor("ABC", "ALPHA", 37.5, -122.25, 10, 114.1, 40)
    view = ManageDataView(gui_env["waypoint_service"], gui_env["navaid_service"])
    assert [_text(view, 0, c) for c in range(6)] == [
        "VOR", "ABC", "ALPHA VOR", "37.500000", "-122.250000", "Custom",
    ]
    assert _text(view, 0, DELETE_COLUMN) == "Delete"
