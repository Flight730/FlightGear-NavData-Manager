import zipfile
from pathlib import Path

import pytest

from flightgear_navdata_manager.infrastructure.parsers.faa_common import (
    SourceFile,
    dms_to_decimal,
    normalize_date,
    normalize_header,
    parse_formatted_dms,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "deg, minutes, sec, hemis, is_lat, expected",
    [
        (33, 7, 12.68, "N", True, 33.12018888),        # QXALL
        (60, 8, 30.34, "W", False, -60.14176111),
        (5, 10, 7.54, "S", True, -5.16876111),        # QXDPO, southern hemisphere
        (160, 33, 13.42, "E", False, 160.55372777),    # QXMYY, eastern hemisphere
        (180, 0, 0, "E", False, 180.0),                # QXTOP, antimeridian
        (0, 0, 0, "S", True, 0.0),                     # QXBON, on the equator
        (90, 0, 0, "n", True, 90.0),                   # hemisphere case-insensitive
    ],
)
def test_dms_conversion_all_hemispheres(deg, minutes, sec, hemis, is_lat, expected):
    # expected values are the sample files' LAT_DECIMAL / LONG_DECIMAL columns
    assert dms_to_decimal(deg, minutes, sec, hemis, is_lat) == pytest.approx(expected, abs=1e-7)


@pytest.mark.parametrize(
    "deg, minutes, sec, hemis, is_lat",
    [
        (91, 0, 0, "N", True),      # latitude > 90
        (180, 0, 1, "E", False),    # longitude > 180
        (40, 60, 0, "N", True),     # minutes out of range
        (40, 0, 60, "N", True),     # seconds out of range
        (-40, 0, 0, "N", True),     # sign belongs in the hemisphere
        (40, 0, 0, "E", True),      # longitude hemisphere on a latitude
        (40, 0, 0, "N", False),     # latitude hemisphere on a longitude
        (40, 0, 0, "", True),
    ],
)
def test_invalid_dms_is_rejected(deg, minutes, sec, hemis, is_lat):
    assert dms_to_decimal(deg, minutes, sec, hemis, is_lat) is None


def test_formatted_dms_as_used_by_fix_txt():
    assert parse_formatted_dms("05-10-07.540S", True) == pytest.approx(-5.16876111, abs=1e-7)
    assert parse_formatted_dms("160-33-13.420E", False) == pytest.approx(160.55372777, abs=1e-7)
    assert parse_formatted_dms("05-10-07.540", True) is None


@pytest.mark.parametrize(
    "raw, expected",
    [("FIX_ID", "FIX_ID"), (" fix id ", "FIX_ID"), ("Lat-Decimal", "LAT_DECIMAL"),
     ("COUNTRY_CODE  ", "COUNTRY_CODE"), ("LAT__DEG", "LAT_DEG"), ("﻿EFF_DATE", "EFF_DATE")],
)
def test_header_normalization(raw, expected):
    assert normalize_header(raw) == expected


def test_effective_dates_are_normalized_and_never_guessed():
    assert normalize_date("2026/09/03") == "2026-09-03"   # CSV
    assert normalize_date("09/03/2026") == "2026-09-03"   # TXT
    assert normalize_date("") is None
    assert normalize_date("Sep 3 2026") is None


def test_zip_member_is_read_without_extracting(tmp_path):
    archive = tmp_path / "cycle.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(FIXTURES / "sample_faa_fix.csv", "FIX_BASE.csv")
    source = SourceFile(str(archive), "FIX_BASE.csv")
    assert source.name == "FIX_BASE.csv"
    assert source.read_head().startswith('"EFF_DATE"')
    with source.open_text("utf-8-sig") as f:
        assert f.read() == (FIXTURES / "sample_faa_fix.csv").read_bytes().decode("utf-8")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cycle.zip"]
