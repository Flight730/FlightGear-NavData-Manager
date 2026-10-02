import os
from pathlib import Path

import pytest

# Headless, with one realistic Retina laptop screen (the offscreen
# default is 800x800, smaller than the window's minimum size, so Qt
# would clamp window geometry in ways a real Mac never does).
_SCREEN = Path(__file__).with_name("offscreen_screen.json")
os.environ.setdefault("QT_QPA_PLATFORM", f"offscreen:configfile={_SCREEN}")

from PySide6.QtWidgets import QApplication  # noqa: E402

from flightgear_navdata_manager.application.dataset_import import DatasetImportService
from flightgear_navdata_manager.application.export_navdata import ExportService
from flightgear_navdata_manager.application.import_navdata import ImportService
from flightgear_navdata_manager.application.navaid_service import NavaidService
from flightgear_navdata_manager.application.waypoint_service import WaypointService
from flightgear_navdata_manager.infrastructure import config
from flightgear_navdata_manager.infrastructure.storage.db import connect
from flightgear_navdata_manager.infrastructure.storage.fix_repository import FixRepository
from flightgear_navdata_manager.infrastructure.storage.navaid_repository import (
    NavaidRepository,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def gui_env(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr(config, "FIX_DAT_OUTPUT", tmp_path / "NavData" / "fix" / "custom.dat")
    monkeypatch.setattr(config, "NAV_DAT_OUTPUT", tmp_path / "NavData" / "nav" / "custom.dat")

    conn = connect(":memory:")
    fix_repo = FixRepository(conn)
    navaid_repo = NavaidRepository(conn)
    export_service = ExportService(fix_repo, navaid_repo)
    waypoint_service = WaypointService(fix_repo, export_service)
    navaid_service = NavaidService(navaid_repo, export_service)
    import_service = ImportService(fix_repo, navaid_repo, export_service)
    dataset_service = DatasetImportService(fix_repo, navaid_repo, export_service)

    return {
        "waypoint_service": waypoint_service,
        "navaid_service": navaid_service,
        "import_service": import_service,
        "dataset_service": dataset_service,
        "export_service": export_service,
        "fix_repo": fix_repo,
        "navaid_repo": navaid_repo,
    }


class FakeInstallService:
    """Detection without touching the real disk; flip .found to simulate
    FlightGear being removed or installed."""

    def __init__(self):
        self.calls = 0
        self.found = True

    def detect(self):
        from flightgear_navdata_manager.infrastructure.fg_detect.macos_locator import (
            FlightGearInstallation,
        )
        self.calls += 1
        if not self.found:
            return FlightGearInstallation(None, None, None, None, None)
        app = Path("/Applications/FlightGear.app")
        return FlightGearInstallation(app, app / "Contents/MacOS/FlightGear", Path("/fg/root"),
                                      Path("/fg/home"), "2024.1.6")


@pytest.fixture
def settings(tmp_path):
    from PySide6.QtCore import QSettings
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def make_window(gui_env, settings):
    """Builds a full MainWindow over the in-memory test database."""
    from flightgear_navdata_manager.application.dashboard_stats import DashboardStatsService
    from flightgear_navdata_manager.presentation.main_window import MainWindow

    install = FakeInstallService()
    stats = DashboardStatsService(gui_env["fix_repo"], gui_env["navaid_repo"], gui_env["export_service"])

    def make():
        window = MainWindow(
            waypoint_service=gui_env["waypoint_service"],
            navaid_service=gui_env["navaid_service"],
            import_service=gui_env["import_service"],
            export_service=gui_env["export_service"],
            install_service=install,
            dataset_import_service=gui_env["dataset_service"],
            settings=settings,
            stats_service=stats,
        )
        window.fake_install = install
        return window

    return make


@pytest.fixture(autouse=True)
def no_real_modal_dialogs(monkeypatch):
    """A modal dialog opened for real would block a headless test run
    forever; fail fast instead. Tests patch the dialog they expect."""
    from PySide6.QtWidgets import QMessageBox

    def refuse(self, *args, **kwargs):
        raise AssertionError(f"unexpected modal dialog in a test: {self.text()!r}")

    monkeypatch.setattr(QMessageBox, "exec", refuse)

    from PySide6.QtWidgets import QInputDialog

    def refuse_input(*args, **kwargs):
        raise AssertionError("unexpected QInputDialog in a test")

    monkeypatch.setattr(QInputDialog, "getItem", refuse_input)


@pytest.fixture(autouse=True)
def close_windows_after_test(qapp):
    """Close and delete every top-level widget a test created. Left for
    interpreter-exit garbage collection, a still-visible window is torn
    down in arbitrary order and can crash Qt (in the app, the main window
    is always closed before exit)."""
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def themed(qapp):
    """Applies the real app theme (style sheet, palette, style) for the
    test, for checks that depend on how the theme lays things out."""
    from flightgear_navdata_manager.presentation import theme

    old_sheet, old_palette = qapp.styleSheet(), qapp.palette()
    theme.apply_theme(qapp)
    yield qapp
    qapp.setStyleSheet(old_sheet)
    qapp.setPalette(old_palette)
