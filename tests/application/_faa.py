"""Helpers for building FAA-format test inputs from the synthetic sample rows."""

import csv
import io
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "infrastructure" / "fixtures"
NAV_TXT = FIXTURES / "sample_faa_nav.txt"
NAV_CSV = FIXTURES / "sample_faa_nav.csv"
FIX_TXT = FIXTURES / "sample_faa_fix.txt"
FIX_CSV = FIXTURES / "sample_faa_fix.csv"


def nav1(ident: str) -> str:
    lines = NAV_TXT.read_text(encoding="latin-1").splitlines()
    return next(l for l in lines if l.startswith("NAV1") and l[28:32].strip() == ident)


def set_field(line: str, start: int, length: int, value: str) -> str:
    """Overwrite a 1-based fixed-width column, as FAA layouts number them."""
    return line[: start - 1] + value.ljust(length)[:length] + line[start - 1 + length :]


def write_lines(path: Path, rows: list[str]) -> str:
    path.write_text("\r\n".join(rows) + "\r\n", encoding="latin-1")
    return str(path)


def csv_table(sample: Path) -> tuple[list[str], list[dict[str, str]]]:
    rows = list(csv.reader(io.StringIO(sample.read_text())))
    return rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
    writer.writerow(header)
    writer.writerows([[r.get(h, "") for h in header] for r in rows])
    path.write_text(buffer.getvalue())
    return str(path)


def by_key(navaids):
    return {(n.type.value, n.ident): n for n in navaids}
