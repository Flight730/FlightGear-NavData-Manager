from dataclasses import dataclass

from flightgear_navdata_manager.domain.duplicates import nearby_duplicates


@dataclass
class P:
    ident: str
    latitude: float
    longitude: float


def test_same_ident_within_radius_is_duplicate():
    records = [P("ABC", 40.0, -75.0)]
    assert nearby_duplicates(records, " abc ", 40.1, -75.0, 10.0) == records  # ~6 nm


def test_same_ident_outside_radius_is_not_duplicate():
    assert nearby_duplicates([P("ABC", 40.0, -75.0)], "ABC", 41.0, -75.0, 10.0) == []  # ~60 nm


def test_different_ident_is_not_duplicate():
    assert nearby_duplicates([P("ABC", 40.0, -75.0)], "ABD", 40.0, -75.0, 10.0) == []
