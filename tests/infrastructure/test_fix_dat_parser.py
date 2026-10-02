from pathlib import Path

from flightgear_navdata_manager.infrastructure.parsers.fix_dat_parser import parse_fix_dat

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_3field_records():
    result = parse_fix_dat(str(FIXTURES / "sample_fix_3field.dat"))
    assert [r.ident for r in result.records] == ["0000E", "0010N", "QXYRR"]
    assert result.records[2].latitude == 37.646819444
    assert result.records[2].longitude == -112.722388889
    # No interop data available from a 3-field source.
    assert all(r.interop is None for r in result.records)


def test_parses_5field_records_and_captures_interop():
    result = parse_fix_dat(str(FIXTURES / "sample_fix_5field.dat"))
    assert len(result.records) == 2
    first = result.records[0]
    assert first.ident == "QXYRR"
    assert first.interop is not None
    assert first.interop.scope == "QZSE"
    assert first.interop.icao_region == "K1"
    assert first.interop.source_field_count == 5

    second = result.records[1]
    assert second.interop.scope == "ENRT"
    assert second.interop.icao_region == "K2"


def test_stops_at_terminator_and_ignores_trailing_lines(tmp_path):
    path = tmp_path / "fix.dat"
    path.write_text("I\n600 Version\n1.0 2.0 ABCDE\n99\n1.0 2.0 SHOULDNOTAPPEAR\n")
    result = parse_fix_dat(str(path))
    assert [r.ident for r in result.records] == ["ABCDE"]


def test_malformed_lines_are_warned_and_skipped(tmp_path):
    path = tmp_path / "fix.dat"
    path.write_text("I\n600 Version\nonlyonefield\n1.0 2.0\n1.0 2.0 OK\n99\n")
    result = parse_fix_dat(str(path))
    assert [r.ident for r in result.records] == ["OK"]
    assert len(result.warnings) == 2


def test_reads_gzip_transparently(tmp_path):
    import gzip

    plain = "I\n600 Version\n1.0 2.0 GZOK\n99\n"
    path = tmp_path / "fix.dat.gz"
    path.write_bytes(gzip.compress(plain.encode("utf-8")))
    result = parse_fix_dat(str(path))
    assert [r.ident for r in result.records] == ["GZOK"]
