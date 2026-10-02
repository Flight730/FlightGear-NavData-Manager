"""MainWindow shell: sidebar navigation, Go menu, shared FlightGear
detection, DataEvents wiring, record count, focus and geometry."""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QMessageBox, QPushButton

from flightgear_navdata_manager.presentation import theme
from flightgear_navdata_manager.presentation.data_events import ChangeKind, DataEvents
from flightgear_navdata_manager.presentation.main_window import (
    ADD_NAVAID,
    ADD_WAYPOINT,
    DASHBOARD,
    IMPORT,
    MANAGE_DATA,
    MainWindow,
)
from flightgear_navdata_manager.presentation.views.manage_data_view import ENABLED_COLUMN


def _events(window):
    seen = []
    window.data_events.changed.connect(lambda change: seen.append(change.kind))
    return seen


def _add_fix(window, ident="SBTST"):
    form = window.add_fix_form
    form._ident_edit.setText(ident)
    form._lat_spin.setValue(10.0)
    form._lon_spin.setValue(20.0)
    form._on_submit()


# -- navigation ---------------------------------------------------------------

def test_starts_on_dashboard_with_all_five_pages(make_window):
    window = make_window()
    labels = [item.text() for item in window.sidebar.items()]
    assert labels == ["Dashboard", "Import", "Manage Data", "Add Waypoint", "Add Navaid"]
    assert window.current_page() == DASHBOARD
    assert window.sidebar.current_index() == DASHBOARD


def test_sidebar_click_switches_page(make_window):
    window = make_window()
    window.show()
    QTest.qWaitForWindowExposed(window)
    item = window.sidebar.items()[ADD_WAYPOINT]
    QTest.mouseClick(item, Qt.MouseButton.LeftButton)
    assert window.current_page() == ADD_WAYPOINT
    assert item.isChecked()
    assert [i.isChecked() for i in window.sidebar.items()].count(True) == 1


def test_go_menu_has_command_shortcuts_for_every_page(make_window):
    window = make_window()
    assert [a.text() for a in window.go_actions] == [i.text() for i in window.sidebar.items()]
    assert [a.shortcut().toString() for a in window.go_actions] == [f"Ctrl+{n}" for n in range(1, 6)]
    for index in (MANAGE_DATA, ADD_NAVAID, IMPORT, DASHBOARD):
        window.go_actions[index].trigger()
        assert window.current_page() == index
        assert window.sidebar.current_index() == index


def test_show_page_by_view(make_window):
    window = make_window()
    window.show_page(window.add_nav_form)
    assert window.current_page() == ADD_NAVAID
    with pytest.raises(ValueError):
        window.show_page(QPushButton())


# -- FlightGear detection -------------------------------------------------------

def test_detection_runs_once_and_is_shared(make_window):
    window = make_window()
    assert window.fake_install.calls == 1
    assert window.sidebar.status_text() == "FlightGear 2024.1.6"
    assert "2024.1.6" in window.dashboard_view._status_headline_label.text()

    window.fake_install.found = False
    window.dashboard_view.refresh_detection()     # the Dashboard's Re-scan
    assert window.fake_install.calls == 2
    assert window.sidebar.status_text() == "FlightGear not found"
    assert "not detected" in window.dashboard_view._status_headline_label.text()


# -- DataEvents and the record count ----------------------------------------------

def test_record_count_in_sidebar_follows_adds_and_deletes(make_window, monkeypatch):
    window = make_window()
    manage = window.sidebar.items()[MANAGE_DATA]
    assert manage.count_text() == "0"
    seen = _events(window)

    _add_fix(window, "SBONE")
    _add_fix(window, "SBTWO")
    assert manage.count_text() == "2"
    assert window.manage_view._model.rowCount() == 2     # Manage Data refreshed
    assert seen == [ChangeKind.RECORD_ADDED, ChangeKind.RECORD_ADDED]

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.manage_view._on_delete_row(0)
    assert manage.count_text() == "1"
    assert seen[-1] == ChangeKind.RECORD_DELETED


def test_toggle_notifies_without_reloading_manage_data(make_window, monkeypatch):
    window = make_window()
    _add_fix(window)
    seen = _events(window)
    reloads = []
    monkeypatch.setattr(window.manage_view, "refresh", lambda: reloads.append(True))

    index = window.manage_view._model.index(0, ENABLED_COLUMN)
    window.manage_view._model.setData(index, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)

    assert seen == [ChangeKind.RECORD_TOGGLED]
    assert reloads == []
    assert window.sidebar.items()[MANAGE_DATA].count_text() == "1"
    assert window.manage_view._waypoint_service.list_all()[0].enabled is False


def test_import_and_regenerate_notify(make_window, monkeypatch):
    window = make_window()
    seen = _events(window)
    reloads = []
    monkeypatch.setattr(window.manage_view, "refresh", lambda: reloads.append(True))

    window.import_view._on_imported()
    assert seen == [ChangeKind.RECORDS_IMPORTED]
    assert reloads == [True]

    regenerate = next(b for b in window.dashboard_view.findChildren(QPushButton) if b.text() == "Regenerate now")
    regenerate.click()
    assert seen[-1] == ChangeKind.EXPORT_REGENERATED
    assert reloads == [True]          # an export doesn't change the records list


def test_change_kinds():
    assert ChangeKind.RECORD_ADDED.changes_records
    assert not ChangeKind.EXPORT_REGENERATED.changes_records
    events = DataEvents()
    got = []
    events.changed.connect(got.append)
    events.notify(ChangeKind.RECORD_DELETED, "src")
    assert got[0].kind is ChangeKind.RECORD_DELETED and got[0].source == "src"


# -- window behavior -------------------------------------------------------------

def test_default_and_minimum_size(make_window):
    window = make_window()
    assert window.size() == QSize(1200, 780)
    assert window.minimumSize() == QSize(980, 640)


def test_geometry_is_saved_and_restored(make_window):
    window = make_window()
    window.show()
    QTest.qWaitForWindowExposed(window)
    window.resize(1100, 700)
    window.close()

    reopened = make_window()
    assert reopened.size() == QSize(1100, 700)


def test_no_page_button_takes_initial_focus(make_window, qapp):
    old_sheet, old_palette = qapp.styleSheet(), qapp.palette()
    theme.apply_theme(qapp)
    try:
        window = make_window()
        window.show()
        QTest.qWaitForWindowExposed(window)
        for index in range(5):
            window.set_current_page(index)
            assert not isinstance(window.focusWidget(), QAbstractButton), index
        buttons = window.findChildren(QPushButton)
        assert buttons and all(b.focusPolicy() == Qt.FocusPolicy.TabFocus for b in buttons)
    finally:
        qapp.setStyleSheet(old_sheet)
        qapp.setPalette(old_palette)


def test_every_page_fits_the_window_width_at_minimum_size(make_window):
    """Regression: an unwrapped Dashboard label made the page wider than
    the window, clipping it at the right edge."""
    from PySide6.QtWidgets import QLabel, QScrollArea

    window = make_window()
    window.resize(window.minimumSize())
    window.show()
    QTest.qWaitForWindowExposed(window)
    for index, page in enumerate(window._pages):
        window.set_current_page(index)
        QTest.qWait(10)
        viewport = page.findChild(QScrollArea, "PageScroll").viewport()
        assert page.content.width() <= viewport.width(), index
        for label in page.content.findChildren(QLabel):
            if label.isVisible():
                right = label.mapTo(page.content, label.rect().topRight()).x()
                assert right <= viewport.width(), (index, label.text()[:40])
