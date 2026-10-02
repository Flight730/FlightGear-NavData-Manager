"""Step 7 polish: dialog styling and wrapping, help text, empty states,
banners, accessible names for icon-only buttons, reachability at the
minimum window size, and stale-terminology checks."""

import html
import re

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QMessageBox, QScrollArea, QTableView

from flightgear_navdata_manager.presentation.components.feedback import InlineBanner
from flightgear_navdata_manager.presentation.theme.dialogs import (
    destructive_confirmation,
    polish_message_box,
)
from flightgear_navdata_manager.presentation.views import duplicate_prompt
from flightgear_navdata_manager.presentation.views.import_view import TABLE_FORMAT_HELP, format_help_html
from flightgear_navdata_manager.presentation.views.manage_data_view import ManageDataView

DELETE_TEXT = ("Permanently delete FIX 'QXALL'? This cannot be undone. "
               "(To keep it but exclude it from export, use the Enabled switch instead.)")


def _question_box(text):
    box = QMessageBox(QMessageBox.Icon.Question, "Delete record", text,
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    return box


# -- dialogs -------------------------------------------------------------------------

def test_delete_confirmation_is_marked_destructive_and_wraps(themed):
    box = _question_box(DELETE_TEXT)
    with destructive_confirmation():
        box.show()                                   # the app-wide polisher runs on Show
    QTest.qWait(10)
    label = box.findChild(QLabel, "qt_msgbox_label")
    assert box.button(QMessageBox.StandardButton.Yes).property("variant") == "danger"
    assert box.defaultButton() is box.button(QMessageBox.StandardButton.No)   # safe default kept
    assert label.property("msgRole") == "body"
    assert label.wordWrap() and label.sizeHint().width() <= box.width()
    box.close()


def test_other_questions_are_not_destructive(themed):
    box = _question_box("Add 6 new record(s) to your data?")
    box.show()
    QTest.qWait(10)
    assert box.button(QMessageBox.StandardButton.Yes).property("variant") is None
    box.close()


def test_duplicate_warning_has_headline_and_safe_default(gui_env, themed):
    ws = gui_env["waypoint_service"]
    existing = ws.create("EBAYE", 37.621, -122.379)
    from flightgear_navdata_manager.application.waypoint_service import build_fix
    candidate = build_fix("EBAYE", 37.621, -122.379)
    box, add_button = duplicate_prompt.build_duplicate_dialog(None, candidate, ws.find_duplicates(candidate))
    polish_message_box(box)
    assert existing.ident == "EBAYE"
    assert box.findChild(QLabel, "qt_msgbox_label").property("msgRole") == "headline"
    assert box.defaultButton() is box.button(QMessageBox.StandardButton.Cancel)
    assert add_button.text() == "Add Anyway"


def test_dialog_icons_are_the_outline_set(themed):
    from PySide6.QtWidgets import QStyle
    from flightgear_navdata_manager.presentation.theme import icons
    from flightgear_navdata_manager.presentation.theme.tokens import COLORS
    for sp, name, color in [
        (QStyle.StandardPixmap.SP_MessageBoxQuestion, "circle-help", COLORS.focus),
        (QStyle.StandardPixmap.SP_MessageBoxInformation, "info", COLORS.info),
        (QStyle.StandardPixmap.SP_MessageBoxWarning, "triangle-alert", COLORS.warning),
    ]:
        got = themed.style().standardIcon(sp).pixmap(36).toImage()
        assert got == icons.icon(name, color, 36).pixmap(36).toImage(), name


def test_format_help_keeps_every_word_and_the_example_lines(gui_env, monkeypatch):
    rendered = format_help_html(TABLE_FORMAT_HELP)
    plain = html.unescape(re.sub(r"<[^>]+>", " ", rendered.replace("&nbsp;", " ")))
    assert plain.split() == TABLE_FORMAT_HELP.split()
    # Example rows stay one per line (never joined into prose).
    assert "type,ident,name,latitude,longitude,frequency,range_nm<br>NDB,ABC" in rendered


# -- empty states and banners ------------------------------------------------------------

def test_empty_states_have_icon_title_text_and_only_useful_actions(gui_env):
    view = ManageDataView(gui_env["waypoint_service"], gui_env["navaid_service"], on_navigate=lambda t: None)
    empty, none = view._empty_state_label, view._no_results
    assert empty.title_label.text() == "No records yet"
    assert [b.text() for b in empty.buttons] == ["Import data", "Add waypoint"]
    assert none.title_label.text() == "No records match your filters"
    assert [b.text() for b in none.buttons] == ["Clear filters"]
    for state in (empty, none):
        assert state.text_label.wordWrap() and state.text_label.text()
        assert any(lbl.pixmap() is not None and not lbl.pixmap().isNull() for lbl in state.findChildren(QLabel))


def test_banner_tones_icons_and_wrapping(qapp):
    banner = InlineBanner()
    assert banner.isHidden()
    for tone in ("success", "warning", "danger", "info", "neutral"):
        banner.show_message("A long message " * 20, tone)
        assert banner.tone() == tone and not banner.isHidden()
        assert banner.text_label.wordWrap()
        assert not banner._icon.pixmap().isNull()
    banner.clear()
    assert banner.isHidden() and banner.text_label.text() == ""


# -- accessibility and reachability -----------------------------------------------------------

def test_icon_only_buttons_have_accessible_names(make_window, seeded_window_data):
    window = make_window()
    QTest.qWait(10)
    for button in window.findChildren(QAbstractButton):
        # Qt's own internals: the line edit's clear button, the table's corner
        # button (unnamed before Qt 6.11), the menu bar's overflow button.
        if (isinstance(button.parent(), (QLineEdit, QTableView))
                or button.objectName().startswith("qt_")):
            continue
        if not button.text().strip():
            assert button.accessibleName() or button.toolTip(), button
    assert window.manage_view._search_edit.accessibleName() == "Search records"


@pytest.mark.parametrize("index", range(5))
def test_every_button_is_reachable_at_minimum_size(make_window, themed, seeded_window_data, index):
    window = make_window()
    window.resize(window.minimumSize())
    window.show()
    QTest.qWaitForWindowExposed(window)
    window.set_current_page(index)
    QTest.qWait(20)
    page = window._pages[index]
    scroll = page.findChild(QScrollArea, "PageScroll")
    for button in page.content.findChildren(QAbstractButton):
        if not button.isVisibleTo(page.content) or isinstance(button.parent(), QLineEdit):
            continue
        right = button.mapTo(page.content, button.rect().topRight()).x()
        assert right <= scroll.viewport().width(), (index, button.text())
        scroll.ensureWidgetVisible(button)
        QTest.qWait(2)
        assert not button.visibleRegion().isEmpty(), (index, button.text())


# -- terminology -------------------------------------------------------------------------------

STALE = re.compile(r"Import tab|Add NAV\b|the \w+ tab\b|Enabled checkbox", re.IGNORECASE)


def test_no_stale_terminology_in_visible_text(make_window, seeded_window_data):
    window = make_window()
    QTest.qWait(10)
    texts = [w.text() for w in window.findChildren(QLabel)]
    texts += [w.text() for w in window.findChildren(QAbstractButton)]
    texts += [w.placeholderText() for w in window.findChildren(QLineEdit)]
    assert not [t for t in texts if STALE.search(t)]


def test_delete_confirmation_text(gui_env, monkeypatch):
    ws = gui_env["waypoint_service"]
    ws.create("TERMS", 1.0, 1.0)
    view = ManageDataView(ws, gui_env["navaid_service"])
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda p, t, text, *a, **k: (asked.append(text),
                                                                             QMessageBox.StandardButton.No)[1])
    view._on_delete_row(0)
    assert asked == ["Permanently delete FIX 'TERMS'? This cannot be undone. "
                     "(To keep it but exclude it from export, use the Enabled switch instead.)"]


@pytest.fixture
def seeded_window_data(gui_env):
    gui_env["waypoint_service"].create("POLSH", 1.0, 2.0)
    gui_env["navaid_service"].create_vor("PVR", "Polish", 3.0, 4.0, 0, 113.2, 130)
    return gui_env
