"""Parser for the FAA NASR CSV navaid file (NAV_BASE.csv).

Produces the same FaaNavaidRecord as the NAV.txt parser, so both feed
one mapping (application/datasets/faa_nav.py). Columns are found by
(normalized) header name, never by position.

TXT -> CSV column correspondence used here:
  facility type NAV_TYPE, ident NAV_ID, name NAME, status NAV_STATUS,
  position LAT_*/LONG_* (DMS + hemisphere, cross-checked with *_DECIMAL),
  TACAN/DME antenna TACAN_DME_LAT_*/TACAN_DME_LONG_*, elevation ELEV,
  magnetic variation MAG_VARN + MAG_VARN_HEMIS, channel CHAN,
  frequency FREQ, VOR service volume ALT_CODE, DME service volume
  DME_SSV, NDB class NDB_CLASS_CODE.
The CSV has no general facility class column (the TXT's "H-VORTACW"),
so a VOR/DME with no service volume can't fall back to its class
altitude code the way the TXT importer can.

NAV_RMK.csv / NAV_CKPT.csv carry no positions and are not parsed.
"""

from __future__ import annotations

from .faa_common import (
    CsvRow,
    FaaNavaidRecord,
    FaaParseIssue,
    FaaParseResult,
    SourceFile,
    csv_coordinate,
    normalize_date,
    read_faa_csv,
)
from .faa_dataset_detector import NAV_CSV_REQUIRED


def parse_faa_nav_csv(source: SourceFile | str) -> FaaParseResult:
    if isinstance(source, str):
        source = SourceFile(source)
    rows, issues = read_faa_csv(source, NAV_CSV_REQUIRED, "NAV")
    result = FaaParseResult(records=[], issues=issues, rows_read=len(rows) + len(issues))
    for row in rows:
        try:
            result.records.append(_record(row))
        except ValueError as exc:
            label = f"{row.get('NAV_ID')} {row.get('NAV_TYPE')}".strip() or "?"
            result.issues.append(FaaParseIssue(row.line_number, label, str(exc)))
    return result


def _record(row: CsvRow) -> FaaNavaidRecord:
    tacan_lat = csv_coordinate(row, "TACAN_DME_LAT", True, "TACAN latitude")
    tacan_lon = csv_coordinate(row, "TACAN_DME_LONG", False, "TACAN longitude")
    if (tacan_lat is None) != (tacan_lon is None):
        tacan_lat = tacan_lon = None  # half a position is no position

    return FaaNavaidRecord(
        line_number=row.line_number,
        facility_type=" ".join(row.get("NAV_TYPE").split()),
        ident=row.get("NAV_ID"),
        name=" ".join(row.get("NAME").split()),
        city=" ".join(row.get("CITY").split()),
        state_code=row.get("STATE_CODE"),
        navaid_class=row.get("NDB_CLASS_CODE"),
        status=" ".join(row.get("NAV_STATUS").split()),
        latitude=csv_coordinate(row, "LAT", True, "latitude"),
        longitude=csv_coordinate(row, "LONG", False, "longitude"),
        tacan_latitude=tacan_lat,
        tacan_longitude=tacan_lon,
        elevation_ft=_optional_float(row.get("ELEV"), "elevation"),
        magnetic_variation_deg=_magnetic_variation(row),
        channel=row.get("CHAN"),
        frequency=_optional_float(row.get("FREQ"), "frequency"),
        vor_service_volume=row.get("ALT_CODE"),
        dme_service_volume=row.get("DME_SSV"),
        effective_date=normalize_date(row.get("EFF_DATE")),
    )


def _optional_float(text: str, what: str) -> float | None:
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"invalid {what} {text!r}") from None


def _magnetic_variation(row: CsvRow) -> float | None:
    degrees, hemisphere = row.get("MAG_VARN"), row.get("MAG_VARN_HEMIS").upper()
    if not degrees and not hemisphere:
        return None
    value = _optional_float(degrees, "magnetic variation")
    if value is None or hemisphere not in ("E", "W") or not (0 <= value <= 180):
        raise ValueError(f"invalid magnetic variation {degrees!r} {hemisphere!r}")
    return -value if hemisphere == "W" else value
