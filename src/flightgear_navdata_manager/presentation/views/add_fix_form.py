"""Add Waypoint/Fix form.

Exactly three fields, matching what FlightGear's fixlist.cxx actually
reads: latitude, longitude, identifier. No scope/region fields are
collected -- FlightGear never uses them (verified against source) and
MVP 1's writer never emits them for CUSTOM-created fixes.

Validation is the domain's (build_fix); its ValidationError message is
shown unchanged in an inline error banner rather than a pop-up.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from flightgear_navdata_manager.application.waypoint_service import WaypointService, build_fix
from flightgear_navdata_manager.domain.exceptions import ValidationError

from ..components.card import Card
from ..components.feedback import InlineBanner
from ..components.field_group import FieldGroup
from ..components.form_layout import FormColumns, coordinate_spin, tip_card
from ..theme import icons
from ..theme.tokens import COLORS, SPACING
from . import duplicate_prompt

COORDINATE_HELP = "Decimal degrees · south/west negative"


class AddFixForm(QWidget):
    def __init__(
        self,
        waypoint_service: WaypointService,
        on_created: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._service = waypoint_service
        self._on_created = on_created

        card = Card()

        self._ident_edit = QLineEdit()
        self._ident_edit.setMaxLength(10)
        self._ident_edit.setPlaceholderText("e.g. EBAYE")
        card.body.addWidget(FieldGroup("Identifier", self._ident_edit, "Up to 10 characters"))

        self._lat_spin = coordinate_spin(-90.0, 90.0)
        self._lon_spin = coordinate_spin(-180.0, 180.0)
        coords = QHBoxLayout()
        coords.setSpacing(SPACING.md)
        coords.addWidget(FieldGroup("Latitude", self._lat_spin), 1)
        coords.addWidget(FieldGroup("Longitude", self._lon_spin), 1)
        card.body.addLayout(coords)
        self._coordinate_help = QLabel(COORDINATE_HELP)
        self._coordinate_help.setProperty("role", "helper")
        card.body.addWidget(self._coordinate_help)
        card.body.addSpacing(SPACING.xs)

        # Result of the last Add: an error (validation) or a success message.
        self._error_banner = InlineBanner()
        card.body.addWidget(self._error_banner)
        self._status_banner = InlineBanner()
        self._status_label = self._status_banner.text_label
        card.body.addWidget(self._status_banner)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self._create_btn = QPushButton("Add Waypoint")
        self._create_btn.setProperty("variant", "primary")
        icons.set_button_icon(self._create_btn, "plus", COLORS.text_on_accent)
        self._create_btn.clicked.connect(self._on_submit)
        footer.addWidget(self._create_btn)
        card.body.addLayout(footer)

        aside = tip_card("About waypoints", [
            "FlightGear reads only a fix's identifier and position.",
            "New waypoints go straight into your custom scenery output. "
            "Use Manage Data to disable or delete them later.",
        ])
        outer = QVBoxLayout(self)
        outer.addWidget(FormColumns(card, aside))
        outer.addStretch(1)

        for edit in (self._ident_edit,):
            edit.returnPressed.connect(self._on_submit)
            edit.textEdited.connect(self._error_banner.clear)
        for spin in (self._lat_spin, self._lon_spin):
            spin.valueChanged.connect(self._error_banner.clear)
            spin.lineEdit().returnPressed.connect(self._on_submit)

    def _on_submit(self) -> None:
        ident = self._ident_edit.text()
        lat = self._lat_spin.value()
        lon = self._lon_spin.value()
        self._error_banner.clear()
        self._status_banner.clear()

        try:
            candidate = build_fix(ident, lat, lon)
        except ValidationError as exc:
            self._error_banner.show_message(str(exc), "danger")
            return
        matches = self._service.find_duplicates(candidate)
        if matches and not duplicate_prompt.confirm_despite_duplicates(self, candidate, matches):
            return

        created = self._service.add(candidate)

        self._status_banner.show_message(f"Added waypoint {created.ident}.", "success")
        self._ident_edit.clear()
        self._lat_spin.setValue(0.0)
        self._lon_spin.setValue(0.0)
        self._ident_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._on_created:
            self._on_created()
