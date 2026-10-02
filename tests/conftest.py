"""Session-wide safety net: no test may ever touch the user's real app
data (database or custom scenery output).

Every path in infrastructure.config is redirected to a throwaway folder
at import time -- before any test or fixture runs -- so even a
monkeypatch.undo() that reverts a fixture's own redirect falls back to
the throwaway folder, never to ~/Library/Application Support. As a
second line of defence the session fails if the real output files
change while the tests run.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from flightgear_navdata_manager.infrastructure import config

_REAL_FILES = [config.DB_PATH, config.FIX_DAT_OUTPUT, config.NAV_DAT_OUTPUT]

_SANDBOX = Path(tempfile.mkdtemp(prefix="fgnav_tests_"))
config.APP_SUPPORT_DIR = _SANDBOX
config.DB_PATH = _SANDBOX / "navdata.sqlite"
config.CUSTOM_SCENERY_DIR = _SANDBOX / "CustomScenery"
config.FIX_DAT_OUTPUT = config.CUSTOM_SCENERY_DIR / "NavData" / "fix" / "custom.dat"
config.NAV_DAT_OUTPUT = config.CUSTOM_SCENERY_DIR / "NavData" / "nav" / "custom.dat"


def _fingerprint(path: Path):
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return st.st_mtime_ns, st.st_size


@pytest.fixture(scope="session", autouse=True)
def real_app_data_is_never_touched():
    before = {p: _fingerprint(p) for p in _REAL_FILES}
    yield
    shutil.rmtree(_SANDBOX, ignore_errors=True)
    changed = [str(p) for p in _REAL_FILES if _fingerprint(p) != before[p]]
    assert not changed, f"tests modified the user's real app data: {changed}"
