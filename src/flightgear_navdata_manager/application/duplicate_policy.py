"""The one duplicate policy, used by manual entry (Add Waypoint / Add
NAV) and by every import (Import Dataset). Records are only ever
compared with records of the same kind -- FIX, or the same navaid type:
a VOR and an NDB sharing an identifier are unrelated.

For a candidate record, each stored record of the same kind and
identifier within the conflict radius is classified as:

  EXACT     same position (within EXACT_TOLERANCE_NM) and, for navaids,
            the same frequency -- the same record again
  NEARBY    within MATCH_TOLERANCE_NM and the same frequency -- the same
            real-world point, e.g. resurveyed a few metres away
  CONFLICT  an *enabled* record within CONFLICT_RADIUS_NM that isn't the
            same (materially different position or frequency). FlightGear
            would keep only one of the two if they're within its own dedup
            radius (15 nm fixes / 10 nm navaids), and beyond that the pair
            is still worth a human look.

Same-identifier records further away are different places (identifiers
are reused far apart) and don't match. EXACT/NEARBY consider disabled
records too, so importing the same data again never resurrects records
the user switched off; a disabled record never blocks a CONFLICT, so
disabling the old record is how a user lets a replacement in.

Proximity uses domain/duplicates.py (haversine, domain/geo.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from flightgear_navdata_manager.domain.duplicates import nearby_duplicates
from flightgear_navdata_manager.domain.geo import haversine_nm
from flightgear_navdata_manager.domain.models import DataSource, Dme, Fix, Navaid, Ndb, Vor

EXACT_TOLERANCE_NM = 0.001        # ~2 m: coordinate rounding, not movement
MATCH_TOLERANCE_NM = 1.0          # resurveys move a charted point by metres, not miles
# FAA fix identifiers are unique nationwide, so a same-named fix within
# 100 nm is the same point moved or a clash worth reviewing. Distinct
# FAA navaids sharing type + identifier are >= 98 nm apart (2026-09
# cycle), so navaids use 50 nm. Both exceed FlightGear's dedup radii.
FIX_CONFLICT_RADIUS_NM = 100.0
NAVAID_CONFLICT_RADIUS_NM = 50.0
_FREQ_TOLERANCE_MHZ = 0.005


class MatchKind(Enum):
    EXACT = "exact duplicate"
    NEARBY = "nearby duplicate"
    CONFLICT = "identifier conflict"


@dataclass(frozen=True)
class DuplicateMatch:
    kind: MatchKind
    record: Fix | Navaid              # the stored (or earlier-imported) record
    distance_nm: float

    @property
    def is_duplicate(self) -> bool:
        return self.kind is not MatchKind.CONFLICT

    def describe(self) -> str:
        """e.g. 'VOR QET (imported) at 51.784837, -150.824330, 114.10 MHz -- 0.3 nm away'"""
        record = self.record
        if record.id is None:
            origin = "earlier in this import"
        else:
            origin = "custom" if record.source == DataSource.CUSTOM else "imported"
            if not record.enabled:
                origin += ", disabled"
        return (
            f"{record_kind(record)} {record.ident} ({origin}) at {position_text(record)}"
            f" -- {self.distance_nm:.1f} nm away"
        )


def record_kind(record: Fix | Navaid) -> str:
    return "FIX" if isinstance(record, Fix) else record.type.value


def frequency_text(record: Fix | Navaid) -> str:
    if isinstance(record, Ndb):
        return f"{record.frequency_khz} kHz"
    if isinstance(record, Vor):
        return f"{record.frequency_mhz:.2f} MHz"
    if isinstance(record, Dme):
        return f"{record.paired_frequency_mhz:.2f} MHz"
    return ""


def position_text(record: Fix | Navaid) -> str:
    text = f"{record.latitude:.6f}, {record.longitude:.6f}"
    freq = frequency_text(record)
    return f"{text}, {freq}" if freq else text


def conflict_radius_nm(record: Fix | Navaid) -> float:
    return FIX_CONFLICT_RADIUS_NM if isinstance(record, Fix) else NAVAID_CONFLICT_RADIUS_NM


class DuplicateIndex:
    """Records by (kind, identifier), for checking many candidates fast."""

    def __init__(self, records: list[Fix | Navaid] = ()):
        self._by_key: dict[tuple[str, str], list[Fix | Navaid]] = {}
        for record in records:
            self.add(record)

    def add(self, record: Fix | Navaid) -> None:
        self._by_key.setdefault((record_kind(record), record.ident), []).append(record)

    def matches(self, candidate: Fix | Navaid) -> list[DuplicateMatch]:
        """Duplicates first (closest first), then conflicts (closest first).
        `candidate.ident` must already be normalized (validated)."""
        same = self._by_key.get((record_kind(candidate), candidate.ident), [])
        found = []
        for record in nearby_duplicates(
            same, candidate.ident, candidate.latitude, candidate.longitude, conflict_radius_nm(candidate)
        ):
            distance = haversine_nm(record.latitude, record.longitude, candidate.latitude, candidate.longitude)
            if distance <= MATCH_TOLERANCE_NM and _same_signal(record, candidate):
                kind = MatchKind.EXACT if distance <= EXACT_TOLERANCE_NM else MatchKind.NEARBY
            elif record.enabled:
                kind = MatchKind.CONFLICT
            else:
                continue
            found.append(DuplicateMatch(kind, record, distance))
        return sorted(found, key=lambda m: (not m.is_duplicate, m.distance_nm))


def _same_signal(a: Fix | Navaid, b: Fix | Navaid) -> bool:
    if isinstance(a, Ndb):
        return a.frequency_khz == b.frequency_khz
    if isinstance(a, Vor):
        return abs(a.frequency_mhz - b.frequency_mhz) < _FREQ_TOLERANCE_MHZ
    if isinstance(a, Dme):
        return abs(a.paired_frequency_mhz - b.paired_frequency_mhz) < _FREQ_TOLERANCE_MHZ
    return True  # fixes have no signal
