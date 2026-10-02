"""Outline icons (Lucide, ISC -- see assets/icons/LICENSE), recolored at
runtime to theme colors.

The SVGs draw with stroke="currentColor", so recoloring is a text
substitution before rendering. Rendered icons are cached per
(name, color, size).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .tokens import COLORS

ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
_SCALES = (1, 2)   # 1x and Retina


def available() -> list[str]:
    return sorted(p.stem for p in ICON_DIR.glob("*.svg"))


@lru_cache(maxsize=None)
def svg_source(name: str, color: str, stroke_width: float = 1.75) -> bytes:
    path = ICON_DIR / f"{name}.svg"
    text = path.read_text(encoding="utf-8")
    text = text.replace("currentColor", color)
    text = text.replace('stroke-width="2"', f'stroke-width="{stroke_width:g}"')
    return text.encode("utf-8")


@lru_cache(maxsize=None)
def pixmap(name: str, color: str = COLORS.text_secondary, size: int = 18, scale: int = 2) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_source(name, color)))
    if not renderer.isValid():
        raise ValueError(f"icon {name!r} could not be rendered")
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(
    name: str,
    color: str = COLORS.text_secondary,
    size: int = 18,
    *,
    active_color: str | None = None,
    disabled_color: str = COLORS.text_tertiary,
) -> QIcon:
    """A QIcon in `color`; `active_color` is used for the Selected/On
    states (e.g. the current sidebar item)."""
    result = QIcon()
    for scale in _SCALES:
        result.addPixmap(pixmap(name, color, size, scale), QIcon.Mode.Normal, QIcon.State.Off)
        result.addPixmap(pixmap(name, disabled_color, size, scale), QIcon.Mode.Disabled, QIcon.State.Off)
        if active_color:
            for mode in (QIcon.Mode.Selected, QIcon.Mode.Active):
                result.addPixmap(pixmap(name, active_color, size, scale), mode, QIcon.State.Off)
            result.addPixmap(pixmap(name, active_color, size, scale), QIcon.Mode.Normal, QIcon.State.On)
    return result


def button_icon(name: str, color: str, size: int = 14, gap: int = 6) -> tuple[QIcon, QSize]:
    """An icon for a text button, with `gap` px of transparent space after
    the glyph (Fusion puts only ~4px between icon and text). Use the
    returned size with QAbstractButton.setIconSize()."""
    result = QIcon()
    for scale in _SCALES:
        canvas = QPixmap((size + gap) * scale, size * scale)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        glyph = QPixmap(pixmap(name, color, size, scale))   # a copy: never alter the cached one
        glyph.setDevicePixelRatio(1)
        painter.drawPixmap(0, 0, glyph)
        painter.end()
        canvas.setDevicePixelRatio(scale)
        result.addPixmap(canvas)
    return result, QSize(size + gap, size)


def set_button_icon(button, name: str, color: str, size: int = 14) -> None:
    """Gives a text button a leading icon with comfortable spacing."""
    icon_, icon_size = button_icon(name, color, size)
    button.setIcon(icon_)
    button.setIconSize(icon_size)


def write_recolored(directory: Path, name: str, color: str, stroke_width: float = 2.0) -> Path:
    """Writes a recolored copy for use in a style sheet url(...), which
    can't recolor an image itself. Returns the file's path."""
    out = directory / f"{name}-{color.lstrip('#')}.svg"
    if not out.exists():
        out.write_bytes(svg_source(name, color, stroke_width))
    return out
