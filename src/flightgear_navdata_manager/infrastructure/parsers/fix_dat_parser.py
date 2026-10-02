"""Parser for FlightGear/X-Plane fix.dat files.

Mirrors FlightGear 2024.1's fixlist.cxx behavior exactly (verified
against source in this project's specification):
  - the header (first two lines) is never parsed for meaning -- skipped
    unconditionally, regardless of content
  - any data line with 1 field equal to "99" ends the file
  - any data line with fewer than 3 fields is malformed and skipped
  - any data line with 3 or more fields is accepted, using only the
    first three (latitude, longitude, identifier); fields 4/5 (scope,
    ICAO region), when present, are captured here as interop metadata
    but are never required
  - a field count that isn't exactly 3, 5, or 6 has no functional
    effect in FlightGear (only an informational log there); this
    parser accepts any count >= 3 uniformly
The source file is opened read-only. This module never writes to it.
"""

from __future__ import annotations

from dataclasses import dataclass

from flightgear_navdata_manager.domain.models import FixInterop

from .dat_file_io import read_text_lines


@dataclass
class ParsedFixRecord:
    latitude: float
    longitude: float
    ident: str
    interop: FixInterop | None
    line_number: int


@dataclass
class FixParseResult:
    records: list[ParsedFixRecord]
    warnings: list[str]


def parse_fix_dat(path: str) -> FixParseResult:
    lines = read_text_lines(path)
    records: list[ParsedFixRecord] = []
    warnings: list[str] = []

    # First two lines are the header; never parsed for meaning (matches
    # fixlist.cxx, which unconditionally skips them via `in >> skipeol`
    # twice).
    data_lines = lines[2:]

    for offset, raw_line in enumerate(data_lines):
        line_number = offset + 3  # 1-based, matching FlightGear's own lineNumber convention
        fields = raw_line.split()
        nb_fields = len(fields)

        if nb_fields == 0:
            continue
        if nb_fields == 1:
            if fields[0] == "99":
                break
            warnings.append(f"line {line_number}: malformed (single field, not '99'), skipped")
            continue
        if nb_fields < 3:
            warnings.append(f"line {line_number}: malformed (fewer than 3 fields), skipped")
            continue

        try:
            lat = float(fields[0])
            lon = float(fields[1])
        except ValueError:
            warnings.append(f"line {line_number}: could not parse latitude/longitude, skipped")
            continue

        ident = fields[2]
        interop = None
        if nb_fields >= 5:
            interop = FixInterop(
                scope=fields[3],
                icao_region=fields[4],
                source_field_count=nb_fields,
            )

        records.append(
            ParsedFixRecord(
                latitude=lat, longitude=lon, ident=ident,
                interop=interop, line_number=line_number,
            )
        )

    return FixParseResult(records=records, warnings=warnings)
