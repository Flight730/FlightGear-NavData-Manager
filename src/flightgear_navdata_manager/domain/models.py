"""Format-neutral domain models.

These represent the navigational objects themselves (a fix/waypoint, an
NDB, a VOR, a DME) -- not the on-disk X-Plane/FlightGear .dat file
layout. Parsers translate a specific file format into these models;
writers translate these models into a specific file format.

NDB/VOR/DME are modeled as three distinct dataclasses rather than one
dataclass with a shared, file-column-shaped field (e.g. a generic
"multiuse" double), because a VOR's slaved variation and a DME's bias
are different real-world concepts that only happen to share a file
column by X-Plane convention -- see the project specification for the
full verification against FlightGear 2024.1 source.

`*Interop` fields hold data that exists only for X-Plane FIX1100+/
NAV1100+ spec compliance or interoperability with other tools.
FlightGear itself never reads these (verified against fixlist.cxx and
navdb.cxx) -- they are optional, populated only when present in an
imported source file, and MVP 1's writers do not re-emit them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DataSource(Enum):
    CUSTOM = "custom"
    IMPORTED = "imported"


class NavaidType(Enum):
    NDB = "NDB"
    VOR = "VOR"
    DME = "DME"


@dataclass
class FixInterop:
    scope: str | None = None          # "ENRT" or an ICAO airport code
    icao_region: str | None = None    # e.g. "K1"
    source_field_count: int | None = None  # 3, 5, or 6 -- diagnostic only


@dataclass
class Fix:
    id: int | None
    source: DataSource
    enabled: bool
    created_at: datetime
    ident: str
    latitude: float
    longitude: float
    interop: FixInterop | None = None
    origin_file: str | None = None    # IMPORTED only; metadata, never opened for writing


@dataclass
class NavaidInterop:
    scope: str | None = None
    icao_region: str | None = None
    source_field_count: int | None = None  # 9 or up to 11 -- diagnostic only


@dataclass
class Ndb:
    id: int | None
    source: DataSource
    enabled: bool
    created_at: datetime
    ident: str               # max 4 chars, spec-verified
    name: str
    latitude: float
    longitude: float
    elevation_ft: int
    frequency_khz: int       # plain integer kHz
    range_nm: int              # MAXIMUM reception range
    interop: NavaidInterop | None = None
    origin_file: str | None = None

    @property
    def type(self) -> NavaidType:
        return NavaidType.NDB


@dataclass
class Vor:
    id: int | None
    source: DataSource
    enabled: bool
    created_at: datetime
    ident: str               # max 4 chars, spec-verified
    name: str
    latitude: float
    longitude: float
    elevation_ft: int
    frequency_mhz: float     # human-readable MHz, e.g. 116.70; writer encodes x100
    range_nm: int              # MAXIMUM reception range
    slaved_variation_deg: float = 0.0
    interop: NavaidInterop | None = None
    origin_file: str | None = None

    @property
    def type(self) -> NavaidType:
        return NavaidType.VOR


@dataclass
class Dme:
    id: int | None
    source: DataSource
    enabled: bool
    created_at: datetime
    ident: str               # max 4 chars, spec-verified
    name: str
    latitude: float
    longitude: float
    elevation_ft: int
    paired_frequency_mhz: float  # VHF paired frequency, NOT a DME channel
    range_nm: int                  # MINIMUM reception range -- differs from NDB/VOR
    bias_nm: float = 0.0
    interop: NavaidInterop | None = None
    origin_file: str | None = None

    @property
    def type(self) -> NavaidType:
        return NavaidType.DME


Navaid = Ndb | Vor | Dme
