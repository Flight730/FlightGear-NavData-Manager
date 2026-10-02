"""The shared duplicate policy (application/duplicate_policy.py), used
by manual creation and every import."""

import pytest

from flightgear_navdata_manager.application.duplicate_policy import (
    DuplicateIndex,
    MatchKind,
)
from flightgear_navdata_manager.application.navaid_service import build_dme, build_ndb, build_vor
from flightgear_navdata_manager.application.waypoint_service import build_fix


def _stored(record, record_id=1, enabled=True):
    record.id = record_id
    record.enabled = enabled
    return record


def _kinds(index, candidate):
    return [m.kind for m in index.matches(candidate)]


# --- FIX ------------------------------------------------------------------------

def test_exact_fix_duplicate():
    index = DuplicateIndex([_stored(build_fix("ABCDE", 37.5, -122.25))])
    assert _kinds(index, build_fix("abcde", 37.5, -122.25)) == [MatchKind.EXACT]


def test_nearby_fix_duplicate():
    index = DuplicateIndex([_stored(build_fix("ABCDE", 37.5, -122.25))])
    assert _kinds(index, build_fix("ABCDE", 37.505, -122.25)) == [MatchKind.NEARBY]   # 0.3 nm


def test_same_fix_ident_materially_moved_is_a_conflict():
    index = DuplicateIndex([_stored(build_fix("ABCDE", 37.5, -122.25))])
    [match] = index.matches(build_fix("ABCDE", 37.7, -122.25))                        # 12 nm
    assert match.kind is MatchKind.CONFLICT
    assert match.distance_nm == pytest.approx(12.0, abs=0.1)


def test_same_fix_ident_far_away_is_a_different_fix():
    index = DuplicateIndex([_stored(build_fix("ABCDE", 37.5, -122.25))])
    assert index.matches(build_fix("ABCDE", 45.0, -100.0)) == []


def test_different_fix_ident_is_unrelated():
    index = DuplicateIndex([_stored(build_fix("ABCDE", 37.5, -122.25))])
    assert index.matches(build_fix("ABCDF", 37.5, -122.25)) == []


# --- navaids ----------------------------------------------------------------------

def test_exact_ndb_duplicate():
    index = DuplicateIndex([_stored(build_ndb("ABC", "Example", 37.5, -122.3, 50, 375, 50))])
    assert _kinds(index, build_ndb("ABC", "Other name", 37.5, -122.3, 60, 375, 25)) == [MatchKind.EXACT]


def test_same_place_different_frequency_is_a_conflict_not_a_duplicate():
    index = DuplicateIndex([_stored(build_vor("XYZ", "Example", 37.6, -122.4, 100, 113.2, 130))])
    assert _kinds(index, build_vor("XYZ", "Example", 37.6, -122.4, 100, 116.8, 130)) == [MatchKind.CONFLICT]


def test_same_identifier_different_navaid_type_is_unrelated():
    index = DuplicateIndex([
        _stored(build_vor("XYZ", "Example", 37.6, -122.4, 100, 113.2, 130), 1),
        _stored(build_ndb("XYZ", "Example", 37.6, -122.4, 100, 375, 50), 2),
        _stored(build_fix("XYZ", 37.6, -122.4), 3),
    ])
    # Same ident, same place, even the same frequency as the VOR -- but a DME.
    assert index.matches(build_dme("XYZ", "Example", 37.6, -122.4, 100, 113.2, 130)) == []


def test_navaid_conflict_radius_is_smaller_than_fix_radius():
    ndb_index = DuplicateIndex([_stored(build_ndb("ABC", "X", 37.0, -122.0, 0, 375, 50))])
    assert ndb_index.matches(build_ndb("ABC", "X", 38.0, -122.0, 0, 375, 50)) == []    # 60 nm
    fix_index = DuplicateIndex([_stored(build_fix("ABCDE", 37.0, -122.0))])
    assert _kinds(fix_index, build_fix("ABCDE", 38.0, -122.0)) == [MatchKind.CONFLICT]


# --- disabled records ----------------------------------------------------------------

def test_disabled_record_still_counts_as_duplicate():
    index = DuplicateIndex([_stored(build_fix("ABCDE", 37.5, -122.25), enabled=False)])
    [match] = index.matches(build_fix("ABCDE", 37.5, -122.25))
    assert match.is_duplicate
    assert "(custom, disabled)" in match.describe()


def test_disabled_record_never_causes_a_conflict():
    index = DuplicateIndex([_stored(build_fix("ABCDE", 37.5, -122.25), enabled=False)])
    assert index.matches(build_fix("ABCDE", 37.7, -122.25)) == []


def test_duplicates_are_listed_before_conflicts():
    index = DuplicateIndex([
        _stored(build_fix("ABCDE", 37.9, -122.25), 1),
        _stored(build_fix("ABCDE", 37.5, -122.25), 2),
    ])
    matches = index.matches(build_fix("ABCDE", 37.5, -122.25))
    assert [(m.kind, m.record.id) for m in matches] == [(MatchKind.EXACT, 2), (MatchKind.CONFLICT, 1)]


def test_describe_names_the_existing_record():
    index = DuplicateIndex([_stored(build_vor("XYZ", "Example", 37.6, -122.4, 100, 113.2, 130))])
    [match] = index.matches(build_vor("XYZ", "Example", 37.6, -122.4, 100, 113.2, 130))
    assert match.describe() == "VOR XYZ (custom) at 37.600000, -122.400000, 113.20 MHz -- 0.0 nm away"


# --- services use the same policy ------------------------------------------------------

def test_services_find_duplicates_against_stored_records(app_env):
    ws, ns = app_env["waypoint_service"], app_env["navaid_service"]
    ws.create("EBAYE", 37.621, -122.379)
    ns.create_ndb("ABC", "Example", 37.5, -122.3, 50, 375, 50)
    assert [m.kind for m in ws.find_duplicates(build_fix("EBAYE", 37.621, -122.379))] == [MatchKind.EXACT]
    assert [m.kind for m in ns.find_duplicates(build_ndb("ABC", "Example", 37.5, -122.3, 50, 375, 50))] == [
        MatchKind.EXACT
    ]
    assert ns.find_duplicates(build_vor("ABC", "Example", 37.5, -122.3, 50, 113.2, 130)) == []
