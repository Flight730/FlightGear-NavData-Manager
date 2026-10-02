"""Use case wrapper around FlightGear installation detection."""

from __future__ import annotations

from flightgear_navdata_manager.infrastructure.fg_detect.macos_locator import (
    FlightGearInstallation,
    detect,
)


class InstallDetectionService:
    def detect(self) -> FlightGearInstallation:
        return detect()
