"""Test-only runtime overrides used to validate the packaged app against
throwaway data. Run in subprocesses so the session's path guard
(tests/conftest.py) is never touched."""

import os
import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")


def _run(code: str, **env) -> subprocess.CompletedProcess:
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("FGNAV_")}
    full_env.update(env, PYTHONPATH=SRC, QT_QPA_PLATFORM="offscreen")
    return subprocess.run([sys.executable, "-c", code], env=full_env, capture_output=True, text=True, timeout=60)


def test_data_dir_override_moves_every_path(tmp_path):
    out = _run("from flightgear_navdata_manager.infrastructure import config as c;"
               "print(c.APP_SUPPORT_DIR, c.DB_PATH, c.FIX_DAT_OUTPUT, c.NAV_DAT_OUTPUT, sep='|')",
               FGNAV_DATA_DIR=str(tmp_path))
    paths = out.stdout.strip().split("|")
    assert len(paths) == 4 and all(p.startswith(str(tmp_path)) for p in paths), out


def test_default_location_without_override():
    out = _run("from flightgear_navdata_manager.infrastructure import config as c; print(c.APP_SUPPORT_DIR)")
    assert out.stdout.strip() == str(Path.home() / "Library" / "Application Support" / "FlightGearNavDataManager")


def test_smoke_mode_refuses_to_run_without_a_throwaway_data_dir(tmp_path):
    out = _run("import sys; from flightgear_navdata_manager.app import main; sys.exit(main())",
               FGNAV_SMOKE_OUT=str(tmp_path / "out"))
    assert out.returncode == 2 and "requires FGNAV_DATA_DIR" in out.stderr
    assert not (tmp_path / "out").exists()
