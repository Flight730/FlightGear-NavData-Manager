"""Verifies the Add Waypoint / Add NAV forms actually create records
when driven like a real user would (typing into fields, clicking
Create), and that the status label added during the usability review
reflects what happened.
"""

from PySide6.QtWidgets import QMessageBox

from flightgear_navdata_manager.presentation.views.add_fix_form import AddFixForm
from flightgear_navdata_manager.presentation.views import duplicate_prompt
from flightgear_navdata_manager.presentation.views.add_nav_form import AddNavForm


def test_add_fix_form_creates_record_and_shows_status(gui_env):
    called = []
    form = AddFixForm(gui_env["waypoint_service"], on_created=lambda: called.append(True))

    form._ident_edit.setText("gwtst")
    form._lat_spin.setValue(10.0)
    form._lon_spin.setValue(20.0)
    form._on_submit()

    assert called == [True]
    assert "GWTST" in form._status_label.text()
    created = gui_env["waypoint_service"].list_all()
    assert len(created) == 1
    assert created[0].ident == "GWTST"
    # Fields reset after a successful create.
    assert form._ident_edit.text() == ""


def test_add_fix_form_shows_inline_error_on_invalid_input(gui_env):
    # Validation errors are shown in the form's inline banner, not a pop-up
    # (an unexpected pop-up fails the test via the autouse modal guard).
    form = AddFixForm(gui_env["waypoint_service"])
    form._ident_edit.setText("")  # empty ident is invalid
    form._on_submit()

    assert not form._error_banner.isHidden()
    assert form._error_banner.tone() == "danger"
    assert form._error_banner.text_label.text() == "Identifier is required."
    assert gui_env["waypoint_service"].list_all() == []


def test_add_nav_form_creates_ndb_and_shows_status(gui_env):
    called = []
    form = AddNavForm(gui_env["navaid_service"], on_created=lambda: called.append(True))

    form._type_combo.setCurrentIndex(0)  # NDB
    form._ident_edit.setText("gwnd")
    form._name_edit.setText("Test")
    form._lat_spin.setValue(10.0)
    form._lon_spin.setValue(20.0)
    form._elev_spin.setValue(100)
    form._ndb_freq_khz.setValue(375)
    form._ndb_range_nm.setValue(50)
    form._on_submit()

    assert called == [True]
    assert "NDB GWND" in form._status_label.text()
    created = gui_env["navaid_service"].list_all()
    assert len(created) == 1
    assert created[0].ident == "GWND"


def test_add_nav_form_duplicate_prompt_declined_skips_creation(gui_env, monkeypatch):
    ns = gui_env["navaid_service"]
    ns.create_ndb("DUP1", "Existing", 10.0, 20.0, 0, 375, 50)

    asked = []
    monkeypatch.setattr(
        duplicate_prompt, "confirm_despite_duplicates",
        lambda parent, candidate, matches: (asked.append(matches), False)[1],
    )
    form = AddNavForm(ns)
    form._type_combo.setCurrentIndex(0)
    form._ident_edit.setText("dup1")
    form._name_edit.setText("Test")
    form._lat_spin.setValue(10.001)  # ~0.06 nm from the existing DUP1, same frequency
    form._lon_spin.setValue(20.0)
    form._ndb_freq_khz.setValue(375)
    form._ndb_range_nm.setValue(50)
    form._on_submit()

    assert len(ns.list_all()) == 1  # unchanged -- second creation was declined
    assert asked[0][0].record.ident == "DUP1"
