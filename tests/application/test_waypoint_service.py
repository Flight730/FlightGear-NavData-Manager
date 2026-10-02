import pytest

from flightgear_navdata_manager.application.duplicate_policy import MatchKind
from flightgear_navdata_manager.application.waypoint_service import build_fix
from flightgear_navdata_manager.domain.exceptions import ValidationError
from flightgear_navdata_manager.infrastructure import config


def test_create_writes_enabled_fix_and_regenerates_export(app_env):
    ws = app_env["waypoint_service"]
    fix = ws.create("wayp1", 40.71279000, -74.00595000)

    assert fix.id is not None
    assert fix.ident == "WAYP1"  # auto-uppercased
    assert fix.enabled is True

    exported = config.FIX_DAT_OUTPUT.read_text()
    assert "40.71279000 -74.00595000 WAYP1" in exported


def test_rejects_invalid_latitude(app_env):
    ws = app_env["waypoint_service"]
    with pytest.raises(ValidationError):
        ws.create("BADLAT", 200.0, 0.0)


def test_rejects_non_alphanumeric_identifier(app_env):
    ws = app_env["waypoint_service"]
    with pytest.raises(ValidationError):
        ws.create("BAD-ID", 0.0, 0.0)


def test_find_duplicates_nearby_and_far(app_env):
    ws = app_env["waypoint_service"]
    ws.create("DUPE1", 40.0, -74.0)
    # ~0.6 nm away -- the same point
    [nearby] = ws.find_duplicates(build_fix("DUPE1", 40.01, -74.0))
    assert nearby.kind is MatchKind.NEARBY
    # Far away -- not a duplicate.
    assert ws.find_duplicates(build_fix("DUPE1", -40.0, 74.0)) == []


def test_disable_removes_record_from_export(app_env):
    ws = app_env["waypoint_service"]
    fix = ws.create("TOGGLE", 1.0, 1.0)
    assert "TOGGLE" in config.FIX_DAT_OUTPUT.read_text()

    ws.set_enabled(fix.id, False)
    assert "TOGGLE" not in config.FIX_DAT_OUTPUT.read_text()


def test_delete_removes_record_entirely(app_env):
    ws = app_env["waypoint_service"]
    fix = ws.create("GONE1", 1.0, 1.0)
    ws.delete(fix.id)
    assert ws.list_all() == []
    assert "GONE1" not in config.FIX_DAT_OUTPUT.read_text()
