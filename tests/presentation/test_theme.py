from pathlib import Path

import pytest
from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QStyle, QWidget

from flightgear_navdata_manager.presentation import theme
from flightgear_navdata_manager.presentation.theme import icons
from flightgear_navdata_manager.presentation.theme.style import AppStyle
from flightgear_navdata_manager.presentation.theme.stylesheet import IMAGES, build_qss
from flightgear_navdata_manager.presentation.theme.tokens import COLORS


@pytest.fixture
def themed_app(qapp):
    old_sheet, old_palette = qapp.styleSheet(), qapp.palette()
    theme.apply_theme(qapp)
    yield qapp
    qapp.setStyleSheet(old_sheet)
    qapp.setPalette(old_palette)


def test_icon_license_is_bundled():
    assert (icons.ICON_DIR / "LICENSE").read_text().startswith("ISC License")


@pytest.mark.parametrize("name", icons.available())
def test_every_icon_renders(qapp, name):
    pm = icons.pixmap(name, COLORS.accent, 18, 2)
    assert pm.width() == 36
    image = pm.toImage()
    assert any(image.pixelColor(x, y).alpha() for x in range(36) for y in range(36))


def test_icons_are_recolored(qapp):
    image = icons.pixmap("plus", "#ff0000", 24, 4).toImage()   # 4x: strokes have solid cores
    opaque = [image.pixelColor(x, y) for x in range(96) for y in range(96) if image.pixelColor(x, y).alpha() == 255]
    assert opaque and all(c.red() == 255 and c.green() == 0 and c.blue() == 0 for c in opaque)


def test_style_sheet_parses_without_warnings(qapp, tmp_path):
    images = {key: icons.write_recolored(tmp_path, name, color) for key, name, color in IMAGES}
    assert all(Path(p).exists() for p in images.values())
    messages = []
    previous = qInstallMessageHandler(lambda mode, ctx, msg: messages.append((mode, msg)))
    try:
        widget = QWidget()
        widget.setStyleSheet(build_qss(images))
        widget.ensurePolished()
    finally:
        qInstallMessageHandler(previous)
    assert not [m for mode, m in messages if mode != QtMsgType.QtDebugMsg], messages


def test_apply_theme_sets_style_palette_and_sheet(themed_app):
    # With a style sheet set, Qt wraps the app style, so check behavior:
    # the app's message-box icon is the theme's.
    warning = themed_app.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
    expected = icons.icon("triangle-alert", COLORS.warning, 36)
    assert warning.pixmap(36).toImage() == expected.pixmap(36).toImage()
    assert themed_app.palette().color(QPalette.ColorRole.Window).name() == COLORS.bg_content
    assert COLORS.accent in themed_app.styleSheet()


def test_message_box_icons_come_from_the_theme(qapp):
    style = AppStyle()
    for sp in (QStyle.StandardPixmap.SP_MessageBoxWarning, QStyle.StandardPixmap.SP_MessageBoxQuestion):
        assert not style.standardIcon(sp).isNull()
    assert style.pixelMetric(QStyle.PixelMetric.PM_MessageBoxIconSize) == 36


def test_long_message_box_text_still_wraps(themed_app):
    """Regression: a min-width on the message label made QMessageBox
    switch word wrap off and clip the delete confirmation."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

    seen = {}

    def inspect():
        box = QApplication.activeModalWidget()
        label = box.findChild(QLabel, "qt_msgbox_label")
        seen["wrap"] = label.wordWrap()
        seen["fits"] = label.sizeHint().width() <= box.width()
        box.reject()

    QTimer.singleShot(0, inspect)
    QMessageBox.question(None, "Delete record", "Permanently delete FIX 'QXALL'? This cannot be undone. "
                         "(To keep it but exclude it from export, use the Enabled checkbox instead.)")
    assert seen == {"wrap": True, "fits": True}
