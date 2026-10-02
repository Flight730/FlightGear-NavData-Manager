"""FAA NASR FIX data (FIX.txt or FIX_BASE.csv) -> Fix records.

  ident                <- FIX ID
  latitude/longitude   <- FAA position (DMS + hemisphere; see the parsers)
  interop.icao_region  <- ICAO region code (e.g. "K2") -- the same concept
                          X-Plane fix.dat stores; never exported by MVP 1
  origin_file          <- the source file

Every FAA fix use (waypoint, reporting point, CNF, VFR waypoint, ...) is
a named position, so all are imported. Not mapped (no place in the
Fix model): state, fix use, ARTCC, charting data, previous name,
pitch/catch flags, compulsory flag, and the detail records (FIX2-FIX5
/ FIX_NAV.csv / FIX_CHRT.csv).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Callable

from flightgear_navdata_manager.domain.models import DataSource, Fix, FixInterop
from flightgear_navdata_manager.infrastructure.parsers.faa_common import FaaParseResult, SourceFile

from .base import FIX, DatasetReadResult, ImportCandidate, RecordIssue

_DETAIL_ROW_DESCRIPTIONS = {
    "FIX2": "navaid makeup",
    "FIX3": "ILS makeup",
    "FIX4": "remarks",
    "FIX5": "charting types",
}


class FaaFixReader:
    category = FIX

    def __init__(self, description: str, parse: Callable[[SourceFile], FaaParseResult]):
        self.description = description
        self._parse = parse

    def read(self, source: SourceFile) -> DatasetReadResult:
        parsed = self._parse(source)
        result = DatasetReadResult(records_read=Counter({FIX: parsed.rows_read}))
        for issue in parsed.issues:
            result.invalid.append(
                RecordIssue(issue.line_number, issue.label, issue.reason, FIX, source.name)
            )

        now = datetime.now(timezone.utc)
        for record in parsed.records:
            if record.effective_date:
                result.effective_dates.add(record.effective_date)
            if not record.ident:
                result.invalid.append(
                    RecordIssue(record.line_number, record.label, "no identifier", FIX, source.name)
                )
                continue
            fix = Fix(
                id=None,
                source=DataSource.IMPORTED,
                enabled=True,
                created_at=now,
                ident=record.ident,
                latitude=record.latitude,
                longitude=record.longitude,
                interop=FixInterop(icao_region=record.icao_region) if record.icao_region else None,
                origin_file=source.display,
            )
            result.candidates.append(ImportCandidate(fix, record.line_number, record.label, source.name))

        if parsed.detail_rows:
            detail = ", ".join(
                f"{count} {_DETAIL_ROW_DESCRIPTIONS[row]}"
                for row, count in sorted(parsed.detail_rows.items())
            )
            result.notes.append(
                f"{source.name}: {sum(parsed.detail_rows.values())} supplementary rows have no "
                f"equivalent in this app: {detail}."
            )
        return result
