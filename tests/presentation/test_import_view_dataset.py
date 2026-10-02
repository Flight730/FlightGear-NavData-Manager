"""Import Dataset workflow in the Import tab: file/folder picker ->
analysis -> confirmation -> import -> summary in the log -> Manage Data
refreshed. Dialogs are monkeypatched so the tests drive the real button
handlers without blocking.
"""

import shutil
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from flightgear_navdata_manager.infrastructure import config
from flightgear_navdata_manager.presentation.views.import_view import ImportView
from flightgear_navdata_manager.presentation.views.manage_data_view import ManageDataView

FIXTURES = Path(__file__).parent.parent / "infrastructure" / "fixtures"
NAV_CSV = FIXTURES / "sample_faa_nav.csv"
FIX_CSV = FIXTURES / "sample_faa_fix.csv"


def _make_view(gui_env):
    manage = ManageDataView(gui_env["waypoint_service"], gui_env["navaid_service"])
    view = ImportView(
        gui_env["import_service"],
        on_imported=manage.refresh,
        dataset_service=gui_env["dataset_service"],
    )
    return view, manage


def _pick_file(monkeypatch, path):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))


def _pick_folder(monkeypatch, path):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(path))


def _answer(monkeypatch, button):
    asked = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda parent, title, text, *a, **k: (asked.append(text), button)[1],
    )
    return asked


def _capture(monkeypatch, name):
    shown = []
    monkeypatch.setattr(QMessageBox, name, lambda parent, title, text, *a, **k: shown.append((title, text)))
    return shown


def _manage_rows(manage):
    model = manage._model
    return {(model.index(r, 0).data(), model.index(r, 1).data()): model.index(r, 5).data()
            for r in range(model.rowCount())}


def test_selecting_a_supported_file_imports_after_confirmation(gui_env, monkeypatch):
    view, manage = _make_view(gui_env)
    _pick_file(monkeypatch, NAV_CSV)
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Yes)

    view._dataset_btn.click()

    assert "FAA effective date: 2026-09-03" in asked[0]
    assert "NAV: 9 new, 3 invalid rows, 2 unsupported" in asked[0]
    assert "Add 9 new record(s)" in asked[0]
    log = view._log.toPlainText()
    assert log.startswith("Dataset import complete")
    assert f"FAA NASR NAV (CSV): {NAV_CSV}" in log
    assert "Imported: 9\nDuplicates skipped: 0\nIdentifier conflicts: 0\nInvalid rows: 3" in log
    assert "sample_faa_nav.csv line 9: QCC NDB (Samplet, AK) -- no elevation in source" in log
    assert "Traceback" not in log
    rows = _manage_rows(manage)
    assert rows[("VOR", "QET")] == "Imported"
    assert len(rows) == 9
    assert "TESTER VORTAC DME" in config.NAV_DAT_OUTPUT.read_text()


def test_selecting_a_folder_imports_fix_and_nav_with_category_summary(gui_env, monkeypatch, tmp_path):
    shutil.copy(FIX_CSV, tmp_path / "FIX_BASE.csv")
    shutil.copy(NAV_CSV, tmp_path / "NAV_BASE.csv")
    (tmp_path / "unrelated.csv").write_text("a,b\n1,2\n")
    view, manage = _make_view(gui_env)
    _pick_folder(monkeypatch, tmp_path)
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)

    view._dataset_folder_btn.click()

    log = view._log.toPlainText()
    assert "FIX (6 records read)\n  Imported: 6" in log
    assert "NAV (11 records read)\n  Imported: 9" in log
    assert log.startswith("Dataset import complete\n\nRecords read: 17\nImported: 15\n")
    assert "Files not used (1):\n  1 x not a recognized navigation data file: unrelated.csv" in log
    assert manage._model.rowCount() == 15


def test_duplicate_summary_on_reimport_without_asking(gui_env, monkeypatch):
    view, _ = _make_view(gui_env)
    _pick_file(monkeypatch, FIX_CSV)
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    view._dataset_btn.click()

    infos = _capture(monkeypatch, "information")
    view._dataset_btn.click()

    assert len(asked) == 1  # nothing new, so no second confirmation
    assert infos[0][0] == "Nothing new to import"
    assert "FIX: 0 new, 6 duplicates skipped" in infos[0][1]
    log = view._log.toPlainText()
    assert "Duplicates skipped: 6" in log
    assert "Duplicates skipped (already in your data):" in log
    assert "QXALL FIX (MA) -- Exact duplicate of FIX QXALL (imported)" in log
    assert len(gui_env["waypoint_service"].list_all()) == 6


def test_conflict_summary_lists_both_positions_and_keeps_existing(gui_env, monkeypatch):
    ws = gui_env["waypoint_service"]
    ws.create("QXALL", 33.70, -60.14)
    view, manage = _make_view(gui_env)
    _pick_file(monkeypatch, FIX_CSV)
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Yes)

    view._dataset_btn.click()

    assert "FIX: 5 new, 1 identifier conflicts" in asked[0]
    log = view._log.toPlainText()
    assert "Identifier conflicts: 1" in log
    assert ("Identifier conflict: FIX QXALL (custom) at 33.700000, -60.140000 -- 34.8 nm away; "
            "this record is at 33.120189, -60.141761") in log
    qxall = [f for f in ws.list_all() if f.ident == "QXALL"]
    assert [(f.latitude, f.source.value) for f in qxall] == [(33.70, "custom")]
    assert _manage_rows(manage)[("FIX", "QXALL")] == "Custom"


def test_cancel_at_confirmation_stores_nothing(gui_env, monkeypatch):
    view, manage = _make_view(gui_env)
    _pick_file(monkeypatch, NAV_CSV)
    _answer(monkeypatch, QMessageBox.StandardButton.No)

    view._dataset_btn.click()

    assert gui_env["navaid_service"].list_all() == []
    assert manage._model.rowCount() == 0
    assert view._log.toPlainText().startswith("Import cancelled: nothing was added")


def test_picker_cancel_does_nothing(gui_env, monkeypatch):
    view, _ = _make_view(gui_env)
    _pick_file(monkeypatch, "")
    _pick_folder(monkeypatch, "")
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    view._dataset_btn.click()
    view._dataset_folder_btn.click()
    assert asked == []
    assert view._log.toPlainText() == ""


def test_malformed_csv_shows_friendly_message(gui_env, monkeypatch, tmp_path):
    header = FIX_CSV.read_text().splitlines()[0].replace('"LAT_SEC",', "")
    path = tmp_path / "FIX_BASE.csv"
    path.write_text(header + "\n")
    view, _ = _make_view(gui_env)
    _pick_file(monkeypatch, path)
    shown = _capture(monkeypatch, "information")

    view._dataset_btn.click()

    assert shown[0][0] == "Nothing to import"
    assert "This CSV does not contain the required FAA FIX fields: LAT_SEC" in shown[0][1]
    assert "Supported:" in shown[0][1]
    assert gui_env["waypoint_service"].list_all() == []


def test_unrelated_file_shows_friendly_message(gui_env, monkeypatch, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not navigation data\n")
    view, _ = _make_view(gui_env)
    _pick_file(monkeypatch, path)
    shown = _capture(monkeypatch, "information")
    view._dataset_btn.click()
    assert shown[0][0] == "Nothing to import"
    assert "notes.txt: not a recognized navigation data file." in shown[0][1]
    assert "FAA NASR FIX_BASE.csv / NAV_BASE.csv" in shown[0][1]


def test_missing_file_shows_warning_not_exception(gui_env, monkeypatch, tmp_path):
    view, _ = _make_view(gui_env)
    _pick_file(monkeypatch, tmp_path / "does-not-exist.csv")
    shown = _capture(monkeypatch, "warning")
    infos = _capture(monkeypatch, "information")
    view._dataset_btn.click()
    assert [title for title, _ in shown] == ["Could not read file"]
    assert infos == []


def test_legacy_buttons_still_present(gui_env):
    view, _ = _make_view(gui_env)
    labels = {b.text() for b in view.findChildren(type(view._dataset_btn))}
    assert {"Choose fix.dat file...", "Choose nav.dat file...", "Import Dataset...", "Import Folder..."} <= labels


def test_dataset_section_absent_without_service(gui_env):
    view = ImportView(gui_env["import_service"])
    assert not hasattr(view, "_dataset_btn")


def test_log_scrolls_to_the_newest_report_headline(gui_env, monkeypatch):
    view, _ = _make_view(gui_env)
    view.resize(900, 650)
    view.show()
    _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    _capture(monkeypatch, "information")
    for sample in (FIXTURES / "sample_faa_nav.txt", NAV_CSV, FIX_CSV):
        _pick_file(monkeypatch, sample)
        view._dataset_btn.click()
        QApplication.processEvents()
        # The newest report's headline is on screen, not scrolled past.
        document = view._log.document()
        headline = document.find("Dataset ", document.characterCount(), document.FindFlag.FindBackward)
        headline.movePosition(headline.MoveOperation.StartOfBlock)
        assert headline.block().text() in ("Dataset import complete", "Dataset analyzed: nothing new to import")
        assert view._log.viewport().rect().contains(view._log.cursorRect(headline)), sample
        # ...and it is the first thing shown unless the report is shorter than the view.
        bar = view._log.verticalScrollBar()
        assert view._log.cursorRect(headline).top() < 20 or bar.value() == bar.maximum(), sample
