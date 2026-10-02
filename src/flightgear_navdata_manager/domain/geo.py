"""Small geo helper shared by the Fix/Navaid services for the soft
duplicate-proximity warning (see project spec: 15 nm for fixes, 10 nm
for navaids -- both values taken directly from FlightGear 2024.1
source, fixlist.cxx and navdb.cxx respectively). This is user guidance
only; it does not reimplement FlightGear's own dedup logic.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_NM = 3440.065


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_NM * asin(sqrt(a))
