"""SQLite schema and connection management.

This is a persistence-layer concern, deliberately decoupled from the
domain model's shape (see domain/models.py docstring): the three
distinct Ndb/Vor/Dme dataclasses are stored in one physical table
discriminated by a `type` column, with nullable per-type columns. That
mapping lives entirely in navaid_repository.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS fixes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    ident TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    interop_scope TEXT,
    interop_icao_region TEXT,
    interop_source_field_count INTEGER,
    origin_file TEXT
);

CREATE TABLE IF NOT EXISTS navaids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    type TEXT NOT NULL,
    ident TEXT NOT NULL,
    name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    elevation_ft INTEGER NOT NULL,
    frequency_khz INTEGER,
    frequency_mhz REAL,
    range_nm INTEGER NOT NULL,
    slaved_variation_deg REAL,
    bias_nm REAL,
    interop_scope TEXT,
    interop_icao_region TEXT,
    interop_source_field_count INTEGER,
    origin_file TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
