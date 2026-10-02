"""Finishing touches for the standard dialogs, without replacing them.

The app keeps calling QMessageBox.question / information / warning (tests
intercept those calls), so styling that depends on a dialog's content is
applied when the dialog is shown, by an application event filter:

- A box with informative text gets a bold headline ("FIX EBAYE already
  exists."); a box whose whole message is in the main text gets body-weight
  text, so long confirmations read as a paragraph, not a heading.
- Inside `destructive_confirmation()`, the Yes button of the box shown is
  styled as the danger action. The safe default (No / Cancel) is unchanged.
"""

from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox


def _repolish(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class DialogPolisher(QObject):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.destructive_depth = 0

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QMessageBox):
            polish_message_box(watched, destructive=self.destructive_depth > 0)
        return False


def polish_message_box(box: QMessageBox, destructive: bool = False) -> None:
    label = box.findChild(QLabel, "qt_msgbox_label")
    if label is not None:
        label.setProperty("msgRole", "headline" if box.informativeText() else "body")
        _repolish(label)
    if destructive:
        button = box.button(QMessageBox.StandardButton.Yes)
        if button is not None:
            button.setProperty("variant", "danger")
            _repolish(button)


def install(app: QApplication) -> DialogPolisher:
    polisher = getattr(app, "_dialog_polisher", None)
    if polisher is None:
        polisher = DialogPolisher(app)
        app.installEventFilter(polisher)
        app._dialog_polisher = polisher
    return polisher


@contextmanager
def destructive_confirmation():
    """Marks the Yes button of message boxes shown inside the block as a
    destructive action. A no-op if the theme isn't installed."""
    polisher = getattr(QApplication.instance(), "_dialog_polisher", None)
    if polisher is not None:
        polisher.destructive_depth += 1
    try:
        yield
    finally:
        if polisher is not None:
            polisher.destructive_depth -= 1
