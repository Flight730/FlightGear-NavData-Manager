from pathlib import Path

import pytest

from flightgear_navdata_manager.infrastructure.parsers.faa_common import SourceFile
from flightgear_navdata_manager.infrastructure.parsers.faa_dataset_detector import (
    FaaSourceType,
    detect_faa_source,
    inspect_faa_source,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIX_CSV_HEADER = (FIXTURES / "sample_faa_fix.csv").read_text().splitlines()[0]
NAV_CSV_HEADER = (FIXTURES / "sample_faa_nav.csv").read_text().splitlines()[0]


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_real_samples_are_recognized():
    assert detect_faa_source(str(FIXTURES / "sample_faa_fix.txt")) is FaaSourceType.FIX_TXT
    assert detect_faa_source(str(FIXTURES / "sample_faa_nav.txt")) is FaaSourceType.NAV_TXT
    assert detect_faa_source(str(FIXTURES / "sample_faa_fix.csv")) is FaaSourceType.FIX_CSV
    assert detect_faa_source(str(FIXTURES / "sample_faa_nav.csv")) is FaaSourceType.NAV_CSV


def test_csv_is_detected_by_header_not_filename(tmp_path):
    assert detect_faa_source(_write(tmp_path, "whatever.csv", FIX_CSV_HEADER + "\n")) is FaaSourceType.FIX_CSV
    assert detect_faa_source(_write(tmp_path, "FIX_BASE.csv", "a,b,c\n1,2,3\n")) is FaaSourceType.UNKNOWN


def test_csv_detection_ignores_column_order_and_header_formatting(tmp_path):
    columns = [c.strip('"') for c in NAV_CSV_HEADER.split(",")]
    reformatted = ",".join(f'" {c.lower().replace("_", " ")} "' for c in reversed(columns))
    assert detect_faa_source(_write(tmp_path, "nav.csv", reformatted + "\n")) is FaaSourceType.NAV_CSV


def test_fix_csv_missing_required_columns_explains_what_is_missing(tmp_path):
    header = FIX_CSV_HEADER.replace('"LAT_SEC",', "").replace('"LONG_HEMIS",', "")
    detection = inspect_faa_source(SourceFile(_write(tmp_path, "FIX_BASE.csv", header + "\n")))
    assert detection.type is FaaSourceType.UNKNOWN
    assert detection.reason == "This CSV does not contain the required FAA FIX fields: LAT_SEC, LONG_HEMIS"


def test_nav_csv_missing_required_columns_explains_what_is_missing(tmp_path):
    header = NAV_CSV_HEADER.replace('"FREQ",', "")
    detection = inspect_faa_source(SourceFile(_write(tmp_path, "NAV_BASE.csv", header + "\n")))
    assert detection.reason == "This CSV does not contain the required FAA NAV fields: FREQ"


@pytest.mark.parametrize(
    "name, header, reason_part",
    [
        ("FIX_NAV.csv", '"EFF_DATE","FIX_ID","ICAO_REGION_CODE","NAV_ID","NAV_TYPE","BEARING","DISTANCE"', "cross-reference"),
        ("FIX_CHRT.csv", '"EFF_DATE","FIX_ID","ICAO_REGION_CODE","CHARTING_TYPE_DESC"', "no positions"),
        ("NAV_RMK.csv", '"EFF_DATE","NAV_ID","NAV_TYPE","REMARK"', "no positions"),
        ("APT_BASE.csv", '"EFF_DATE","SITE_NO","ARPT_ID","LAT_DECIMAL"', "not an FAA FIX or NAV file"),
    ],
)
def test_related_but_unimportable_csvs_are_unknown(tmp_path, name, header, reason_part):
    detection = inspect_faa_source(SourceFile(_write(tmp_path, name, header + "\n")))
    assert detection.type is FaaSourceType.UNKNOWN
    assert reason_part in detection.reason


@pytest.mark.parametrize(
    "name, text",
    [
        ("APT.txt", "APT 50009.1A  AIRPORT  QDK     09/03/2026AAL" + " " * 900),
        ("nav_rf.txt", "\n                                NAVAID\n   DATA BASE RECORD LAYOUT\n"),
        ("NAV.txt", "NAV1QET VORTAC  truncated\n"),         # right prefix, wrong width
        ("empty.txt", ""),
        ("notes.md", "NAV1..."),                             # not .txt/.csv
        ("binary.csv", "\x00\x01\x02garbage"),
    ],
)
def test_unrelated_or_malformed_files_are_unknown(tmp_path, name, text):
    assert detect_faa_source(_write(tmp_path, name, text)) is FaaSourceType.UNKNOWN


def test_txt_with_trailing_blanks_stripped_is_still_recognized(tmp_path):
    first = (FIXTURES / "sample_faa_fix.txt").read_text().splitlines()[0].rstrip()
    assert detect_faa_source(_write(tmp_path, "FIX.txt", first + "\n")) is FaaSourceType.FIX_TXT
