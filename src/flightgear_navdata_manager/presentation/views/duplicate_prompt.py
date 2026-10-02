"""The duplicate warning shown by Add Waypoint / Add Navaid before creating
a record that duplicates or conflicts with existing data (see
application/duplicate_policy.py). It names every matching record and
defaults to Cancel; creating the record anyway takes an explicit
"Add Anyway" click.
"""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractButton, QMessageBox, QWidget

from flightgear_navdata_manager.application.duplicate_policy import (
    DuplicateMatch,
    record_kind,
)
from flightgear_navdata_manager.domain.models import Fix, Navaid

_MAX_LISTED = 10


def build_duplicate_dialog(
    parent: QWidget | None, candidate: Fix | Navaid, matches: list[DuplicateMatch]
) -> tuple[QMessageBox, QAbstractButton]:
    kind = record_kind(candidate)
    duplicates = [m for m in matches if m.is_duplicate]
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Possible duplicate")
    if duplicates:
        box.setText(f"{kind} {candidate.ident} already exists.")
    else:
        box.setText(f"Another {kind} named {candidate.ident} is nearby.")
    lines = [f"• {m.kind.value.capitalize()}: {m.describe()}" for m in matches[:_MAX_LISTED]]
    if len(matches) > _MAX_LISTED:
        lines.append(f"• ...and {len(matches) - _MAX_LISTED} more")
    lines.append("")
    lines.append(
        "Adding it anyway creates a second record. FlightGear keeps only one of two "
        "same-named records close together (within 15 nm for fixes, 10 nm for navaids)."
    )
    box.setInformativeText("\n".join(lines))
    add_button = box.addButton("Add Anyway", QMessageBox.ButtonRole.AcceptRole)
    cancel_button = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(cancel_button)
    box.setEscapeButton(cancel_button)
    return box, add_button


def confirm_despite_duplicates(
    parent: QWidget | None, candidate: Fix | Navaid, matches: list[DuplicateMatch]
) -> bool:
    """True only if the user explicitly chose "Add Anyway"."""
    box, add_button = build_duplicate_dialog(parent, candidate, matches)
    box.exec()
    return box.clickedButton() is add_button
