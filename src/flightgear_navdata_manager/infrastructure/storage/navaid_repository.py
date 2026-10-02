"""Persistence for Ndb/Vor/Dme domain objects.

The three domain dataclasses are intentionally distinct (see
domain/models.py), but share one physical SQLite table discriminated
by the `type` column -- an ordinary persistence-layer decision that is
independent of the domain model's shape.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from flightgear_navdata_manager.domain.models import (
    DataSource,
    Dme,
    Ndb,
    NavaidInterop,
    NavaidType,
    Vor,
)

Navaid = Ndb | Vor | Dme


class NavaidRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, navaid: Navaid) -> Navaid:
        self._insert(navaid)
        self._conn.commit()
        return navaid

    def add_many(self, navaids: list[Navaid]) -> None:
        """Inserts all of `navaids` in one transaction: either every record
        is stored or, on any database error, none is.
        """
        with self._conn:
            for navaid in navaids:
                self._insert(navaid)

    def _insert(self, navaid: Navaid) -> None:
        interop = navaid.interop or NavaidInterop()
        freq_khz = navaid.frequency_khz if isinstance(navaid, Ndb) else None
        freq_mhz = None
        slaved = None
        bias = None
        if isinstance(navaid, Vor):
            freq_mhz = navaid.frequency_mhz
            slaved = navaid.slaved_variation_deg
        elif isinstance(navaid, Dme):
            freq_mhz = navaid.paired_frequency_mhz
            bias = navaid.bias_nm

        cur = self._conn.execute(
            """INSERT INTO navaids
               (source, enabled, created_at, type, ident, name, latitude, longitude,
                elevation_ft, frequency_khz, frequency_mhz, range_nm,
                slaved_variation_deg, bias_nm,
                interop_scope, interop_icao_region, interop_source_field_count, origin_file)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                navaid.source.value, int(navaid.enabled), navaid.created_at.isoformat(),
                navaid.type.value, navaid.ident, navaid.name,
                navaid.latitude, navaid.longitude, navaid.elevation_ft,
                freq_khz, freq_mhz, navaid.range_nm, slaved, bias,
                interop.scope, interop.icao_region, interop.source_field_count,
                navaid.origin_file,
            ),
        )
        navaid.id = cur.lastrowid

    def set_enabled(self, navaid_id: int, enabled: bool) -> None:
        self._conn.execute("UPDATE navaids SET enabled=? WHERE id=?", (int(enabled), navaid_id))
        self._conn.commit()

    def delete(self, navaid_id: int) -> None:
        self._conn.execute("DELETE FROM navaids WHERE id=?", (navaid_id,))
        self._conn.commit()

    def get(self, navaid_id: int) -> Navaid | None:
        row = self._conn.execute("SELECT * FROM navaids WHERE id=?", (navaid_id,)).fetchone()
        return self._row_to_navaid(row) if row else None

    def list_all(self) -> list[Navaid]:
        rows = self._conn.execute("SELECT * FROM navaids ORDER BY ident").fetchall()
        return [self._row_to_navaid(row) for row in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM navaids").fetchone()[0]

    def count_summary(self) -> list[tuple[str, str, bool, int]]:
        """(type, source, enabled, count) for every combination present --
        one GROUP BY query, no records loaded."""
        rows = self._conn.execute(
            "SELECT type, source, enabled, COUNT(*) FROM navaids GROUP BY type, source, enabled"
        ).fetchall()
        return [(row[0], row[1], bool(row[2]), row[3]) for row in rows]

    def list_enabled(self) -> list[Navaid]:
        rows = self._conn.execute(
            "SELECT * FROM navaids WHERE enabled=1 ORDER BY ident"
        ).fetchall()
        return [self._row_to_navaid(row) for row in rows]

    @staticmethod
    def _row_to_navaid(row: sqlite3.Row) -> Navaid:
        interop = None
        if row["interop_scope"] is not None or row["interop_icao_region"] is not None:
            interop = NavaidInterop(
                scope=row["interop_scope"],
                icao_region=row["interop_icao_region"],
                source_field_count=row["interop_source_field_count"],
            )
        common = dict(
            id=row["id"],
            source=DataSource(row["source"]),
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            ident=row["ident"],
            name=row["name"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            elevation_ft=row["elevation_ft"],
            interop=interop,
            origin_file=row["origin_file"],
        )
        navaid_type = NavaidType(row["type"])
        if navaid_type == NavaidType.NDB:
            return Ndb(frequency_khz=row["frequency_khz"], range_nm=row["range_nm"], **common)
        if navaid_type == NavaidType.VOR:
            return Vor(
                frequency_mhz=row["frequency_mhz"],
                range_nm=row["range_nm"],
                slaved_variation_deg=row["slaved_variation_deg"] or 0.0,
                **common,
            )
        if navaid_type == NavaidType.DME:
            return Dme(
                paired_frequency_mhz=row["frequency_mhz"],
                range_nm=row["range_nm"],
                bias_nm=row["bias_nm"] or 0.0,
                **common,
            )
        raise ValueError(f"Unknown navaid type in DB: {row['type']!r}")
