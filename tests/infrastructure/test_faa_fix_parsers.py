"""FIX.txt and FIX_BASE.csv parsers: same six real fixes (one per
hemisphere case), same results."""

import csv
import io
from pathlib import Path

import pytest

from flightgear_navdata_manager.infrastructure.parsers.faa_common import FaaFormatError
from flightgear_navdata_manager.infrastructure.parsers.faa_fix_csv_parser import parse_faa_fix_csv
from flightgear_navdata_manager.infrastructure.parsers.faa_fix_txt_parser import parse_faa_fix_txt

FIXTURES = Path(__file__).parent / "fixtures"
CSV_SAMPLE = FIXTURES / "sample_faa_fix.csv"
TXT_SAMPLE = FIXTURES / "sample_faa_fix.txt"

EXPECTED = {  # FAA's own decimal columns
    "QXALL": (33.12018888, -60.14176111),
    "QXAME": (28.77090833, -111.08281111),
    "QXMYY": (42.39993055, 160.55372777),
    "QXDPO": (-5.16876111, -159.96753333),
    "QXTOP": (-0.87805555, 180.0),
    "QXBON": (0.0, 143.22833333),
}


def _csv_rows() -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(CSV_SAMPLE.read_text())))
    return rows[0], rows[1:]


def _write_csv(tmp_path, header, rows) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, quoting=csv.QUOTE_ALL).writerows([header, *rows])
    path = tmp_path / "FIX_BASE.csv"
    path.write_text(buffer.getvalue())
    return str(path)


@pytest.mark.parametrize("parse, sample", [(parse_faa_fix_csv, CSV_SAMPLE), (parse_faa_fix_txt, TXT_SAMPLE)])
def test_both_formats_give_the_same_positions(parse, sample):
    result = parse(str(sample))
    assert result.issues == []
    assert result.rows_read == 6
    positions = {r.ident: (r.latitude, r.longitude) for r in result.records}
    assert positions.keys() == EXPECTED.keys()
    for ident, (lat, lon) in EXPECTED.items():
        assert positions[ident] == pytest.approx((lat, lon), abs=1e-7), ident


def test_csv_fields_and_effective_date():
    record = next(r for r in parse_faa_fix_csv(str(CSV_SAMPLE)).records if r.ident == "QXAME")
    assert record.icao_region == "K2"
    assert record.state == "CA"
    assert record.use == "WP"
    assert record.effective_date == "2026-09-03"


def test_txt_fields_and_detail_rows_counted():
    result = parse_faa_fix_txt(str(TXT_SAMPLE))
    record = next(r for r in result.records if r.ident == "QXDPO")
    assert record.icao_region == "P"
    assert record.state == "AMERICAN SAMOA"
    assert record.effective_date is None       # FIX.txt has no date field; never invented
    assert result.detail_rows == {"FIX2": 2, "FIX5": 2}


def test_csv_column_order_does_not_matter(tmp_path):
    header, rows = _csv_rows()
    order = list(reversed(range(len(header))))
    path = _write_csv(tmp_path, [header[i] for i in order], [[r[i] for i in order] for r in rows])
    positions = {r.ident: (r.latitude, r.longitude) for r in parse_faa_fix_csv(path).records}
    assert positions["QXDPO"] == pytest.approx(EXPECTED["QXDPO"], abs=1e-7)


def test_csv_quoted_fields_with_commas_and_quotes(tmp_path):
    header, rows = _csv_rows()
    remark = header.index("CHARTING_REMARK")
    rows[0][remark] = 'SEE "NOTE", CHART A, B'
    result = parse_faa_fix_csv(_write_csv(tmp_path, header, rows))
    assert result.issues == []
    assert len(result.records) == 6


def test_csv_invalid_and_inconsistent_coordinates_are_reported(tmp_path):
    header, rows = _csv_rows()
    col = {name: i for i, name in enumerate(header)}
    rows[0][col["LAT_MIN"]] = "75"                     # out of range
    rows[1][col["LONG_HEMIS"]] = "N"                   # wrong hemisphere letter
    rows[2][col["LAT_DECIMAL"]] = "12.5"               # disagrees with the DMS columns
    rows[3][col["LAT_SEC"]] = "abc"
    result = parse_faa_fix_csv(_write_csv(tmp_path, header, rows))
    assert len(result.records) == 2
    reasons = [i.reason for i in result.issues]
    assert sum("invalid latitude" in r for r in reasons) == 2
    assert any("invalid longitude" in r for r in reasons)
    assert any("disagrees with decimal value 12.5" in r for r in reasons)


def test_csv_row_with_wrong_field_count_is_reported(tmp_path):
    path = tmp_path / "FIX_BASE.csv"
    text = CSV_SAMPLE.read_text().splitlines()
    text.insert(2, '"2026/09/03","SHORT","K2"')
    path.write_text("\n".join(text) + "\n")
    result = parse_faa_fix_csv(str(path))
    assert len(result.records) == 6
    assert result.issues[0].reason.startswith("malformed row: 3 fields")


def test_csv_missing_required_columns_is_a_clear_error(tmp_path):
    header, rows = _csv_rows()
    keep = [i for i, name in enumerate(header) if name not in ("FIX_ID", "LAT_DEG")]
    path = _write_csv(tmp_path, [header[i] for i in keep], [[r[i] for i in keep] for r in rows])
    with pytest.raises(FaaFormatError, match="required FAA FIX fields: FIX_ID, LAT_DEG"):
        parse_faa_fix_csv(path)


def test_txt_invalid_coordinates_are_reported(tmp_path):
    lines = TXT_SAMPLE.read_text().splitlines()
    lines[0] = lines[0][:66] + "14-10-07.540X" + lines[0][79:]
    path = tmp_path / "FIX.txt"
    path.write_text("\n".join(lines) + "\n")
    result = parse_faa_fix_txt(str(path))
    assert len(result.records) == 5
    assert result.issues[0].reason == "invalid latitude '14-10-07.540X'"
