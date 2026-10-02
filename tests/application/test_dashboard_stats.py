from datetime import datetime, timedelta, timezone

import pytest

from flightgear_navdata_manager.application import export_navdata
from flightgear_navdata_manager.application.dashboard_stats import DashboardStatsService, ExportState
from flightgear_navdata_manager.application.navaid_service import build_dme, build_ndb, build_vor
from flightgear_navdata_manager.domain.models import DataSource, Fix, NavaidType


def _fix(ident, source=DataSource.CUSTOM, enabled=True):
    return Fix(id=None, source=source, enabled=enabled, created_at=datetime.now(timezone.utc),
               ident=ident, latitude=1.0, longitude=2.0)


@pytest.fixture
def stats(app_env):
    return DashboardStatsService(app_env["fix_repo"], app_env["navaid_repo"], app_env["export_service"])


def test_empty_database(stats):
    s = stats.summary()
    assert (s.total, s.fixes, s.navaids, s.enabled, s.disabled) == (0, 0, 0, 0, 0)
    assert all(s.navaid_count(t) == 0 for t in NavaidType)


def test_counts_by_source_type_and_enabled(app_env, stats):
    fixes, navaids = app_env["fix_repo"], app_env["navaid_repo"]
    fixes.add(_fix("CUSTA"))
    fixes.add(_fix("IMPA", DataSource.IMPORTED))
    fixes.add(_fix("IMPB", DataSource.IMPORTED, enabled=False))
    navaids.add(build_ndb("NA", "A", 1, 2, 0, 375, 50))
    navaids.add(build_ndb("NB", "B", 1, 2, 0, 380, 50, source=DataSource.IMPORTED))
    navaids.add(build_vor("VA", "A", 1, 2, 0, 113.2, 130, source=DataSource.IMPORTED))
    dme = navaids.add(build_dme("DA", "A", 1, 2, 0, 113.2, 25))
    navaids.set_enabled(dme.id, False)

    s = stats.summary()
    assert (s.fixes, s.fixes_custom, s.fixes_imported) == (3, 1, 2)
    assert (s.navaids, s.navaids_custom, s.navaids_imported) == (4, 2, 2)
    assert [s.navaid_count(t) for t in (NavaidType.NDB, NavaidType.VOR, NavaidType.DME)] == [2, 1, 1]
    assert (s.total, s.enabled, s.disabled) == (7, 5, 2)


def test_summary_never_loads_records(app_env, stats, monkeypatch):
    app_env["fix_repo"].add(_fix("CUSTA"))
    for repo in (app_env["fix_repo"], app_env["navaid_repo"]):
        for name in ("list_all", "list_enabled", "get"):
            monkeypatch.setattr(repo, name, lambda *a: pytest.fail("summary loaded records"))
    assert stats.summary().total == 1


def test_export_status_follows_regeneration(app_env, stats, monkeypatch):
    export = app_env["export_service"]
    assert stats.export_status().state is ExportState.NOT_WRITTEN
    assert export.last_written() is None

    export.regenerate()
    status = stats.export_status()
    assert status.state is ExportState.UP_TO_DATE
    assert abs((datetime.now() - status.last_written).total_seconds()) < 5

    failure = PermissionError(13, "Permission denied", "/blocked/custom.dat")

    def fail(*a):
        raise failure
    # A scoped patch: undoing it must not also undo the fixture's redirect
    # of the output paths (monkeypatch.undo() would, and the next
    # regenerate would write to the real location).
    with monkeypatch.context() as patch:
        patch.setattr(export_navdata, "write_fix_dat", fail)
        with pytest.raises(PermissionError):          # still raised to the caller
            export.regenerate()
        status = stats.export_status()
        assert status.state is ExportState.FAILED and status.error is failure
        assert status.last_written is not None        # the earlier files are still there

    export.regenerate()
    assert stats.export_status().state is ExportState.UP_TO_DATE
    assert export.last_error is None


def test_last_written_is_the_newer_output_file(app_env):
    import os
    from flightgear_navdata_manager.infrastructure import config

    app_env["export_service"].regenerate()
    old = (datetime.now() - timedelta(hours=3)).timestamp()
    os.utime(config.FIX_DAT_OUTPUT, (old, old))
    newest = config.NAV_DAT_OUTPUT.stat().st_mtime
    assert app_env["export_service"].last_written() == datetime.fromtimestamp(newest)
