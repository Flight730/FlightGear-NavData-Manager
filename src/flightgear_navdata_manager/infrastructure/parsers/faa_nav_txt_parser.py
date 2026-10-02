"""Parser for the FAA NASR legacy NAV.txt file.

Layout: FAA "NAVAID DATA BASE RECORD LAYOUT (NAV-FILE)", nav_rf.txt,
information effective 9/9/2021 -- fixed-width records, logical record
length 805, CR/LF terminated. Verified against the 2026-09-03 cycle.

Record types:
  NAV1  base facility data -- one per facility; the only row type that
        carries a position, frequency, etc. Parsed here.
  NAV2  free-text remarks
  NAV3  names of airspace fixes associated with the facility (name,
        state, ICAO region only -- NO coordinates; those are in FIX.txt)
  NAV4  holding patterns
  NAV5  fan markers
  NAV6  VOR receiver checkpoints
NAV2-NAV6 are only counted: none of them describes a record this app
can store.

This module handles syntax only -- slicing fixed-width columns and
converting FAA units. Which facilities become which domain records is
decided by application/datasets/faa_nav.py, shared with the CSV parser.

A NAV1 row whose fields can't be converted is reported as an issue and
skipped; it never aborts the parse. The source is opened read-only.
"""

from __future__ import annotations

from .faa_common import (
    FaaNavaidRecord,
    FaaParseIssue,
    FaaParseResult,
    SourceFile,
    normalize_date,
    parse_all_seconds,
    parse_formatted_dms,
    parse_magnetic_variation,
)

RECORD_LENGTH = 805

# (1-based start column, length), from nav_rf.txt.
_FACILITY_TYPE = (9, 20)
_IDENT = (29, 4)                 # official navaid facility identifier
_EFFECTIVE_DATE = (33, 10)       # MM/DD/YYYY
_NAME = (43, 30)
_CITY = (73, 40)
_STATE_CODE = (143, 2)
_CLASS = (282, 11)
_LAT_FORMATTED = (372, 14)
_LAT_SECONDS = (386, 11)
_LON_FORMATTED = (397, 14)
_LON_SECONDS = (411, 11)
_TACAN_LAT_FORMATTED = (423, 14)
_TACAN_LAT_SECONDS = (437, 11)
_TACAN_LON_FORMATTED = (448, 14)
_TACAN_LON_SECONDS = (462, 11)
_ELEVATION = (473, 7)            # feet MSL, to one decimal place
_MAG_VAR = (480, 5)              # e.g. "14E", "03W"
_CHANNEL = (530, 4)              # TACAN channel, e.g. "88X"
_FREQUENCY = (534, 6)            # MHz for VHF facilities, kHz for NDBs
_VOR_SSV = (577, 2)              # VOR standard service volume
_DME_SSV = (579, 2)              # DME standard service volume
_STATUS = (770, 30)

_DETAIL_ROW_TYPES = ("NAV2", "NAV3", "NAV4", "NAV5", "NAV6")


def parse_faa_nav_txt(source: SourceFile | str) -> FaaParseResult:
    if isinstance(source, str):
        source = SourceFile(source)
    # latin-1: one byte per character, so fixed-width columns stay aligned.
    with source.open_text("latin-1") as f:
        lines = f.read().splitlines()

    result = FaaParseResult(records=[], issues=[], rows_read=0)
    for index, raw in enumerate(lines):
        line_number = index + 1
        if not raw.strip():
            continue
        row_type = raw[:4]
        if row_type in _DETAIL_ROW_TYPES:
            result.detail_rows[row_type] = result.detail_rows.get(row_type, 0) + 1
            continue
        if row_type != "NAV1":
            result.issues.append(
                FaaParseIssue(line_number, raw[:28].strip() or "?", "unrecognized row type")
            )
            continue

        result.rows_read += 1
        # Some tools strip trailing blanks; restore the fixed width so
        # absent trailing fields read as blank rather than shifting.
        line = raw.ljust(RECORD_LENGTH)
        try:
            result.records.append(_parse_nav1(line, line_number))
        except ValueError as exc:
            label = f"{_field(line, _IDENT)} {_field(line, _FACILITY_TYPE)}".strip() or "?"
            result.issues.append(FaaParseIssue(line_number, label, str(exc)))
    return result


def _parse_nav1(line: str, line_number: int) -> FaaNavaidRecord:
    latitude = _coordinate(line, _LAT_SECONDS, _LAT_FORMATTED, "latitude")
    longitude = _coordinate(line, _LON_SECONDS, _LON_FORMATTED, "longitude")
    tacan_lat = _coordinate(line, _TACAN_LAT_SECONDS, _TACAN_LAT_FORMATTED, "TACAN latitude")
    tacan_lon = _coordinate(line, _TACAN_LON_SECONDS, _TACAN_LON_FORMATTED, "TACAN longitude")
    if (tacan_lat is None) != (tacan_lon is None):
        tacan_lat = tacan_lon = None  # half a position is no position

    return FaaNavaidRecord(
        line_number=line_number,
        facility_type=" ".join(_field(line, _FACILITY_TYPE).split()),
        ident=_field(line, _IDENT),
        name=" ".join(_field(line, _NAME).split()),
        city=" ".join(_field(line, _CITY).split()),
        state_code=_field(line, _STATE_CODE),
        navaid_class=_field(line, _CLASS),
        status=" ".join(_field(line, _STATUS).split()),
        latitude=latitude,
        longitude=longitude,
        tacan_latitude=tacan_lat,
        tacan_longitude=tacan_lon,
        elevation_ft=_optional_float(_field(line, _ELEVATION), "elevation"),
        magnetic_variation_deg=parse_magnetic_variation(_field(line, _MAG_VAR)),
        channel=_field(line, _CHANNEL),
        frequency=_optional_float(_field(line, _FREQUENCY), "frequency"),
        vor_service_volume=_field(line, _VOR_SSV),
        dme_service_volume=_field(line, _DME_SSV),
        effective_date=normalize_date(_field(line, _EFFECTIVE_DATE)),
    )


def _field(line: str, spec: tuple[int, int]) -> str:
    start, length = spec
    return line[start - 1 : start - 1 + length].strip()


def _optional_float(text: str, what: str) -> float | None:
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"invalid {what} {text!r}") from None


def _coordinate(
    line: str, seconds_spec: tuple[int, int], formatted_spec: tuple[int, int], what: str
) -> float | None:
    """Prefers the all-seconds form; falls back to DD-MM-SS.SSSH."""
    is_lat = "latitude" in what
    seconds = _field(line, seconds_spec)
    if seconds:
        value = parse_all_seconds(seconds, is_lat)
    else:
        formatted = _field(line, formatted_spec)
        if not formatted:
            return None
        value = parse_formatted_dms(formatted, is_lat)
    if value is None:
        raw = seconds or _field(line, formatted_spec)
        raise ValueError(f"invalid {what} {raw!r}")
    return value
