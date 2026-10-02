"""Manual creation: the duplicate warning names the matching record,
defaults to Cancel, and only "Add Anyway" creates the record."""

from PySide6.QtWidgets import QMessageBox

from flightgear_navdata_manager.application.waypoint_service import build_fix
from flightgear_navdata_manager.presentation.views import duplicate_prompt
from flightgear_navdata_manager.presentation.views.add_fix_form import AddFixForm
from flightgear_navdata_manager.presentation.views.add_nav_form import AddNavForm


def _fill_fix(form, ident, lat, lon):
    form._ident_edit.setText(ident)
    form._lat_spin.setValue(lat)
    form._lon_spin.setValue(lon)


def test_dialog_names_the_existing_record_and_defaults_to_cancel(gui_env):
    ws = gui_env["waypoint_service"]
    ws.create("EBAYE", 37.621, -122.379)
    candidate = build_fix("EBAYE", 37.621, -122.379)
    box, add_button = duplicate_prompt.build_duplicate_dialog(None, candidate, ws.find_duplicates(candidate))

    assert box.text() == "FIX EBAYE already exists."
    assert "Exact duplicate: FIX EBAYE (custom) at 37.621000, -122.379000 -- 0.0 nm away" in box.informativeText()
    assert add_button.text() == "Add Anyway"
    assert box.defaultButton() is box.button(QMessageBox.StandardButton.Cancel)
    assert box.escapeButton() is box.button(QMessageBox.StandardButton.Cancel)


def test_dialog_for_a_conflict_says_so(gui_env):
    ws = gui_env["waypoint_service"]
    ws.create("EBAYE", 37.621, -122.379)
    candidate = build_fix("EBAYE", 37.9, -122.379)                     # ~17 nm away
    box, _ = duplicate_prompt.build_duplicate_dialog(None, candidate, ws.find_duplicates(candidate))
    assert box.text() == "Another FIX named EBAYE is nearby."
    assert "Identifier conflict: FIX EBAYE (custom)" in box.informativeText()


def test_manual_fix_duplicate_is_warned_and_cancel_creates_nothing(gui_env, monkeypatch):
    ws = gui_env["waypoint_service"]
    ws.create("EBAYE", 37.621, -122.379)
    seen = []
    monkeypatch.setattr(duplicate_prompt, "confirm_despite_duplicates",
                        lambda parent, candidate, matches: (seen.append(matches), False)[1])
    form = AddFixForm(ws)
    _fill_fix(form, "ebaye", 37.621, -122.379)
    form._on_submit()

    assert seen[0][0].record.ident == "EBAYE"
    assert len(ws.list_all()) == 1
    assert form._status_label.text() == ""
    assert form._ident_edit.text() == "ebaye"      # the user's input is kept


def test_manual_duplicate_add_anyway_creates_it(gui_env, monkeypatch):
    ws = gui_env["waypoint_service"]
    ws.create("EBAYE", 37.621, -122.379)
    monkeypatch.setattr(duplicate_prompt, "confirm_despite_duplicates", lambda *a: True)
    form = AddFixForm(ws)
    _fill_fix(form, "EBAYE", 37.621, -122.379)
    form._on_submit()
    assert len(ws.list_all()) == 2


def test_no_prompt_without_duplicates(gui_env, monkeypatch):
    ws = gui_env["waypoint_service"]
    ws.create("EBAYE", 37.621, -122.379)
    monkeypatch.setattr(duplicate_prompt, "confirm_despite_duplicates",
                        lambda *a: (_ for _ in ()).throw(AssertionError("should not ask")))
    form = AddFixForm(ws)
    _fill_fix(form, "EBAYE", 10.0, 10.0)                                # far away: a different fix
    form._on_submit()
    assert len(ws.list_all()) == 2


def test_manual_navaid_same_ident_different_type_is_not_a_duplicate(gui_env, monkeypatch):
    ns = gui_env["navaid_service"]
    ns.create_vor("XYZ", "Example", 37.6, -122.4, 100, 113.2, 130)
    monkeypatch.setattr(duplicate_prompt, "confirm_despite_duplicates",
                        lambda *a: (_ for _ in ()).throw(AssertionError("should not ask")))
    form = AddNavForm(ns)
    form._type_combo.setCurrentIndex(2)  # DME
    form._ident_edit.setText("XYZ")
    form._name_edit.setText("Example")
    form._lat_spin.setValue(37.6)
    form._lon_spin.setValue(-122.4)
    form._dme_freq_mhz.setValue(113.2)
    form._on_submit()
    assert {n.type.value for n in ns.list_all()} == {"VOR", "DME"}


def test_invalid_input_is_reported_before_any_duplicate_check(gui_env, monkeypatch):
    monkeypatch.setattr(duplicate_prompt, "confirm_despite_duplicates",
                        lambda *a: (_ for _ in ()).throw(AssertionError("should not ask")))
    form = AddFixForm(gui_env["waypoint_service"])
    _fill_fix(form, "", 1.0, 1.0)
    form._on_submit()
    assert form._error_banner.text_label.text() == "Identifier is required."
