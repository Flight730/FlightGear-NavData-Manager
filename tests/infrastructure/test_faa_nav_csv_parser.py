import csv
import io
from pathlib import Path

import pytest

from flightgear_navdata_manager.infrastructure.parsers.faa_nav_csv_parser import parse_faa_nav_csv
from flightgear_navdata_manager.infrastructure.parsers.faa_nav_txt_parser import parse_faa_nav_txt

FIXTURES = Path(__file__).parent / "fixtures"
CSV_SAMPLE = FIXTURES / "sample_faa_nav.csv"


def test_csv_and_txt_agree_on_shared_facilities():
    csv_records = {(r.ident, r.facility_type): r for r in parse_faa_nav_csv(str(CSV_SAMPLE)).records}
    txt_records = {(r.ident, r.facility_type): r for r in parse_faa_nav_txt(str(FIXTURES / "sample_faa_nav.txt")).records}
    shared = csv_records.keys() & txt_records.keys()
    assert len(shared) >= 9
    for key in shared:
        c, t = csv_records[key], txt_records[key]
        assert (c.latitude, c.longitude) == pytest.approx((t.latitude, t.longitude), abs=1e-6), key
        assert c.frequency == t.frequency, key
        assert c.channel == t.channel, key
        assert c.elevation_ft == t.elevation_ft, key
        assert c.magnetic_variation_deg == t.magnetic_variation_deg, key
        assert c.name == t.name, key


def test_csv_vortac_fields():
    qet = next(r for r in parse_faa_nav_csv(str(CSV_SAMPLE)).records if r.ident == "QET")
    assert qet.facility_type == "VORTAC"
    assert qet.frequency == 114.10
    assert qet.channel == "88X"
    assert qet.magnetic_variation_deg == 14.0
    assert qet.vor_service_volume == "H"      # ALT_CODE
    assert qet.dme_service_volume == "H"
    assert qet.effective_date == "2026-09-03"


def test_csv_ndb_class_and_tacan_position():
    records = {r.ident: r for r in parse_faa_nav_csv(str(CSV_SAMPLE)).records}
    assert records["QNI"].navaid_class == "HW"
    assert records["QDK"].tacan_latitude == pytest.approx(154335.867 / 3600, abs=1e-6)


def test_csv_bad_values_are_reported_per_row(tmp_path):
    rows = list(csv.reader(io.StringIO(CSV_SAMPLE.read_text())))
    header, data = rows[0], rows[1:]
    col = {name: i for i, name in enumerate(header)}
    data[0][col["FREQ"]] = "one-ten"
    data[1][col["MAG_VARN_HEMIS"]] = "Q"
    buffer = io.StringIO()
    csv.writer(buffer).writerows([header, *data])
    path = tmp_path / "NAV_BASE.csv"
    path.write_text(buffer.getvalue())

    result = parse_faa_nav_csv(str(path))
    assert len(result.records) == len(data) - 2
    reasons = sorted(i.reason for i in result.issues)
    assert reasons[0].startswith("invalid frequency")
    assert reasons[1].startswith("invalid magnetic variation")
