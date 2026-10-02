"""FlightGear/X-Plane fix.dat and nav.dat through the Import Dataset
workflow (so they get the same validation and duplicate handling as FAA
data). Reuses the existing parsers and the record mapping the legacy
Import fix.dat / nav.dat buttons use -- those buttons are unchanged.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from flightgear_navdata_manager.infrastructure.parsers.faa_common import SourceFile
from flightgear_navdata_manager.infrastructure.parsers.fix_dat_parser import parse_fix_dat
from flightgear_navdata_manager.infrastructure.parsers.nav_dat_parser import parse_nav_dat

from ..import_navdata import fix_from_parsed, navaid_from_parsed
from .base import FIX, NAV, DatasetReadResult, ImportCandidate, RecordIssue


class FlightGearFixDatReader:
    category = FIX
    description = "FlightGear fix.dat"

    def read(self, source: SourceFile) -> DatasetReadResult:
        parsed = parse_fix_dat(source.path)
        result = DatasetReadResult(records_read=Counter({FIX: len(parsed.records) + len(parsed.warnings)}))
        result.invalid.extend(RecordIssue(None, source.name, w, FIX, source.name) for w in parsed.warnings)
        now = datetime.now(timezone.utc)
        for record in parsed.records:
            fix = fix_from_parsed(record, source.path, now)
            result.candidates.append(
                ImportCandidate(fix, record.line_number, f"{record.ident} FIX", source.name)
            )
        return result


class FlightGearNavDatReader:
    category = NAV
    description = "FlightGear nav.dat"

    def read(self, source: SourceFile) -> DatasetReadResult:
        parsed = parse_nav_dat(source.path)
        skipped = sum(parsed.skipped_unsupported_row_codes.values())
        result = DatasetReadResult(
            records_read=Counter({NAV: len(parsed.records) + len(parsed.warnings) + skipped}),
        )
        result.invalid.extend(RecordIssue(None, source.name, w, NAV, source.name) for w in parsed.warnings)
        for row_code, count in sorted(parsed.skipped_unsupported_row_codes.items()):
            issue = RecordIssue(
                None, f"row code {row_code}",
                f"nav.dat row code {row_code} is not NDB/VOR/DME", NAV, source.name,
            )
            result.unsupported.extend([issue] * count)
        now = datetime.now(timezone.utc)
        for record in parsed.records:
            navaid = navaid_from_parsed(record, source.path, now)
            if navaid is None:  # parser already filters to 2/3/13; defensive
                continue
            label = f"{record.ident} {navaid.type.value} ({record.name})"
            result.candidates.append(ImportCandidate(navaid, record.line_number, label, source.name))
        return result
