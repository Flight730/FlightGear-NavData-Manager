"""Pieces shared by the FAA NASR parsers (FIX/NAV x TXT/CSV):

  - SourceFile: a plain file, or a member of a .zip (FAA ships its CSV
    files zipped), opened read-only
  - the normalized record types every FAA parser produces, so the
    TXT and CSV variants of a dataset feed one mapping
  - FAA unit conversions (coordinates, magnetic variation, dates)
  - CSV header normalization

Nothing here writes to any file.
"""

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import IO

# --- sources ----------------------------------------------------------------


@dataclass(frozen=True)
class SourceFile:
    path: str                       # file on disk (the .zip, for a zip member)
    member: str | None = None       # name inside the zip, if any

    @property
    def name(self) -> str:
        return os.path.basename(self.member or self.path)

    @property
    def display(self) -> str:
        return f"{self.path} > {self.member}" if self.member else self.path

    def open_binary(self) -> IO[bytes]:
        if self.member is None:
            return open(self.path, "rb")
        archive = zipfile.ZipFile(self.path)
        try:
            return io.BufferedReader(_ZipMemberStream(archive, archive.open(self.member)))
        except Exception:
            archive.close()
            raise

    def open_text(self, encoding: str, errors: str = "replace") -> IO[str]:
        # newline="" so the csv module sees raw line endings; fixed-width
        # callers use splitlines(), which handles CR/LF either way.
        return io.TextIOWrapper(self.open_binary(), encoding=encoding, errors=errors, newline="")

    def read_head(self, size: int = 16384) -> str:
        with self.open_binary() as f:
            return f.read(size).decode("latin-1")


class _ZipMemberStream(io.RawIOBase):
    """Closes the owning ZipFile together with the member stream."""

    def __init__(self, archive: zipfile.ZipFile, stream: IO[bytes]):
        self._archive = archive
        self._stream = stream

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        data = self._stream.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def close(self) -> None:
        try:
            self._stream.close()
            self._archive.close()
        finally:
            super().close()


# --- records ------------------------------------------------------------------


@dataclass
class FaaNavaidRecord:
    line_number: int
    facility_type: str           # e.g. "VORTAC", "NDB/DME"
    ident: str
    name: str
    city: str
    state_code: str
    navaid_class: str            # e.g. "H-VORTACW", "MHW/LOM" ("" when not given)
    status: str                  # e.g. "OPERATIONAL IFR", "DECOMMISSIONED"
    latitude: float | None
    longitude: float | None
    tacan_latitude: float | None   # TACAN/DME antenna, when sited apart from the VOR/NDB
    tacan_longitude: float | None
    elevation_ft: float | None
    magnetic_variation_deg: float | None  # east positive, west negative
    channel: str                 # "" when absent
    frequency: float | None      # MHz or kHz depending on facility type
    vor_service_volume: str      # "" when absent
    dme_service_volume: str      # "" when absent
    effective_date: str | None = None     # ISO yyyy-mm-dd, only if the source gives one

    @property
    def label(self) -> str:
        place = ", ".join(p for p in (self.city.title(), self.state_code) if p)
        return f"{self.ident} {self.facility_type}" + (f" ({place})" if place else "")


@dataclass
class FaaFixRecord:
    line_number: int
    ident: str
    latitude: float
    longitude: float
    icao_region: str             # e.g. "K2" ("" when not given)
    state: str                   # state code (CSV) or state name (TXT)
    use: str                     # e.g. "WP", "REP-PT"
    effective_date: str | None = None

    @property
    def label(self) -> str:
        state = self.state if len(self.state) <= 2 else self.state.title()  # "MA" / "Massachusetts"
        return f"{self.ident} FIX" + (f" ({state})" if state else "")


@dataclass
class FaaParseIssue:
    line_number: int
    label: str
    reason: str


@dataclass
class FaaParseResult:
    records: list                                  # FaaNavaidRecord or FaaFixRecord
    issues: list[FaaParseIssue]
    rows_read: int                                 # primary rows (NAV1/FIX1/CSV data rows)
    detail_rows: dict[str, int] = field(default_factory=dict)   # TXT only, e.g. NAV2 -> count


class FaaFormatError(Exception):
    """The file as a whole can't be interpreted (e.g. required columns missing)."""


# --- conversions --------------------------------------------------------------

_FORMATTED_RE = re.compile(r"^(\d{1,3})-(\d{1,2})-(\d{1,2}(?:\.\d+)?)([NSEW])$")
_SECONDS_RE = re.compile(r"^(\d+(?:\.\d+)?)([NSEW])$")
_MAG_VAR_RE = re.compile(r"^(\d{1,2})([EW])$")


def _signed(degrees: float, hemisphere: str, is_latitude: bool) -> float | None:
    if hemisphere not in (("N", "S") if is_latitude else ("E", "W")):
        return None
    if degrees > (90.0 if is_latitude else 180.0):
        return None
    return -degrees if hemisphere in ("S", "W") else degrees


def dms_to_decimal(
    degrees: float, minutes: float, seconds: float, hemisphere: str, is_latitude: bool
) -> float | None:
    """Signed decimal degrees, or None if any part is out of range."""
    if degrees < 0 or not (0 <= minutes < 60) or not (0 <= seconds < 60):
        return None
    return _signed(degrees + minutes / 60.0 + seconds / 3600.0, hemisphere.strip().upper(), is_latitude)


def parse_all_seconds(text: str, is_latitude: bool) -> float | None:
    """'140811.070N' -> 39.114186...; None if malformed."""
    match = _SECONDS_RE.match(text.strip())
    if not match:
        return None
    return _signed(float(match.group(1)) / 3600.0, match.group(2), is_latitude)


def parse_formatted_dms(text: str, is_latitude: bool) -> float | None:
    """'39-06-51.070N' / '075-27-54.660W' -> signed decimal degrees; None if malformed."""
    match = _FORMATTED_RE.match(text.strip())
    if not match:
        return None
    deg, minutes, seconds, hemisphere = match.groups()
    return dms_to_decimal(int(deg), int(minutes), float(seconds), hemisphere, is_latitude)


def parse_magnetic_variation(text: str) -> float | None:
    """'14E' -> 14.0, '03W' -> -3.0, '' -> None. Anything else raises ValueError."""
    text = text.strip()
    if not text:
        return None
    match = _MAG_VAR_RE.match(text)
    if not match:
        raise ValueError(f"invalid magnetic variation {text!r}")
    value = float(match.group(1))
    return -value if match.group(2) == "W" else value


def normalize_date(text: str) -> str | None:
    """FAA 'YYYY/MM/DD' (CSV) or 'MM/DD/YYYY' (TXT) -> 'YYYY-MM-DD'; None
    for anything else -- never guessed."""
    text = text.strip()
    match = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", text)
    if match:
        return f"{match.group(3)}-{match.group(1)}-{match.group(2)}"
    return None


def normalize_header(name: str) -> str:
    """' Lat Decimal ' / 'lat-decimal' / 'LAT__DECIMAL' -> 'LAT_DECIMAL'."""
    return re.sub(r"[\s\-_]+", "_", name.strip().lstrip("﻿")).strip("_").upper()


# --- CSV ----------------------------------------------------------------------

_DECIMAL_TOLERANCE_DEG = 1e-5    # ~1 m; FAA's decimal columns are rounded to 8 places


@dataclass
class CsvRow:
    line_number: int
    values: dict[str, str]       # normalized header -> stripped value

    def get(self, column: str) -> str:
        return self.values.get(column, "")


def read_faa_csv(
    source: SourceFile, required: tuple[str, ...], dataset: str
) -> tuple[list[CsvRow], list[FaaParseIssue]]:
    """Reads an FAA CSV by header name (any column order). Raises
    FaaFormatError if a required column is missing; a row with the
    wrong number of fields is reported, not guessed at."""
    rows: list[CsvRow] = []
    issues: list[FaaParseIssue] = []
    with source.open_text("utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = [normalize_header(h) for h in next(reader)]
        except StopIteration:
            raise FaaFormatError(f"{source.name} is empty") from None
        missing = [c for c in required if c not in header]
        if missing:
            raise FaaFormatError(
                f"This CSV does not contain the required FAA {dataset} fields: {', '.join(missing)}"
            )
        try:
            for fields in reader:
                if not any(v.strip() for v in fields):
                    continue
                if len(fields) != len(header):
                    issues.append(FaaParseIssue(
                        reader.line_num, fields[0] if fields else "?",
                        f"malformed row: {len(fields)} fields, expected {len(header)}",
                    ))
                    continue
                rows.append(CsvRow(reader.line_num, {h: v.strip() for h, v in zip(header, fields)}))
        except csv.Error as exc:
            issues.append(FaaParseIssue(reader.line_num, "?", f"unreadable CSV from here on ({exc})"))
    return rows, issues


def csv_coordinate(row: CsvRow, prefix: str, is_latitude: bool, what: str) -> float | None:
    """Reads FAA's <prefix>_DEG/_MIN/_SEC/_HEMIS columns (e.g. LAT, LONG,
    TACAN_DME_LAT). None if all are blank; ValueError if they're
    malformed or disagree with the <prefix>_DECIMAL column."""
    parts = [row.get(f"{prefix}_{p}") for p in ("DEG", "MIN", "SEC", "HEMIS")]
    if not any(parts):
        return None
    try:
        value = dms_to_decimal(float(parts[0]), float(parts[1]), float(parts[2]), parts[3], is_latitude)
    except ValueError:
        value = None
    if value is None:
        raise ValueError(f"invalid {what} {'/'.join(parts)!r}")
    decimal = row.get(f"{prefix}_DECIMAL")
    if decimal:
        try:
            mismatch = abs(float(decimal) - value) > _DECIMAL_TOLERANCE_DEG
        except ValueError:
            mismatch = True
        if mismatch:
            raise ValueError(f"{what} {'/'.join(parts)} disagrees with decimal value {decimal}")
    return value
