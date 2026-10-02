"""Regenerates the custom NavData output files from currently-enabled
records.

Never touches FlightGear's own files. Always writes the full set of
currently-enabled custom + imported records -- never a copy of
FlightGear's stock database (custom-only export, per project spec).
"""

from __future__ import annotations

from datetime import datetime

from flightgear_navdata_manager.infrastructure import config
from flightgear_navdata_manager.infrastructure.storage.fix_repository import FixRepository
from flightgear_navdata_manager.infrastructure.storage.navaid_repository import (
    NavaidRepository,
)
from flightgear_navdata_manager.infrastructure.writers.fix_dat_writer import write_fix_dat
from flightgear_navdata_manager.infrastructure.writers.nav_dat_writer import write_nav_dat


class ExportService:
    def __init__(self, fix_repo: FixRepository, navaid_repo: NavaidRepository):
        self._fix_repo = fix_repo
        self._navaid_repo = navaid_repo
        # The exception from the most recent regenerate() if it failed,
        # else None. Exceptions still propagate to the caller.
        self.last_error: Exception | None = None

    def regenerate(self) -> None:
        try:
            config.ensure_dirs()
            fixes = self._fix_repo.list_enabled()
            navaids = self._navaid_repo.list_enabled()
            write_fix_dat(fixes, str(config.FIX_DAT_OUTPUT))
            write_nav_dat(navaids, str(config.NAV_DAT_OUTPUT))
        except Exception as exc:
            self.last_error = exc
            raise
        self.last_error = None

    def last_written(self) -> datetime | None:
        """When the output files were last written (the newer of the two),
        or None if neither exists yet. Only stats this app's own files."""
        times = [
            path.stat().st_mtime
            for path in (config.FIX_DAT_OUTPUT, config.NAV_DAT_OUTPUT)
            if path.exists()
        ]
        return datetime.fromtimestamp(max(times)) if times else None
