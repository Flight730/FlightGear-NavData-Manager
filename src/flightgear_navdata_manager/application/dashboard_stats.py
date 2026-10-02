"""Live counts and export status for the Dashboard.

Every number comes from the database at the time summary() is called,
via GROUP BY count queries -- no records are loaded, so this stays
cheap with a full FAA dataset (~70,000 records).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from flightgear_navdata_manager.application.export_navdata import ExportService
from flightgear_navdata_manager.domain.models import DataSource, NavaidType
from flightgear_navdata_manager.infrastructure.storage.fix_repository import FixRepository
from flightgear_navdata_manager.infrastructure.storage.navaid_repository import NavaidRepository


class ExportState(Enum):
    UP_TO_DATE = "up_to_date"      # written, and the last regeneration succeeded
    NOT_WRITTEN = "not_written"    # no output files yet
    FAILED = "failed"              # the last regeneration raised


@dataclass(frozen=True)
class ExportStatus:
    state: ExportState
    last_written: datetime | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class DataSummary:
    fixes_custom: int = 0
    fixes_imported: int = 0
    navaids_by_type: dict[NavaidType, int] = field(default_factory=dict)
    navaids_custom: int = 0
    navaids_imported: int = 0
    enabled: int = 0
    disabled: int = 0

    @property
    def fixes(self) -> int:
        return self.fixes_custom + self.fixes_imported

    @property
    def navaids(self) -> int:
        return sum(self.navaids_by_type.values())

    @property
    def total(self) -> int:
        return self.fixes + self.navaids

    def navaid_count(self, navaid_type: NavaidType) -> int:
        return self.navaids_by_type.get(navaid_type, 0)


class DashboardStatsService:
    def __init__(self, fix_repo: FixRepository, navaid_repo: NavaidRepository,
                 export_service: ExportService):
        self._fix_repo = fix_repo
        self._navaid_repo = navaid_repo
        self._export = export_service

    def summary(self) -> DataSummary:
        fixes = {DataSource.CUSTOM: 0, DataSource.IMPORTED: 0}
        navaid_sources = {DataSource.CUSTOM: 0, DataSource.IMPORTED: 0}
        by_type = {t: 0 for t in NavaidType}
        enabled = disabled = 0

        for source, is_enabled, count in self._fix_repo.count_summary():
            fixes[DataSource(source)] += count
            enabled, disabled = _tally(enabled, disabled, is_enabled, count)
        for navaid_type, source, is_enabled, count in self._navaid_repo.count_summary():
            by_type[NavaidType(navaid_type)] += count
            navaid_sources[DataSource(source)] += count
            enabled, disabled = _tally(enabled, disabled, is_enabled, count)

        return DataSummary(
            fixes_custom=fixes[DataSource.CUSTOM],
            fixes_imported=fixes[DataSource.IMPORTED],
            navaids_by_type=by_type,
            navaids_custom=navaid_sources[DataSource.CUSTOM],
            navaids_imported=navaid_sources[DataSource.IMPORTED],
            enabled=enabled,
            disabled=disabled,
        )

    def export_status(self) -> ExportStatus:
        last_written = self._export.last_written()
        if self._export.last_error is not None:
            return ExportStatus(ExportState.FAILED, last_written, self._export.last_error)
        if last_written is None:
            return ExportStatus(ExportState.NOT_WRITTEN)
        return ExportStatus(ExportState.UP_TO_DATE, last_written)


def _tally(enabled: int, disabled: int, is_enabled: bool, count: int) -> tuple[int, int]:
    return (enabled + count, disabled) if is_enabled else (enabled, disabled + count)
