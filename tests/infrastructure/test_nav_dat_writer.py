from datetime import datetime, timezone

from flightgear_navdata_manager.domain.models import DataSource, Dme, Ndb, Vor
from flightgear_navdata_manager.infrastructure.writers.nav_dat_writer import (
    format_dme_record,
    format_ndb_record,
    format_vor_record,
    write_nav_dat,
)

_NOW = datetime.now(timezone.utc)


def _ndb() -> Ndb:
    return Ndb(
        id=None, source=DataSource.CUSTOM, enabled=True, created_at=_NOW,
        ident="TSTA", name="TEST STATION NDB", latitude=40.71279000, longitude=-74.00595000,
        elevation_ft=150, frequency_khz=362, range_nm=50,
    )


def _vor() -> Vor:
    return Vor(
        id=None, source=DataSource.CUSTOM, enabled=True, created_at=_NOW,
        ident="TSTV", name="TEST STATION VOR", latitude=40.71279000, longitude=-74.00595000,
        elevation_ft=210, frequency_mhz=116.80, range_nm=130, slaved_variation_deg=19.0,
    )


def _dme() -> Dme:
    return Dme(
        id=None, source=DataSource.CUSTOM, enabled=True, created_at=_NOW,
        ident="TSTD", name="TEST STATION DME", latitude=40.71279000, longitude=-74.00595000,
        elevation_ft=210, paired_frequency_mhz=116.80, range_nm=25, bias_nm=0.0,
    )


def test_ndb_record_matches_verified_9field_810_shape():
    line = format_ndb_record(_ndb())
    assert line == "2 40.71279000 -74.00595000 150 362 50 0.0 TSTA TEST STATION NDB"
    assert len(line.split(None, 8)) == 9


def test_vor_record_encodes_frequency_as_mhz_x100():
    line = format_vor_record(_vor())
    assert line == "3 40.71279000 -74.00595000 210 11680 130 19.000 TSTV TEST STATION VOR"
    assert len(line.split(None, 8)) == 9


def test_dme_record_uses_row_13_and_paired_vhf_frequency_not_a_channel():
    line = format_dme_record(_dme())
    assert line == "13 40.71279000 -74.00595000 210 11680 25 0.000 TSTD TEST STATION DME"
    assert len(line.split(None, 8)) == 9


def test_write_nav_dat_header_declares_810_matching_9field_output(tmp_path):
    path = tmp_path / "custom.dat"
    write_nav_dat([_ndb(), _vor(), _dme()], str(path))
    lines = path.read_text().splitlines()

    assert lines[0] == "I"
    assert lines[1].startswith("810 Version")
    assert lines[-1] == "99"

    record_lines = lines[2:-1]
    assert len(record_lines) == 3
    for line in record_lines:
        # Exactly 9 fields, every record, no exceptions -- this is the
        # safety-critical invariant behind declaring an 810 header.
        assert len(line.split(None, 8)) == 9


def test_write_nav_dat_orders_records_by_row_code(tmp_path):
    path = tmp_path / "custom.dat"
    # Deliberately out of order on input.
    write_nav_dat([_dme(), _ndb(), _vor()], str(path))
    lines = path.read_text().splitlines()
    row_codes = [int(line.split()[0]) for line in lines[2:-1]]
    assert row_codes == [2, 3, 13]
