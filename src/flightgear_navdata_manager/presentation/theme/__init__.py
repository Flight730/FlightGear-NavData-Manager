"""The app's visual theme: dark-only navy palette, Fusion-based style,
token-generated style sheet and outline icons.

Call apply_theme(app) once, right after creating the QApplication.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTemporaryDir, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from . import dialogs, icons
from .style import AppStyle
from .stylesheet import IMAGES, build_qss
from .tokens import COLORS

__all__ = ["apply_theme", "build_palette", "icons", "COLORS"]


def build_palette() -> QPalette:
    c = COLORS
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: c.bg_content,
        QPalette.ColorRole.WindowText: c.text_primary,
        QPalette.ColorRole.Base: c.surface_inset,
        QPalette.ColorRole.AlternateBase: c.surface_card,
        QPalette.ColorRole.Text: c.text_primary,
        QPalette.ColorRole.PlaceholderText: c.text_tertiary,
        QPalette.ColorRole.Button: c.surface_raised,
        QPalette.ColorRole.ButtonText: c.text_primary,
        QPalette.ColorRole.BrightText: c.text_primary,
        QPalette.ColorRole.Highlight: c.focus_soft,
        QPalette.ColorRole.HighlightedText: c.text_primary,
        QPalette.ColorRole.ToolTipBase: c.surface_raised,
        QPalette.ColorRole.ToolTipText: c.text_primary,
        QPalette.ColorRole.Link: c.focus,
        QPalette.ColorRole.LinkVisited: c.focus,
        QPalette.ColorRole.Light: c.border_strong,
        QPalette.ColorRole.Midlight: c.border,
        QPalette.ColorRole.Mid: c.border,
        QPalette.ColorRole.Dark: c.bg_window,
        QPalette.ColorRole.Shadow: "#000000",
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c.text_tertiary))
    return palette


def apply_theme(app: QApplication) -> None:
    # Dark title bar and native dialogs regardless of the system setting.
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    app.setStyle(AppStyle())
    app.setPalette(build_palette())

    # Style sheets can't recolor images, so the few glyphs they use are
    # written out pre-colored. The directory lives as long as the app.
    assets = QTemporaryDir()
    app._theme_assets = assets
    images = {
        key: icons.write_recolored(Path(assets.path()), name, color)
        for key, name, color in IMAGES
    }
    app.setStyleSheet(build_qss(images))
    dialogs.install(app)
