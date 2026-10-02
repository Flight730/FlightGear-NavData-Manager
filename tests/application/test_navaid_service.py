import pytest

from flightgear_navdata_manager.domain.exceptions import ValidationError
from flightgear_navdata_manager.application.navaid_service import build_ndb, build_vor
from flightgear_navdata_manager.infrastructure import config


def test_create_ndb_writes_expected_810_record(app_env):
    ns = app_env["navaid_service"]
    ndb = ns.create_ndb("tsta", "Test Station", 40.71279000, -74.00595000, 150, 362, 50)

    assert ndb.ident == "TSTA"
    assert ndb.name == "Test Station NDB"  # auto-suffixed

    exported = config.NAV_DAT_OUTPUT.read_text()
    assert "2 40.71279000 -74.00595000 150 362 50 0.0 TSTA Test Station NDB" in exported


def test_create_vor_encodes_frequency_x100(app_env):
    ns = app_env["navaid_service"]
    vor = ns.create_vor("tstv", "Test Station", 40.0, -74.0, 210, 116.80, 130, 19.0)
    assert vor.frequency_mhz == 116.80

    exported = config.NAV_DAT_OUTPUT.read_text()
    assert " 11680 " in exported


def test_create_dme_uses_row_13(app_env):
    ns = app_env["navaid_service"]
    ns.create_dme("tstd", "Test Station", 40.0, -74.0, 210, 116.80, 25)
    exported = config.NAV_DAT_OUTPUT.read_text()
    assert exported.splitlines()[2].startswith("13 ")


def test_ndb_ident_over_4_chars_rejected(app_env):
    ns = app_env["navaid_service"]
    with pytest.raises(ValidationError):
        ns.create_ndb("TOOLONG", "Name", 0.0, 0.0, 0, 400, 50)


def test_vor_frequency_out_of_band_rejected(app_env):
    ns = app_env["navaid_service"]
    with pytest.raises(ValidationError):
        ns.create_vor("TSTV", "Name", 0.0, 0.0, 0, 50.0, 100)


def test_ndb_frequency_out_of_band_rejected(app_env):
    ns = app_env["navaid_service"]
    with pytest.raises(ValidationError):
        ns.create_ndb("TSTA", "Name", 0.0, 0.0, 0, 5000, 50)


def test_find_duplicates_scoped_by_type(app_env):
    ns = app_env["navaid_service"]
    ns.create_ndb("DUP1", "Name", 40.0, -74.0, 0, 362, 50)
    # Same ident, different type (VOR) at the same location -- must NOT
    # be reported as a duplicate of the NDB.
    assert ns.find_duplicates(build_vor("DUP1", "Name", 40.0, -74.0, 0, 110.0, 100)) == []
    [ndb_dupe] = ns.find_duplicates(build_ndb("DUP1", "Name", 40.001, -74.0, 0, 362, 50))
    assert ndb_dupe.is_duplicate


def test_disable_and_delete_regenerate_export(app_env):
    ns = app_env["navaid_service"]
    vor = ns.create_vor("TSTV", "Name", 0.0, 0.0, 0, 110.0, 100)
    assert "TSTV" in config.NAV_DAT_OUTPUT.read_text()

    ns.set_enabled(vor.id, False)
    assert "TSTV" not in config.NAV_DAT_OUTPUT.read_text()

    ns.set_enabled(vor.id, True)
    ns.delete(vor.id)
    assert "TSTV" not in config.NAV_DAT_OUTPUT.read_text()
    assert ns.list_all() == []
