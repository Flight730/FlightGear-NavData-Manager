"""FAA FIX data (FIX.txt and FIX_BASE.csv) through DatasetImportService."""

import pytest

from flightgear_navdata_manager.application.dataset_import import UnrecognizedDatasetError
from flightgear_navdata_manager.domain.models import DataSource
from flightgear_navdata_manager.infrastructure import config

from ._faa import FIX_CSV, FIX_TXT, csv_table, write_csv

EXPECTED = {
    "QXALL": (33.12018888, -60.14176111),
    "QXAME": (28.77090833, -111.08281111),
    "QXMYY": (42.39993055, 160.55372777),
    "QXDPO": (-5.16876111, -159.96753333),
    "QXTOP": (-0.87805555, 180.0),
    "QXBON": (0.0, 143.22833333),
}


@pytest.mark.parametrize("sample", [FIX_CSV, FIX_TXT])
def test_valid_fixes_import(app_env, sample):
    summary = app_env["dataset_service"].import_dataset(str(sample))
    assert summary.plan.counts("FIX") == {
        "Imported": 6, "Duplicates skipped": 0, "Identifier conflicts": 0, "Invalid rows": 0,
        "Unsupported": 0, "Warnings": 0,
    }
    fixes = {f.ident: f for f in app_env["waypoint_service"].list_all()}
    for ident, position in EXPECTED.items():
        assert (fixes[ident].latitude, fixes[ident].longitude) == pytest.approx(position, abs=1e-7)
    assert all(f.source == DataSource.IMPORTED for f in fixes.values())


def test_csv_fix_keeps_icao_region_and_cycle(app_env):
    summary = app_env["dataset_service"].import_dataset(str(FIX_CSV))
    fix = next(f for f in app_env["waypoint_service"].list_all() if f.ident == "QXAME")
    assert fix.interop.icao_region == "K2"
    assert fix.origin_file == str(FIX_CSV)
    assert summary.plan.effective_dates == ["2026-09-03"]


def test_fix_txt_has_no_cycle_date_and_none_is_invented(app_env):
    assert app_env["dataset_service"].analyze(str(FIX_TXT)).effective_dates == []


def test_txt_after_csv_is_entirely_already_existing(app_env):
    service = app_env["dataset_service"]
    service.import_dataset(str(FIX_CSV))
    again = service.import_dataset(str(FIX_TXT))
    assert again.plan.counts("FIX")["Duplicates skipped"] == 6
    assert again.imported_count == 0


def test_invalid_fixes_are_reported(app_env, tmp_path):
    header, rows = csv_table(FIX_CSV)
    rows[0]["LAT_MIN"] = "61"                      # invalid coordinate
    rows[1]["FIX_ID"] = "TOOLONGIDENT1"            # fails the manual-entry ident rule
    rows[2]["FIX_ID"] = ""                         # missing identifier
    summary = app_env["dataset_service"].import_dataset(write_csv(tmp_path / "FIX_BASE.csv", header, rows))
    assert summary.plan.counts("FIX")["Imported"] == 3
    reasons = sorted(i.reason for i in summary.plan.invalid)
    assert reasons == [
        "Identifier must be 10 characters or fewer.",
        "invalid latitude '33/61/12.68/N'",
        "no identifier",
    ]


def test_csv_missing_required_fields_is_a_clear_error(app_env, tmp_path):
    header, rows = csv_table(FIX_CSV)
    header = [h for h in header if h not in ("LAT_DEG", "LONG_DEG")]
    with pytest.raises(UnrecognizedDatasetError, match="required FAA FIX fields: LAT_DEG, LONG_DEG"):
        app_env["dataset_service"].analyze(write_csv(tmp_path / "FIX_BASE.csv", header, rows))
    assert app_env["waypoint_service"].list_all() == []


def test_export_contains_imported_fixes(app_env):
    app_env["dataset_service"].import_dataset(str(FIX_CSV))
    lines = config.FIX_DAT_OUTPUT.read_text().splitlines()
    records = {l.split()[2]: l.split() for l in lines[2:-1]}
    assert records.keys() == EXPECTED.keys()
    assert all(len(r) == 3 for r in records.values())
    assert records["QXDPO"][:2] == ["-5.16876111", "-159.96753333"]
