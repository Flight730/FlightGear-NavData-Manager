"""Parser for the FAA NASR CSV fix file (FIX_BASE.csv).

Columns are found by (normalized) header name, never by position.
Position comes from FAA's LAT_/LONG_ DEG/MIN/SEC/HEMIS columns and is
cross-checked against LAT_/LONG_DECIMAL when those are present.

Syntax only; application/datasets/faa_fix.py maps records to Fix.
FIX_NAV.csv / FIX_CHRT.csv carry no positions and are not parsed.
"""

from __future__ import annotations

from .faa_common import (
    FaaFixRecord,
    FaaParseIssue,
    FaaParseResult,
    SourceFile,
    csv_coordinate,
    normalize_date,
    read_faa_csv,
)
from .faa_dataset_detector import FIX_CSV_REQUIRED


def parse_faa_fix_csv(source: SourceFile | str) -> FaaParseResult:
    if isinstance(source, str):
        source = SourceFile(source)
    rows, issues = read_faa_csv(source, FIX_CSV_REQUIRED, "FIX")
    result = FaaParseResult(records=[], issues=issues, rows_read=len(rows) + len(issues))
    for row in rows:
        ident = row.get("FIX_ID")
        try:
            latitude = csv_coordinate(row, "LAT", True, "latitude")
            longitude = csv_coordinate(row, "LONG", False, "longitude")
            if latitude is None or longitude is None:
                raise ValueError("no position")
        except ValueError as exc:
            result.issues.append(FaaParseIssue(row.line_number, f"{ident or '?'} FIX", str(exc)))
            continue
        result.records.append(
            FaaFixRecord(
                line_number=row.line_number,
                ident=ident,
                latitude=latitude,
                longitude=longitude,
                icao_region=row.get("ICAO_REGION_CODE"),
                state=row.get("STATE_CODE"),
                use=row.get("FIX_USE_CODE"),
                effective_date=normalize_date(row.get("EFF_DATE")),
            )
        )
    return result
