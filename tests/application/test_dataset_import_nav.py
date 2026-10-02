"""FAA NAV data (NAV.txt and NAV_BASE.csv) through DatasetImportService."""

from collections import Counter

import pytest

from flightgear_navdata_manager.domain.models import DataSource, Dme, Ndb, Vor
from flightgear_navdata_manager.infrastructure import config

from ._faa import NAV_CSV, NAV_TXT, by_key, csv_table, nav1, set_field, write_csv, write_lines


def _counts(summary):
    return summary.plan.counts("NAV")


def test_txt_sample_outcomes(app_env):
    summary = app_env["dataset_service"].import_dataset(str(NAV_TXT))
    plan = summary.plan
    assert plan.records_read["NAV"] == 12
    assert _counts(summary) == {
        "Imported": 9, "Duplicates skipped": 0, "Identifier conflicts": 0, "Invalid rows": 3,
        "Unsupported": 3, "Warnings": 0,
    }
    assert plan.to_import_by_kind() == Counter({"DME": 4, "VOR": 3, "NDB": 2})
    assert plan.effective_dates == ["2026-09-03"]
    assert Counter(i.reason for i in plan.unsupported) == {
        "not operational (decommissioned)": 1,
        "VOT facilities are not supported": 1,
        "FAN MARKER facilities are not supported": 1,
    }
    assert sorted(i.reason for i in plan.invalid) == [
        "channel 1X has no paired VHF frequency",
        "no elevation in source",
        "service range can't be determined (class 'HW/DME')",
    ]


def test_csv_sample_outcomes(app_env):
    summary = app_env["dataset_service"].import_dataset(str(NAV_CSV))
    assert summary.plan.sources == [("FAA NASR NAV (CSV)", str(NAV_CSV))]
    assert summary.plan.effective_dates == ["2026-09-03"]
    assert _counts(summary) == {
        "Imported": 9, "Duplicates skipped": 0, "Identifier conflicts": 0, "Invalid rows": 3,
        "Unsupported": 2, "Warnings": 0,
    }


def test_txt_and_csv_produce_equivalent_records(app_env):
    service = app_env["dataset_service"]
    service.import_dataset(str(NAV_CSV))
    again = service.import_dataset(str(NAV_TXT))
    assert _counts(again)["Imported"] == 0
    assert _counts(again)["Duplicates skipped"] == 9


def test_vortac_becomes_vor_plus_dme_with_explicit_field_mapping(app_env):
    app_env["dataset_service"].import_dataset(str(NAV_CSV))
    navaids = by_key(app_env["navaid_service"].list_all())

    vor = navaids[("VOR", "QET")]
    assert isinstance(vor, Vor)
    assert vor.name == "TESTER VORTAC"
    assert vor.latitude == pytest.approx(186425.413 / 3600)
    assert vor.longitude == pytest.approx(-542967.587 / 3600)
    assert vor.elevation_ft == 105            # 105.4 ft, rounded
    assert vor.frequency_mhz == 114.10
    assert vor.range_nm == 130                # VOR service volume "H"
    assert vor.slaved_variation_deg == 14.0   # 14E
    assert vor.source == DataSource.IMPORTED
    assert vor.origin_file == str(NAV_CSV)

    dme = navaids[("DME", "QET")]
    assert isinstance(dme, Dme)
    assert dme.name == "TESTER VORTAC DME"
    assert dme.paired_frequency_mhz == 114.10
    assert dme.range_nm == 130
    assert dme.bias_nm == 0.0


def test_vor_west_variation_and_terminal_service_volume(app_env):
    app_env["dataset_service"].import_dataset(str(NAV_TXT))
    qdn = by_key(app_env["navaid_service"].list_all())[("VOR", "QDN")]
    assert qdn.slaved_variation_deg == -3.0   # 03W
    assert qdn.range_nm == 25                 # "T"
    assert qdn.frequency_mhz == 116.60


def test_ndb_frequency_is_khz_and_range_from_class(app_env):
    app_env["dataset_service"].import_dataset(str(NAV_CSV))
    navaids = by_key(app_env["navaid_service"].list_all())
    qni = navaids[("NDB", "QNI")]
    assert isinstance(qni, Ndb)
    assert qni.frequency_khz == 359
    assert qni.range_nm == 50                 # class "HW": H = 50 nm
    assert qni.name == "BRAVO NDB"
    assert navaids[("NDB", "QDK")].frequency_khz == 530


def test_standalone_dme_and_tacan_use_faa_paired_frequency(app_env):
    app_env["dataset_service"].import_dataset(str(NAV_TXT))
    navaids = by_key(app_env["navaid_service"].list_all())
    assert navaids[("DME", "QZF")].paired_frequency_mhz == 116.75   # channel 114Y
    assert navaids[("DME", "QZF")].name == "CAPE FICTIONA DME"
    assert navaids[("DME", "QER")].paired_frequency_mhz == 113.00   # channel 77X
    assert navaids[("DME", "QER")].name == "ZETA TACAN"


def test_ndb_dme_derives_dme_frequency_from_channel_and_uses_tacan_position(app_env, tmp_path):
    qdk = set_field(nav1("QDK"), 579, 2, "L")  # give it a DME service volume
    app_env["dataset_service"].import_dataset(write_lines(tmp_path / "NAV.txt", [qdk]))
    dme = by_key(app_env["navaid_service"].list_all())[("DME", "QDK")]
    assert dme.paired_frequency_mhz == 114.00           # 87X; the row's 530 is the NDB's kHz
    assert dme.latitude == pytest.approx(154335.867 / 3600)   # TACAN antenna, not the NDB
    assert dme.longitude == pytest.approx(-596427.392 / 3600)
    assert dme.range_nm == 40


def test_txt_service_volume_falls_back_to_class_altitude_code(app_env, tmp_path):
    qet = set_field(set_field(nav1("QET"), 577, 2, ""), 579, 2, "")  # class "H-VORTACW"
    app_env["dataset_service"].import_dataset(write_lines(tmp_path / "NAV.txt", [qet]))
    navaids = by_key(app_env["navaid_service"].list_all())
    assert navaids[("VOR", "QET")].range_nm == 130
    assert navaids[("DME", "QET")].range_nm == 130


def test_csv_vor_without_service_volume_is_invalid_not_guessed(app_env, tmp_path):
    header, rows = csv_table(NAV_CSV)
    qdn = next(r for r in rows if r["NAV_ID"] == "QDN")
    qdn["ALT_CODE"] = ""
    summary = app_env["dataset_service"].import_dataset(write_csv(tmp_path / "NAV_BASE.csv", header, [qdn]))
    assert _counts(summary)["Imported"] == 0
    assert summary.plan.invalid[0].reason == "no service volume or class in source, so its range is unknown"


def test_bad_rows_are_invalid_without_aborting_import(app_env, tmp_path):
    rows = [
        nav1("QET"),
        set_field(nav1("QNI"), 386, 11, "not-a-coord"),     # unparseable latitude
        "NAV9 something odd",                                 # unknown row type
        set_field(nav1("QDN"), 534, 6, "999.99"),           # invalid VOR frequency
        set_field(nav1("QED"), 480, 5, ""),                  # VOR with no mag var
    ]
    summary = app_env["dataset_service"].import_dataset(write_lines(tmp_path / "NAV.txt", rows))
    reasons = [i.reason for i in summary.plan.invalid]
    assert any("latitude" in r for r in reasons)
    assert "unrecognized row type" in reasons
    assert any("VOR frequency should be between" in r for r in reasons)
    assert "no magnetic variation in source" in reasons
    assert summary.plan.to_import_by_kind() == Counter({"VOR": 1, "DME": 2})  # QET VOR+DME, QED DME


def test_csv_invalid_frequency_is_reported(app_env, tmp_path):
    header, rows = csv_table(NAV_CSV)
    qni = next(r for r in rows if r["NAV_ID"] == "QNI")
    qni["FREQ"] = "12"
    summary = app_env["dataset_service"].import_dataset(write_csv(tmp_path / "NAV_BASE.csv", header, [qni]))
    assert summary.plan.invalid[0].reason == "NDB frequency should be between 190 and 1750 kHz."


def test_unsupported_types_are_reported_not_guessed(app_env, tmp_path):
    rows = [
        set_field(nav1("QNI"), 770, 30, "SHUTDOWN"),
        set_field(nav1("QDN"), 9, 20, "CONSOLAN"),
        set_field(nav1("QZF"), 9, 20, ""),                  # no type at all
    ]
    summary = app_env["dataset_service"].import_dataset(write_lines(tmp_path / "NAV.txt", rows))
    assert _counts(summary)["Imported"] == 0
    assert sorted(i.reason for i in summary.plan.unsupported) == [
        "CONSOLAN facilities are not supported",
        "not operational (shutdown)",
        "unknown facilities are not supported",
    ]


def test_fractional_ndb_khz_is_invalid_not_rounded(app_env, tmp_path):
    qni = set_field(nav1("QNI"), 534, 6, "359.5")
    summary = app_env["dataset_service"].import_dataset(write_lines(tmp_path / "NAV.txt", [qni]))
    assert "not a whole number of kHz" in summary.plan.invalid[0].reason


def test_export_is_valid_810_nav_dat(app_env):
    app_env["dataset_service"].import_dataset(str(NAV_CSV))
    lines = config.NAV_DAT_OUTPUT.read_text().splitlines()
    assert lines[0] == "I"
    assert lines[1].startswith("810 Version")
    assert lines[-1] == "99"
    records = [l.split(None, 8) for l in lines[2:-1]]
    assert len(records) == 9
    assert all(len(r) == 9 for r in records)
    by_ident = {(r[0], r[7]): r for r in records}
    assert by_ident[("3", "QET")][4] == "11410"          # MHz*100
    assert by_ident[("2", "QNI")][4] == "359"            # kHz
    assert by_ident[("13", "QET")][8] == "TESTER VORTAC DME"
