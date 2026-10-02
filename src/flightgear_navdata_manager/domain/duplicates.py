"""Proximity-duplicate rule shared by the manual-entry services and the
dataset importer.

A record is a "nearby duplicate" of another when both have the same
identifier and lie within a given radius of each other. The radii
themselves (15 nm for fixes, 10 nm for navaids) are FlightGear's own
dedup radii -- see domain/geo.py -- and are owned by WaypointService /
NavaidService. Callers are responsible for pre-filtering `records` to
the same kind (FIX vs. a specific navaid type) and, where relevant, to
enabled records only.
"""

from __future__ import annotations

from typing import Iterable, Protocol, TypeVar

from .geo import haversine_nm


class _Positioned(Protocol):
    ident: str
    latitude: float
    longitude: float


T = TypeVar("T", bound=_Positioned)


def nearby_duplicates(
    records: Iterable[T], ident: str, latitude: float, longitude: float, radius_nm: float
) -> list[T]:
    ident = ident.strip().upper()
    return [
        r
        for r in records
        if r.ident == ident
        and haversine_nm(r.latitude, r.longitude, latitude, longitude) <= radius_nm
    ]
