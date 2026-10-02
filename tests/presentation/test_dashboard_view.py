"""Dashboard: live statistics through DataEvents, installation card,
scenery output card and the inline Regenerate error banner."""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox

from flightgear_navdata_manager.application import export_navdata
from flightgear_navdata_manager.infrastructure import config
from flightgear_navdata_manager.presentation.data_events import ChangeKind
from flightgear_navdata_manager.presentation.views.manage_data_view import ENABLED_COLUMN

FIX_CSV = Path(__file__).parent.parent / "infrastructure" / "fixtures" / "sample_faa_fix.csv"


def _stats(window):
    cards = window.dashboard_view.stat_cards
    return {name: (card.value_text(), card.detail_text().replace("\u00a0", " "))
            for name, card in cards.items()}


def _add_fix(window, ident):
    form = window.add_fix_form
    form._ident_edit.setText(ident)
    form._lat_spin.setValue(10.0)
    form._lon_spin.setValue(20.0)
    form._on_submit()


def _add_navaid(window, type_index, ident, freq_widget, freq):
    form = window.add_nav_form
    form._type_combo.setCurrentIndex(type_index)
    form._ident_edit.setText(ident)
    form._name_edit.setText("Dash")
    form._lat_spin.setValue(11.0 + type_index)
    form._lon_spin.setValue(21.0)
    getattr(form, freq_widget).setValue(freq)
    form._on_submit()


def test_empty_database(make_window):
    stats = _stats(make_window())
    assert stats["records"] == ("0", "0 enabled · 0 disabled")
    assert stats["waypoints"] == ("0", "0 custom · 0 imported")
    assert stats["navaids"] == ("0", "NDB 0 · VOR 0 · DME 0")
    assert stats["export"][0] == "Not written"


def test_dashboard_follows_every_kind_of_change(make_window, monkeypatch):
    window = make_window()
    kinds = []
    window.data_events.changed.connect(lambda c: kinds.append(c.kind))

    # 1. add a FIX
    _add_fix(window, "DSHA")
    stats = _stats(window)
    assert stats["records"] == ("1", "1 enabled · 0 disabled")
    assert stats["waypoints"] == ("1", "1 custom · 0 imported")
    assert stats["export"] == ("Up to date", "Last written just now")

    # 2. add an NDB, a VOR and a DME
    _add_navaid(window, 0, "DSN", "_ndb_freq_khz", 375)
    _add_navaid(window, 1, "DSV", "_vor_freq_mhz", 113.2)
    _add_navaid(window, 2, "DSD", "_dme_freq_mhz", 113.4)
    stats = _stats(window)
    assert stats["navaids"] == ("3", "NDB 1 · VOR 1 · DME 1")
    assert stats["records"] == ("4", "4 enabled · 0 disabled")

    # 3. import records (the real Import Dataset path: pick, confirm, apply)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(FIX_CSV), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.import_view._dataset_btn.click()
    stats = _stats(window)
    assert stats["waypoints"] == ("7", "1 custom · 6 imported")
    assert stats["records"] == ("10", "10 enabled · 0 disabled")

    # 4. toggle a record off in Manage Data
    model = window.manage_view._model
    model.setData(model.index(0, ENABLED_COLUMN), Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)
    assert _stats(window)["records"] == ("10", "9 enabled · 1 disabled")

    # 5. delete it
    window.manage_view._on_delete_row(0)
    assert _stats(window)["records"] == ("9", "9 enabled · 0 disabled")

    # 6. regenerate: the last-written time moves
    old = (datetime.now() - timedelta(days=3)).timestamp()
    for path in (config.FIX_DAT_OUTPUT, config.NAV_DAT_OUTPUT):
        os.utime(path, (old, old))
    window.dashboard_view.refresh_stats()
    assert _stats(window)["export"][1].startswith("Last written 20")      # an older date
    regenerate = window.dashboard_view._regenerate_btn
    regenerate.click()
    assert _stats(window)["export"] == ("Up to date", "Last written just now")

    assert kinds == [ChangeKind.RECORD_ADDED] * 4 + [
        ChangeKind.RECORDS_IMPORTED, ChangeKind.RECORD_TOGGLED,
        ChangeKind.RECORD_DELETED, ChangeKind.EXPORT_REGENERATED,
    ]


def test_regenerate_failure_shows_inline_error_and_is_logged(make_window, monkeypatch, caplog):
    window = make_window()
    dashboard = window.dashboard_view
    kinds = []
    window.data_events.changed.connect(lambda c: kinds.append(c.kind))
    failure = PermissionError(13, "Permission denied", "/blocked/NavData/fix/custom.dat")

    def fail(*a):
        raise failure
    # Scoped, so ending it doesn't also undo gui_env's output-path redirect.
    with monkeypatch.context() as patch, caplog.at_level(logging.ERROR):
        patch.setattr(export_navdata, "write_fix_dat", fail)
        dashboard._regenerate_btn.click()        # must not raise, and no pop-up (autouse guard)

    banner = dashboard.status_banner
    assert not banner.isHidden() and banner.tone() == "danger"
    assert "Permission denied" in banner.text_label.text()
    assert "/blocked/NavData/fix/custom.dat" in banner.text_label.text()
    assert dashboard.last_regenerate_error is failure
    logged = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert logged and logged[0].exc_info[1] is failure
    assert _stats(window)["export"][0] == "Failed"
    assert kinds == []                           # nothing was regenerated

    dashboard._regenerate_btn.click()
    assert banner.tone() == "success" and banner.text_label.text() == "Custom NavData files regenerated."
    assert dashboard.last_regenerate_error is None
    assert _stats(window)["export"][0] == "Up to date"


def test_installation_card_found_and_not_found(make_window):
    window = make_window()
    dashboard = window.dashboard_view
    assert dashboard._install_pill.text() == "Detected"
    assert dashboard._status_headline_label.text() == "FlightGear 2024.1.6"
    assert dashboard._not_found_help.isHidden()
    assert dashboard._app_bundle_label.text() == "/Applications/FlightGear.app"

    window.fake_install.found = False
    dashboard._rescan_btn.click()
    assert window.fake_install.calls == 2
    assert (dashboard._install_pill.text(), dashboard._install_pill.tone()) == ("Not found", "warning")
    assert dashboard._status_headline_label.text() == "FlightGear not detected"
    assert not dashboard._not_found_help.isHidden()
    assert dashboard._fg_root_label.text() == "Not found"


def test_scenery_card_copy_path(make_window):
    dashboard = make_window().dashboard_view
    assert dashboard._scenery_path_field.isReadOnly()
    assert dashboard._scenery_path_field.text() == str(config.CUSTOM_SCENERY_DIR)
    copy = next(b for b in dashboard.findChildren(type(dashboard._regenerate_btn)) if b.text() == "Copy path")
    copy.click()
    assert QApplication.clipboard().text() == str(config.CUSTOM_SCENERY_DIR)
    assert dashboard.status_banner.text_label.text() == "Path copied to clipboard."


def test_safety_message_kept_and_long_description_removed(make_window):
    dashboard = make_window().dashboard_view
    assert not dashboard.safety_banner.isHidden()
    assert "never modified" in dashboard.safety_banner.text_label.text()
    texts = [label.text() for label in dashboard.findChildren(QLabel)]
    assert not any("lets you import, create, and manage" in t for t in texts)


def test_layout_adapts_to_window_width_and_stat_cards_line_up(make_window):
    from PySide6.QtTest import QTest

    window = make_window()
    window.show()
    QTest.qWaitForWindowExposed(window)
    dashboard = window.dashboard_view
    cards = list(dashboard.stat_cards.values())

    QTest.qWait(20)
    assert not dashboard.is_narrow()                     # default 1200x780
    assert len({c.geometry().top() for c in cards}) == 1
    assert len({c.height() for c in cards}) == 1         # one row, equal heights
    assert dashboard._install_card.geometry().top() == dashboard._scenery_card.geometry().top()

    window.resize(window.minimumSize())
    QTest.qWait(20)
    assert dashboard.is_narrow()
    assert len({c.geometry().top() for c in cards}) == 2   # 2 x 2
    assert dashboard._scenery_card.geometry().top() > dashboard._install_card.geometry().bottom()
