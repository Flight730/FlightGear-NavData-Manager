"""Writer for our generated custom nav.dat.

Always emits exactly 9 fields per record (810-compatible shape) and
declares "810 Version" in the header. This pairing is NOT cosmetic:
per this project's verified source-level analysis of FlightGear
2024.1's navdb.cxx, declaring a >=1100 header while emitting fewer
than 11 actual fields risks an out-of-bounds vector access
(`fields[10]` on a 9- or 10-element vector) which is undefined
behavior in FlightGear's C++ parser. Since every record this module
writes has exactly 9 fields, "810" is always the correct and safe
header to declare -- do not change this without re-verifying the
version/field-count coupling in navdb.cxx.

Only NDB (row 2), VOR (row 3) and standalone DME (row 13) are
supported -- MVP 1 scope.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from flightgear_navdata_manager.domain.models import Dme, Ndb, NavaidType, Vor

HEADER_LINE_1 = "I"

ROW_CODE = {
    NavaidType.NDB: 2,
    NavaidType.VOR: 3,
    NavaidType.DME: 13,
}


def _header_line_2() -> str:
    build = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return (
        f"810 Version - data cycle 0000, build {build}, "
        "metadata FlightGearNavDataManager custom data (non-AIRAC, user-generated)."
    )


def format_ndb_record(navaid: Ndb) -> str:
    # 2 lat lon elev_ft freq_khz range_nm 0.0 ident name
    return (
        f"2 {navaid.latitude:.8f} {navaid.longitude:.8f} {navaid.elevation_ft:d} "
        f"{navaid.frequency_khz:d} {navaid.range_nm:d} 0.0 {navaid.ident} {navaid.name}"
    )


def format_vor_record(navaid: Vor) -> str:
    # 3 lat lon elev_ft freq(MHz*100) range_nm slaved_var ident name
    freq_x100 = round(navaid.frequency_mhz * 100)
    return (
        f"3 {navaid.latitude:.8f} {navaid.longitude:.8f} {navaid.elevation_ft:d} "
        f"{freq_x100:d} {navaid.range_nm:d} {navaid.slaved_variation_deg:.3f} "
        f"{navaid.ident} {navaid.name}"
    )


def format_dme_record(navaid: Dme) -> str:
    # 13 lat lon elev_ft freq(MHz*100, paired VHF freq -- not a channel) range_nm bias ident name
    freq_x100 = round(navaid.paired_frequency_mhz * 100)
    return (
        f"13 {navaid.latitude:.8f} {navaid.longitude:.8f} {navaid.elevation_ft:d} "
        f"{freq_x100:d} {navaid.range_nm:d} {navaid.bias_nm:.3f} "
        f"{navaid.ident} {navaid.name}"
    )


def format_navaid_record(navaid: Ndb | Vor | Dme) -> str:
    if isinstance(navaid, Ndb):
        return format_ndb_record(navaid)
    if isinstance(navaid, Vor):
        return format_vor_record(navaid)
    if isinstance(navaid, Dme):
        return format_dme_record(navaid)
    raise TypeError(f"Unsupported navaid type: {type(navaid)!r}")


def write_nav_dat(navaids: list[Ndb | Vor | Dme], path: str) -> None:
    """Overwrites `path` with a full regeneration of `navaids`.

    `navaids` should already be filtered to enabled records by the
    caller. Records are sorted by row code, which satisfies the
    X-Plane spec's inter-record file-ordering requirements (e.g.
    glideslope must follow its localizer) for forward compatibility,
    even though MVP 1's three supported types have no such ordering
    dependency among themselves.

    Writes to a temporary file in the same directory and atomically
    renames it into place (os.replace) -- see fix_dat_writer.py for why.
    """
    lines = [HEADER_LINE_1, _header_line_2()]
    ordered = sorted(navaids, key=lambda n: ROW_CODE[n.type])
    for navaid in ordered:
        lines.append(format_navaid_record(navaid))
    lines.append("99")

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp_path, path)
