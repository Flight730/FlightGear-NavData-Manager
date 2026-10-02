"""Use cases for creating/managing Ndb/Vor/Dme records.

MVP 1 supports exactly three navaid types (NDB, VOR, standalone DME),
all treated as enroute (ENRT) only -- no terminal/airport association,
matching the structural limits of the 810 nav.dat layout our writer
targets (see project spec).

Frequency validation ranges are real-world VHF NDB/VOR band sanity
checks, not literal spec maximums -- they exist to catch obvious
data-entry mistakes, not to enforce an X-Plane/FlightGear rule.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flightgear_navdata_manager.domain.exceptions import ValidationError
from flightgear_navdata_manager.domain.models import DataSource, Dme, Navaid, Ndb, Vor
from flightgear_navdata_manager.domain.validation import validate_latlon
from flightgear_navdata_manager.infrastructure.storage.navaid_repository import (
    NavaidRepository,
)

from .duplicate_policy import DuplicateIndex, DuplicateMatch
from .export_navdata import ExportService

# FlightGear's own navaid dedup radius (navdb.cxx, DUPLICATE_DETECTION_RADIUS_NM),
# for reference: duplicate_policy.py's conflict radius is deliberately wider.
DUPLICATE_RADIUS_NM = 10.0

_NDB_FREQ_MIN_KHZ = 190
_NDB_FREQ_MAX_KHZ = 1750
_VHF_NAV_FREQ_MIN_MHZ = 108.00
_VHF_NAV_FREQ_MAX_MHZ = 117.95


class NavaidService:
    def __init__(self, navaid_repo: NavaidRepository, export_service: ExportService):
        self._repo = navaid_repo
        self._export = export_service

    def create_ndb(
        self,
        ident: str,
        name: str,
        latitude: float,
        longitude: float,
        elevation_ft: int,
        frequency_khz: int,
        range_nm: int,
    ) -> Ndb:
        return self.add(build_ndb(ident, name, latitude, longitude, elevation_ft, frequency_khz, range_nm))

    def create_vor(
        self,
        ident: str,
        name: str,
        latitude: float,
        longitude: float,
        elevation_ft: int,
        frequency_mhz: float,
        range_nm: int,
        slaved_variation_deg: float = 0.0,
    ) -> Vor:
        return self.add(build_vor(
            ident, name, latitude, longitude, elevation_ft, frequency_mhz, range_nm,
            slaved_variation_deg,
        ))

    def create_dme(
        self,
        ident: str,
        name: str,
        latitude: float,
        longitude: float,
        elevation_ft: int,
        paired_frequency_mhz: float,
        range_nm: int,
        bias_nm: float = 0.0,
    ) -> Dme:
        return self.add(build_dme(
            ident, name, latitude, longitude, elevation_ft, paired_frequency_mhz, range_nm, bias_nm,
        ))

    def find_duplicates(self, candidate: Navaid) -> list[DuplicateMatch]:
        """Stored navaids that duplicate or conflict with `candidate` under
        the shared policy (application/duplicate_policy.py). Only the same
        navaid type is ever compared."""
        return DuplicateIndex(self._repo.list_all()).matches(candidate)

    def add(self, navaid: Navaid) -> Navaid:
        """Stores a record built by build_ndb/build_vor/build_dme."""
        navaid = self._repo.add(navaid)
        self._export.regenerate()
        return navaid

    def set_enabled(self, navaid_id: int, enabled: bool) -> None:
        self._repo.set_enabled(navaid_id, enabled)
        self._export.regenerate()

    def delete(self, navaid_id: int) -> None:
        self._repo.delete(navaid_id)
        self._export.regenerate()

    def list_all(self) -> list[Navaid]:
        return self._repo.list_all()

    def count(self) -> int:
        return self._repo.count()


# --- validated, unsaved records ------------------------------------------------
# What create_ndb/create_vor/create_dme store. Shared with the CSV/TXT
# importer so manual entry and import apply identical rules, including
# the type suffix on names. All raise ValidationError.


def build_ndb(
    ident: str, name: str, latitude: float, longitude: float, elevation_ft: int,
    frequency_khz: int, range_nm: int,
    source: DataSource = DataSource.CUSTOM, origin_file: str | None = None,
) -> Ndb:
    ident = _validate_navaid_ident(ident)
    validate_latlon(latitude, longitude)
    _validate_ndb_freq(frequency_khz)
    _validate_range(range_nm)
    return Ndb(
        name=_ensure_suffix(name, "NDB"), frequency_khz=int(frequency_khz), range_nm=int(range_nm),
        **_common(ident, latitude, longitude, elevation_ft, source, origin_file),
    )


def build_vor(
    ident: str, name: str, latitude: float, longitude: float, elevation_ft: int,
    frequency_mhz: float, range_nm: int, slaved_variation_deg: float = 0.0,
    source: DataSource = DataSource.CUSTOM, origin_file: str | None = None,
) -> Vor:
    ident = _validate_navaid_ident(ident)
    validate_latlon(latitude, longitude)
    _validate_vhf_nav_freq(frequency_mhz, "VOR")
    _validate_range(range_nm)
    _validate_slaved_variation(slaved_variation_deg)
    return Vor(
        name=_ensure_suffix(name, "VOR"), frequency_mhz=float(frequency_mhz), range_nm=int(range_nm),
        slaved_variation_deg=float(slaved_variation_deg),
        **_common(ident, latitude, longitude, elevation_ft, source, origin_file),
    )


def build_dme(
    ident: str, name: str, latitude: float, longitude: float, elevation_ft: int,
    paired_frequency_mhz: float, range_nm: int, bias_nm: float = 0.0,
    source: DataSource = DataSource.CUSTOM, origin_file: str | None = None,
) -> Dme:
    ident = _validate_navaid_ident(ident)
    validate_latlon(latitude, longitude)
    _validate_vhf_nav_freq(paired_frequency_mhz, "DME paired")
    _validate_range(range_nm)
    return Dme(
        name=_ensure_suffix(name, "DME"), paired_frequency_mhz=float(paired_frequency_mhz),
        range_nm=int(range_nm), bias_nm=float(bias_nm),
        **_common(ident, latitude, longitude, elevation_ft, source, origin_file),
    )


def _common(ident, latitude, longitude, elevation_ft, source, origin_file) -> dict:
    return dict(
        id=None,
        source=source,
        enabled=True,
        created_at=datetime.now(timezone.utc),
        ident=ident,
        latitude=latitude,
        longitude=longitude,
        elevation_ft=int(elevation_ft),
        origin_file=origin_file,
    )


def validate_navaid(navaid: Navaid) -> None:
    """Applies the same field rules as create_ndb/create_vor/create_dme
    to an already-built navaid (e.g. one produced by a dataset
    importer), normalizing its ident. Unlike the create_* methods it
    does not append a type suffix to the name -- importers supply the
    source's own name. Raises ValidationError.
    """
    navaid.ident = _validate_navaid_ident(navaid.ident)
    validate_latlon(navaid.latitude, navaid.longitude)
    if not navaid.name.strip():
        raise ValidationError("Name is required.")
    if isinstance(navaid, Ndb):
        _validate_ndb_freq(navaid.frequency_khz)
    elif isinstance(navaid, Vor):
        _validate_vhf_nav_freq(navaid.frequency_mhz, "VOR")
        _validate_slaved_variation(navaid.slaved_variation_deg)
    elif isinstance(navaid, Dme):
        _validate_vhf_nav_freq(navaid.paired_frequency_mhz, "DME paired")
    _validate_range(navaid.range_nm)


def _validate_navaid_ident(ident: str) -> str:
    ident = ident.strip().upper()
    if not ident:
        raise ValidationError("Identifier is required.")
    if len(ident) > 4:
        raise ValidationError("Identifier must be 4 characters or fewer.")
    if not ident.isalnum():
        raise ValidationError("Identifier must contain only letters and digits.")
    return ident


def _validate_vhf_nav_freq(frequency_mhz: float, label: str) -> None:
    if not (_VHF_NAV_FREQ_MIN_MHZ <= frequency_mhz <= _VHF_NAV_FREQ_MAX_MHZ):
        raise ValidationError(
            f"{label} frequency should be between {_VHF_NAV_FREQ_MIN_MHZ:.2f} and "
            f"{_VHF_NAV_FREQ_MAX_MHZ:.2f} MHz."
        )


def _validate_ndb_freq(frequency_khz: int) -> None:
    if not (_NDB_FREQ_MIN_KHZ <= frequency_khz <= _NDB_FREQ_MAX_KHZ):
        raise ValidationError(
            f"NDB frequency should be between {_NDB_FREQ_MIN_KHZ} and "
            f"{_NDB_FREQ_MAX_KHZ} kHz."
        )


def _validate_slaved_variation(slaved_variation_deg: float) -> None:
    if not (-180.0 <= slaved_variation_deg <= 180.0):
        raise ValidationError("Slaved variation must be between -180 and 180 degrees.")


def _validate_range(range_nm: int) -> None:
    if range_nm < 1:
        raise ValidationError("Range must be at least 1 nm.")


def _ensure_suffix(name: str, suffix: str) -> str:
    name = name.strip()
    if not name:
        raise ValidationError("Name is required.")
    if not name.upper().endswith(suffix):
        name = f"{name} {suffix}"
    return name
