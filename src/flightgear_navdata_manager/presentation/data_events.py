"""App-wide notification that the user's data or its export changed.

Views keep reporting changes through their existing callbacks
(on_created, on_imported, on_changed, on_regenerated); MainWindow turns
those into DataEvents.changed so every interested part of the UI (the
record list, the sidebar count, the dashboard) can update without the
views knowing about each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, Signal


class ChangeKind(Enum):
    RECORD_ADDED = "record_added"          # Add Waypoint / Add Navaid
    RECORDS_IMPORTED = "records_imported"  # any import
    RECORD_TOGGLED = "record_toggled"      # Manage Data: Enabled
    RECORD_DELETED = "record_deleted"      # Manage Data: Delete
    EXPORT_REGENERATED = "export_regenerated"  # Dashboard: Regenerate now

    @property
    def changes_records(self) -> bool:
        return self is not ChangeKind.EXPORT_REGENERATED


@dataclass(frozen=True)
class DataChange:
    kind: ChangeKind
    source: object | None = None   # the view that made the change


class DataEvents(QObject):
    changed = Signal(object)   # DataChange

    def notify(self, kind: ChangeKind, source: object | None = None) -> None:
        self.changed.emit(DataChange(kind, source))
