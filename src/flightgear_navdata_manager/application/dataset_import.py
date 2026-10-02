"""Import Dataset use case: brings external navigation data -- FAA NASR
FIX/NAV (CSV or TXT) or FlightGear fix.dat/nav.dat, as a file, a .zip or
a whole folder (see application/datasets/) -- into this application's
own database.

Two steps, so the user can see what a dataset contains before anything
is stored:

  analyze(path) -> DatasetImportPlan     read-only: discovers, parses,
                                         validates, classifies every record
  apply(plan)   -> DatasetImportSummary  stores the plan's new records in
                                         one transaction per kind, then
                                         regenerates the custom export once

Every source record ends up in exactly one outcome:

  Imported             new record
  Duplicate            the same record is already stored (or appeared
                       earlier in this import) -- skipped
  Identifier conflict  same kind + identifier as an enabled record nearby,
                       but a materially different position or frequency --
                       skipped, both positions reported; the existing
                       record is never modified
  Invalid              malformed, incomplete, or fails the same validation
                       rules as manual entry
  Unsupported          a type this app doesn't model, or not in service
Rows can additionally carry warnings (e.g. a value that was ignored).

Duplicate / conflict rules are application/duplicate_policy.py -- the
same policy the Add Waypoint / Add NAV forms use.

The source is only ever read. Nothing here touches FlightGear's own
navdata, FG_ROOT, or its saved configuration -- the only files written
are this app's database and its own custom scenery output (via
ExportService).
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field

from flightgear_navdata_manager.domain.exceptions import NavDataError, ValidationError
from flightgear_navdata_manager.domain.models import Fix, Navaid
from flightgear_navdata_manager.infrastructure.parsers.faa_common import FaaFormatError
from flightgear_navdata_manager.infrastructure.parsers.navdata_table_parser import NAVAID_TYPES
from flightgear_navdata_manager.infrastructure.storage.fix_repository import FixRepository
from flightgear_navdata_manager.infrastructure.storage.navaid_repository import (
    NavaidRepository,
)

from . import navaid_service, waypoint_service
from .datasets import SUPPORTED_FORMATS, discover_sources
from .datasets.base import FIX, NAV, ImportCandidate, RecordIssue
from .duplicate_policy import DuplicateIndex, position_text, record_kind
from .export_navdata import ExportService

class UnrecognizedDatasetError(NavDataError):
    """Nothing importable was found at the chosen path."""


class RecordTypeNeededError(NavDataError):
    """The chosen table holds navaids but doesn't say which kind; call
    analyze() again with record_type set to one of `choices`."""

    def __init__(self, message: str, choices: tuple[str, ...]):
        super().__init__(message)
        self.choices = choices


@dataclass
class DatasetImportPlan:
    path: str
    sources: list[tuple[str, str]]                    # (description, file shown to the user)
    ignored: list[tuple[str, str]]                    # (file, reason)
    effective_dates: list[str]
    records_read: Counter[str]                        # category -> source records
    to_import: list[ImportCandidate] = field(default_factory=list)
    existing: list[RecordIssue] = field(default_factory=list)
    conflicts: list[RecordIssue] = field(default_factory=list)
    invalid: list[RecordIssue] = field(default_factory=list)
    unsupported: list[RecordIssue] = field(default_factory=list)
    warnings: list[RecordIssue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def categories(self) -> list[str]:
        return [
            c for c in (FIX, NAV)
            if self.records_read[c] or any(i.category == c for i in self.invalid)
        ]

    def counts(self, category: str | None = None) -> dict[str, int]:
        """Outcome counts for FIX or NAV, or totals when `category` is None."""
        def n(items):
            return sum(1 for i in items if category is None or i.category == category)
        return {
            "Imported": sum(
                1 for c in self.to_import if category is None or _category(c.record) == category
            ),
            "Duplicates skipped": n(self.existing),
            "Identifier conflicts": n(self.conflicts),
            "Invalid rows": n(self.invalid),
            "Unsupported": n(self.unsupported),
            "Warnings": n(self.warnings),
        }

    def to_import_by_kind(self) -> Counter[str]:
        return Counter(record_kind(c.record) for c in self.to_import)


@dataclass
class DatasetImportSummary:
    plan: DatasetImportPlan
    imported_count: int


class DatasetImportService:
    def __init__(
        self,
        fix_repo: FixRepository,
        navaid_repo: NavaidRepository,
        export_service: ExportService,
    ):
        self._fix_repo = fix_repo
        self._navaid_repo = navaid_repo
        self._export = export_service

    def analyze(self, path: str, record_type: str | None = None) -> DatasetImportPlan:
        """Read-only. Raises UnrecognizedDatasetError, RecordTypeNeededError
        (for a single table of navaids without a type column, unless
        `record_type` says NDB/VOR/DME) or OSError."""
        discovery = discover_sources(path)
        untyped = [s for s in discovery.sources if s.needs_type]
        if untyped and len(discovery.sources) == 1 and record_type is None:
            raise RecordTypeNeededError(
                f"{untyped[0].file.name} has no type column, and its records have a frequency "
                "or range, so they could be NDBs, VORs or DMEs.",
                NAVAID_TYPES,
            )
        if len(discovery.sources) > 1:   # can't ask per file in a folder: leave those out
            for source in untyped:
                discovery.sources.remove(source)
                discovery.ignored.append((
                    source.file.name,
                    "a table of navaids with no type column -- import it on its own to choose "
                    "NDB, VOR or DME",
                ))
        if not discovery.sources:
            single_file = not os.path.isdir(path) and not path.lower().endswith(".zip")
            if single_file and discovery.ignored:  # say why that file wasn't recognized
                name, reason = discovery.ignored[0]
                raise UnrecognizedDatasetError(f"{name}: {reason}.\n\nSupported: {SUPPORTED_FORMATS}.")
            raise UnrecognizedDatasetError(
                f"No supported navigation data was found.\n\nSupported: {SUPPORTED_FORMATS}."
            )

        plan = DatasetImportPlan(
            path=path,
            sources=[(s.reader.description, s.file.display) for s in discovery.sources],
            ignored=list(discovery.ignored),
            effective_dates=[],
            records_read=Counter(),
        )
        index = DuplicateIndex([*self._fix_repo.list_all(), *self._navaid_repo.list_all()])
        dates: set[str] = set()

        for discovered in discovery.sources:
            try:
                if discovered.needs_type:
                    read = discovered.reader.read(discovered.file, record_type=record_type)
                else:
                    read = discovered.reader.read(discovered.file)
            except FaaFormatError as exc:
                plan.invalid.append(RecordIssue(
                    None, discovered.file.name, str(exc), discovered.reader.category, discovered.file.name,
                ))
                continue
            plan.records_read.update(read.records_read)
            plan.invalid.extend(read.invalid)
            plan.unsupported.extend(read.unsupported)
            plan.warnings.extend(read.warnings)
            plan.notes.extend(read.notes)
            dates |= read.effective_dates
            for candidate in read.candidates:
                self._classify(candidate, index, plan)

        plan.effective_dates = sorted(dates)
        return plan

    def apply(self, plan: DatasetImportPlan) -> DatasetImportSummary:
        fixes = [c.record for c in plan.to_import if isinstance(c.record, Fix)]
        navaids = [c.record for c in plan.to_import if not isinstance(c.record, Fix)]
        if fixes:
            self._fix_repo.add_many(fixes)
        if navaids:
            self._navaid_repo.add_many(navaids)
        if plan.to_import:
            self._export.regenerate()
        return DatasetImportSummary(plan=plan, imported_count=len(plan.to_import))

    def import_dataset(self, path: str, record_type: str | None = None) -> DatasetImportSummary:
        """analyze + apply without a confirmation step."""
        return self.apply(self.analyze(path, record_type))

    def _classify(self, candidate: ImportCandidate, index: DuplicateIndex, plan: DatasetImportPlan) -> None:
        record = candidate.record
        category = _category(record)

        def issue(reason: str) -> RecordIssue:
            return RecordIssue(candidate.line_number, candidate.label, reason, category, candidate.source)

        try:
            if isinstance(record, Fix):
                waypoint_service.validate_fix(record)
            else:
                navaid_service.validate_navaid(record)
        except ValidationError as exc:
            plan.invalid.append(issue(str(exc)))
            return

        matches = index.matches(record)
        if matches and matches[0].is_duplicate:
            match = matches[0]
            plan.existing.append(issue(f"{match.kind.value.capitalize()} of {match.describe()}"))
            return
        if matches:
            match = matches[0]
            plan.conflicts.append(issue(
                f"Identifier conflict: {match.describe()}; "
                f"this record is at {position_text(record)}"
            ))
            return

        index.add(record)
        plan.to_import.append(candidate)


def _category(record: Fix | Navaid) -> str:
    return FIX if isinstance(record, Fix) else NAV
