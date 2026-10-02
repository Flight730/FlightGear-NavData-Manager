"""Use cases for creating/managing Fix records.

Validation rules per project spec:
  - identifier: non-empty, app-level sanity bound of 10 chars (the
    X-Plane spec states no hard maximum for fixes, just "usually
    five"), uppercase alphanumeric convention
  - latitude/longitude: standard ranges
No scope/region fields are collected here -- FlightGear never reads
them (verified against fixlist.cxx) and MVP 1's writer never emits
them for CUSTOM-created fixes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flightgear_navdata_manager.domain.exceptions import ValidationError
from flightgear_navdata_manager.domain.models import DataSource, Fix
from flightgear_navdata_manager.domain.validation import validate_latlon
from flightgear_navdata_manager.infrastructure.storage.fix_repository import FixRepository

from .duplicate_policy import DuplicateIndex, DuplicateMatch
from .export_navdata import ExportService

# FlightGear's own fix dedup radius (fixlist.cxx, DUPLICATE_DETECTION_RADIUS_NM),
# for reference: duplicate_policy.py's conflict radius is deliberately wider.
DUPLICATE_RADIUS_NM = 15.0


class WaypointService:
    def __init__(self, fix_repo: FixRepository, export_service: ExportService):
        self._fix_repo = fix_repo
        self._export = export_service

    def create(self, ident: str, latitude: float, longitude: float) -> Fix:
        return self.add(build_fix(ident, latitude, longitude))

    def add(self, fix: Fix) -> Fix:
        """Stores a record built by build_fix."""
        fix = self._fix_repo.add(fix)
        self._export.regenerate()
        return fix

    def find_duplicates(self, candidate: Fix) -> list[DuplicateMatch]:
        """Stored fixes that duplicate or conflict with `candidate` under
        the shared policy (application/duplicate_policy.py)."""
        return DuplicateIndex(self._fix_repo.list_all()).matches(candidate)

    def set_enabled(self, fix_id: int, enabled: bool) -> None:
        self._fix_repo.set_enabled(fix_id, enabled)
        self._export.regenerate()

    def delete(self, fix_id: int) -> None:
        self._fix_repo.delete(fix_id)
        self._export.regenerate()

    def list_all(self) -> list[Fix]:
        return self._fix_repo.list_all()

    def count(self) -> int:
        return self._fix_repo.count()


def build_fix(
    ident: str,
    latitude: float,
    longitude: float,
    source: DataSource = DataSource.CUSTOM,
    origin_file: str | None = None,
) -> Fix:
    """A validated, unsaved Fix -- what `create` stores. Shared with the
    CSV/TXT importer so both apply identical rules. Raises ValidationError."""
    ident = _validate_fix_ident(ident)
    validate_latlon(latitude, longitude)
    return Fix(
        id=None,
        source=source,
        enabled=True,
        created_at=datetime.now(timezone.utc),
        ident=ident,
        latitude=latitude,
        longitude=longitude,
        origin_file=origin_file,
    )


def validate_fix(fix: Fix) -> None:
    """Applies the same rules as `create` to an already-built Fix
    (e.g. one produced by a dataset importer), normalizing its ident.
    Raises ValidationError.
    """
    fix.ident = _validate_fix_ident(fix.ident)
    validate_latlon(fix.latitude, fix.longitude)


def _validate_fix_ident(ident: str) -> str:
    ident = ident.strip().upper()
    if not ident:
        raise ValidationError("Identifier is required.")
    if len(ident) > 10:
        raise ValidationError("Identifier must be 10 characters or fewer.")
    if not ident.isalnum():
        raise ValidationError("Identifier must contain only letters and digits.")
    return ident
