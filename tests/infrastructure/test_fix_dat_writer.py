from datetime import datetime, timezone

from flightgear_navdata_manager.domain.models import DataSource, Fix
from flightgear_navdata_manager.infrastructure.writers.fix_dat_writer import (
    format_fix_record,
    write_fix_dat,
)


def _fix(ident="WAYP1", lat=40.71279000, lon=-74.00595000) -> Fix:
    return Fix(
        id=None,
        source=DataSource.CUSTOM,
        enabled=True,
        created_at=datetime.now(timezone.utc),
        ident=ident,
        latitude=lat,
        longitude=lon,
    )


def test_format_fix_record_matches_verified_3field_shape():
    assert format_fix_record(_fix()) == "40.71279000 -74.00595000 WAYP1"


def test_write_fix_dat_header_terminator_and_field_count(tmp_path):
    path = tmp_path / "custom.dat"
    write_fix_dat([_fix()], str(path))
    lines = path.read_text().splitlines()

    assert lines[0] == "I"
    assert lines[1].startswith("600 Version")
    assert lines[-1] == "99"

    record_line = lines[2]
    assert len(record_line.split()) == 3
    assert record_line == "40.71279000 -74.00595000 WAYP1"


def test_write_fix_dat_with_no_records_still_has_valid_header_and_terminator(tmp_path):
    path = tmp_path / "empty.dat"
    write_fix_dat([], str(path))
    lines = path.read_text().splitlines()
    assert lines == [lines[0], lines[1], "99"]
    assert lines[0] == "I"
