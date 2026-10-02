"""Parser for the FAA NASR legacy FIX.txt file.

Layout: FAA fix_rf.txt -- fixed-width records, 466 characters, CR/LF
terminated, one FIX1 base record per fix followed by optional detail
records:
  FIX2  navaid makeup text        FIX4  remarks
  FIX3  ILS makeup text           FIX5  charting types
Only FIX1 carries a position; the detail records are counted, not
parsed. FIX.txt has no effective-date field.

Syntax only; application/datasets/faa_fix.py maps records to Fix.
A FIX1 row with an unreadable position is reported and skipped; it
never aborts the parse. The source is opened read-only.
"""

from __future__ import annotations

from .faa_common import FaaFixRecord, FaaParseIssue, FaaParseResult, SourceFile, parse_formatted_dms

RECORD_LENGTH = 466

# (1-based start column, length), from fix_rf.txt.
_IDENT = (5, 30)
_STATE_NAME = (35, 30)
_ICAO_REGION = (65, 2)
_LATITUDE = (67, 14)             # DD-MM-SS.SSSH
_LONGITUDE = (81, 14)            # DDD-MM-SS.SSSH
_FIX_USE = (214, 15)             # e.g. WAYPOINT, REP-PT, CNF

_DETAIL_ROW_TYPES = ("FIX2", "FIX3", "FIX4", "FIX5")


def parse_faa_fix_txt(source: SourceFile | str) -> FaaParseResult:
    if isinstance(source, str):
        source = SourceFile(source)
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
        if row_type != "FIX1":
            result.issues.append(
                FaaParseIssue(line_number, raw[:34].strip() or "?", "unrecognized row type")
            )
            continue

        result.rows_read += 1
        line = raw.ljust(RECORD_LENGTH)
        ident = _field(line, _IDENT)
        label = f"{ident or '?'} FIX"
        lat_text, lon_text = _field(line, _LATITUDE), _field(line, _LONGITUDE)
        latitude = parse_formatted_dms(lat_text, True)
        longitude = parse_formatted_dms(lon_text, False)
        if latitude is None or longitude is None:
            bad = f"latitude {lat_text!r}" if latitude is None else f"longitude {lon_text!r}"
            result.issues.append(FaaParseIssue(line_number, label, f"invalid {bad}"))
            continue
        result.records.append(
            FaaFixRecord(
                line_number=line_number,
                ident=ident,
                latitude=latitude,
                longitude=longitude,
                icao_region=_field(line, _ICAO_REGION),
                state=_field(line, _STATE_NAME),
                use=_field(line, _FIX_USE),
            )
        )
    return result


def _field(line: str, spec: tuple[int, int]) -> str:
    start, length = spec
    return line[start - 1 : start - 1 + length].strip()
