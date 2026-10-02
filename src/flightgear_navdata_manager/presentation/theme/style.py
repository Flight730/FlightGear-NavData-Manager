"""Application QStyle: Fusion (which honours the style sheet consistently,
unlike the native macOS style) with the outline icon set swapped in for
the standard message-box icons.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton, QComboBox, QProxyStyle, QStyle

from . import icons
from .tokens import COLORS

_MESSAGE_ICON_SIZE = 36

_STANDARD_ICONS = {
    QStyle.StandardPixmap.SP_MessageBoxInformation: ("info", COLORS.info),
    QStyle.StandardPixmap.SP_MessageBoxWarning: ("triangle-alert", COLORS.warning),
    QStyle.StandardPixmap.SP_MessageBoxCritical: ("circle-x", COLORS.danger),
    QStyle.StandardPixmap.SP_MessageBoxQuestion: ("circle-help", COLORS.focus),
}


class AppStyle(QProxyStyle):
    def __init__(self):
        super().__init__("Fusion")

    def polish(self, target):
        # As in the native macOS style: buttons and pop-ups take focus
        # from the Tab key only, never from a click or when a page opens,
        # so no button shows a focus ring until the keyboard is used.
        if isinstance(target, (QAbstractButton, QComboBox)):
            target.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        return super().polish(target)

    def standardIcon(self, standard_icon, option=None, widget=None):
        if standard_icon in _STANDARD_ICONS:
            name, color = _STANDARD_ICONS[standard_icon]
            return icons.icon(name, color, _MESSAGE_ICON_SIZE)
        return super().standardIcon(standard_icon, option, widget)

    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PixelMetric.PM_MessageBoxIconSize:
            return _MESSAGE_ICON_SIZE
        return super().pixelMetric(metric, option, widget)

    def styleHint(self, hint, option=None, widget=None, return_data=None):
        if hint == QStyle.StyleHint.SH_DialogButtonBox_ButtonsHaveIcons:
            return 0
        if hint == QStyle.StyleHint.SH_UnderlineShortcut:
            return 0
        return super().styleHint(hint, option, widget, return_data)
