"""Import use case: parses a user-supplied fix.dat/nav.dat file and
stores its records as IMPORTED.

The source file is opened read-only by the parsers (infrastructure/
parsers/dat_file_io.py) and is never modified, moved, or deleted by
this application at any point.

Only NAV row codes 2 (NDB), 3 (VOR) and 13 (DME) are converted into
stored records; any other row code encountered is counted and reported
back to the caller as skipped, never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from flightgear_navdata_manager.domain.models import DataSource, Dme, Fix, Ndb, Vor
from flightgear_navdata_manager.infrastructure.parsers.fix_dat_parser import (
    ParsedFixRecord,
    parse_fix_dat,
)
from flightgear_navdata_manager.infrastructure.parsers.nav_dat_parser import (
    ParsedNavRecord,
    parse_nav_dat,
)
from flightgear_navdata_manager.infrastructure.storage.fix_repository import FixRepository
from flightgear_navdata_manager.infrastructure.storage.navaid_repository import (
    NavaidRepository,
)

from .export_navdata import ExportService


@dataclass
class ImportSummary:
    imported_count: int
    warnings: list[str] = field(default_factory=list)
    skipped_unsupported: dict[int, int] = field(default_factory=dict)


class ImportService:
    def __init__(
        self,
        fix_repo: FixRepository,
        navaid_repo: NavaidRepository,
        export_service: ExportService,
    ):
        self._fix_repo = fix_repo
        self._navaid_repo = navaid_repo
        self._export = export_service

    def import_fix_file(self, path: str) -> ImportSummary:
        result = parse_fix_dat(path)
        now = datetime.now(timezone.utc)
        for record in result.records:
            self._fix_repo.add(fix_from_parsed(record, path, now))
        self._export.regenerate()
        return ImportSummary(imported_count=len(result.records), warnings=result.warnings)

    def import_nav_file(self, path: str) -> ImportSummary:
        result = parse_nav_dat(path)
        now = datetime.now(timezone.utc)
        count = 0
        for record in result.records:
            navaid = navaid_from_parsed(record, path, now)
            if navaid is None:
                continue
            self._navaid_repo.add(navaid)
            count += 1
        self._export.regenerate()
        return ImportSummary(
            imported_count=count,
            warnings=result.warnings,
            skipped_unsupported=result.skipped_unsupported_row_codes,
        )


def fix_from_parsed(record: ParsedFixRecord, path: str, now: datetime) -> Fix:
    """fix.dat record -> Fix. Shared with the Import Dataset workflow."""
    return Fix(
        id=None,
        source=DataSource.IMPORTED,
        enabled=True,
        created_at=now,
        ident=record.ident,
        latitude=record.latitude,
        longitude=record.longitude,
        interop=record.interop,
        origin_file=path,
    )


def navaid_from_parsed(record: ParsedNavRecord, path: str, now: datetime) -> Ndb | Vor | Dme | None:
    """nav.dat record -> Ndb/Vor/Dme, or None for an unsupported row code.
    Shared with the Import Dataset workflow."""
    common = dict(
        id=None,
        source=DataSource.IMPORTED,
        enabled=True,
        created_at=now,
        ident=record.ident,
        name=record.name,
        latitude=record.latitude,
        longitude=record.longitude,
        elevation_ft=record.elevation_ft,
        interop=record.interop,
        origin_file=path,
    )
    if record.row_code == 2:
        return Ndb(frequency_khz=record.freq_raw, range_nm=record.range_nm, **common)
    if record.row_code == 3:
        return Vor(
            frequency_mhz=record.freq_raw / 100.0,
            range_nm=record.range_nm,
            slaved_variation_deg=record.multiuse,
            **common,
        )
    if record.row_code == 13:
        return Dme(
            paired_frequency_mhz=record.freq_raw / 100.0,
            range_nm=record.range_nm,
            bias_nm=record.multiuse,
            **common,
        )
    return None
