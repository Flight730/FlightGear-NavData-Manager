"""Add Navaid form -- NDB, VOR, or standalone DME (MVP 1's only supported
navaid types). Field sets and units follow the project specification
exactly:

  NDB: ident, name, lat, lon, elevation_ft, frequency (kHz), range_nm
       (max reception range)
  VOR: ident, name, lat, lon, elevation_ft, frequency (MHz),
       range_nm (max reception range), slaved variation (deg)
  DME: ident, name, lat, lon, elevation_ft, paired frequency (MHz,
       NOT a channel number), range_nm (MINIMUM reception range), bias
       (nm, optional, default 0.000)

All three types are ENRT-only in MVP 1 -- no airport/terminal field is
shown, matching the 810 nav.dat layout's structural limits.

The type is chosen with a segmented control (NDB | VOR | DME) that keeps
the combo-box API under its old name, _type_combo. Validation is the
domain's (build_ndb / build_vor / build_dme); its ValidationError
message is shown unchanged in an inline error banner.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from flightgear_navdata_manager.application.navaid_service import (
    NavaidService,
    build_dme,
    build_ndb,
    build_vor,
)
from flightgear_navdata_manager.domain.exceptions import ValidationError
from flightgear_navdata_manager.domain.models import NavaidType

from ..components.card import Card
from ..components.feedback import InlineBanner
from ..components.field_group import FieldGroup, section_title
from ..components.form_layout import FormColumns, coordinate_spin, tip_card
from ..components.segmented import SegmentedControl
from ..theme import icons
from ..theme.tokens import COLORS, SPACING
from . import duplicate_prompt
from .add_fix_form import COORDINATE_HELP

_NDB_INDEX = 0
_VOR_INDEX = 1
_DME_INDEX = 2
_TYPE_BY_INDEX = {_NDB_INDEX: NavaidType.NDB, _VOR_INDEX: NavaidType.VOR, _DME_INDEX: NavaidType.DME}

DME_PAIRING_HELP = "Paired VHF frequency, not a channel number."


COLUMNS = 3


def _grid(*cells: QWidget | tuple[QWidget, int]) -> QGridLayout:
    """One row of FieldGroups on the form's shared three-column grid, top
    aligned so a field with a longer helper never pushes its neighbours
    down. A cell is a widget or (widget, column span)."""
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(SPACING.md)
    column = 0
    for cell in cells:
        widget, span = cell if isinstance(cell, tuple) else (cell, 1)
        # Ignore content minimum widths so every section's columns line up.
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        grid.addWidget(widget, 0, column, 1, span, Qt.AlignmentFlag.AlignTop)
        column += span
    for c in range(COLUMNS):
        grid.setColumnStretch(c, 1)
        # QGridLayout drops the spacing beside a column with no item of its
        # own (e.g. under a span), which would shift that section's column
        # edges; a zero-height placeholder keeps every column occupied.
        placeholder = QWidget()
        placeholder.setFixedHeight(0)
        placeholder.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        grid.addWidget(placeholder, 1, c)
    grid.setVerticalSpacing(0)
    return grid


def _frequency_help(spin: QDoubleSpinBox | QSpinBox, decimals: int) -> str:
    unit = spin.suffix().strip()
    return f"{spin.minimum():.{decimals}f}–{spin.maximum():.{decimals}f} {unit}"


class AddNavForm(QWidget):
    def __init__(
        self,
        navaid_service: NavaidService,
        on_created: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._service = navaid_service
        self._on_created = on_created

        card = Card()

        self._type_combo = SegmentedControl(["NDB", "VOR", "DME"])
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_row = QHBoxLayout()
        type_row.addWidget(FieldGroup("Type", self._type_combo))
        type_row.addStretch(1)
        card.body.addLayout(type_row)

        # -- Identity
        card.body.addWidget(section_title("Identity"))
        self._ident_edit = QLineEdit()
        self._ident_edit.setMaxLength(4)
        self._name_edit = QLineEdit()
        card.body.addLayout(_grid(
            FieldGroup("Identifier", self._ident_edit, "Up to 4 characters"),
            (FieldGroup("Name", self._name_edit, "Required · the type (NDB, VOR or DME) is appended if missing"), 2),
        ))

        # -- Position
        card.body.addWidget(section_title("Position"))
        self._lat_spin = coordinate_spin(-90.0, 90.0)
        self._lon_spin = coordinate_spin(-180.0, 180.0)
        self._elev_spin = QSpinBox()
        self._elev_spin.setRange(-1500, 30000)
        self._elev_spin.setSuffix(" ft")
        card.body.addLayout(_grid(
            FieldGroup("Latitude", self._lat_spin, COORDINATE_HELP),
            FieldGroup("Longitude", self._lon_spin),
            FieldGroup("Elevation", self._elev_spin, "Above mean sea level"),
        ))

        # -- Radio (one page per type)
        card.body.addWidget(section_title("Radio"))
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_ndb_page())
        self._stack.addWidget(self._build_vor_page())
        self._stack.addWidget(self._build_dme_page())
        card.body.addWidget(self._stack)
        card.body.addSpacing(SPACING.xs)

        # Result of the last Add: an error (validation) or a success message.
        self._error_banner = InlineBanner()
        card.body.addWidget(self._error_banner)
        self._status_banner = InlineBanner()
        self._status_label = self._status_banner.text_label
        card.body.addWidget(self._status_banner)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self._create_btn = QPushButton("Add Navaid")
        self._create_btn.setProperty("variant", "primary")
        icons.set_button_icon(self._create_btn, "plus", COLORS.text_on_accent)
        self._create_btn.clicked.connect(self._on_submit)
        footer.addWidget(self._create_btn)
        card.body.addLayout(footer)

        aside = tip_card("About navaids", [
            "Navaids are written as enroute stations, with no airport association.",
            "A DME tunes with the VHF frequency it is paired with, the same "
            "number you would dial for a VOR.",
            "Use Manage Data to disable or delete navaids later.",
        ])
        outer = QVBoxLayout(self)
        outer.addWidget(FormColumns(card, aside))
        outer.addStretch(1)

        self._on_type_changed(self._type_combo.currentIndex())
        for edit in (self._ident_edit, self._name_edit):
            edit.returnPressed.connect(self._on_submit)
            edit.textEdited.connect(self._error_banner.clear)
        for spin in [*self.findChildren(QSpinBox), *self.findChildren(QDoubleSpinBox)]:
            spin.valueChanged.connect(self._error_banner.clear)

    def _build_ndb_page(self) -> QWidget:
        page = QWidget()
        self._ndb_freq_khz = QSpinBox()
        self._ndb_freq_khz.setRange(190, 1750)
        self._ndb_freq_khz.setSuffix(" kHz")
        self._ndb_range_nm = QSpinBox()
        self._ndb_range_nm.setRange(1, 500)
        self._ndb_range_nm.setValue(50)
        self._ndb_range_nm.setSuffix(" nm")
        page.setLayout(_grid(
            FieldGroup("Frequency", self._ndb_freq_khz, _frequency_help(self._ndb_freq_khz, 0)),
            FieldGroup("Range (maximum)", self._ndb_range_nm, "Maximum reception range"),
        ))
        return page

    def _build_vor_page(self) -> QWidget:
        page = QWidget()
        self._vor_freq_mhz = QDoubleSpinBox()
        self._vor_freq_mhz.setRange(108.00, 117.95)
        self._vor_freq_mhz.setDecimals(2)
        self._vor_freq_mhz.setSingleStep(0.05)
        self._vor_freq_mhz.setSuffix(" MHz")
        self._vor_freq_mhz.setValue(108.00)
        self._vor_range_nm = QSpinBox()
        self._vor_range_nm.setRange(1, 500)
        self._vor_range_nm.setValue(130)
        self._vor_range_nm.setSuffix(" nm")
        self._vor_slaved_var = QDoubleSpinBox()
        self._vor_slaved_var.setRange(-180.0, 180.0)
        self._vor_slaved_var.setDecimals(3)
        self._vor_slaved_var.setSuffix("°")
        page.setLayout(_grid(
            FieldGroup("Frequency", self._vor_freq_mhz, _frequency_help(self._vor_freq_mhz, 2)),
            FieldGroup("Range (maximum)", self._vor_range_nm, "Maximum reception range"),
            FieldGroup("Slaved variation", self._vor_slaved_var, "Degrees, true"),
        ))
        return page

    def _build_dme_page(self) -> QWidget:
        page = QWidget()
        self._dme_freq_mhz = QDoubleSpinBox()
        self._dme_freq_mhz.setRange(108.00, 117.95)
        self._dme_freq_mhz.setDecimals(2)
        self._dme_freq_mhz.setSingleStep(0.05)
        self._dme_freq_mhz.setSuffix(" MHz")
        self._dme_freq_mhz.setValue(108.00)
        self._dme_freq_mhz.setToolTip(
            "The VHF frequency this DME is paired/tuned with (same units as a "
            "VOR frequency) -- not a UHF DME channel number."
        )
        self._dme_range_nm = QSpinBox()
        self._dme_range_nm.setRange(1, 500)
        self._dme_range_nm.setValue(25)
        self._dme_range_nm.setSuffix(" nm")
        self._dme_bias_nm = QDoubleSpinBox()
        self._dme_bias_nm.setRange(0.0, 99.999)
        self._dme_bias_nm.setDecimals(3)
        self._dme_bias_nm.setValue(0.0)
        self._dme_bias_nm.setSuffix(" nm")
        page.setLayout(_grid(
            FieldGroup("Paired frequency", self._dme_freq_mhz, DME_PAIRING_HELP),
            FieldGroup("Range (minimum)", self._dme_range_nm, "Minimum reception range"),
            FieldGroup("Bias", self._dme_bias_nm, "Optional"),
        ))
        return page

    def _on_type_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._fit_stack()
        self._error_banner.clear()

    def _fit_stack(self) -> None:
        """Makes the Radio section exactly as tall as the current type's
        fields at the current width (helper text may wrap), rather than
        as tall as the tallest type's."""
        layout = self._stack.currentWidget().layout()
        width = self._stack.width()
        if width > 0 and layout.hasHeightForWidth():
            height = layout.heightForWidth(width)
        else:
            height = layout.sizeHint().height()
        if self._stack.height() != height:
            self._stack.setFixedHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_stack()

    def _current_type(self) -> NavaidType:
        return _TYPE_BY_INDEX[self._type_combo.currentIndex()]

    def _on_submit(self) -> None:
        ident = self._ident_edit.text()
        name = self._name_edit.text()
        lat = self._lat_spin.value()
        lon = self._lon_spin.value()
        elev_ft = self._elev_spin.value()
        navaid_type = self._current_type()
        self._error_banner.clear()
        self._status_banner.clear()

        try:
            if navaid_type == NavaidType.NDB:
                candidate = build_ndb(
                    ident, name, lat, lon, elev_ft,
                    self._ndb_freq_khz.value(), self._ndb_range_nm.value(),
                )
            elif navaid_type == NavaidType.VOR:
                candidate = build_vor(
                    ident, name, lat, lon, elev_ft,
                    self._vor_freq_mhz.value(), self._vor_range_nm.value(),
                    self._vor_slaved_var.value(),
                )
            else:
                candidate = build_dme(
                    ident, name, lat, lon, elev_ft,
                    self._dme_freq_mhz.value(), self._dme_range_nm.value(),
                    self._dme_bias_nm.value(),
                )
        except ValidationError as exc:
            self._error_banner.show_message(str(exc), "danger")
            return
        matches = self._service.find_duplicates(candidate)
        if matches and not duplicate_prompt.confirm_despite_duplicates(self, candidate, matches):
            return

        created = self._service.add(candidate)

        self._status_banner.show_message(f"Added {navaid_type.value} {created.ident}.", "success")
        self._ident_edit.clear()
        self._name_edit.clear()
        self._ident_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._on_created:
            self._on_created()
