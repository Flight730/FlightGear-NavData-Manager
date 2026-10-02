"""Validation shared by WaypointService and NavaidService.

Extracted because both services previously defined an identical
`_validate_latlon` helper independently.
"""

from __future__ import annotations

from .exceptions import ValidationError


def validate_latlon(latitude: float, longitude: float) -> None:
    if not (-90.0 <= latitude <= 90.0):
        raise ValidationError("Latitude must be between -90 and 90.")
    if not (-180.0 <= longitude <= 180.0):
        raise ValidationError("Longitude must be between -180 and 180.")
