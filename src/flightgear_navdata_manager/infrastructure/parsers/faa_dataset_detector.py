"""Recognizes FAA NASR FIX/NAV data files, by content rather than
trusting the filename alone.

  CSV: by header names (normalized -- see faa_common.normalize_header),
       never by column order. A CSV is FIX_CSV / NAV_CSV only if every
       column the importer needs is present.
  TXT: by the legacy fixed-width record type indicator that starts
       every row (FIX1..FIX5 / NAV1..NAV6) and the documented width.

Everything else -- the other ~20 NASR datasets (APT, AWY, ILS, ...),
FAA supplementary FIX/NAV files that carry no positions (FIX_NAV,
FIX_CHRT, NAV_RMK, NAV_CKPT), layout documents -- is UNKNOWN, with a
reason. Detection only reads the start of the file and never converts
records; that is the parsers' job.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum

from .faa_common import SourceFile, normalize_header


class FaaSourceType(Enum):
    FIX_TXT = "FAA FIX.txt"
    NAV_TXT = "FAA NAV.txt"
    FIX_CSV = "FAA FIX CSV"
    NAV_CSV = "FAA NAV CSV"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Detection:
    type: FaaSourceType
    reason: str = ""             # why it's UNKNOWN, in plain language


# Columns the CSV parsers need. Coordinates: FAA's degrees/minutes/
# seconds/hemisphere columns (the decimal columns are used only as a
# cross-check when present).
LAT_COLUMNS = ("LAT_DEG", "LAT_MIN", "LAT_SEC", "LAT_HEMIS")
LONG_COLUMNS = ("LONG_DEG", "LONG_MIN", "LONG_SEC", "LONG_HEMIS")
FIX_CSV_REQUIRED = ("FIX_ID", *LAT_COLUMNS, *LONG_COLUMNS)
NAV_CSV_REQUIRED = (
    "NAV_ID", "NAV_TYPE", "NAV_STATUS", "NAME", *LAT_COLUMNS, *LONG_COLUMNS,
    "ELEV", "FREQ", "CHAN",
)

# Documented record widths are 466 (FIX) and 805 (NAV), but tools may
# strip trailing blanks; require at least the columns the parsers need
# (FIX: through longitude, col 94; NAV: through elevation, col 479).
_TXT_MIN_WIDTH = {"FIX": 94, "NAV": 479}
_TXT_ROW_TYPES = {
    "FIX": ("FIX1", "FIX2", "FIX3", "FIX4", "FIX5"),
    "NAV": ("NAV1", "NAV2", "NAV3", "NAV4", "NAV5", "NAV6"),
}


def detect_faa_source(path: str) -> FaaSourceType:
    return inspect_faa_source(SourceFile(path)).type


def inspect_faa_source(source: SourceFile) -> Detection:
    head = source.read_head()
    lower = source.name.lower()
    if lower.endswith(".csv"):
        return _detect_csv(source.name, head)
    if lower.endswith(".txt"):
        return _detect_txt(head)
    return Detection(FaaSourceType.UNKNOWN, "not a .txt or .csv file")


def csv_header(head: str) -> list[str]:
    first_line = head.splitlines()[0] if head.strip() else ""
    first_line = first_line.removeprefix("\xef\xbb\xbf")  # UTF-8 BOM, as read by read_head
    try:
        return [normalize_header(h) for h in next(csv.reader([first_line]), [])]
    except csv.Error:
        return []


def missing_columns(header: list[str], required: tuple[str, ...]) -> list[str]:
    present = set(header)
    return [c for c in required if c not in present]


def _detect_csv(name: str, head: str) -> Detection:
    header = csv_header(head)
    missing_fix = missing_columns(header, FIX_CSV_REQUIRED)
    missing_nav = missing_columns(header, NAV_CSV_REQUIRED)
    if not missing_fix and "NAV_ID" not in header:
        return Detection(FaaSourceType.FIX_CSV)
    if not missing_nav and "FIX_ID" not in header:
        return Detection(FaaSourceType.NAV_CSV)

    has_fix, has_nav = "FIX_ID" in header, "NAV_ID" in header
    if has_fix and has_nav:
        return Detection(FaaSourceType.UNKNOWN, "FAA fix/navaid cross-reference; contains no positions")
    if (has_fix or has_nav) and not any(c in header for c in ("LAT_DEG", "LAT_DECIMAL")):
        return Detection(FaaSourceType.UNKNOWN, "FAA supplementary data; contains no positions")
    if has_fix:
        return Detection(
            FaaSourceType.UNKNOWN,
            "This CSV does not contain the required FAA FIX fields: " + ", ".join(missing_fix),
        )
    if has_nav:
        return Detection(
            FaaSourceType.UNKNOWN,
            "This CSV does not contain the required FAA NAV fields: " + ", ".join(missing_nav),
        )
    return Detection(FaaSourceType.UNKNOWN, "not an FAA FIX or NAV file")


def _detect_txt(head: str) -> Detection:
    first = next((line for line in head.splitlines() if line.strip()), "")
    for kind, row_types in _TXT_ROW_TYPES.items():
        if first[:4] in row_types:
            if len(first.rstrip("\r\n")) < _TXT_MIN_WIDTH[kind]:
                return Detection(
                    FaaSourceType.UNKNOWN,
                    f"starts like an FAA {kind}.txt record but isn't the documented fixed width",
                )
            return Detection(FaaSourceType.FIX_TXT if kind == "FIX" else FaaSourceType.NAV_TXT)
    return Detection(FaaSourceType.UNKNOWN, "not an FAA FIX or NAV file")
