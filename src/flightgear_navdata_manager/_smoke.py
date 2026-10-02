"""Packaged-app smoke test, run inside the real (frozen) app.

Activated only by FGNAV_SMOKE_OUT=<dir>, and app.main() refuses to start
it unless FGNAV_DATA_DIR points the app at throwaway data. It drives the
real window and real dialogs, records each check in <dir>/results.json and
saves screenshots to <dir>/*.png, then quits.

FGNAV_SMOKE_FIXTURES=<dir> supplies the files to import (copies of the
test fixtures); FGNAV_ASSUME_NO_FLIGHTGEAR=1 runs the short
"FlightGear not installed" pass.
"""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLabel, QMessageBox, QStyle

from flightgear_navdata_manager.infrastructure import config
from flightgear_navdata_manager.presentation.main_window import (
    ADD_NAVAID, ADD_WAYPOINT, DASHBOARD, IMPORT, MANAGE_DATA,
)
from flightgear_navdata_manager.presentation.theme import icons
from flightgear_navdata_manager.presentation.theme.tokens import COLORS
from flightgear_navdata_manager.presentation.views.manage_data_view import ENABLED_COLUMN

SETTLE_MS = 350


class _Smoke:
    def __init__(self, window, out: str, fix_repo, navaid_repo):
        self.w = window
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.fix_repo, self.navaid_repo = fix_repo, navaid_repo
        self.fixtures = Path(os.environ.get("FGNAV_SMOKE_FIXTURES", ""))
        self.no_fg = os.environ.get("FGNAV_ASSUME_NO_FLIGHTGEAR") == "1"
        self.results: list[dict] = []
        self.steps: list = []
        self.shots = 0
        self.dialog_seen: dict = {}

    # -- bookkeeping -------------------------------------------------------------
    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append({"check": name, "ok": bool(ok), "detail": detail})

    def shot(self, widget, name: str) -> None:
        self.shots += 1
        widget.grab().save(str(self.out / f"{self.shots:02d}_{name}.png"))

    def next(self) -> None:
        if not self.steps:
            self.finish()
            return
        step = self.steps.pop(0)
        try:
            step()
        except Exception:
            self.check(f"step {getattr(step, '__name__', step)} raised", False, traceback.format_exc())
            QTimer.singleShot(0, self.next)

    def finish(self) -> None:
        summary = {"passed": sum(r["ok"] for r in self.results), "failed": sum(not r["ok"] for r in self.results),
                   "frozen": bool(getattr(__import__("sys"), "frozen", False)),
                   "data_dir": str(config.APP_SUPPORT_DIR), "results": self.results}
        (self.out / "results.json").write_text(json.dumps(summary, indent=2))
        QApplication.quit()

    # -- helpers -------------------------------------------------------------------------
    def page(self, index: int, name: str, before=None, checks=None):
        def run():
            self.w.set_current_page(index)
            if before:
                before()

            def done():
                if checks:
                    checks()
                self.shot(self.w, name)
                self.next()
            QTimer.singleShot(SETTLE_MS, done)
        run.__name__ = f"page_{name}"
        return run

    def modal(self, trigger, name: str, choose: str | None, inspect=None):
        """Runs trigger(); screenshots the real dialog it opens, then
        answers it with the button labelled `choose` (or rejects it)."""
        def run():
            def capture():
                dlg = QApplication.activeModalWidget()
                if dlg is None:
                    self.check(f"dialog {name} opened", False)
                    return
                self.check(f"dialog {name} opened", True, dlg.windowTitle())
                if inspect:
                    inspect(dlg)
                self.shot(dlg, name)
                if choose and isinstance(dlg, QMessageBox):
                    for b in dlg.buttons():
                        if b.text().replace("&", "") == choose:
                            b.click()
                            return
                if isinstance(dlg, QDialog):
                    dlg.reject()
            QTimer.singleShot(SETTLE_MS + 250, capture)
            trigger()
            QTimer.singleShot(SETTLE_MS, self.next)
        run.__name__ = f"modal_{name}"
        return run

    def act(self, fn, name: str):
        def run():
            fn()
            QTimer.singleShot(SETTLE_MS, self.next)
        run.__name__ = name
        return run

    def pick(self, path: Path) -> None:
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(path), ""))

    def total(self) -> int:
        return self.fix_repo.count() + self.navaid_repo.count()

    # -- the run ----------------------------------------------------------------------------
    def build(self) -> None:
        w = self.w
        if self.no_fg:
            self.steps = [
                self.page(DASHBOARD, "fg_not_found_dashboard", checks=lambda: (
                    self.check("20 starts without FlightGear", w.current_page() == DASHBOARD),
                    self.check("20 sidebar shows not found", w.sidebar.status_text() == "FlightGear not found",
                               w.sidebar.status_text()),
                    self.check("20 dashboard shows not detected",
                               w.dashboard_view._status_headline_label.text() == "FlightGear not detected"),
                )),
            ]
            return

        self.steps = [
            self.page(DASHBOARD, "dashboard", checks=self.check_dashboard),
            self.act(self.check_navigation, "navigation"),
            self.act(self.check_icons, "icons"),
            self.page(IMPORT, "import", checks=lambda: self.check(
                "7 import page opens", w.current_page() == IMPORT and w.import_view._dataset_btn.isEnabled())),
            self.act(lambda: self.pick(self.fixtures / "sample_faa_fix.csv"), "pick_fix_csv"),
            self.modal(lambda: w.import_view._dataset_btn.click(), "dialog_import_confirm", "Yes",
                       inspect=self.inspect_question_icon),
            self.page(IMPORT, "import_after_dataset", checks=self.check_import),
            self.act(lambda: self.pick(self.fixtures / "untyped_navaids.csv"), "pick_untyped"),
            self.modal(lambda: w.import_view._dataset_btn.click(), "dialog_record_type", None,
                       inspect=lambda d: self.check("record-type dialog offers NDB/VOR/DME",
                                                    "What does this file contain?" in d.labelText())),
            self.page(ADD_WAYPOINT, "add_waypoint", before=self.add_waypoint, checks=self.check_waypoint),
            self.act(self.fill_duplicate_waypoint, "fill_duplicate"),
            self.modal(lambda: w.add_fix_form._on_submit(), "dialog_duplicate", "Cancel",
                       inspect=lambda d: self.check("duplicate dialog themed headline",
                                                    d.findChild(QLabel, "qt_msgbox_label").property("msgRole")
                                                    == "headline")),
            self.page(ADD_NAVAID, "add_navaid_ndb", before=lambda: self.add_navaid(0, "SMN", "_ndb_freq_khz", 375)),
            self.page(ADD_NAVAID, "add_navaid_vor", before=lambda: self.add_navaid(1, "SMV", "_vor_freq_mhz", 113.2)),
            self.page(ADD_NAVAID, "add_navaid_dme", before=lambda: self.add_navaid(2, "SMD", "_dme_freq_mhz", 113.4),
                      checks=self.check_navaids),
            self.page(MANAGE_DATA, "manage_data", checks=self.check_manage),
            self.act(self.check_toggle, "toggle"),
            self.act(lambda: self.filter_to("SMWPT"), "filter_for_delete"),
            self.modal(lambda: w.manage_view._on_delete_row(self.row_of("SMWPT")), "dialog_delete", "Yes",
                       inspect=self.inspect_delete),
            self.act(self.check_deleted, "check_deleted"),
            self.page(DASHBOARD, "dashboard_after_changes", before=lambda: w.dashboard_view._regenerate_btn.click(),
                      checks=self.check_regenerate),
        ]

    # -- checks ---------------------------------------------------------------------------------
    def check_dashboard(self):
        w = self.w
        self.check("1 dashboard is the initial page", w.current_page() == DASHBOARD)
        found = w.install_state.installation.found
        self.check("5 FlightGear detection shown",
                   (w.sidebar.status_text().startswith("FlightGear ") and found)
                   or w.sidebar.status_text() == "FlightGear not found",
                   f"{w.sidebar.status_text()} / {w.dashboard_view._status_headline_label.text()}")
        shown = int(w.dashboard_view.stat_cards["records"].value_text().replace(",", ""))
        self.check("6 dashboard live count matches database", shown == self.total(), f"{shown} vs {self.total()}")
        self.check("window opens at the default size", (w.width(), w.height()) == (1200, 780),
                   f"{w.width()}x{w.height()}")

    def check_navigation(self):
        w = self.w
        ok = True
        for index, item in enumerate(w.sidebar.items()):
            item.click()
            ok &= w.current_page() == index
        self.check("2 sidebar navigation", ok)
        ok = True
        for index, action in enumerate(w.go_actions):
            action.trigger()
            ok &= w.current_page() == index
        self.check("3 Go menu", ok and len(w.menuBar().actions()) >= 1, w.menuBar().actions()[0].text())
        # Shortcuts need the window to be active, as it is when a user
        # opens the app; launched from a terminal it may not be yet.
        for _ in range(20):                    # up to ~2 s for macOS to hand over focus
            w.raise_()
            w.activateWindow()
            QTest.qWait(100)
            if w.isActiveWindow():
                break
        visited = []
        for index in (4, 2, 0, 3, 1, 0):
            QTest.keyClick(w, Qt.Key(Qt.Key.Key_1 + index), Qt.KeyboardModifier.ControlModifier)
            visited.append(w.current_page())
        self.check("4 Cmd-1..5 shortcuts", visited == [4, 2, 0, 3, 1, 0],
                   f"active={w.isActiveWindow()} visited={visited}")
        w.set_current_page(DASHBOARD)

    def check_icons(self):
        bad = [n for n in icons.available() if icons.pixmap(n, COLORS.accent, 18, 2).isNull()]
        self.check("18 every bundled icon loads", not bad and len(icons.available()) >= 30,
                   f"{len(icons.available())} icons, failed: {bad}")
        style = QApplication.style()
        same = (style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(36).toImage()
                == icons.icon("triangle-alert", COLORS.warning, 36).pixmap(36).toImage())
        self.check("19 dialog icons come from the theme", same)

    def inspect_question_icon(self, dlg):
        self.check("19 import confirmation is themed",
                   dlg.palette().color(dlg.backgroundRole()).name() == COLORS.bg_content,
                   dlg.palette().color(dlg.backgroundRole()).name())

    def check_import(self):
        imported = sum(1 for f in self.fix_repo.list_all() if f.source.value == "imported")
        self.check("16 import into throwaway database", imported == 6, f"{imported} imported fixes")
        self.check("16 import log written", self.w.import_view._log.toPlainText().startswith("Dataset import complete"))

    def add_waypoint(self):
        f = self.w.add_fix_form
        f._ident_edit.setText("SMWPT")
        f._lat_spin.setValue(12.3456789)
        f._lon_spin.setValue(-45.6789012)
        f._on_submit()

    def check_waypoint(self):
        made = [x for x in self.fix_repo.list_all() if x.ident == "SMWPT"]
        self.check("8 add waypoint page opens", self.w.current_page() == ADD_WAYPOINT)
        self.check("14 waypoint created in throwaway database", len(made) == 1)

    def fill_duplicate_waypoint(self):
        f = self.w.add_fix_form
        f._ident_edit.setText("SMWPT")
        f._lat_spin.setValue(12.3456789)
        f._lon_spin.setValue(-45.6789012)

    def add_navaid(self, index, ident, freq_widget, freq):
        f = self.w.add_nav_form
        f._type_combo.buttons()[index].click()
        self.check(f"9 navaid type switch to {('NDB', 'VOR', 'DME')[index]}", f._stack.currentIndex() == index)
        f._ident_edit.setText(ident)
        f._name_edit.setText("Smoke")
        f._lat_spin.setValue(20.0 + index)
        f._lon_spin.setValue(30.0)
        getattr(f, freq_widget).setValue(freq)
        f._on_submit()
        # Leave the form showing this type, freshly cleared, for the screenshot.

    def check_navaids(self):
        idents = {n.ident: n.type.value for n in self.navaid_repo.list_all() if n.name.startswith("Smoke")}
        self.check("15 NDB/VOR/DME created in throwaway database",
                   idents == {"SMN": "NDB", "SMV": "VOR", "SMD": "DME"}, str(idents))

    def check_manage(self):
        v = self.w.manage_view
        self.check("10 manage data shows records", v._model.rowCount() == self.total() > 0,
                   f"{v._model.rowCount()} rows")
        self.filter_to("SMN")
        idents = [v._model.row(r)[1].ident for r in range(v._model.rowCount())]
        ok = "SMN" in idents and all("smn" in v._model.row(r)[1].ident.lower()
                                     or "smn" in getattr(v._model.row(r)[1], "name", "").lower()
                                     for r in range(v._model.rowCount()))
        v._kind_filter.setCurrentIndex(3)       # VOR: SMN is an NDB, so nothing matches
        ok &= v._model.rowCount() == 0 and not v._no_results.isHidden()
        v.clear_filters()
        self.check("11 search and filters", ok and v._model.rowCount() == self.total())

    def filter_to(self, text):
        v = self.w.manage_view
        v._search_edit.setText(text)
        v._apply_filters()

    def row_of(self, ident) -> int:
        """Visible row of the record with exactly this identifier (search
        is a substring match, so other records may also be listed)."""
        model = self.w.manage_view._model
        return next(r for r in range(model.rowCount()) if model.row(r)[1].ident == ident)

    def check_toggle(self):
        v = self.w.manage_view
        self.filter_to("SMV")
        v._model.setData(v._model.index(self.row_of("SMV"), ENABLED_COLUMN), Qt.CheckState.Unchecked.value,
                         Qt.ItemDataRole.CheckStateRole)
        vor = next(n for n in self.navaid_repo.list_all() if n.ident == "SMV")
        in_export = " SMV " in config.NAV_DAT_OUTPUT.read_text()
        self.check("12 toggle writes to throwaway database and export", not vor.enabled and not in_export)

    def inspect_delete(self, dlg):
        yes = dlg.button(QMessageBox.StandardButton.Yes)
        no = dlg.button(QMessageBox.StandardButton.No)
        # A static QMessageBox.question leaves defaultButton() unset; Qt
        # makes No the default (Enter) button when the box is shown.
        parts = {"yes_danger": yes.property("variant") == "danger", "no_is_default": no.isDefault(),
                 "yes_not_default": not yes.isDefault(), "names_record": "SMWPT" in dlg.text()}
        self.check("13 delete confirmation shown, destructive and safe default", all(parts.values()), str(parts))

    def check_deleted(self):
        self.check("13 delete removed the record", not any(f.ident == "SMWPT" for f in self.fix_repo.list_all()))
        self.w.manage_view.clear_filters()

    def check_regenerate(self):
        banner = self.w.dashboard_view.status_banner
        out_ok = config.FIX_DAT_OUTPUT.exists() and config.NAV_DAT_OUTPUT.exists()
        inside = str(config.FIX_DAT_OUTPUT).startswith(str(config.APP_SUPPORT_DIR))
        self.check("17 regenerate writes the throwaway output", out_ok and inside and banner.tone() == "success",
                   str(config.FIX_DAT_OUTPUT))


def start(window, out: str, fix_repo, navaid_repo) -> None:
    smoke = _Smoke(window, out, fix_repo, navaid_repo)
    window._smoke = smoke                      # keep it alive for the timers below
    smoke.build()
    QTimer.singleShot(1200, window, smoke.next)    # let the window appear and Manage Data load

    def watchdog():                            # never hang: record and quit
        smoke.check("smoke run finished within 120 s", False, f"{len(smoke.steps)} steps left")
        modal = QApplication.activeModalWidget()
        if modal is not None:
            modal.close()
        smoke.finish()
    QTimer.singleShot(120_000, window, watchdog)
