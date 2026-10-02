"""Datasets the Import Dataset workflow understands, and discovery of
them in a file, a .zip, or a folder (e.g. a whole FAA NASR subscription).

  FAA NASR FIX / NAV   CSV (FIX_BASE.csv, NAV_BASE.csv -- preferred) or
                       legacy TXT (FIX.txt, NAV.txt); recognized by
                       content (infrastructure/parsers/faa_dataset_detector.py)
  FlightGear fix.dat / nav.dat (plain or .gz)
  NavData Manager CSV/TXT   this app's own simple table format (one record
                       per row: type, ident, name, latitude, longitude,
                       elevation_ft, frequency, range_nm)

Everything else in a folder or zip (airports, airways, procedures, ...)
is ignored, not treated as an error. When a folder holds the same FAA
dataset as both CSV and TXT, only the CSV is used -- FAA is retiring
the TXT format.

Each dataset is read by a DatasetReader (base.py); everything
format-independent lives in application/dataset_import.py.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass, field

from flightgear_navdata_manager.infrastructure.parsers.dat_file_io import detect_dat_kind
from flightgear_navdata_manager.infrastructure.parsers.faa_common import SourceFile
from flightgear_navdata_manager.infrastructure.parsers.faa_dataset_detector import (
    FaaSourceType,
    inspect_faa_source,
)
from flightgear_navdata_manager.infrastructure.parsers.faa_fix_csv_parser import parse_faa_fix_csv
from flightgear_navdata_manager.infrastructure.parsers.faa_fix_txt_parser import parse_faa_fix_txt
from flightgear_navdata_manager.infrastructure.parsers.faa_nav_csv_parser import parse_faa_nav_csv
from flightgear_navdata_manager.infrastructure.parsers.faa_nav_txt_parser import parse_faa_nav_txt
from flightgear_navdata_manager.infrastructure.parsers.navdata_table_parser import (
    inspect_navdata_table,
)

from .base import DatasetReader
from .faa_fix import FaaFixReader
from .faa_nav import FaaNavReader
from .flightgear_dat import FlightGearFixDatReader, FlightGearNavDatReader
from .navdata_table import NavDataTableReader

SUPPORTED_FORMATS = (
    "FlightGear fix.dat / nav.dat (.dat or .dat.gz); "
    "CSV/TXT tables of fixes (ident, latitude, longitude) or navaids "
    "(type, ident, name, latitude, longitude, frequency, range_nm); "
    "FAA NASR FIX_BASE.csv / NAV_BASE.csv; FAA NASR FIX.txt / NAV.txt -- "
    "as single files, in a .zip, or in a folder"
)
_UNRECOGNIZED = "not a recognized navigation data file"

FAA_READERS: dict[FaaSourceType, DatasetReader] = {
    FaaSourceType.FIX_CSV: FaaFixReader("FAA NASR FIX (CSV)", parse_faa_fix_csv),
    FaaSourceType.NAV_CSV: FaaNavReader("FAA NASR NAV (CSV)", parse_faa_nav_csv),
    FaaSourceType.FIX_TXT: FaaFixReader("FAA NASR FIX (TXT)", parse_faa_fix_txt),
    FaaSourceType.NAV_TXT: FaaNavReader("FAA NASR NAV (TXT)", parse_faa_nav_txt),
}
TABLE_READER: DatasetReader = NavDataTableReader("NavData Manager CSV/TXT")
DAT_READERS: dict[str, DatasetReader] = {
    "fix": FlightGearFixDatReader(),
    "nav": FlightGearNavDatReader(),
}

_CANDIDATE_SUFFIXES = (".csv", ".txt", ".zip", ".dat", ".gz")
_MAX_FOLDER_DEPTH = 3


@dataclass
class DiscoveredSource:
    file: SourceFile
    reader: DatasetReader
    faa_type: FaaSourceType | None = None
    needs_type: bool = False     # a table of navaids with no type column


@dataclass
class Discovery:
    sources: list[DiscoveredSource] = field(default_factory=list)
    ignored: list[tuple[str, str]] = field(default_factory=list)   # (file, reason)


def discover_sources(path: str) -> Discovery:
    """Raises OSError if `path` itself can't be read; unreadable files
    found inside a folder are reported in `ignored` instead."""
    if not os.path.isdir(path):
        with open(path, "rb"):
            pass
    discovery = Discovery()
    for file_path in _candidate_files(path):
        if file_path.lower().endswith(".zip"):
            _discover_zip(file_path, discovery)
        else:
            _classify(SourceFile(file_path), discovery)
    _prefer_csv(discovery)
    return discovery


def _candidate_files(path: str) -> list[str]:
    if not os.path.isdir(path):
        return [path]
    found = []
    base_depth = path.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if root.count(os.sep) - base_depth >= _MAX_FOLDER_DEPTH:
            dirs[:] = []
        found.extend(
            os.path.join(root, f) for f in sorted(files)
            if not f.startswith(".") and f.lower().endswith(_CANDIDATE_SUFFIXES)
        )
    return found


def _discover_zip(zip_path: str, discovery: Discovery) -> None:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = [
                m for m in archive.namelist()
                if not m.endswith("/") and "__MACOSX" not in m
                and not os.path.basename(m).startswith(".")
                and m.lower().endswith((".csv", ".txt"))
            ]
    except (OSError, zipfile.BadZipFile) as exc:
        discovery.ignored.append((os.path.basename(zip_path), f"unreadable zip ({exc})"))
        return
    for member in members:
        _classify(SourceFile(zip_path, member), discovery)


def _classify(source: SourceFile, discovery: Discovery) -> None:
    name = source.name.lower()
    try:
        if name.endswith((".csv", ".txt")):
            detection = inspect_faa_source(source)
            if detection.type is not FaaSourceType.UNKNOWN:
                discovery.sources.append(
                    DiscoveredSource(source, FAA_READERS[detection.type], detection.type)
                )
                return
            probe = inspect_navdata_table(source)
            table_reason = probe.reason
            if table_reason is None:
                discovery.sources.append(DiscoveredSource(source, TABLE_READER, needs_type=probe.needs_type))
                return
            # Neither format: give the more specific explanation, if any.
            if detection.reason != "not an FAA FIX or NAV file":
                reason = detection.reason
            elif table_reason != _UNRECOGNIZED:
                reason = table_reason
            else:
                reason = _UNRECOGNIZED
            discovery.ignored.append((source.name, reason))
            return
        kind = detect_dat_kind(source.path) if source.member is None else None
        if kind:
            discovery.sources.append(DiscoveredSource(source, DAT_READERS[kind]))
        else:
            discovery.ignored.append((source.name, "not a FlightGear fix.dat or nav.dat"))
    except OSError as exc:
        discovery.ignored.append((source.name, f"could not be read ({exc.strerror or exc})"))


def _prefer_csv(discovery: Discovery) -> None:
    for csv_type, txt_type in (
        (FaaSourceType.FIX_CSV, FaaSourceType.FIX_TXT),
        (FaaSourceType.NAV_CSV, FaaSourceType.NAV_TXT),
    ):
        csv_names = [s.file.name for s in discovery.sources if s.faa_type is csv_type]
        if not csv_names:
            continue
        for source in [s for s in discovery.sources if s.faa_type is txt_type]:
            discovery.sources.remove(source)
            discovery.ignored.append(
                (source.file.name, f"not used: {', '.join(csv_names)} has the same data (CSV preferred)")
            )
