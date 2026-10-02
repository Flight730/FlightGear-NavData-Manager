import pytest

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


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    """Wires an in-memory DB and redirects export output under tmp_path,
    so tests never touch the real ~/Library/Application Support location.
    """
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
        "fix_repo": fix_repo,
        "navaid_repo": navaid_repo,
        "export_service": export_service,
        "waypoint_service": waypoint_service,
        "navaid_service": navaid_service,
        "import_service": import_service,
        "dataset_service": dataset_service,
    }
