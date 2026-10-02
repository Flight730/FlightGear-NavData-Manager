"""Parser for simple, human-readable tables of navigation records -- CSV
(.csv) or delimited text (.txt), one record per row. Examples:

    type,ident,name,latitude,longitude,elevation_ft,frequency,range_nm
    NDB,ABC,Example NDB,37.500,-122.300,50,375,50

    ident,latitude,longitude            (a list of fixes)
    EBAYE,37.123,-122.456

    # whitespace-delimited; quote names that contain spaces
    VOR XYZ "Example VOR" 37.6 -122.4 113.2 130

Columns: type, ident, name, latitude, longitude, elevation_ft, frequency,
range_nm, plus optional slaved_variation_deg (VOR) and bias_nm (DME).
Which values each record type needs, and their units, are decided by
application/datasets/navdata_table.py; this module only reads the table.

Deliberately conservative -- it never guesses:
  - Encoding: UTF-8 (a BOM is fine). Undecodable bytes are an error.
  - Blank lines and lines starting with "#" are ignored.
  - Delimiter: .csv is comma-separated. .txt may be tab-, comma- or
    whitespace-separated. csv.Sniffer suggests tab or comma; a choice is
    only accepted if the first row splits into enough columns and most
    rows agree with it. Tab, comma, then whitespace are tried the same
    way; otherwise the file is refused. Whitespace-separated names with
    spaces must be quoted.
  - Header: a first row naming the "ident" column is a header (names are
    case/whitespace-insensitive, any order). Without one, only these
    layouts are accepted, recognized by field count:
        type ident name latitude longitude frequency range_nm        (7)
        type ident name latitude longitude elevation_ft frequency range_nm   (8)
        ... the 8 above + slaved_variation_deg bias_nm              (10)
        ident latitude longitude                                     (3, fixes)
        ident name latitude longitude                                (4, fixes)
        ident name latitude longitude frequency range_nm             (6)
        ident name latitude longitude elevation_ft frequency range_nm (7)
    and the untyped ones only if the first and most sampled rows have a
    valid position where the layout says it is. Anything else is refused.
  - Record type: from the "type" column when there is one. Without it, a
    table with no frequency/range column holds fixes; one with a
    frequency or range could be NDBs, VORs or DMEs, so the caller must
    say which (RecordTypeRequired) -- it is never inferred from the
    frequency's magnitude.
  - A row that doesn't split into the expected number of fields is
    reported and skipped; it never aborts the file or shifts columns.
The source is opened read-only.
"""

from __future__ import annotations

import csv
import re
import shlex
from dataclasses import dataclass, field

from .faa_common import SourceFile

COLUMNS = ("type", "ident", "name", "latitude", "longitude", "elevation_ft", "frequency", "range_nm")
OPTIONAL_COLUMNS = ("slaved_variation_deg", "bias_nm")
REQUIRED_COLUMNS = ("ident", "latitude", "longitude")
NAVAID_TYPES = ("NDB", "VOR", "DME")
RECORD_TYPES = ("FIX", *NAVAID_TYPES)
WHITESPACE = "whitespace"
_SNIFF_LINES = 20

_TYPED_LAYOUTS = {
    7: ("type", "ident", "name", "latitude", "longitude", "frequency", "range_nm"),
    8: COLUMNS,
    10: COLUMNS + OPTIONAL_COLUMNS,
}
_UNTYPED_LAYOUTS = {
    3: ("ident", "latitude", "longitude"),
    4: ("ident", "name", "latitude", "longitude"),
    6: ("ident", "name", "latitude", "longitude", "frequency", "range_nm"),
    7: ("ident", "name", "latitude", "longitude", "elevation_ft", "frequency", "range_nm"),
}
_SIGNAL_COLUMNS = ("frequency", "range_nm")


class TableFormatError(Exception):
    """The file's layout can't be determined safely."""


class NotATableError(TableFormatError):
    """The file doesn't look like a navigation table at all."""


class RecordTypeRequired(TableFormatError):
    """The table has no type column and holds navaids: the caller must
    choose NDB, VOR or DME."""

    choices = NAVAID_TYPES


@dataclass
class TableRow:
    line_number: int
    values: dict[str, str]       # column -> trimmed value ("" when blank)

    def get(self, column: str) -> str:
        return self.values.get(column, "")


@dataclass
class TableLayout:
    delimiter: str               # ",", "\t" or WHITESPACE
    header: list[str] | None     # normalized column names, or None when headerless
    columns: list[str]           # columns in file order
    record_type: str | None = None   # every row's type, when the table has no type column
    needs_type: bool = False         # no type column, and holds navaids


@dataclass
class TableParseResult:
    layout: TableLayout
    rows: list[TableRow]
    issues: list[tuple[int, str]] = field(default_factory=list)   # (line, reason)
    ignored_columns: list[str] = field(default_factory=list)


def normalize_column(name: str) -> str:
    return re.sub(r"[\s\-]+", "_", name.strip().lstrip("﻿")).lower()


def content_lines(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line that isn't blank or a # comment."""
    return [
        (number, line) for number, line in enumerate(text.splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#")
    ]


def split_row(line: str, delimiter: str) -> list[str]:
    """Raises ValueError for a row that can't be split (e.g. an unclosed quote)."""
    if delimiter == WHITESPACE:
        return shlex.split(line)
    # skipinitialspace: a quoted field may follow "<delimiter><space>".
    return next(csv.reader([line], delimiter=delimiter, skipinitialspace=True), [])


def detect_layout(lines: list[str], is_csv: bool) -> TableLayout:
    """Delimiter, header and record type from the first content lines.
    Raises TableFormatError (NotATableError when it isn't a table at all)."""
    lines = lines[:_SNIFF_LINES]
    if not lines:
        raise NotATableError("the file has no data rows")
    delimiter = "," if is_csv else _txt_delimiter(lines)
    try:
        first = [c.strip() for c in split_row(lines[0], delimiter)]
    except ValueError as exc:
        raise TableFormatError(f"the first row can't be split ({exc})") from None
    normalized = [normalize_column(c) for c in first]

    if "ident" in normalized:
        missing = [c for c in REQUIRED_COLUMNS if c not in normalized]
        if missing:
            raise TableFormatError(f"missing required column(s): {', '.join(missing)}")
        return _typed(TableLayout(delimiter, normalized, normalized))

    if first and first[0].upper() in RECORD_TYPES:
        if len(first) in _TYPED_LAYOUTS:
            return TableLayout(delimiter, None, list(_TYPED_LAYOUTS[len(first)]))
        raise TableFormatError(
            f"no header row, and the first row has {len(first)} fields -- a row starting with "
            f"its type needs {', '.join(str(n) for n in sorted(_TYPED_LAYOUTS))} fields "
            "(see the format help)"
        )
    untyped = _UNTYPED_LAYOUTS.get(len(first))
    if untyped and _positions_valid(lines, delimiter, untyped):
        return _typed(TableLayout(delimiter, None, list(untyped)))
    raise NotATableError(
        "the first row is neither a header (naming ident, latitude, longitude, ...) nor a "
        "recognized record layout"
    )


def _typed(layout: TableLayout) -> TableLayout:
    if "type" in layout.columns:
        return layout
    if any(c in layout.columns for c in _SIGNAL_COLUMNS):
        layout.needs_type = True     # NDB, VOR or DME -- the caller must say which
    else:
        layout.record_type = "FIX"   # no frequency or range: only fixes fit
    return layout


def _positions_valid(lines: list[str], delimiter: str, columns: tuple[str, ...]) -> bool:
    """The first row, and most rows, have an alphanumeric ident and a valid
    position where `columns` puts them."""
    lat, lon = columns.index("latitude"), columns.index("longitude")

    def valid(line: str) -> bool:
        try:
            fields = split_row(line, delimiter)
            return (
                len(fields) == len(columns)
                and fields[0].strip().isalnum()
                and -90 <= float(fields[lat]) <= 90
                and -180 <= float(fields[lon]) <= 180
            )
        except ValueError:
            return False

    results = [valid(line) for line in lines]
    return results[0] and results.count(True) * 2 > len(results)


def _field_count(line: str, delimiter: str) -> int:
    try:
        return len(split_row(line, delimiter))
    except ValueError:
        return -1                # unsplittable: counts as disagreeing, not as fatal


def _txt_delimiter(lines: list[str]) -> str:
    candidates = []
    try:
        candidates.append(csv.Sniffer().sniff("\n".join(lines), delimiters="\t,").delimiter)
    except csv.Error:
        pass
    candidates += ["\t", ",", WHITESPACE]
    for delimiter in dict.fromkeys(candidates):
        counts = [_field_count(line, delimiter) for line in lines]
        # The first row must split into enough columns, and most rows must
        # agree with it (a few malformed rows are reported later, per row).
        if counts[0] >= len(REQUIRED_COLUMNS) and counts.count(counts[0]) * 2 > len(counts):
            return delimiter
    raise NotATableError(
        "couldn't determine the columns -- expected tab-, comma- or whitespace-separated "
        "fields with the same number on each row"
    )


def parse_navdata_table(source: SourceFile | str, record_type: str | None = None) -> TableParseResult:
    """`record_type` (NDB/VOR/DME) is required when the table has no type
    column but holds navaids; RecordTypeRequired is raised otherwise."""
    if isinstance(source, str):
        source = SourceFile(source)
    try:
        with source.open_text("utf-8-sig", errors="strict") as f:
            text = f.read()
    except UnicodeDecodeError as exc:
        raise TableFormatError(f"not valid UTF-8 text (byte {exc.start})") from None

    lines = content_lines(text)
    layout = detect_layout([line for _, line in lines], source.name.lower().endswith(".csv"))
    if layout.needs_type:
        if record_type is None:
            raise RecordTypeRequired(
                "the file has no type column and its records have a frequency or range, "
                "so they could be NDBs, VORs or DMEs"
            )
        if record_type not in NAVAID_TYPES:
            raise TableFormatError(f"record type must be one of {', '.join(NAVAID_TYPES)}")
        layout.record_type = record_type

    known = set(COLUMNS + OPTIONAL_COLUMNS)
    result = TableParseResult(
        layout=layout, rows=[],
        ignored_columns=[c for c in layout.columns if c not in known] if layout.header else [],
    )
    for index, (line_number, line) in enumerate(lines):
        if layout.header is not None and index == 0:
            continue
        try:
            fields = split_row(line, layout.delimiter)
        except ValueError as exc:
            result.issues.append((line_number, f"can't split row ({exc})"))
            continue
        if len(fields) != len(layout.columns):
            result.issues.append((
                line_number,
                f"expected {len(layout.columns)} fields, found {len(fields)}"
                + (" (quote names that contain spaces)" if layout.delimiter == WHITESPACE else ""),
            ))
            continue
        values = {c: v.strip() for c, v in zip(layout.columns, fields)}
        if layout.record_type:
            values["type"] = layout.record_type
        result.rows.append(TableRow(line_number, values))
    return result


@dataclass(frozen=True)
class TableProbe:
    reason: str | None           # None: this format; otherwise why not
    needs_type: bool = False


def inspect_navdata_table(source: SourceFile) -> TableProbe:
    name = source.name.lower()
    if not name.endswith((".csv", ".txt")):
        return TableProbe("not a .csv or .txt file")
    head = source.read_head().removeprefix("\xef\xbb\xbf")
    lines = [line for _, line in content_lines(head)][:_SNIFF_LINES + 1]
    if len(head) >= 16384 and len(lines) > 1:
        lines = lines[:-1]       # the last sampled line may be cut off
    try:
        layout = detect_layout(lines, name.endswith(".csv"))
    except NotATableError:
        return TableProbe("not a recognized navigation data file")
    except TableFormatError as exc:
        return TableProbe(f"looks like a navigation data table, but {exc}")
    return TableProbe(None, layout.needs_type)
