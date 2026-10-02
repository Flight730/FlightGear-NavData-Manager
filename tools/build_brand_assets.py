"""Generates the app's brand assets from one geometric definition.

The mark ("waypoint rose"): the four-pointed star that marks an RNAV
waypoint on aeronautical charts, set in a segmented VOR compass-rose ring.
Its north point -- the heading -- is the teal accent. Every colour is an
existing theme token; nothing here changes the theme.

Writes:
  src/.../presentation/theme/assets/brand/waypoint_rose.svg       colour mark
  src/.../presentation/theme/assets/brand/waypoint_rose_mono.svg  one colour (currentColor)
  src/.../presentation/theme/assets/brand/app_icon.svg            1024 px macOS icon artwork
  packaging/AppIcon.icns                                           built with macOS `iconutil`

Rendering uses PySide6's QtSvg (already a dependency). Usage:
    .venv/bin/python tools/build_brand_assets.py
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flightgear_navdata_manager.presentation.theme.tokens import COLORS  # noqa: E402

BRAND_DIR = ROOT / "src" / "flightgear_navdata_manager" / "presentation" / "theme" / "assets" / "brand"
ICNS = ROOT / "packaging" / "AppIcon.icns"

# -- geometry (64-unit square) -----------------------------------------------------
CENTER = 32.0
RING_R, RING_W, RING_GAP_DEG = 22.5, 3.6, 13.0
STAR_INNER = 6.2                        # waist of the star, on the diagonals
NORTH_R, SIDE_R = 30.0, 25.5            # north (heading) point is longer


def _pt(r: float, deg: float, cx: float = CENTER, cy: float = CENTER) -> tuple[float, float]:
    a = math.radians(deg - 90)          # 0 deg = north, clockwise
    return cx + r * math.cos(a), cy + r * math.sin(a)


def _f(p) -> str:
    return f"{p[0]:.2f},{p[1]:.2f}"


def _ring_arcs() -> str:
    arcs = []
    for start in (0, 90, 180, 270):
        p1, p2 = _pt(RING_R, start + RING_GAP_DEG), _pt(RING_R, start + 90 - RING_GAP_DEG)
        arcs.append(f'<path d="M{_f(p1)} A{RING_R},{RING_R} 0 0 1 {_f(p2)}"/>')
    return "".join(arcs)


def _star() -> tuple[str, str]:
    """(whole star, north point) as polygon point lists. The north point is
    drawn over the whole star, so there is no seam between the halves."""
    n, e, s, w = _pt(NORTH_R, 0), _pt(SIDE_R, 90), _pt(SIDE_R, 180), _pt(SIDE_R, 270)
    ne, se, sw, nw = (_pt(STAR_INNER, d) for d in (45, 135, 225, 315))
    c = (CENTER, CENTER)
    whole = " ".join(map(_f, (n, ne, e, se, s, sw, w, nw)))
    north = " ".join(map(_f, (n, ne, c, nw)))
    return whole, north


def mark_body(ring: str, star: str, heading: str) -> str:
    whole, north = _star()
    body = (f'<g fill="none" stroke="{ring}" stroke-width="{RING_W}" stroke-linecap="round">{_ring_arcs()}</g>'
            f'<polygon fill="{star}" points="{whole}"/>')
    if heading != star:                 # one-colour version: no separate heading shape
        body += f'<polygon fill="{heading}" points="{north}"/>'
    return body


def mark_svg(ring=COLORS.focus, star=COLORS.text_primary, heading=COLORS.accent) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
            + mark_body(ring, star, heading) + "</svg>\n")


def app_icon_svg() -> str:
    """1024 px canvas, macOS grid: an 824 px rounded plate (radius ~185)
    with a soft drop shadow; the mark's 64-unit square spans 78% of the plate."""
    plate, offset, radius = 824, 100, 185
    scale = plate * 0.78 / 64
    mark_offset = 512 - 32 * scale
    shadow = "".join(
        f'<rect x="{offset - i}" y="{offset + 12 - i + i * 0.6:.1f}" width="{plate + 2 * i}" height="{plate + 2 * i}" '
        f'rx="{radius + i}" fill="#000" fill-opacity="{0.06 - i * 0.0035:.4f}"/>'
        for i in range(0, 16, 2))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<defs>
  <linearGradient id="plate" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{COLORS.focus_soft}"/>
    <stop offset="1" stop-color="{COLORS.bg_window}"/>
  </linearGradient>
  <radialGradient id="glow" cx="0.5" cy="0.42" r="0.55">
    <stop offset="0" stop-color="{COLORS.focus}" stop-opacity="0.16"/>
    <stop offset="1" stop-color="{COLORS.focus}" stop-opacity="0"/>
  </radialGradient>
</defs>
{shadow}
<rect x="{offset}" y="{offset}" width="{plate}" height="{plate}" rx="{radius}" fill="url(#plate)"/>
<rect x="{offset}" y="{offset}" width="{plate}" height="{plate}" rx="{radius}" fill="url(#glow)"/>
<rect x="{offset + 1.5}" y="{offset + 1.5}" width="{plate - 3}" height="{plate - 3}" rx="{radius - 1.5}"
      fill="none" stroke="#ffffff" stroke-opacity="0.09" stroke-width="3"/>
<g transform="translate({mark_offset:.2f},{mark_offset:.2f}) scale({scale:.4f})">{mark_body(COLORS.focus, COLORS.text_primary, COLORS.accent)}</g>
</svg>
'''


ICONSET = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2)]


def build_icns(svg_path: Path) -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 -- needed for QPainter/fonts
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise SystemExit(f"invalid SVG: {svg_path}")
    work = Path(tempfile.mkdtemp(prefix="appicon_"))
    iconset = work / "AppIcon.iconset"
    iconset.mkdir()
    try:
        for size, scale in ICONSET:
            px = size * scale
            image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            renderer.render(painter, QRectF(0, 0, px, px))
            painter.end()
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            if not image.save(str(iconset / name)):
                raise SystemExit(f"could not write {name}")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ICNS)], check=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    (BRAND_DIR / "waypoint_rose.svg").write_text(mark_svg())
    (BRAND_DIR / "waypoint_rose_mono.svg").write_text(
        mark_svg("currentColor", "currentColor", "currentColor"))
    (BRAND_DIR / "app_icon.svg").write_text(app_icon_svg())
    build_icns(BRAND_DIR / "app_icon.svg")
    print("wrote", *sorted(p.name for p in BRAND_DIR.iterdir()), ICNS.relative_to(ROOT))


if __name__ == "__main__":
    main()
