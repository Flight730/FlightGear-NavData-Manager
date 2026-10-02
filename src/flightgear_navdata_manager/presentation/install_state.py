"""The FlightGear installation as detected at startup, shared by every
view that shows it (sidebar footer, Dashboard).

Detection runs once when this is created and again only on rescan().
It is read-only: nothing here changes FlightGear's files or settings.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from flightgear_navdata_manager.application.install_detection import InstallDetectionService
from flightgear_navdata_manager.infrastructure.fg_detect.macos_locator import FlightGearInstallation


class InstallationState(QObject):
    changed = Signal(object)   # FlightGearInstallation

    def __init__(self, install_service: InstallDetectionService, parent: QObject | None = None):
        super().__init__(parent)
        self._service = install_service
        self._installation = install_service.detect()

    @property
    def installation(self) -> FlightGearInstallation:
        return self._installation

    def rescan(self) -> FlightGearInstallation:
        self._installation = self._service.detect()
        self.changed.emit(self._installation)
        return self._installation
