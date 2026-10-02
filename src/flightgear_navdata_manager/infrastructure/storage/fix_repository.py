"""Persistence for Fix domain objects."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from flightgear_navdata_manager.domain.models import DataSource, Fix, FixInterop


class FixRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, fix: Fix) -> Fix:
        self._insert(fix)
        self._conn.commit()
        return fix

    def add_many(self, fixes: list[Fix]) -> None:
        """Inserts all of `fixes` in one transaction: either every record
        is stored or, on any database error, none is.
        """
        with self._conn:
            for fix in fixes:
                self._insert(fix)

    def _insert(self, fix: Fix) -> None:
        interop = fix.interop or FixInterop()
        cur = self._conn.execute(
            """INSERT INTO fixes
               (source, enabled, created_at, ident, latitude, longitude,
                interop_scope, interop_icao_region, interop_source_field_count, origin_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fix.source.value, int(fix.enabled), fix.created_at.isoformat(),
                fix.ident, fix.latitude, fix.longitude,
                interop.scope, interop.icao_region, interop.source_field_count,
                fix.origin_file,
            ),
        )
        fix.id = cur.lastrowid

    def set_enabled(self, fix_id: int, enabled: bool) -> None:
        self._conn.execute("UPDATE fixes SET enabled=? WHERE id=?", (int(enabled), fix_id))
        self._conn.commit()

    def delete(self, fix_id: int) -> None:
        self._conn.execute("DELETE FROM fixes WHERE id=?", (fix_id,))
        self._conn.commit()

    def get(self, fix_id: int) -> Fix | None:
        row = self._conn.execute("SELECT * FROM fixes WHERE id=?", (fix_id,)).fetchone()
        return self._row_to_fix(row) if row else None

    def list_all(self) -> list[Fix]:
        rows = self._conn.execute("SELECT * FROM fixes ORDER BY ident").fetchall()
        return [self._row_to_fix(row) for row in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM fixes").fetchone()[0]

    def count_summary(self) -> list[tuple[str, bool, int]]:
        """(source, enabled, count) for every combination present -- one
        GROUP BY query, no records loaded."""
        rows = self._conn.execute(
            "SELECT source, enabled, COUNT(*) FROM fixes GROUP BY source, enabled"
        ).fetchall()
        return [(row[0], bool(row[1]), row[2]) for row in rows]

    def list_enabled(self) -> list[Fix]:
        rows = self._conn.execute(
            "SELECT * FROM fixes WHERE enabled=1 ORDER BY ident"
        ).fetchall()
        return [self._row_to_fix(row) for row in rows]

    @staticmethod
    def _row_to_fix(row: sqlite3.Row) -> Fix:
        interop = None
        if row["interop_scope"] is not None or row["interop_icao_region"] is not None:
            interop = FixInterop(
                scope=row["interop_scope"],
                icao_region=row["interop_icao_region"],
                source_field_count=row["interop_source_field_count"],
            )
        return Fix(
            id=row["id"],
            source=DataSource(row["source"]),
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            ident=row["ident"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            interop=interop,
            origin_file=row["origin_file"],
        )
