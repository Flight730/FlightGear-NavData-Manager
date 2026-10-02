"""Parser for FlightGear/X-Plane nav.dat files.

Mirrors FlightGear 2024.1's navdb.cxx parsing rules (verified against
source in this project's specification):
  - the format version is read ONCE from line 2 and applies to every
    line of the file -- nav.dat cannot mix field-count shapes the way
    fix.dat can
  - version < 1100  -> exactly 9 fields per record
  - version >= 1100 -> up to 11 fields per record; the name is either
    fields[10] alone (when fields[8] == "ENRT") or
    fields[8] + " " + fields[10] otherwise
  - a line with fewer than 9 fields is rejected regardless of version

Unlike FlightGear's own C++ (which uses unchecked vector indexing and
can suffer undefined behavior reading fields[10] off a too-short
vector under a >=1100 header -- see project spec), this parser
defensively catches IndexError/ValueError per line and reports it as a
warning rather than crashing, since we may be importing arbitrary
third-party files whose declared version doesn't match their actual
content.

MVP 1 only converts row codes 2 (NDB), 3 (VOR) and 13 (DME) into
records; any other recognized X-Plane row code is counted and reported
as skipped, never silently dropped without notice.

The source file is opened read-only. This module never writes to it.
"""

from __future__ import annotations

from dataclasses import dataclass

from flightgear_navdata_manager.domain.models import NavaidInterop

from .dat_file_io import read_text_lines

SUPPORTED_ROW_CODES = {2, 3, 13}


@dataclass
class ParsedNavRecord:
    row_code: int
    latitude: float
    longitude: float
    elevation_ft: int
    freq_raw: int          # exactly as stored in the file: kHz for NDB, MHz*100 for VOR/DME
    range_nm: int
    multiuse: float
    ident: str
    name: str
    interop: NavaidInterop | None
    line_number: int


@dataclass
class NavParseResult:
    records: list[ParsedNavRecord]
    warnings: list[str]
    skipped_unsupported_row_codes: dict[int, int]  # row_code -> count


def parse_nav_dat(path: str) -> NavParseResult:
    lines = read_text_lines(path)
    warnings: list[str] = []
    skipped: dict[int, int] = {}
    records: list[ParsedNavRecord] = []

    if len(lines) < 2:
        warnings.append("file has fewer than 2 header lines; cannot determine format version")
        return NavParseResult(records=[], warnings=warnings, skipped_unsupported_row_codes={})

    version_line = lines[1].strip()
    version_tokens = version_line.split()
    if not version_tokens:
        warnings.append(f"could not parse format version from header line 2: {version_line!r}")
        return NavParseResult(records=[], warnings=warnings, skipped_unsupported_row_codes={})
    try:
        version = int(version_tokens[0])
    except ValueError:
        warnings.append(f"could not parse format version from header line 2: {version_line!r}")
        return NavParseResult(records=[], warnings=warnings, skipped_unsupported_row_codes={})

    max_splits = 8 if version < 1100 else 10
    is_extended = version >= 1100

    for offset, raw_line in enumerate(lines[2:]):
        line_number = offset + 3
        if raw_line.strip().startswith("#"):
            continue  # carrier_nav.dat-style comment line

        fields = raw_line.split(None, max_splits)
        nb_fields = len(fields)

        if nb_fields == 0:
            continue
        if nb_fields == 1:
            if fields[0] == "99":
                break
            warnings.append(f"line {line_number}: malformed (single field, not '99'), skipped")
            continue
        if nb_fields < 9:
            warnings.append(f"line {line_number}: fewer than 9 fields, skipped")
            continue

        try:
            row_code = int(fields[0])
            lat = float(fields[1])
            lon = float(fields[2])
            elev_ft = int(float(fields[3]))
            freq_raw = int(float(fields[4]))
            range_nm = int(float(fields[5]))
            multiuse = float(fields[6])
            ident = fields[7]

            interop = None
            if is_extended:
                scope = fields[8]
                icao_region = fields[9]
                if scope == "ENRT":
                    name = fields[10]
                else:
                    name = f"{fields[8]} {fields[10]}"
                interop = NavaidInterop(
                    scope=scope, icao_region=icao_region, source_field_count=nb_fields,
                )
            else:
                name = fields[8]
            name = " ".join(name.split())  # collapse internal whitespace
        except (ValueError, IndexError) as exc:
            warnings.append(f"line {line_number}: could not parse record ({exc}), skipped")
            continue

        if row_code not in SUPPORTED_ROW_CODES:
            skipped[row_code] = skipped.get(row_code, 0) + 1
            continue

        records.append(
            ParsedNavRecord(
                row_code=row_code, latitude=lat, longitude=lon, elevation_ft=elev_ft,
                freq_raw=freq_raw, range_nm=range_nm, multiuse=multiuse, ident=ident,
                name=name, interop=interop, line_number=line_number,
            )
        )

    return NavParseResult(
        records=records, warnings=warnings, skipped_unsupported_row_codes=skipped,
    )
