"""Best-effort detection of a FlightGear installation on macOS.

Read-only: this module never opens any FlightGear file for writing and
never modifies FlightGear's own configuration.

Layout verified against a real FlightGear 2024.1.6 installation
(official flightgear.org .app bundle) during integration testing:
  - the app bundle's main executable is named "FlightGear", not "fgfs"
    (that name is used by other build variants, e.g. Linux/Homebrew,
    kept as a fallback)
  - the bundle does NOT carry FG_ROOT inside Contents/Resources/data;
    fgdata is downloaded on first run to
    ~/Library/Application Support/FlightGear/fgdata_<version>/
  - FG_HOME is nested under the same parent, at
    ~/Library/Application Support/FlightGear/flightgear.org/
    (not directly under "Application Support")
The older bundle-relative FG_ROOT layout is kept as a fallback in case
a different packaging (e.g. a self-contained build) is encountered.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FlightGearInstallation:
    app_bundle: Path | None
    fgfs_binary: Path | None
    fg_root: Path | None
    fg_home: Path | None
    version: str | None

    @property
    def found(self) -> bool:
        return self.app_bundle is not None or self.fgfs_binary is not None


def detect() -> FlightGearInstallation:
    app_bundle = _find_app_bundle()
    fgfs_binary = _find_fgfs_binary(app_bundle)
    fg_root = _find_fg_root(app_bundle)
    fg_home = _find_fg_home()
    version = _read_version(fg_root)
    return FlightGearInstallation(
        app_bundle=app_bundle, fgfs_binary=fgfs_binary, fg_root=fg_root, fg_home=fg_home,
        version=version,
    )


def _find_app_bundle() -> Path | None:
    candidates = [
        Path("/Applications/FlightGear.app"),
        Path.home() / "Applications" / "FlightGear.app",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _find_fgfs_binary(app_bundle: Path | None) -> Path | None:
    if app_bundle is not None:
        macos_dir = app_bundle / "Contents" / "MacOS"
        for name in ("FlightGear", "fgfs"):
            candidate = macos_dir / name
            if candidate.exists():
                return candidate
    which = shutil.which("fgfs")
    if which:
        return Path(which)
    return None


def _find_fg_root(app_bundle: Path | None) -> Path | None:
    # Current official .app bundles download fgdata into a versioned
    # directory under Application Support on first run.
    support_dir = Path.home() / "Library" / "Application Support" / "FlightGear"
    if support_dir.is_dir():
        for candidate in sorted(support_dir.glob("fgdata_*")):
            if (candidate / "version").exists():
                return candidate

    # Fallback: older/alternative packaging with FG_ROOT bundled inside
    # the .app itself.
    if app_bundle is not None:
        candidate = app_bundle / "Contents" / "Resources" / "data"
        if candidate.exists() and (candidate / "version").exists():
            return candidate

    return None


def _read_version(fg_root: Path | None) -> str | None:
    # FG_ROOT/version is a plain text file containing e.g. "2024.1.6"
    # (confirmed against a real installation during integration testing).
    if fg_root is None:
        return None
    version_file = fg_root / "version"
    if not version_file.is_file():
        return None
    try:
        return version_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _find_fg_home() -> Path | None:
    candidates = [
        Path.home() / "Library" / "Application Support" / "FlightGear" / "flightgear.org",
        Path.home() / "Library" / "Application Support" / "flightgear.org",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
