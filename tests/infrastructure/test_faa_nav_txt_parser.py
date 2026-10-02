from pathlib import Path

import pytest

from flightgear_navdata_manager.infrastructure.parsers.faa_common import (
    parse_all_seconds,
    parse_formatted_dms,
    parse_magnetic_variation,
)
from flightgear_navdata_manager.infrastructure.parsers.faa_nav_txt_parser import (
    parse_faa_nav_txt as parse_faa_nav,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample_faa_nav.txt"


def sample_lines() -> list[str]:
    return SAMPLE.read_text(encoding="latin-1").splitlines()


def set_field(line: str, start: int, length: int, value: str) -> str:
    """Overwrite a 1-based fixed-width column, as nav_rf.txt numbers them."""
    return line[: start - 1] + value.ljust(length)[:length] + line[start - 1 + length :]


def nav1(ident: str) -> str:
    return next(l for l in sample_lines() if l.startswith("NAV1") and l[28:32].strip() == ident)


# --- conversions --------------------------------------------------------

def test_all_seconds_conversion_matches_faa_layout_example():
    # 30-06-51.070N == 108411.070N ; 064-27-54.660W == 232074.660W (synthetic values)
    assert parse_all_seconds("108411.070N", True) == pytest.approx(30.1141861, abs=1e-7)
    assert parse_all_seconds("232074.660W", False) == pytest.approx(-64.4651833, abs=1e-7)
    assert parse_all_seconds("154336.430S", True) == pytest.approx(-42.8712306, abs=1e-7)


def test_formatted_dms_conversion_agrees_with_all_seconds():
    assert parse_formatted_dms("30-06-51.070N", True) == pytest.approx(
        parse_all_seconds("108411.070N", True)
    )
    assert parse_formatted_dms("064-27-54.660W", False) == pytest.approx(-64.4651833, abs=1e-7)


@pytest.mark.parametrize(
    "text, is_lat",
    [("108411.070E", True), ("108411.070N", False), ("abc", True), ("400000.000N", True),
     ("30-61-00.000N", True), ("", True)],
)
def test_invalid_coordinates_return_none(text, is_lat):
    assert parse_all_seconds(text, is_lat) is None
    assert parse_formatted_dms(text, is_lat) is None


def test_magnetic_variation_signs():
    assert parse_magnetic_variation("14E") == 14.0
    assert parse_magnetic_variation("03W") == -3.0
    assert parse_magnetic_variation("  ") is None
    with pytest.raises(ValueError):
        parse_magnetic_variation("14X")


# --- whole-file parsing ---------------------------------------------------

def test_parses_real_sample_rows_and_counts_detail_rows():
    result = parse_faa_nav(str(SAMPLE))
    assert result.rows_read == 12
    assert len(result.records) == 12
    assert result.issues == []
    assert result.detail_rows == {"NAV2": 1, "NAV3": 1, "NAV4": 1}


def test_real_vortac_fields():
    qet = next(r for r in parse_faa_nav(str(SAMPLE)).records if r.ident == "QET")
    assert qet.facility_type == "VORTAC"
    assert qet.name == "TESTER"
    assert qet.state_code == "AK"
    assert qet.latitude == pytest.approx(51 + 47 / 60 + 5.413 / 3600)
    assert qet.longitude == pytest.approx(-(150 + 49 / 60 + 27.587 / 3600))
    assert qet.elevation_ft == 105.4
    assert qet.magnetic_variation_deg == 14.0
    assert qet.channel == "88X"
    assert qet.frequency == 114.10
    assert qet.vor_service_volume == "H"
    assert qet.dme_service_volume == "H"
    assert qet.status == "OPERATIONAL IFR"
    assert qet.effective_date == "2026-09-03"   # NAV1 col 33, "09/03/2026"


def test_separately_sited_tacan_position_is_captured():
    qdk = next(r for r in parse_faa_nav(str(SAMPLE)).records if r.ident == "QDK")
    assert qdk.latitude == pytest.approx(154338.755 / 3600)
    assert qdk.tacan_latitude == pytest.approx(154335.867 / 3600)
    assert qdk.tacan_longitude == pytest.approx(-596427.392 / 3600)


def test_malformed_rows_are_reported_without_aborting(tmp_path):
    bad_lat = set_field(nav1("QNI"), 386, 11, "12X456.000N")
    bad_elev = set_field(nav1("QDN"), 473, 7, "  12a.4")
    bad_var = set_field(nav1("QZF"), 480, 5, "  99Q")
    path = tmp_path / "NAV.txt"
    path.write_text(
        "\r\n".join([nav1("QET"), bad_lat, "XXXXgarbage", bad_elev, bad_var, "", nav1("QED")]) + "\r\n",
        encoding="latin-1",
    )

    result = parse_faa_nav(str(path))

    assert [r.ident for r in result.records] == ["QET", "QED"]
    assert result.rows_read == 5
    reasons = {i.line_number: i.reason for i in result.issues}
    assert "latitude" in reasons[2]
    assert reasons[3] == "unrecognized row type"
    assert "elevation" in reasons[4]
    assert "magnetic variation" in reasons[5]


def test_row_with_trailing_blanks_stripped_still_parses(tmp_path):
    path = tmp_path / "NAV.txt"
    path.write_text(nav1("QDN").rstrip() + "\n", encoding="latin-1")
    [record] = parse_faa_nav(str(path)).records
    assert record.status == "OPERATIONAL IFR"
    assert record.frequency == 116.60


def test_parser_never_modifies_source():
    before = SAMPLE.read_bytes()
    parse_faa_nav(str(SAMPLE))
    assert SAMPLE.read_bytes() == before
