"""Step 4 form rebuild: inline validation, the NDB | VOR | DME segmented
control, all three navaid types end to end, unchanged field
ranges/defaults, duplicates, DataEvents and fit at minimum window size."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractSpinBox, QLabel, QScrollArea

from flightgear_navdata_manager.presentation.components.segmented import SegmentedControl
from flightgear_navdata_manager.presentation.data_events import ChangeKind
from flightgear_navdata_manager.presentation.main_window import ADD_NAVAID, ADD_WAYPOINT, MANAGE_DATA
from flightgear_navdata_manager.presentation.views import duplicate_prompt
from flightgear_navdata_manager.presentation.views.add_fix_form import AddFixForm
from flightgear_navdata_manager.presentation.views.add_nav_form import AddNavForm


def _texts(widget):
    return [label.text() for label in widget.findChildren(QLabel)]


def _fill_navaid(form, index, ident="FRM", name="Form"):
    form._type_combo.setCurrentIndex(index)
    form._ident_edit.setText(ident)
    form._name_edit.setText(name)
    form._lat_spin.setValue(12.5)
    form._lon_spin.setValue(-45.25)
    form._elev_spin.setValue(320)


# -- Add Waypoint ---------------------------------------------------------------

def test_waypoint_form_fields_and_helpers(gui_env):
    form = AddFixForm(gui_env["waypoint_service"])
    assert form._ident_edit.maxLength() == 10
    for spin in (form._lat_spin, form._lon_spin):
        assert spin.decimals() == 8
        assert spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
    assert (form._lat_spin.minimum(), form._lat_spin.maximum()) == (-90.0, 90.0)
    assert (form._lon_spin.minimum(), form._lon_spin.maximum()) == (-180.0, 180.0)
    texts = _texts(form)
    assert "Up to 10 characters" in texts
    assert "Decimal degrees · south/west negative" in texts
    assert form._create_btn.property("variant") == "primary"


def test_waypoint_error_banner_clears_when_the_user_edits(gui_env):
    form = AddFixForm(gui_env["waypoint_service"])
    form._on_submit()
    assert form._error_banner.text_label.text() == "Identifier is required."
    QTest.keyClicks(form._ident_edit, "E")
    assert form._error_banner.isHidden()


def test_waypoint_keeps_full_precision(gui_env):
    form = AddFixForm(gui_env["waypoint_service"])
    form._ident_edit.setText("PRCSN")
    form._lat_spin.setValue(12.34567891)
    form._lon_spin.setValue(-98.76543219)
    form._on_submit()
    fix = gui_env["waypoint_service"].list_all()[0]
    assert (fix.latitude, fix.longitude) == (12.34567891, -98.76543219)
    assert form._lat_spin.value() == 0.0 and form._ident_edit.text() == ""    # cleared


# -- Add Navaid: segmented type control -----------------------------------------

def test_segmented_control_is_combo_compatible():
    seg = SegmentedControl(["NDB", "VOR", "DME"])
    changes = []
    seg.currentIndexChanged.connect(changes.append)
    assert (seg.count(), seg.currentIndex(), seg.currentText()) == (3, 0, "NDB")
    assert [seg.itemText(i) for i in range(3)] == ["NDB", "VOR", "DME"]
    seg.setCurrentIndex(2)
    seg.setCurrentIndex(2)                     # no change, no signal
    seg.buttons()[1].click()
    assert changes == [2, 1] and seg.currentText() == "VOR"


def test_segmented_control_arrow_keys(qapp):
    seg = SegmentedControl(["NDB", "VOR", "DME"])
    seg.show()
    QTest.keyClick(seg.buttons()[0], Qt.Key.Key_Right)
    QTest.keyClick(seg.buttons()[1], Qt.Key.Key_Right)
    QTest.keyClick(seg.buttons()[2], Qt.Key.Key_Right)     # stays on the last
    assert seg.currentIndex() == 2
    QTest.keyClick(seg.buttons()[2], Qt.Key.Key_Left)
    assert seg.currentIndex() == 1


def test_type_switching_shows_the_matching_radio_fields(gui_env):
    form = AddNavForm(gui_env["navaid_service"])
    assert isinstance(form._type_combo, SegmentedControl)
    for index in (1, 2, 0):
        form._type_combo.buttons()[index].click()
        assert form._stack.currentIndex() == index
        assert form._current_type().value == ("NDB", "VOR", "DME")[index]


def test_navaid_fields_keep_their_ranges_defaults_and_units(gui_env):
    f = AddNavForm(gui_env["navaid_service"])
    spec = {
        "_elev_spin": (-1500, 30000, 0, " ft"),
        "_ndb_freq_khz": (190, 1750, 190, " kHz"),
        "_ndb_range_nm": (1, 500, 50, " nm"),
        "_vor_freq_mhz": (108.0, 117.95, 108.0, " MHz"),
        "_vor_range_nm": (1, 500, 130, " nm"),
        "_vor_slaved_var": (-180.0, 180.0, 0.0, "°"),
        "_dme_freq_mhz": (108.0, 117.95, 108.0, " MHz"),
        "_dme_range_nm": (1, 500, 25, " nm"),
        "_dme_bias_nm": (0.0, 99.999, 0.0, " nm"),
    }
    for name, (lo, hi, default, suffix) in spec.items():
        spin = getattr(f, name)
        assert (spin.minimum(), spin.maximum(), spin.value(), spin.suffix()) == (lo, hi, default, suffix), name
    assert f._vor_freq_mhz.singleStep() == 0.05 and f._dme_freq_mhz.singleStep() == 0.05
    assert (f._vor_slaved_var.decimals(), f._dme_bias_nm.decimals()) == (3, 3)
    assert f._ident_edit.maxLength() == 4
    for spin in (f._lat_spin, f._lon_spin):
        assert spin.decimals() == 8
        assert spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
    assert "Paired VHF frequency, not a channel number." in _texts(f)
    assert "not a UHF DME channel number" in f._dme_freq_mhz.toolTip()
    assert f._create_btn.property("variant") == "primary"


# -- Add Navaid: all three types end to end ---------------------------------------

def test_creates_ndb_vor_and_dme_with_every_field(gui_env):
    ns = gui_env["navaid_service"]
    created = []
    form = AddNavForm(ns, on_created=lambda: created.append(True))

    _fill_navaid(form, 0, "FNDB")
    form._ndb_freq_khz.setValue(375)
    form._ndb_range_nm.setValue(75)
    form._on_submit()
    assert form._status_label.text() == "Added NDB FNDB."

    _fill_navaid(form, 1, "FVOR")
    form._vor_freq_mhz.setValue(113.25)
    form._vor_range_nm.setValue(120)
    form._vor_slaved_var.setValue(-12.5)
    form._on_submit()
    assert form._status_label.text() == "Added VOR FVOR."

    _fill_navaid(form, 2, "FDME")
    form._dme_freq_mhz.setValue(114.6)
    form._dme_range_nm.setValue(30)
    form._dme_bias_nm.setValue(0.25)
    form._on_submit()
    assert form._status_label.text() == "Added DME FDME."

    assert created == [True, True, True]
    by_ident = {n.ident: n for n in ns.list_all()}
    ndb, vor, dme = by_ident["FNDB"], by_ident["FVOR"], by_ident["FDME"]
    assert (ndb.frequency_khz, ndb.range_nm, ndb.elevation_ft, ndb.name) == (375, 75, 320, "Form NDB")
    assert (vor.frequency_mhz, vor.range_nm, vor.slaved_variation_deg) == (113.25, 120, -12.5)
    assert (dme.paired_frequency_mhz, dme.range_nm, dme.bias_nm) == (114.6, 30, 0.25)
    assert (dme.latitude, dme.longitude) == (12.5, -45.25)
    assert form._ident_edit.text() == "" and form._name_edit.text() == ""


@pytest.mark.parametrize("index", [0, 1, 2])
def test_navaid_validation_error_is_inline_and_unchanged(gui_env, index):
    form = AddNavForm(gui_env["navaid_service"])
    _fill_navaid(form, index, name="   ")          # blank name is invalid for every type
    form._on_submit()
    assert form._error_banner.tone() == "danger"
    assert form._error_banner.text_label.text() == "Name is required."
    assert form._status_label.text() == ""
    assert gui_env["navaid_service"].list_all() == []
    form._type_combo.setCurrentIndex((index + 1) % 3)  # switching type clears the error
    assert form._error_banner.isHidden()


def test_navaid_duplicate_add_anyway_creates_and_cancel_keeps_input(gui_env, monkeypatch):
    ns = gui_env["navaid_service"]
    ns.create_vor("DUPV", "Existing", 12.5, -45.25, 0, 113.2, 130)
    form = AddNavForm(ns)

    with monkeypatch.context() as patch:
        patch.setattr(duplicate_prompt, "confirm_despite_duplicates", lambda *a: False)
        _fill_navaid(form, 1, "DUPV")
        form._vor_freq_mhz.setValue(113.2)
        form._on_submit()
    assert len(ns.list_all()) == 1 and form._ident_edit.text() == "DUPV"
    assert form._status_label.text() == ""

    with monkeypatch.context() as patch:
        patch.setattr(duplicate_prompt, "confirm_despite_duplicates", lambda *a: True)
        form._on_submit()
    assert len(ns.list_all()) == 2 and form._status_label.text() == "Added VOR DUPV."


# -- In the window: DataEvents and fit -------------------------------------------------

def test_creation_notifies_data_events(make_window):
    window = make_window()
    kinds = []
    window.data_events.changed.connect(lambda c: kinds.append(c.kind))
    form = window.add_fix_form
    form._ident_edit.setText("EVTA")
    form._on_submit()
    for index, ident in enumerate(("EVN", "EVV", "EVD")):
        _fill_navaid(window.add_nav_form, index, ident)
        window.add_nav_form._on_submit()
    assert kinds == [ChangeKind.RECORD_ADDED] * 4
    assert window.sidebar.items()[MANAGE_DATA].count_text() == "4"
    assert window.manage_view._model.rowCount() == 4


@pytest.mark.parametrize("size", ["minimum", "default"])
def test_forms_fit_and_primary_action_is_reachable(make_window, size, themed):
    window = make_window()
    if size == "minimum":
        window.resize(window.minimumSize())
    window.show()
    QTest.qWaitForWindowExposed(window)
    for page_index, view in ((ADD_WAYPOINT, window.add_fix_form), (ADD_NAVAID, window.add_nav_form)):
        window.set_current_page(page_index)
        for i in range(3) if view is window.add_nav_form else range(1):
            if view is window.add_nav_form:
                view._type_combo.setCurrentIndex(i)
            QTest.qWait(10)
            scroll = window._pages[page_index].findChild(QScrollArea, "PageScroll")
            form_card = view.layout().itemAt(0).widget().form      # FormColumns.form
            assert form_card.width() <= 600
            assert form_card.mapTo(view, form_card.rect().topRight()).x() <= scroll.viewport().width()
            scroll.ensureWidgetVisible(view._create_btn)
            QTest.qWait(10)
            assert not view._create_btn.visibleRegion().isEmpty(), (page_index, i)
        aside = view.layout().itemAt(0).widget().aside
        assert aside.isHidden() == (size == "minimum")


def test_navaid_sections_share_column_edges(make_window, themed):
    window = make_window()
    window.show()
    QTest.qWaitForWindowExposed(window)
    window.set_current_page(ADD_NAVAID)
    form = window.add_nav_form
    for index in range(3):
        form._type_combo.setCurrentIndex(index)
        QTest.qWait(10)
        left = lambda w: w.mapTo(form, w.rect().topLeft()).x()      # noqa: E731
        assert left(form._ident_edit) == left(form._lat_spin)
        radio_first = form._stack.currentWidget().layout().itemAt(0).widget().field
        assert left(radio_first) == left(form._lat_spin)
        assert left(form._name_edit) == left(form._lon_spin)
        radio_second = form._stack.currentWidget().layout().itemAt(1).widget().field
        assert left(radio_second) == left(form._lon_spin), index


def test_section_titles_align_with_field_labels(make_window, themed):
    from flightgear_navdata_manager.presentation.components.field_group import FieldGroup

    window = make_window()
    window.show()
    QTest.qWaitForWindowExposed(window)
    window.set_current_page(ADD_NAVAID)
    form = window.add_nav_form
    QTest.qWait(10)
    titles = [lbl for lbl in form.findChildren(QLabel) if lbl.property("role") == "sectionTitle"]
    assert [t.text() for t in titles] == ["Identity", "Position", "Radio"]
    field_label = form._ident_edit.parent().label
    assert isinstance(form._ident_edit.parent(), FieldGroup)
    def text_x(lbl):
        # Qt's rule: indent -1 on a label with a frame means half an "x".
        indent = lbl.indent()
        if indent < 0:
            indent = lbl.fontMetrics().horizontalAdvance("x") // 2 if lbl.frameWidth() > 0 else 0
        return lbl.mapTo(form, lbl.contentsRect().topLeft()).x() + indent
    assert {text_x(t) for t in titles} == {text_x(field_label)}
