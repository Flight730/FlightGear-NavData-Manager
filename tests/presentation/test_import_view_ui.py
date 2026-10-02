"""Step 5 Import page rebuild: cards and labels, the empty log, the
analyze -> confirm -> apply order, busy state (buttons disabled for the
whole flow, restored after success or failure), page-level results,
read-only sources, DataEvents, and fit at both window sizes."""

import hashlib
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QLabel, QMessageBox, QPushButton, QScrollArea

from flightgear_navdata_manager.presentation.data_events import ChangeKind
from flightgear_navdata_manager.presentation.main_window import IMPORT, MANAGE_DATA
from flightgear_navdata_manager.presentation.views.import_view import (
    LOG_PLACEHOLDER,
    READ_ONLY_NOTE,
    ImportView,
)

FIXTURES = Path(__file__).parent.parent / "infrastructure" / "fixtures"
FIX_CSV = FIXTURES / "sample_faa_fix.csv"
FIX_DAT = FIXTURES / "sample_fix_3field.dat"
NAV_DAT = FIXTURES / "sample_nav_810.dat"
UNTYPED = "ident,name,latitude,longitude,frequency,range_nm\nXYZ,Example,37.6,-122.4,113.2,130\n"


def _view(gui_env, on_imported=None):
    return ImportView(gui_env["import_service"], on_imported=on_imported,
                      dataset_service=gui_env["dataset_service"])


def _button(view, text) -> QPushButton:
    [button] = [b for b in view.findChildren(QPushButton) if b.text() == text]
    return button


def _pick(monkeypatch, path):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))


def _fingerprint(path: Path):
    return path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


def _action_states(view):
    return [b.isEnabled() for b in view._action_buttons]


# -- structure --------------------------------------------------------------------

def test_page_structure_and_labels(gui_env):
    view = _view(gui_env)
    assert view._dataset_btn.text() == "Import Dataset..." and view._dataset_btn.property("variant") == "primary"
    assert view._dataset_folder_btn.text() == "Import Folder..."
    assert _button(view, "CSV/TXT format...").property("variant") == "link"
    chips = [w.text() for w in view.findChildren(QLabel) if w.property("chip")]
    assert chips == ["fix.dat / nav.dat", "CSV", "TXT", "FAA NASR", "ZIP"]
    texts = [w.text() for w in view.findChildren(QLabel)]
    assert texts.count(READ_ONLY_NOTE) == 2                         # on both source cards
    assert any("Imports waypoints (fixes)" in t for t in texts)
    assert any("Imports NDB, VOR and DME navaids" in t for t in texts)
    assert not any("FlightGear's own" in t and "modif" in t and "import" in t.lower() for t in texts)
    assert len(view._action_buttons) == 4


def test_empty_log_shows_placeholder_not_text(gui_env):
    view = _view(gui_env)
    assert view._log.isReadOnly()
    assert view._log.placeholderText() == LOG_PLACEHOLDER == "Import results will appear here."
    assert view._log.toPlainText() == ""
    assert view.result_banner.isHidden()


# -- dedicated fix.dat / nav.dat cards ------------------------------------------------

@pytest.mark.parametrize("button_text, source, kind", [
    ("Choose fix.dat file...", FIX_DAT, "fix.dat"),
    ("Choose nav.dat file...", NAV_DAT, "nav.dat"),
])
def test_source_card_imports_and_leaves_the_file_untouched(gui_env, monkeypatch, button_text, source, kind):
    imported = []
    view = _view(gui_env, on_imported=lambda: imported.append(True))
    before = _fingerprint(source)
    _pick(monkeypatch, source)
    _button(view, button_text).click()

    assert imported == [True]
    assert f"from {kind}: {source}" in view._log.toPlainText()
    assert view.result_banner.tone() == "success" and kind in view.result_banner.text_label.text()
    assert _fingerprint(source) == before                         # read-only
    assert all(_action_states(view))


def test_source_card_read_failure_uses_native_warning_and_restores(gui_env, monkeypatch, tmp_path):
    view = _view(gui_env)
    _pick(monkeypatch, tmp_path / "missing.dat")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda p, t, text, *a, **k: warnings.append(t))
    _button(view, "Choose fix.dat file...").click()
    assert warnings == ["Could not read file"]
    assert view.result_banner.isHidden()
    assert all(_action_states(view)) and not view.is_busy()


# -- dataset flow -----------------------------------------------------------------------

def test_analyze_confirm_apply_order_with_buttons_disabled_throughout(gui_env, monkeypatch):
    service = gui_env["dataset_service"]
    view = _view(gui_env)
    events = []
    real_analyze, real_apply = service.analyze, service.apply

    def analyze(*a):
        events.append(("analyze", _action_states(view), view.result_banner.text_label.text()))
        view._import_dataset_file()                    # a second click while busy is ignored
        return real_analyze(*a)

    def apply(plan):
        events.append(("apply", _action_states(view)))
        return real_apply(plan)

    monkeypatch.setattr(service, "analyze", analyze)
    monkeypatch.setattr(service, "apply", apply)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda p, t, text, *a, **k: (events.append(("confirm", _action_states(view), text)),
                                                     QMessageBox.StandardButton.Yes)[1])
    _pick(monkeypatch, FIX_CSV)
    view._dataset_btn.click()

    assert [e[0] for e in events] == ["analyze", "confirm", "apply"]       # analyze ran once
    assert events[0][1] == [False] * 4 and events[0][2] == "Analyzing sample_faa_fix.csv..."
    assert events[1][1] == [False] * 4 and "Add 6 new record(s) to your data?" in events[1][2]
    assert events[2][1] == [False] * 4
    assert all(_action_states(view)) and QApplication.overrideCursor() is None
    assert view._log.toPlainText().startswith("Dataset import complete")
    assert view.result_banner.tone() == "success"
    assert view.result_banner.text_label.text().startswith("Imported 6 new record(s).")
    assert len(gui_env["waypoint_service"].list_all()) == 6


def test_cancel_and_nothing_new_results(gui_env, monkeypatch):
    view = _view(gui_env)
    _pick(monkeypatch, FIX_CSV)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    view._dataset_btn.click()
    assert (view.result_banner.tone(), view.result_banner.text_label.text()) == \
        ("neutral", "Import cancelled. Nothing was added.")

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    view._dataset_btn.click()                                      # now import it
    infos = []
    monkeypatch.setattr(QMessageBox, "information", lambda p, t, *a, **k: infos.append(t))
    view._dataset_btn.click()                                      # and again: all duplicates
    assert infos == ["Nothing new to import"]
    assert view.result_banner.tone() == "info"
    assert view.result_banner.text_label.text().startswith("Nothing new to import.")


def test_record_type_prompt_keeps_buttons_disabled_then_imports(gui_env, monkeypatch, tmp_path):
    path = tmp_path / "navaids.csv"
    path.write_text(UNTYPED)
    view = _view(gui_env)
    seen = []
    monkeypatch.setattr(QInputDialog, "getItem",
                        lambda p, title, label, items, *a: (seen.append((title, items, _action_states(view))),
                                                            ("DME", True))[1])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    _pick(monkeypatch, path)
    view._dataset_btn.click()
    assert seen == [("Choose record type", ["NDB", "VOR", "DME"], [False] * 4)]
    assert [n.type.value for n in gui_env["navaid_service"].list_all()] == ["DME"]
    assert all(_action_states(view)) and not view.is_busy()


def test_apply_failure_restores_buttons_and_cursor(gui_env, monkeypatch):
    service = gui_env["dataset_service"]
    view = _view(gui_env)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    with monkeypatch.context() as patch:              # scoped: never undo the path guard
        patch.setattr(service, "apply", lambda plan: (_ for _ in ()).throw(RuntimeError("disk on fire")))
        with pytest.raises(RuntimeError):
            view._import_dataset(str(FIX_CSV))         # behavior unchanged: the error propagates
    assert all(_action_states(view)) and not view.is_busy()
    assert QApplication.overrideCursor() is None
    assert view.result_banner.isHidden()              # no stale "Importing..." message
    assert gui_env["waypoint_service"].list_all() == []


def test_unreadable_dataset_keeps_native_dialog(gui_env, monkeypatch, tmp_path):
    view = _view(gui_env)
    _pick(monkeypatch, tmp_path / "gone.csv")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda p, t, text, *a, **k: warnings.append(t))
    view._dataset_btn.click()
    assert warnings == ["Could not read file"]
    assert view.result_banner.isHidden() and all(_action_states(view))


# -- in the window ----------------------------------------------------------------------------

def test_import_notifies_data_events_and_updates_counts(make_window, monkeypatch):
    window = make_window()
    kinds = []
    window.data_events.changed.connect(lambda c: kinds.append(c.kind))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    _pick(monkeypatch, FIX_CSV)
    window.import_view._dataset_btn.click()
    assert kinds == [ChangeKind.RECORDS_IMPORTED]
    assert window.sidebar.items()[MANAGE_DATA].count_text() == "6"
    assert window.dashboard_view.stat_cards["waypoints"].value_text() == "6"
    assert window.manage_view._model.rowCount() == 6


@pytest.mark.parametrize("size", ["minimum", "default"])
def test_page_fits_and_every_action_is_reachable(make_window, themed, size):
    window = make_window()
    if size == "minimum":
        window.resize(window.minimumSize())
    window.show()
    QTest.qWaitForWindowExposed(window)
    window.set_current_page(IMPORT)
    QTest.qWait(20)
    view = window.import_view
    scroll = window._pages[IMPORT].findChild(QScrollArea, "PageScroll")
    assert view.width() <= scroll.viewport().width()
    for button in [*view._action_buttons, _button(view, "CSV/TXT format...")]:
        assert button.mapTo(view, button.rect().topRight()).x() <= scroll.viewport().width()
        scroll.ensureWidgetVisible(button)
        QTest.qWait(5)
        assert not button.visibleRegion().isEmpty(), button.text()
    assert view._log.height() >= 180


def test_log_is_in_view_at_the_default_window_size(make_window, themed):
    """At 1200x780 the import log is visible without scrolling, so a
    finished import's report can be read right away."""
    window = make_window()
    window.show()
    QTest.qWaitForWindowExposed(window)
    window.set_current_page(IMPORT)
    QTest.qWait(20)
    log = window.import_view._log
    visible = log.visibleRegion().boundingRect()
    assert visible.height() >= 150, visible
