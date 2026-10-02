"""Screenshot harness for UI before/after comparison.

Runs the real application wiring (app.main) against a TEMPORARY copy of
the user's database and output folder, then drives each page and the
real dialog code paths, saving a PNG per state. The user's own data,
custom scenery output and FlightGear installation are never written.

Usage:
    .venv/bin/python tools/capture_ui.py OUT_DIR                  # populated copy of real DB
    .venv/bin/python tools/capture_ui.py OUT_DIR --empty --no-fg  # empty DB, FlightGear "not found"
    .venv/bin/python tools/capture_ui.py OUT_DIR --empty          # empty DB, FlightGear found
    .venv/bin/python tools/capture_ui.py OUT_DIR --no-fg          # populated DB, FlightGear "not found"
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
)

from flightgear_navdata_manager import app as appmod  # noqa: E402
from flightgear_navdata_manager.infrastructure import config  # noqa: E402
from flightgear_navdata_manager.infrastructure.fg_detect import macos_locator  # noqa: E402
from flightgear_navdata_manager.presentation import main_window as mw  # noqa: E402
from flightgear_navdata_manager.presentation.views.add_fix_form import AddFixForm  # noqa: E402
from flightgear_navdata_manager.presentation.views.add_nav_form import AddNavForm  # noqa: E402
from flightgear_navdata_manager.presentation.views.dashboard_view import DashboardView  # noqa: E402
from flightgear_navdata_manager.presentation.views.import_view import ImportView  # noqa: E402
from flightgear_navdata_manager.presentation.views.manage_data_view import ManageDataView  # noqa: E402

FIXTURES = ROOT / "tests" / "infrastructure" / "fixtures"
SETTLE_MS = 350

out_dir = Path(sys.argv[1]).resolve()
empty = "--empty" in sys.argv
no_fg = "--no-fg" in sys.argv
large = "--large" in sys.argv     # add ~70,000 synthetic fixes to the sandbox DB
out_dir.mkdir(parents=True, exist_ok=True)

# --- Redirect all app data to a temp sandbox ---------------------------------
sandbox = Path(tempfile.mkdtemp(prefix="fgnav_capture_"))
real_db = config.DB_PATH
config.APP_SUPPORT_DIR = sandbox
config.DB_PATH = sandbox / "navdata.sqlite"
config.CUSTOM_SCENERY_DIR = sandbox / "CustomScenery"
config.FIX_DAT_OUTPUT = config.CUSTOM_SCENERY_DIR / "NavData" / "fix" / "custom.dat"
config.NAV_DAT_OUTPUT = config.CUSTOM_SCENERY_DIR / "NavData" / "nav" / "custom.dat"
# Window geometry is remembered in QSettings; keep that in the sandbox too.
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(sandbox / "settings"))
if not empty and real_db.exists():
    shutil.copy2(real_db, config.DB_PATH)
if no_fg:
    not_found = macos_locator.FlightGearInstallation(None, None, None, None, None)
    macos_locator.detect = lambda: not_found
    from flightgear_navdata_manager.application import install_detection
    install_detection.detect = lambda: not_found

if large:
    from datetime import datetime, timezone

    from flightgear_navdata_manager.domain.models import DataSource, Fix
    from flightgear_navdata_manager.infrastructure.storage.db import connect
    from flightgear_navdata_manager.infrastructure.storage.fix_repository import FixRepository

    stamp = datetime.now(timezone.utc)
    FixRepository(connect(config.DB_PATH)).add_many([
        Fix(id=None, source=DataSource.IMPORTED, enabled=i % 9 != 0, created_at=stamp,
            ident=f"SY{i:05d}", latitude=(i % 1700) / 10 - 85, longitude=(i % 3500) / 10 - 175)
        for i in range(68_000)
    ])

# A navaid table with no type column, to trigger the record-type prompt.
untyped_csv = sandbox / "untyped_navaids.csv"
untyped_csv.write_text("ident,name,latitude,longitude,frequency,range_nm\nQQA,Test,10.0,20.0,375,50\n")

window = None
steps: list = []
shot_no = [0]


def save(widget, name: str) -> None:
    shot_no[0] += 1
    path = out_dir / f"{shot_no[0]:02d}_{name}.png"
    widget.grab().save(str(path))
    print("saved", path.name)


def show_page(view_cls) -> object:
    view = window.findChild(view_cls)
    if hasattr(window, "show_page"):
        window.show_page(view)
    else:
        tabs = window.findChild(QTabWidget)
        if tabs is not None:
            tabs.setCurrentWidget(view)
        else:
            window.findChild(QStackedWidget).setCurrentWidget(view)
    return view


def button(parent, text: str) -> QPushButton:
    for b in parent.findChildren(QPushButton):
        if b.text() == text:
            return b
    raise LookupError(text)


def with_modal(trigger, name: str, choose: str | None = None) -> None:
    """Runs trigger(), screenshots the modal dialog it opens, then closes it
    by clicking the button labelled `choose` (or rejecting)."""
    def capture() -> None:
        dlg = QApplication.activeModalWidget()
        if dlg is None:
            print("NO MODAL for", name)
            return
        save(dlg, name)
        if choose and isinstance(dlg, QMessageBox):
            for b in dlg.buttons():
                if b.text().replace("&", "") == choose:
                    b.click()
                    return
        if isinstance(dlg, QDialog):
            dlg.reject()
    QTimer.singleShot(SETTLE_MS + 200, capture)
    trigger()


def page(view_cls, name: str, before=None):
    def run():
        view = show_page(view_cls)
        if before:
            before(view)
        QTimer.singleShot(SETTLE_MS, lambda: save(window, name) or next_step())
    return run


def action(fn):
    def run():
        fn()
        QTimer.singleShot(SETTLE_MS, next_step)
    return run


def next_step() -> None:
    if not steps:
        QApplication.quit()
        return
    steps.pop(0)()


def set_fix(form, ident, lat, lon):
    form._ident_edit.setText(ident)
    form._lat_spin.setValue(lat)
    form._lon_spin.setValue(lon)


def set_ndb(form, ident):
    form._type_combo.setCurrentIndex(0)
    form._ident_edit.setText(ident)
    form._name_edit.setText("Capture Test")
    form._lat_spin.setValue(10.5)
    form._lon_spin.setValue(20.5)
    form._ndb_freq_khz.setValue(375)


def set_output_writable(writable: bool) -> None:
    """Makes the sandbox's fix output folder read-only (or writable again),
    so Regenerate fails through the real code path."""
    folder = config.FIX_DAT_OUTPUT.parent
    folder.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IRWXU if writable else stat.S_IRUSR | stat.S_IXUSR
    os.chmod(folder, mode)


def at_min_size(view_cls, name: str):
    def run():
        normal = window.size()
        show_page(view_cls)
        window.resize(window.minimumSize())

        def shoot():
            save(window, name)
            window.resize(normal)
            QTimer.singleShot(SETTLE_MS, next_step)
        QTimer.singleShot(SETTLE_MS, shoot)
    return run


def manage_filter(kind=0, source=0, text=""):
    def apply(view):
        view._kind_filter.setCurrentIndex(kind)
        view._source_filter.setCurrentIndex(source)
        view._search_edit.setText(text)
        view._apply_filters()
    return apply


def manage_hover_and_select(view):
    table = view._table
    rect = table.visualRect(view._model.index(2, 2))
    table.hover_row, table.hover_pos = 2, rect.center()
    table.selectRow(4)
    table.viewport().update()


def manage_toggle_off(view):
    from PySide6.QtCore import Qt
    model = view._model
    for row in (1, 3):
        model.setData(model.index(row, 6), Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)


def build_steps() -> None:
    open_file = lambda p: setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(p), "")))  # noqa: E731

    if large:
        steps.extend([
            page(ManageDataView, "manage_large_dataset"),
            page(ManageDataView, "manage_large_search", before=manage_filter(text="SY123")),
            page(ManageDataView, "manage_large_vor_imported", before=manage_filter(kind=3, source=2)),
            at_min_size(ManageDataView, "manage_large_min_size"),
        ])
        return

    if empty or no_fg:
        label = ("empty_" if empty else "") + ("not_detected" if no_fg else "detected")
        steps.append(page(DashboardView, f"dashboard_{label}"))
        if empty and no_fg:
            steps.extend([
                page(ManageDataView, "manage_data_empty"),
                page(ImportView, "import_empty"),
            ])
        return

    steps.extend([
        page(DashboardView, "dashboard"),
        at_min_size(DashboardView, "dashboard_min_size"),
        page(DashboardView, "dashboard_after_regenerate",
             before=lambda v: button(v, "Regenerate now").click()),
        action(lambda: set_output_writable(False)),
        page(DashboardView, "dashboard_regenerate_error",
             before=lambda v: button(v, "Regenerate now").click()),
        action(lambda: set_output_writable(True)),
        page(DashboardView, "dashboard_regenerate_recovered",
             before=lambda v: button(v, "Regenerate now").click()),
        page(ImportView, "import_empty"),
        at_min_size(ImportView, "import_min_size"),
        action(lambda: with_modal(lambda: button(window.findChild(ImportView), "CSV/TXT format...").click(),
                                  "dialog_csv_format_help", "OK")),
        action(lambda: open_file(FIXTURES / "sample_faa_fix.csv")),
        action(lambda: with_modal(lambda: window.findChild(ImportView)._dataset_btn.click(),
                                  "dialog_import_confirm", "Yes")),
        page(ImportView, "import_log_after_dataset"),
        action(lambda: open_file(untyped_csv)),
        action(lambda: with_modal(lambda: window.findChild(ImportView)._dataset_btn.click(),
                                  "dialog_record_type_prompt")),
        action(lambda: open_file(FIXTURES / "sample_nav_810.dat")),
        page(ImportView, "import_after_navdat_card",
             before=lambda v: button(v, "Choose nav.dat file...").click()),
        action(lambda: open_file(sandbox / "no-such-file.csv")),
        action(lambda: with_modal(lambda: window.findChild(ImportView)._dataset_btn.click(),
                                  "dialog_import_read_error", "OK")),
        page(ImportView, "import_after_read_error"),
        page(AddFixForm, "add_waypoint_empty"),
        at_min_size(AddFixForm, "add_waypoint_min_size"),
        page(AddFixForm, "add_waypoint_validation_error", before=lambda f: f._on_submit()),
        at_min_size(AddFixForm, "add_waypoint_validation_error_min_size"),
        page(AddFixForm, "add_waypoint_filled", before=lambda f: set_fix(f, "CAPTA", 12.345678, -45.678901)),
        page(AddFixForm, "add_waypoint_success", before=lambda f: f._on_submit()),
        action(lambda: set_fix(window.findChild(AddFixForm), "CAPTA", 12.345678, -45.678901)),
        action(lambda: with_modal(lambda: window.findChild(AddFixForm)._on_submit(),
                                  "dialog_duplicate_prompt", "Cancel")),
        page(AddNavForm, "add_navaid_ndb", before=lambda f: f._type_combo.setCurrentIndex(0)),
        at_min_size(AddNavForm, "add_navaid_ndb_min_size"),
        page(AddNavForm, "add_navaid_vor", before=lambda f: f._type_combo.setCurrentIndex(1)),
        page(AddNavForm, "add_navaid_dme", before=lambda f: f._type_combo.setCurrentIndex(2)),
        at_min_size(AddNavForm, "add_navaid_dme_min_size"),
        page(AddNavForm, "add_navaid_validation_error",
             before=lambda f: (f._type_combo.setCurrentIndex(1), f._ident_edit.setText("CPV"), f._on_submit())),
        page(AddNavForm, "add_navaid_success", before=lambda f: (set_ndb(f, "CPTN"), f._on_submit())),
        page(ManageDataView, "manage_data"),
        at_min_size(ManageDataView, "manage_data_min_size"),
        page(ManageDataView, "manage_search", before=manage_filter(text="abi")),
        page(ManageDataView, "manage_type_vor", before=manage_filter(kind=3)),
        page(ManageDataView, "manage_source_custom", before=manage_filter(source=1)),
        page(ManageDataView, "manage_combined_ndb_imported_search",
             before=manage_filter(kind=2, source=2, text="al")),
        page(ManageDataView, "manage_no_results", before=manage_filter(kind=4, text="zzzz")),
        page(ManageDataView, "manage_hover_and_selected", before=lambda v: (manage_filter()(v),
                                                                           manage_hover_and_select(v))),
        page(ManageDataView, "manage_toggled_off", before=manage_toggle_off),
        action(lambda: with_modal(lambda: window.findChild(ManageDataView)._on_delete_row(0),
                                  "dialog_delete_confirm", "No")),
        page(DashboardView, "dashboard_after_all_changes"),
    ])


_orig_show = mw.MainWindow.show


def _show(self):
    global window
    window = self
    _orig_show(self)
    build_steps()
    QTimer.singleShot(800, next_step)


mw.MainWindow.show = _show
code = appmod.main()
set_output_writable(True)
shutil.rmtree(sandbox, ignore_errors=True)
sys.exit(code)
