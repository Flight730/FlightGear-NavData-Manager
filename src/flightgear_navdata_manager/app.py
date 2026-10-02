"""Application bootstrap and dependency wiring."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from flightgear_navdata_manager.application.dashboard_stats import DashboardStatsService
from flightgear_navdata_manager.application.dataset_import import DatasetImportService
from flightgear_navdata_manager.application.export_navdata import ExportService
from flightgear_navdata_manager.application.import_navdata import ImportService
from flightgear_navdata_manager.application.install_detection import InstallDetectionService
from flightgear_navdata_manager.application.navaid_service import NavaidService
from flightgear_navdata_manager.application.waypoint_service import WaypointService
from flightgear_navdata_manager.infrastructure import config
from flightgear_navdata_manager.infrastructure.fg_detect.macos_locator import FlightGearInstallation
from flightgear_navdata_manager.infrastructure.storage.db import connect
from flightgear_navdata_manager.infrastructure.storage.fix_repository import FixRepository
from flightgear_navdata_manager.infrastructure.storage.navaid_repository import (
    NavaidRepository,
)
from flightgear_navdata_manager.presentation.main_window import MainWindow
from flightgear_navdata_manager.presentation.theme import apply_theme, brand


class _NoFlightGear(InstallDetectionService):
    """FGNAV_ASSUME_NO_FLIGHTGEAR=1: behave as if FlightGear isn't installed."""

    def detect(self) -> FlightGearInstallation:
        return FlightGearInstallation(None, None, None, None, None)


def main() -> int:
    # Test-only overrides (see infrastructure/config.py for FGNAV_DATA_DIR).
    settings_dir = os.environ.get("FGNAV_SETTINGS_DIR")
    if settings_dir:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings_dir)
    smoke_out = os.environ.get("FGNAV_SMOKE_OUT")
    if smoke_out and not os.environ.get("FGNAV_DATA_DIR"):
        print("FGNAV_SMOKE_OUT requires FGNAV_DATA_DIR (the smoke test never uses real data)",
              file=sys.stderr)
        return 2

    config.ensure_dirs()
    conn = connect(config.DB_PATH)

    fix_repo = FixRepository(conn)
    navaid_repo = NavaidRepository(conn)
    export_service = ExportService(fix_repo, navaid_repo)
    waypoint_service = WaypointService(fix_repo, export_service)
    navaid_service = NavaidService(navaid_repo, export_service)
    import_service = ImportService(fix_repo, navaid_repo, export_service)
    dataset_import_service = DatasetImportService(fix_repo, navaid_repo, export_service)
    install_service = (_NoFlightGear() if os.environ.get("FGNAV_ASSUME_NO_FLIGHTGEAR") == "1"
                       else InstallDetectionService())
    stats_service = DashboardStatsService(fix_repo, navaid_repo, export_service)

    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(brand.app_icon())
    window = MainWindow(
        waypoint_service=waypoint_service,
        navaid_service=navaid_service,
        import_service=import_service,
        export_service=export_service,
        install_service=install_service,
        dataset_import_service=dataset_import_service,
        stats_service=stats_service,
    )
    window.show()
    if smoke_out:
        from flightgear_navdata_manager import _smoke
        _smoke.start(window, smoke_out, fix_repo=fix_repo, navaid_repo=navaid_repo)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
