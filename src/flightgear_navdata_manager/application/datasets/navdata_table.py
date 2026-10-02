"""This app's own CSV/TXT table format (see
infrastructure/parsers/navdata_table_parser.py) -> Fix/Ndb/Vor/Dme.

Records are built by the same functions the Add Waypoint / Add NAV
forms use (WaypointService.build_fix, NavaidService.build_ndb/vor/dme),
so validation, ident rules and name suffixes are identical to manual
entry. Values per type, and units -- exactly the domain model's:

  type  required                                           ignored
  FIX   ident, latitude, longitude                          name, elevation_ft
  NDB   ident, name, latitude, longitude, elevation_ft*,
        frequency (kHz, whole number), range_nm
  VOR   ... frequency (MHz), range_nm; slaved_variation_deg optional (default 0)
  DME   ... frequency (paired VHF MHz), range_nm; bias_nm optional (default 0)

  * A table with no elevation_ft column at all gives navaids 0 ft -- the
    Add NAV form's default -- with one warning for the file. A blank value
    in an elevation_ft column is still an invalid row.

A value given where the type has no such field (a FIX frequency or range,
a slaved variation on an NDB, ...) is ignored with a warning rather than
rejecting the row. Numbers must be plain decimals; elevation_ft,
range_nm and NDB kHz must be whole numbers -- nothing is rounded.
"""

from __future__ import annotations

from collections import Counter

from flightgear_navdata_manager.domain.exceptions import ValidationError
from flightgear_navdata_manager.domain.models import DataSource, Fix
from flightgear_navdata_manager.infrastructure.parsers.faa_common import SourceFile
from flightgear_navdata_manager.infrastructure.parsers.navdata_table_parser import (
    RECORD_TYPES,
    RecordTypeRequired,
    TableFormatError,
    TableRow,
    parse_navdata_table,
)

from ..navaid_service import build_dme, build_ndb, build_vor
from ..waypoint_service import build_fix
from .base import FIX, NAV, DatasetReadResult, ImportCandidate, RecordIssue

_TYPE_ONLY_COLUMNS = {
    "frequency": ("NDB", "VOR", "DME"),
    "range_nm": ("NDB", "VOR", "DME"),
    "slaved_variation_deg": ("VOR",),
    "bias_nm": ("DME",),
}


class NavDataTableReader:
    category = ""            # a table can hold fixes and navaids

    def __init__(self, description: str):
        self.description = description

    def read(self, source: SourceFile, record_type: str | None = None) -> DatasetReadResult:
        """Raises RecordTypeRequired if the table holds navaids without a
        type column and `record_type` (NDB/VOR/DME) wasn't given."""
        try:
            parsed = parse_navdata_table(source, record_type)
        except RecordTypeRequired:
            raise
        except TableFormatError as exc:
            result = DatasetReadResult()
            result.invalid.append(RecordIssue(None, source.name, str(exc), "", source.name))
            return result

        result = DatasetReadResult()
        for line_number, reason in parsed.issues:
            result.records_read[""] += 1
            result.invalid.append(RecordIssue(line_number, f"line {line_number}", reason, "", source.name))
        if parsed.ignored_columns:
            result.notes.append(
                f"{source.name}: ignored unknown column(s): {', '.join(parsed.ignored_columns)}"
            )
        default_elevation = "elevation_ft" not in parsed.layout.columns
        for row in parsed.rows:
            _read_row(row, source, result, default_elevation)
        if default_elevation and any(not isinstance(c.record, Fix) for c in result.candidates):
            result.warnings.append(RecordIssue(
                None, source.name,
                "no elevation_ft column: navaids were given 0 ft, the Add NAV form's default",
                NAV, source.name,
            ))
        return result


class _Invalid(Exception):
    pass


def _read_row(row: TableRow, source: SourceFile, result: DatasetReadResult, default_elevation: bool) -> None:
    record_type = row.get("type").upper()
    category = FIX if record_type == "FIX" else NAV if record_type in RECORD_TYPES else ""
    result.records_read[category] += 1
    label = f"{record_type or '?'} {row.get('ident') or '?'}"

    def issue(reason: str) -> RecordIssue:
        return RecordIssue(row.line_number, label, reason, category, source.name)

    if not category:
        shown = row.get("type") or "(blank)"
        result.invalid.append(issue(f"unknown type {shown!r} (expected {', '.join(RECORD_TYPES)})"))
        return
    for column, types in _TYPE_ONLY_COLUMNS.items():
        if row.get(column) and record_type not in types:
            result.warnings.append(issue(f"{column} ignored: {record_type} has no {column.replace('_', ' ')}"))

    try:
        record = _build(record_type, row, source.display, default_elevation)
    except (_Invalid, ValidationError) as exc:
        result.invalid.append(issue(str(exc)))
        return
    result.candidates.append(ImportCandidate(record, row.line_number, label, source.name))


def _build(record_type: str, row: TableRow, origin: str, default_elevation: bool):
    common = dict(source=DataSource.IMPORTED, origin_file=origin)
    ident = _required(row, "ident")
    latitude = _number(row, "latitude")
    longitude = _number(row, "longitude")
    if record_type == "FIX":
        return build_fix(ident, latitude, longitude, **common)

    name = _required(row, "name")
    elevation = 0 if default_elevation else _whole(row, "elevation_ft")
    range_nm = _whole(row, "range_nm")
    if record_type == "NDB":
        return build_ndb(ident, name, latitude, longitude, elevation, _whole(row, "frequency", "kHz"), range_nm, **common)
    if record_type == "VOR":
        return build_vor(
            ident, name, latitude, longitude, elevation, _number(row, "frequency"), range_nm,
            _number(row, "slaved_variation_deg", default=0.0), **common,
        )
    return build_dme(
        ident, name, latitude, longitude, elevation, _number(row, "frequency"), range_nm,
        _number(row, "bias_nm", default=0.0), **common,
    )


def _required(row: TableRow, column: str) -> str:
    value = row.get(column)
    if not value:
        raise _Invalid(f"missing {column}")
    return value


def _number(row: TableRow, column: str, default: float | None = None) -> float:
    value = row.get(column)
    if not value:
        if default is not None:
            return default
        raise _Invalid(f"missing {column}")
    try:
        number = float(value)
    except ValueError:
        raise _Invalid(f"malformed {column} {value!r}") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise _Invalid(f"malformed {column} {value!r}")
    return number


def _whole(row: TableRow, column: str, unit: str = "") -> int:
    number = _number(row, column)
    if number != int(number):
        suffix = f" {unit}" if unit else ""
        raise _Invalid(f"{column} must be a whole number{suffix}, got {row.get(column)!r}")
    return int(number)
