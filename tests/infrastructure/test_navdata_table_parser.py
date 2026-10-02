"""This app's CSV/TXT table format: layout detection and row reading."""

import pytest

from flightgear_navdata_manager.infrastructure.parsers.faa_common import SourceFile
from flightgear_navdata_manager.infrastructure.parsers.navdata_table_parser import (
    COLUMNS,
    RecordTypeRequired,
    TableFormatError,
    TableProbe,
    detect_layout,
    inspect_navdata_table,
    parse_navdata_table,
)

HEADER = ",".join(COLUMNS)
EXAMPLE = f"""{HEADER}
FIX,EBAYE,EBAYE,37.621,-122.379,0,,
NDB,ABC,Example NDB,37.500,-122.300,50,375,50
VOR,XYZ,Example VOR,37.600,-122.400,100,113.2,130
DME,XYZ,Example DME,37.600,-122.400,100,113.2,130
"""


def _write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding) if isinstance(text, str) else text)
    return str(path)


def test_csv_with_header(tmp_path):
    result = parse_navdata_table(_write(tmp_path, "data.csv", EXAMPLE))
    assert result.layout.delimiter == ","
    assert result.layout.header == list(COLUMNS)
    assert [r.get("ident") for r in result.rows] == ["EBAYE", "ABC", "XYZ", "XYZ"]
    assert [r.line_number for r in result.rows] == [2, 3, 4, 5]
    assert result.rows[0].get("frequency") == ""          # blank optional field
    assert result.issues == []


def test_quoted_name_containing_commas_and_quotes(tmp_path):
    text = HEADER + '\nNDB,ABC,"Smith, Jones ""North"" NDB",37.5,-122.3,50,375,50\n'
    [row] = parse_navdata_table(_write(tmp_path, "data.csv", text)).rows
    assert row.get("name") == 'Smith, Jones "North" NDB'


def test_whitespace_is_trimmed_everywhere(tmp_path):
    text = " Type , IDENT ,name,latitude,longitude,elevation_ft,frequency,range_nm\n  FIX ,  EBAYE , , 37.621 ,-122.379,,,\n"
    [row] = parse_navdata_table(_write(tmp_path, "data.csv", text)).rows
    assert (row.get("type"), row.get("ident"), row.get("latitude")) == ("FIX", "EBAYE", "37.621")


def test_columns_found_by_name_in_any_order(tmp_path):
    text = "latitude,longitude,ident,type\n37.621,-122.379,EBAYE,FIX\n"
    [row] = parse_navdata_table(_write(tmp_path, "fixes.csv", text)).rows
    assert row.get("ident") == "EBAYE" and row.get("name") == ""


def test_missing_required_column_is_refused(tmp_path):
    with pytest.raises(TableFormatError, match="missing required column\\(s\\): latitude"):
        parse_navdata_table(_write(tmp_path, "data.csv", "type,ident,longitude\nFIX,A,1\n"))


def test_unknown_columns_are_reported_not_used(tmp_path):
    result = parse_navdata_table(_write(tmp_path, "data.csv", "type,ident,latitude,longitude,notes\nFIX,A,1,2,hi\n"))
    assert result.ignored_columns == ["notes"]


def test_wrong_field_count_is_reported_per_row(tmp_path):
    text = EXAMPLE + "VOR,BAD,Too few,37.6\n" + "FIX,OK,OK,1,2,,,\n"
    result = parse_navdata_table(_write(tmp_path, "data.csv", text))
    assert result.issues == [(6, "expected 8 fields, found 4")]
    assert result.rows[-1].get("ident") == "OK"


def test_utf8_with_bom_and_non_ascii_names(tmp_path):
    text = "﻿" + HEADER + "\nNDB,ZRH,Zürich Kloten NDB,47.45,8.56,1400,380,50\n"
    [row] = parse_navdata_table(_write(tmp_path, "data.csv", text)).rows
    assert row.get("name") == "Zürich Kloten NDB"


def test_invalid_utf8_is_refused_not_mangled(tmp_path):
    raw = (HEADER + "\nNDB,ABC,Caf\xe9 NDB,1,2,0,375,50\n").encode("latin-1")
    with pytest.raises(TableFormatError, match="not valid UTF-8"):
        parse_navdata_table(_write(tmp_path, "data.csv", raw))


# --- TXT ------------------------------------------------------------------------

def test_txt_tab_separated_with_header(tmp_path):
    text = EXAMPLE.replace(",", "\t")
    result = parse_navdata_table(_write(tmp_path, "data.txt", text))
    assert result.layout.delimiter == "\t"
    assert len(result.rows) == 4


def test_txt_tab_separated_names_may_contain_commas(tmp_path):
    text = "\t".join(COLUMNS) + "\nNDB\tABC\tSmith, Jones NDB\t37.5\t-122.3\t50\t375\t50\n"
    result = parse_navdata_table(_write(tmp_path, "data.txt", text))
    assert result.layout.delimiter == "\t"
    assert result.rows[0].get("name") == "Smith, Jones NDB"


def test_txt_comma_separated(tmp_path):
    result = parse_navdata_table(_write(tmp_path, "data.txt", EXAMPLE))
    assert result.layout.delimiter == ","
    assert len(result.rows) == 4


def test_txt_without_header_uses_documented_column_order(tmp_path):
    body = "\n".join(EXAMPLE.splitlines()[1:]).replace(",", "\t") + "\n"
    result = parse_navdata_table(_write(tmp_path, "data.txt", body))
    assert result.layout.header is None
    assert [r.line_number for r in result.rows] == [1, 2, 3, 4]
    assert result.rows[1].get("frequency") == "375"


def test_txt_without_header_with_optional_columns(tmp_path):
    result = parse_navdata_table(_write(tmp_path, "data.txt", "VOR\tXYZ\tV\t1\t2\t0\t113.2\t130\t-3.0\t\n"))
    assert result.rows[0].get("slaved_variation_deg") == "-3.0"


def test_txt_malformed_row_does_not_abort(tmp_path):
    text = EXAMPLE.replace(",", "\t") + "NDB\tBROKEN\n" + "FIX\tLAST\t\t1\t2\t\t\t\n"
    result = parse_navdata_table(_write(tmp_path, "data.txt", text))
    assert result.issues == [(6, "expected 8 fields, found 2")]
    assert result.rows[-1].get("ident") == "LAST"


@pytest.mark.parametrize(
    "text, message",
    [
        # names with spaces, unquoted: every row splits differently from the header
        ("type ident name latitude longitude frequency range_nm\n"
         "NDB ABC Big Bear 37.5 -122.3 375 50\nVOR XYZ Palo Alto Hills 37.6 -122.4 113.2 130\n",
         "couldn't determine the columns"),
        ("hello world\n", "couldn't determine the columns"),
        ("a,b,c,d\n1,2,3,4\n", "neither a header"),
        ("FIX,EBAYE,1,2\n", "no header row, and the first row has 4 fields"),
        ("EBAYE 37.1 north\n", "neither a header"),          # position isn't a position
        ("", "the file has no data rows"),
        ("# only a comment\n\n", "the file has no data rows"),
    ],
)
def test_ambiguous_txt_is_refused_with_a_reason(tmp_path, text, message):
    with pytest.raises(TableFormatError, match=message):
        parse_navdata_table(_write(tmp_path, "data.txt", text))


def test_sniffer_failure_falls_back_safely():
    # One line: csv.Sniffer can't decide, the tab fallback still works.
    layout = detect_layout(["FIX\tA\tA\t1\t2\t0\t\t"], is_csv=False)
    assert layout.delimiter == "\t"


def test_inspect_recognizes_only_this_format(tmp_path):
    assert inspect_navdata_table(SourceFile(_write(tmp_path, "a.csv", EXAMPLE))) == TableProbe(None, False)
    assert inspect_navdata_table(SourceFile(_write(tmp_path, "b.txt", "just notes\n"))).reason == (
        "not a recognized navigation data file"
    )
    probe = inspect_navdata_table(SourceFile(_write(tmp_path, "c.csv", "type,ident\nFIX,A\n")))
    assert probe.reason == "looks like a navigation data table, but missing required column(s): latitude, longitude"
    untyped = inspect_navdata_table(SourceFile(_write(tmp_path, "d.csv", "ident,name,latitude,longitude,frequency\n")))
    assert untyped == TableProbe(None, needs_type=True)


# --- this cycle: type-less fix lists, whitespace, comments, asking for the type ---------

def test_fix_list_with_header_needs_no_type_column(tmp_path):
    result = parse_navdata_table(_write(tmp_path, "fixes.csv", "ident,latitude,longitude\nEBAYE,37.123,-122.456\n"))
    assert result.layout.record_type == "FIX"
    assert result.rows[0].values == {"ident": "EBAYE", "latitude": "37.123", "longitude": "-122.456", "type": "FIX"}


def test_fix_list_with_optional_name(tmp_path):
    result = parse_navdata_table(_write(tmp_path, "fixes.csv", "ident,name,latitude,longitude\nEBAYE,Bay,37.1,-122.4\n"))
    assert result.layout.record_type == "FIX"
    assert result.rows[0].get("name") == "Bay"


def test_headerless_whitespace_fix_list(tmp_path):
    result = parse_navdata_table(_write(tmp_path, "fixes.txt", "EBAYE  37.123  -122.456\nWAYPT 38.0 -121.0\n"))
    assert (result.layout.delimiter, result.layout.record_type) == ("whitespace", "FIX")
    assert [r.get("ident") for r in result.rows] == ["EBAYE", "WAYPT"]


def test_whitespace_navaids_with_quoted_names(tmp_path):
    text = 'type ident name latitude longitude frequency range_nm\nVOR XYZ "Example VOR" 37.6 -122.4 113.2 130\n'
    [row] = parse_navdata_table(_write(tmp_path, "navaids.txt", text)).rows
    assert (row.get("type"), row.get("name"), row.get("frequency")) == ("VOR", "Example VOR", "113.2")


def test_headerless_typed_rows_without_elevation(tmp_path):
    result = parse_navdata_table(_write(tmp_path, "navaids.txt", 'NDB ABC "Example NDB" 37.5 -122.3 375 50\n'))
    assert result.layout.columns == ["type", "ident", "name", "latitude", "longitude", "frequency", "range_nm"]


def test_comments_and_blank_lines_are_ignored_and_line_numbers_kept(tmp_path):
    text = "# my fixes\n\nident,latitude,longitude\n\n# first\nEBAYE,37.1,-122.4\n   \nWAYPT,38.0,-121.0\n"
    result = parse_navdata_table(_write(tmp_path, "fixes.csv", text))
    assert [(r.line_number, r.get("ident")) for r in result.rows] == [(6, "EBAYE"), (8, "WAYPT")]


def test_whitespace_row_with_unquoted_spaces_is_reported_not_shifted(tmp_path):
    text = 'type ident name latitude longitude frequency range_nm\nNDB ABC "Good" 37.5 -122.3 375 50\n' \
           "NDB DEF Big Bear 37.5 -122.3 380 50\nNDB GHI Fine 37.6 -122.3 385 50\n"
    result = parse_navdata_table(_write(tmp_path, "navaids.txt", text))
    assert [r.get("ident") for r in result.rows] == ["ABC", "GHI"]
    assert result.issues == [(3, "expected 7 fields, found 8 (quote names that contain spaces)")]


def test_unclosed_quote_is_reported_per_row(tmp_path):
    text = "ident latitude longitude\nEBAYE 37.1 -122.4\n\"BROKEN 37.2 -122.5\nWAYPT 38.0 -121.0\n"
    result = parse_navdata_table(_write(tmp_path, "fixes.txt", text))
    assert [r.get("ident") for r in result.rows] == ["EBAYE", "WAYPT"]
    assert result.issues[0][0] == 3 and result.issues[0][1].startswith("can't split row")


def test_navaid_table_without_type_requires_a_choice(tmp_path):
    path = _write(tmp_path, "navaids.csv", "ident,name,latitude,longitude,frequency,range_nm\nABC,N,37.5,-122.3,375,50\n")
    with pytest.raises(RecordTypeRequired):
        parse_navdata_table(path)
    [row] = parse_navdata_table(path, record_type="NDB").rows
    assert row.get("type") == "NDB"
    with pytest.raises(TableFormatError, match="record type must be one of NDB, VOR, DME"):
        parse_navdata_table(path, record_type="FIX")


def test_headerless_untyped_navaids_require_a_choice(tmp_path):
    path = _write(tmp_path, "navaids.txt", 'ABC "Example" 37.5 -122.3 375 50\n')
    with pytest.raises(RecordTypeRequired):
        parse_navdata_table(path)


def test_text_that_merely_contains_numbers_is_not_a_fix_list(tmp_path):
    with pytest.raises(TableFormatError, match="neither a header"):
        parse_navdata_table(_write(tmp_path, "notes.txt", "Version 2026 09\n"))


def test_unsplittable_first_row_is_a_format_error_not_a_crash(tmp_path):
    with pytest.raises(TableFormatError):
        parse_navdata_table(_write(tmp_path, "data.csv", 'ident,"latitude,longitude\nA,1,2\n'))
