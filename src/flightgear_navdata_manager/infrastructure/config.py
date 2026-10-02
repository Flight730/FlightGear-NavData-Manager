"""Application data-directory locations.

CUSTOM_SCENERY_DIR is the folder the user adds to FlightGear's own
scenery path list (Launcher "Additional Scenery Paths" or
--fg-scenery). This application never modifies FlightGear's own
configuration to do that automatically -- see project spec.
"""

from __future__ import annotations

import os
from pathlib import Path

# FGNAV_DATA_DIR relocates all of this app's data (database and scenery
# output) -- used to test the packaged app against throwaway data. Unset,
# the normal per-user location is used.
APP_SUPPORT_DIR = (
    Path(os.environ["FGNAV_DATA_DIR"]) if os.environ.get("FGNAV_DATA_DIR")
    else Path.home() / "Library" / "Application Support" / "FlightGearNavDataManager"
)
DB_PATH = APP_SUPPORT_DIR / "navdata.sqlite"
CUSTOM_SCENERY_DIR = APP_SUPPORT_DIR / "CustomScenery"
FIX_DAT_OUTPUT = CUSTOM_SCENERY_DIR / "NavData" / "fix" / "custom.dat"
NAV_DAT_OUTPUT = CUSTOM_SCENERY_DIR / "NavData" / "nav" / "custom.dat"


def ensure_dirs() -> None:
    FIX_DAT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    NAV_DAT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
