import hashlib
from pathlib import Path

from flightgear_navdata_manager.domain.models import DataSource
from flightgear_navdata_manager.infrastructure import config

FIXTURES = Path(__file__).parent.parent / "infrastructure" / "fixtures"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_import_fix_file_never_modifies_source_and_normalizes_output(app_env):
    source = FIXTURES / "sample_fix_5field.dat"
    before = _sha256(source)

    summary = app_env["import_service"].import_fix_file(str(source))

    assert _sha256(source) == before  # source file untouched
    assert summary.imported_count == 2

    fixes = app_env["waypoint_service"].list_all()
    assert all(f.source == DataSource.IMPORTED for f in fixes)
    assert all(f.origin_file == str(source) for f in fixes)
    # Interop scope/region were captured from the 5-field source...
    assert any(f.interop and f.interop.scope == "QZSE" for f in fixes)

    # ...but MVP 1's exporter always normalizes to the 3-field shape,
    # regardless of what the source file contained.
    exported_lines = config.FIX_DAT_OUTPUT.read_text().splitlines()
    record_lines = exported_lines[2:-1]
    assert record_lines  # something was exported
    for line in record_lines:
        assert len(line.split()) == 3


def test_import_nav_file_reports_unsupported_rows_and_never_modifies_source(app_env):
    source = FIXTURES / "sample_nav_1100.dat"
    before = _sha256(source)

    summary = app_env["import_service"].import_nav_file(str(source))

    assert _sha256(source) == before  # source file untouched
    assert summary.imported_count == 2  # NDB + VOR only
    assert summary.skipped_unsupported == {12: 1, 4: 1, 6: 1, 9: 1}

    navaids = app_env["navaid_service"].list_all()
    assert all(n.source == DataSource.IMPORTED for n in navaids)

    # Exporter always writes the 810 (9-field) shape, regardless of the
    # 1100-shaped source.
    exported_lines = config.NAV_DAT_OUTPUT.read_text().splitlines()
    assert exported_lines[1].startswith("810 Version")
    for line in exported_lines[2:-1]:
        assert len(line.split(None, 8)) == 9


def test_export_never_contains_disabled_records(app_env):
    app_env["import_service"].import_fix_file(str(FIXTURES / "sample_fix_3field.dat"))
    fixes = app_env["waypoint_service"].list_all()
    app_env["waypoint_service"].set_enabled(fixes[0].id, False)

    exported = config.FIX_DAT_OUTPUT.read_text()
    assert fixes[0].ident not in exported
