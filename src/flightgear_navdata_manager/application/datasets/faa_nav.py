"""FAA NASR NAV data (NAV.txt or NAV_BASE.csv) -> domain records.

Facility type mapping (FAA NAV1 "NAVAID FACILITY TYPE"):

  NDB, MARINE NDB  -> Ndb
  VOR              -> Vor
  VOR/DME, VORTAC  -> Vor + Dme   (as FlightGear/X-Plane data models them)
  NDB/DME          -> Ndb + Dme
  DME, TACAN       -> Dme         (TACAN's distance function is what civil
                                   receivers use; its azimuth isn't modeled)
  VOT, FAN MARKER, CONSOLAN, UHF/NDB, anything else -> unsupported

Only facilities whose status starts with "OPERATIONAL" are imported;
DECOMMISSIONED / SHUTDOWN / blank are reported as unsupported.

Field mapping:

  ident             <- official facility identifier (TXT col 29 / CSV NAV_ID)
  name              <- facility name + facility type, e.g. "TESTER VORTAC";
                       the DME half of a composite gets " DME" appended
  latitude/longitude<- FAA position (see the parsers). The DME
                       half of a composite uses the separate TACAN/DME
                       antenna position when FAA gives one.
  elevation_ft      <- elevation, rounded to whole feet
  NDB frequency_khz <- frequency (must be a whole number of kHz)
  VOR frequency_mhz <- frequency
  VOR slaved_variation_deg <- magnetic variation (E positive, W negative)
  DME paired_frequency_mhz <- frequency for DME/TACAN/VOR-DME/VORTAC; for
                       NDB/DME (whose frequency is the NDB's kHz) and any
                       DME lacking a frequency, derived from the TACAN
                       channel via the ICAO pairing table
  range_nm          <- derived from FAA's own published service volumes,
                       see _SERVICE_VOLUME_NM / _ndb_range_nm
  DME bias_nm       <- not in source; 0.0 (the model default, and correct
                       for enroute DMEs)

Not mapped (no place in the domain model): city, state, country, FAA
region, owner/operator, class, hours, ARTCC, survey accuracy, mag-var
epoch year, voice/power/monitoring features, FSS/NOTAM data, status
detail, remarks (NAV2), associated fix names (NAV3), holding patterns
(NAV4), fan markers (NAV5), checkpoints (NAV6) -- and their CSV
equivalents NAV_RMK / NAV_CKPT.

Required values that are missing are never invented: the component is
reported as invalid with a reason instead (e.g. an NDB without elevation, a DME on
a channel with no paired VHF frequency).
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from flightgear_navdata_manager.domain.dme_channels import paired_vhf_mhz
from flightgear_navdata_manager.domain.models import DataSource, Dme, Ndb, Vor
from flightgear_navdata_manager.infrastructure.parsers.faa_common import (
    FaaNavaidRecord,
    FaaParseResult,
    SourceFile,
)

from typing import Callable

from .base import NAV, DatasetReadResult, ImportCandidate, RecordIssue

_COMPONENTS: dict[str, tuple[str, ...]] = {
    "NDB": ("NDB",),
    "MARINE NDB": ("NDB",),
    "VOR": ("VOR",),
    "VOR/DME": ("VOR", "DME"),
    "VORTAC": ("VOR", "DME"),
    "NDB/DME": ("NDB", "DME"),
    "DME": ("DME",),
    "TACAN": ("DME",),
}

# Maximum distance of each FAA standard service volume (nav_rf.txt, N29
# and NA). The one-letter codes double as the NAV1 class altitude code
# (H/L/T), used when a facility has no explicit service volume.
_SERVICE_VOLUME_NM = {"T": 25, "L": 40, "H": 130, "VL": 70, "VH": 130, "DL": 130, "DH": 130}

# NDB class codes with a published range (nav_rf.txt, N28).
_NDB_CLASS_NM = {"HH": 75, "MH": 25, "H": 50, "LOM": 15, "LMM": 15}

_DETAIL_ROW_DESCRIPTIONS = {
    "NAV2": "remarks",
    "NAV3": "associated fix names (positions come from the FIX dataset)",
    "NAV4": "holding patterns",
    "NAV5": "fan markers",
    "NAV6": "VOR checkpoints",
}


class FaaNavReader:
    """FAA NAV data from either NAV.txt or NAV_BASE.csv -- both parsers
    produce FaaNavaidRecord, so the mapping below is shared."""

    category = NAV

    def __init__(self, description: str, parse: Callable[[SourceFile], FaaParseResult]):
        self.description = description
        self._parse = parse

    def read(self, source: SourceFile) -> DatasetReadResult:
        parsed = self._parse(source)
        result = DatasetReadResult(records_read=Counter({NAV: parsed.rows_read}))
        for issue in parsed.issues:
            result.invalid.append(
                RecordIssue(issue.line_number, issue.label, issue.reason, NAV, source.name)
            )

        now = datetime.now(timezone.utc)
        for record in parsed.records:
            if record.effective_date:
                result.effective_dates.add(record.effective_date)
            _map_facility(record, source, now, result)

        if parsed.detail_rows:
            detail = ", ".join(
                f"{count} {_DETAIL_ROW_DESCRIPTIONS[row]}"
                for row, count in sorted(parsed.detail_rows.items())
            )
            result.notes.append(
                f"{source.name}: {sum(parsed.detail_rows.values())} supplementary rows have no "
                f"equivalent in this app: {detail}."
            )
        return result


def _map_facility(
    record: FaaNavaidRecord, source: SourceFile, now: datetime, result: DatasetReadResult
) -> None:
    components = _COMPONENTS.get(record.facility_type)
    if components is None:
        result.unsupported.append(
            _issue(record, source, f"{record.facility_type or 'unknown'} facilities are not supported")
        )
        return
    if not record.status.startswith("OPERATIONAL"):
        status = record.status.lower() if record.status else "no status given"
        result.unsupported.append(_issue(record, source, f"not operational ({status})"))
        return

    for component in components:
        is_composite_dme = component == "DME" and len(components) > 1
        label = f"{record.label} DME part" if is_composite_dme else record.label
        try:
            navaid = _build(component, record, source.display, now)
        except _Reject as exc:
            result.invalid.append(RecordIssue(record.line_number, label, str(exc), NAV, source.name))
            continue
        result.candidates.append(ImportCandidate(navaid, record.line_number, label, source.name))


class _Reject(Exception):
    pass


def _build(component: str, record: FaaNavaidRecord, path: str, now: datetime) -> Ndb | Vor | Dme:
    if not record.ident:
        raise _Reject("no identifier")
    if not record.name:
        raise _Reject("no name")
    if record.elevation_ft is None:
        raise _Reject("no elevation in source")

    common = dict(
        id=None,
        source=DataSource.IMPORTED,
        enabled=True,
        created_at=now,
        ident=record.ident,
        elevation_ft=round(record.elevation_ft),
        origin_file=path,
    )
    base_name = f"{record.name} {record.facility_type}"

    if component == "NDB":
        lat, lon = _position(record, prefer_tacan=False)
        return Ndb(
            name=base_name, latitude=lat, longitude=lon,
            frequency_khz=_ndb_khz(record), range_nm=_ndb_range_nm(record), **common,
        )
    if component == "VOR":
        lat, lon = _position(record, prefer_tacan=False)
        if record.frequency is None:
            raise _Reject("no frequency in source")
        if record.magnetic_variation_deg is None:
            raise _Reject("no magnetic variation in source")
        return Vor(
            name=base_name, latitude=lat, longitude=lon,
            frequency_mhz=record.frequency,
            range_nm=_service_volume_nm(record.vor_service_volume, record),
            slaved_variation_deg=record.magnetic_variation_deg,
            **common,
        )
    # DME
    lat, lon = _position(record, prefer_tacan=True)
    is_composite = len(_COMPONENTS[record.facility_type]) > 1
    return Dme(
        name=f"{base_name} DME" if is_composite else base_name,
        latitude=lat, longitude=lon,
        paired_frequency_mhz=_dme_paired_mhz(record),
        range_nm=_service_volume_nm(record.dme_service_volume, record),
        **common,
    )


def _position(record: FaaNavaidRecord, prefer_tacan: bool) -> tuple[float, float]:
    if prefer_tacan and record.tacan_latitude is not None and record.tacan_longitude is not None:
        return record.tacan_latitude, record.tacan_longitude
    if record.latitude is None or record.longitude is None:
        raise _Reject("no position in source")
    return record.latitude, record.longitude


def _ndb_khz(record: FaaNavaidRecord) -> int:
    if record.frequency is None:
        raise _Reject("no frequency in source")
    if record.frequency != int(record.frequency):
        raise _Reject(f"frequency {record.frequency} kHz is not a whole number of kHz")
    return int(record.frequency)


def _dme_paired_mhz(record: FaaNavaidRecord) -> float:
    paired = paired_vhf_mhz(record.channel) if record.channel else None
    if record.channel and paired is None:
        # Channels 1-16/60-69 are military-only; FAA lists a non-NAV-band
        # pseudo frequency for some of them, which no VHF receiver tunes.
        raise _Reject(f"channel {record.channel} has no paired VHF frequency")
    ndb_based = record.facility_type.startswith(("NDB", "MARINE NDB"))
    if record.frequency is not None and not ndb_based:
        return record.frequency
    if paired is None:
        raise _Reject("no frequency or channel in source")
    return paired


def _service_volume_nm(service_volume: str, record: FaaNavaidRecord) -> int:
    if service_volume in _SERVICE_VOLUME_NM:
        return _SERVICE_VOLUME_NM[service_volume]
    altitude_code = record.navaid_class.split("-", 1)[0] if "-" in record.navaid_class else ""
    if altitude_code in ("H", "L", "T"):
        return _SERVICE_VOLUME_NM[altitude_code]
    raise _Reject(_no_range_reason(record))


def _ndb_range_nm(record: FaaNavaidRecord) -> int:
    ranges = []
    for token in record.navaid_class.replace("-", "/").split("/"):
        for code in ("HH", "MH", "LOM", "LMM", "H"):  # longest/most specific first
            if token.startswith(code):
                ranges.append(_NDB_CLASS_NM[code])
                break
    if not ranges:
        raise _Reject(_no_range_reason(record))
    return max(ranges)


def _no_range_reason(record: FaaNavaidRecord) -> str:
    if not record.navaid_class:
        return "no service volume or class in source, so its range is unknown"
    return f"service range can't be determined (class {record.navaid_class!r})"


def _issue(record: FaaNavaidRecord, source: SourceFile, reason: str) -> RecordIssue:
    return RecordIssue(record.line_number, record.label, reason, NAV, source.name)
