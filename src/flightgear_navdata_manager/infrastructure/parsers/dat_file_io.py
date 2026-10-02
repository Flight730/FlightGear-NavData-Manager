"""Shared helper for reading FlightGear/X-Plane .dat files.

Mirrors simgear's sg_gzifstream behavior for MVP 1's purposes: a file is
read as gzip if it starts with the gzip magic bytes, regardless of its
extension, and as plain text otherwise. We do not attempt
sg_gzifstream's extension-toggling fallback (trying <name>.gz or
<name> minus ".gz" if the exact given path doesn't open) -- the caller
is expected to pass an existing, readable path.
"""

from __future__ import annotations

import gzip

GZIP_MAGIC = b"\x1f\x8b"


def read_text_lines(path: str) -> list[str]:
    """Read a .dat (or .dat.gz) file, read-only, and return its lines.

    Never writes to `path`. Detects gzip by content, not extension.
    """
    with open(path, "rb") as f:
        head = f.read(2)
        f.seek(0)
        raw = f.read()
    if head == GZIP_MAGIC:
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8", errors="replace")
    return text.splitlines()


def detect_dat_kind(path: str) -> str | None:
    """'fix' or 'nav' for a FlightGear/X-Plane fix.dat / nav.dat (plain
    or gzip), else None. Reads only the first few lines: header "I"/"A",
    a numeric version line, then the first data record's shape --
    fix: lat lon ident; nav: row-code lat lon ... (>= 9 fields)."""
    try:
        with open(path, "rb") as f:
            magic = f.read(2)
        opener = gzip.open if magic == GZIP_MAGIC else open
        with opener(path, "rt", encoding="utf-8", errors="replace") as f:
            lines = [next(f, "") for _ in range(40)]
    except (OSError, EOFError, gzip.BadGzipFile):
        return None
    if lines[0].strip() not in ("I", "A") or not lines[1].split()[:1] or not lines[1].split()[0].isdigit():
        return None
    for line in lines[2:]:
        fields = line.split()
        if len(fields) < 3 or line.lstrip().startswith("#"):
            continue
        try:
            float(fields[0]), float(fields[1])
        except ValueError:
            return None
        if fields[0].lstrip("-").isdigit() and len(fields) >= 9:
            return "nav"
        return "fix"
    return None
