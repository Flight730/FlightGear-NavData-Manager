"""Writer for our generated custom fix.dat.

Always emits exactly 3 fields per record (latitude, longitude,
identifier), matching FlightGear's fixlist.cxx minimum requirement and
deliberately omitting the scope/region interop columns in MVP 1 (see
project spec section on FIX interop fields). Header declares "600
Version" -- this is cosmetic only, since FlightGear's fixlist.cxx never
parses the fix.dat header at all (verified against source).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from flightgear_navdata_manager.domain.models import Fix

HEADER_LINE_1 = "I"


def _header_line_2() -> str:
    build = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return (
        f"600 Version - data cycle 0000, build {build}, "
        "metadata FlightGearNavDataManager custom data (non-AIRAC, user-generated)."
    )


def format_fix_record(fix: Fix) -> str:
    return f"{fix.latitude:.8f} {fix.longitude:.8f} {fix.ident}"


def write_fix_dat(fixes: list[Fix], path: str) -> None:
    """Overwrites `path` with a full regeneration of `fixes`.

    `fixes` should already be filtered to enabled records by the
    caller -- this writer makes no enabled/disabled distinction itself.

    Writes to a temporary file in the same directory and atomically
    renames it into place (os.replace), so a reader (e.g. FlightGear
    rebuilding its nav cache at the moment we happen to regenerate)
    never observes a partially-written file.
    """
    lines = [HEADER_LINE_1, _header_line_2()]
    for fix in fixes:
        lines.append(format_fix_record(fix))
    lines.append("99")

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp_path, path)
