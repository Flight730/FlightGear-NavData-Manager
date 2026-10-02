"""Import Dataset with a folder or .zip: discovery, CSV preference,
ignoring unrelated data, FlightGear .dat through the same path, safety."""

import hashlib
import shutil
import zipfile
from pathlib import Path

import pytest

from flightgear_navdata_manager.application.dataset_import import UnrecognizedDatasetError
from flightgear_navdata_manager.infrastructure import config

from ._faa import FIX_CSV, FIX_TXT, FIXTURES, NAV_CSV, NAV_TXT

REAL_NASR = Path.home() / "Desktop" / "28DaySubscription_Effective_2026-09-03"


@pytest.fixture
def nasr_dir(tmp_path):
    folder = tmp_path / "NASR"
    folder.mkdir()
    shutil.copy(FIX_CSV, folder / "FIX_BASE.csv")
    shutil.copy(NAV_CSV, folder / "NAV_BASE.csv")
    (folder / "unrelated.csv").write_text('"EFF_DATE","SITE_NO","ARPT_ID"\n"2026/09/03","1","QDK"\n')
    (folder / "APT.txt").write_text("APT 50009.1A  AIRPORT  QDK" + " " * 1200 + "\n")
    (folder / "FIX_NAV.csv").write_text('"EFF_DATE","FIX_ID","NAV_ID","NAV_TYPE"\n')
    (folder / "README.txt").write_text("FAA NASR subscription\n")
    return folder


def test_folder_imports_only_fix_and_nav(app_env, nasr_dir):
    summary = app_env["dataset_service"].import_dataset(str(nasr_dir))
    plan = summary.plan
    assert sorted(d for d, _ in plan.sources) == ["FAA NASR FIX (CSV)", "FAA NASR NAV (CSV)"]
    assert plan.counts("FIX")["Imported"] == 6
    assert plan.counts("NAV")["Imported"] == 9
    assert {name for name, _ in plan.ignored} == {"unrelated.csv", "APT.txt", "FIX_NAV.csv", "README.txt"}
    assert plan.effective_dates == ["2026-09-03"]


def test_folder_with_both_formats_uses_csv(app_env, nasr_dir):
    shutil.copy(FIX_TXT, nasr_dir / "FIX.txt")
    shutil.copy(NAV_TXT, nasr_dir / "NAV.txt")
    plan = app_env["dataset_service"].analyze(str(nasr_dir))
    assert sorted(d for d, _ in plan.sources) == ["FAA NASR FIX (CSV)", "FAA NASR NAV (CSV)"]
    reasons = dict(plan.ignored)
    assert reasons["FIX.txt"] == "not used: FIX_BASE.csv has the same data (CSV preferred)"
    assert reasons["NAV.txt"] == "not used: NAV_BASE.csv has the same data (CSV preferred)"


def test_folder_with_only_txt_uses_txt(app_env, tmp_path):
    shutil.copy(FIX_TXT, tmp_path / "FIX.txt")
    shutil.copy(NAV_TXT, tmp_path / "NAV.txt")
    plan = app_env["dataset_service"].analyze(str(tmp_path))
    assert sorted(d for d, _ in plan.sources) == ["FAA NASR FIX (TXT)", "FAA NASR NAV (TXT)"]


def test_csv_inside_zip_in_subfolder_is_found(app_env, tmp_path):
    (tmp_path / "CSV_Data").mkdir()
    archive = tmp_path / "CSV_Data" / "03_Sep_2026_CSV.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(FIX_CSV, "FIX_BASE.csv")
        z.write(NAV_CSV, "NAV_BASE.csv")
        z.writestr("APT_BASE.csv", '"EFF_DATE","SITE_NO"\n')
    summary = app_env["dataset_service"].import_dataset(str(tmp_path))
    assert summary.imported_count == 15
    assert all(display.startswith(str(archive) + " > ") for _, display in summary.plan.sources)
    assert sorted(p.name for p in (tmp_path / "CSV_Data").iterdir()) == ["03_Sep_2026_CSV.zip"]


def test_selecting_a_zip_file_directly(app_env, tmp_path):
    archive = tmp_path / "cycle.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(FIX_CSV, "FIX_BASE.csv")
    assert app_env["dataset_service"].import_dataset(str(archive)).imported_count == 6


def test_folder_without_navigation_data_is_a_friendly_error(app_env, tmp_path):
    (tmp_path / "unrelated.csv").write_text("a,b\n1,2\n")
    with pytest.raises(UnrecognizedDatasetError, match="No supported navigation data was found"):
        app_env["dataset_service"].analyze(str(tmp_path))


def test_single_unrecognized_file_says_why(app_env, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello\n")
    with pytest.raises(UnrecognizedDatasetError, match=r"(?s)notes\.txt: not a recognized navigation data file.*Supported:"):
        app_env["dataset_service"].analyze(str(path))


def test_flightgear_dat_files_go_through_the_same_workflow(app_env):
    service = app_env["dataset_service"]
    first = service.import_dataset(str(FIXTURES / "sample_fix_3field.dat"))
    assert first.plan.sources[0][0] == "FlightGear fix.dat"
    assert first.imported_count > 0
    assert service.import_dataset(str(FIXTURES / "sample_fix_3field.dat")).imported_count == 0
    nav = service.import_dataset(str(FIXTURES / "sample_nav_1100.dat"))
    assert nav.plan.sources[0][0] == "FlightGear nav.dat"
    assert nav.plan.counts("NAV")["Imported"] == 2
    assert nav.plan.counts("NAV")["Unsupported"] == 4   # row codes 4, 6, 9, 12


def test_legacy_fix_and_nav_dat_buttons_are_unchanged(app_env):
    summary = app_env["import_service"].import_nav_file(str(FIXTURES / "sample_nav_1100.dat"))
    assert summary.imported_count == 2
    assert summary.skipped_unsupported == {12: 1, 4: 1, 6: 1, 9: 1}


def test_analyze_is_read_only(app_env, nasr_dir):
    app_env["dataset_service"].analyze(str(nasr_dir))
    assert app_env["navaid_service"].list_all() == []
    assert app_env["waypoint_service"].list_all() == []
    assert not config.NAV_DAT_OUTPUT.exists()


def test_sources_are_never_modified_and_only_export_files_are_written(app_env, nasr_dir, tmp_path):
    fg_root = tmp_path / "FlightGear.app" / "Contents" / "Resources" / "data" / "Navaids"
    fg_root.mkdir(parents=True)
    stock = [fg_root / "nav.dat", fg_root / "fix.dat"]
    for f in stock:
        f.write_text("I\n1100 stock\n99\n")
    watched = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}

    app_env["dataset_service"].import_dataset(str(nasr_dir))

    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched} == before
    new_files = {p for p in tmp_path.rglob("*") if p.is_file()} - set(watched)
    assert new_files == {config.FIX_DAT_OUTPUT, config.NAV_DAT_OUTPUT}


@pytest.mark.skipif(not REAL_NASR.exists(), reason="real FAA NASR subscription not available")
def test_real_nasr_subscription_folder(app_env):
    service = app_env["dataset_service"]
    summary = service.import_dataset(str(REAL_NASR))
    plan = summary.plan
    assert sorted(d for d, _ in plan.sources) == ["FAA NASR FIX (CSV)", "FAA NASR NAV (CSV)"]
    assert plan.counts("FIX")["Imported"] > 60000
    assert plan.counts("NAV")["Imported"] > 2000
    assert plan.counts("FIX")["Invalid rows"] == 0
    # The legacy TXT files describe the same cycle.
    fix_txt = service.analyze(str(REAL_NASR / "FIX.txt"))
    assert fix_txt.counts("FIX")["Imported"] == 0
    assert fix_txt.counts("FIX")["Identifier conflicts"] == 0
