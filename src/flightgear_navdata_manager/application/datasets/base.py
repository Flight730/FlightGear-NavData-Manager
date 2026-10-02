"""Format-neutral contract between a dataset reader and
DatasetImportService.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from flightgear_navdata_manager.domain.models import Fix, Navaid
from flightgear_navdata_manager.infrastructure.parsers.faa_common import SourceFile

FIX = "FIX"
NAV = "NAV"


@dataclass
class ImportCandidate:
    """A domain record built from one source record, not yet stored."""

    record: Fix | Navaid
    line_number: int | None
    label: str               # human-readable source description, e.g. "QET VORTAC (Tester, AK)"
    source: str = ""         # source file name


@dataclass
class RecordIssue:
    line_number: int | None
    label: str
    reason: str              # plain-language, shown to the user
    category: str = ""       # FIX or NAV
    source: str = ""         # source file name


@dataclass
class DatasetReadResult:
    records_read: Counter[str] = field(default_factory=Counter)  # FIX/NAV -> source records
    candidates: list[ImportCandidate] = field(default_factory=list)
    unsupported: list[RecordIssue] = field(default_factory=list)  # intentionally not imported
    invalid: list[RecordIssue] = field(default_factory=list)      # malformed / incomplete
    warnings: list[RecordIssue] = field(default_factory=list)     # imported, but worth knowing
    notes: list[str] = field(default_factory=list)                # file-level information
    effective_dates: set[str] = field(default_factory=set)        # as stated by the source


class DatasetReader(Protocol):
    category: str            # FIX, NAV, or "" for a format that holds both
    description: str         # e.g. "FAA NASR FIX (CSV)"

    def read(self, source: SourceFile) -> DatasetReadResult:
        """Parse `source` (read-only) into import candidates. Must not raise
        for bad individual records -- report them in `invalid`. May raise
        FaaFormatError / OSError for a file that can't be read at all."""
