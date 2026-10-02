from pathlib import Path

from flightgear_navdata_manager.infrastructure.parsers.nav_dat_parser import parse_nav_dat

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_810_shape_supported_rows_and_skips_unsupported():
    result = parse_nav_dat(str(FIXTURES / "sample_nav_810.dat"))
    # 3 supported records (NDB, VOR, DME); the LOC (row 4) line is
    # unsupported in MVP 1 and must be reported, not silently dropped.
    assert [r.row_code for r in result.records] == [2, 3, 13]
    assert result.skipped_unsupported_row_codes == {4: 1}

    ndb = result.records[0]
    assert ndb.ident == "QPH"
    assert ndb.freq_raw == 396  # literal kHz, verified against navdb.cxx
    assert ndb.name == "EXAMPLE NDB"
    assert ndb.interop is None  # 810 shape has no region/terminal columns

    vor = result.records[1]
    assert vor.ident == "QAL"
    assert vor.freq_raw == 11670  # MHz x100
    assert vor.multiuse == 1.0  # slaved variation

    dme = result.records[2]
    assert dme.ident == "QS"
    assert dme.row_code == 13
    assert dme.freq_raw == 10875  # paired VHF freq, MHz x100 -- not a channel


def test_parses_1100_shape_and_captures_interop():
    result = parse_nav_dat(str(FIXTURES / "sample_nav_1100.dat"))
    # Supported: NDB (2), VOR (3). Unsupported: paired DME (12), LOC (4),
    # GS (6), IM (9) -- all correctly excluded from MVP 1.
    assert [r.row_code for r in result.records] == [2, 3]
    assert result.skipped_unsupported_row_codes == {12: 1, 4: 1, 6: 1, 9: 1}

    ndb = result.records[0]
    assert ndb.ident == "QF"
    assert ndb.interop is not None
    assert ndb.interop.scope == "ENRT"
    assert ndb.interop.icao_region == "K1"
    assert ndb.name == "QXOLA/QZBF LMM RW13R NDB"

    vor = result.records[1]
    assert vor.ident == "QSA"
    assert vor.name == "TESTCTR VORTAC"


def test_unparseable_version_header_yields_no_records(tmp_path):
    path = tmp_path / "nav.dat"
    path.write_text("I\nnot-a-version\n2 1.0 2.0 0 100 10 0.0 X NAME\n99\n")
    result = parse_nav_dat(str(path))
    assert result.records == []
    assert result.warnings


def test_line_shorter_than_9_fields_is_skipped_not_crashed(tmp_path):
    # A >=1100 header with a too-short line must not raise -- this is
    # exactly the scenario that is undefined behavior in FlightGear's
    # own C++ parser; our parser must degrade to a warning instead.
    path = tmp_path / "nav.dat"
    path.write_text("I\n1100 Version\n2 1.0 2.0 0 100 10 0.0\n99\n")
    result = parse_nav_dat(str(path))
    assert result.records == []
    assert any("skipped" in w for w in result.warnings)


def test_frequency_and_range_tolerate_float_formatted_integers(tmp_path):
    # Real-world third-party files sometimes write "396.0" instead of
    # "396" for fields the spec defines as integers. Elevation already
    # tolerated this (int(float(...))); freq/range previously used a
    # bare int() and would have raised ValueError -- fixed during code
    # review, verified here.
    path = tmp_path / "nav.dat"
    path.write_text("I\n810 Version\n2 1.0 2.0 0.0 396.0 50.0 0.0 TEST NAME\n99\n")
    result = parse_nav_dat(str(path))
    assert result.warnings == []
    assert len(result.records) == 1
    assert result.records[0].freq_raw == 396
    assert result.records[0].range_nm == 50


def test_1100_header_with_only_9_actual_fields_is_handled_safely(tmp_path):
    # This is precisely the unsafe FlightGear scenario: version >= 1100
    # declared, but the line only has 9 real fields, so fields[10] would
    # be out-of-bounds in FlightGear's C++. Our parser must catch this
    # as an IndexError and report a warning, never raise out of parse_nav_dat.
    path = tmp_path / "nav.dat"
    path.write_text("I\n1100 Version\n2 1.0 2.0 0 100 10 0.0 IDNT ENRT\n99\n")
    result = parse_nav_dat(str(path))
    assert result.records == []
    assert any("skipped" in w for w in result.warnings)
