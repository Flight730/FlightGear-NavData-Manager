"""The app's mark and application icon: assets render, the sidebar uses
the mark, the packaged icon exists with every macOS size, and the Lucide
icon set is untouched."""

import subprocess
from pathlib import Path

from PySide6.QtWidgets import QLabel

from flightgear_navdata_manager.presentation.theme import brand, icons

ROOT = Path(__file__).resolve().parents[2]
ICNS = ROOT / "packaging" / "AppIcon.icns"
SPEC = ROOT / "packaging" / "FlightGear NavData Manager.spec"


def test_brand_assets_render(qapp):
    for svg in ("waypoint_rose.svg", "waypoint_rose_mono.svg", "app_icon.svg"):
        assert (brand.BRAND_DIR / svg).exists(), svg
    pm = brand.mark_pixmap(22, 2)
    assert (pm.width(), pm.devicePixelRatio()) == (44, 2.0)
    image = pm.toImage()
    assert any(image.pixelColor(x, y).alpha() for x in range(44) for y in range(44))
    assert not brand.app_icon().isNull()


def test_mono_mark_is_one_colour():
    text = (brand.BRAND_DIR / "waypoint_rose_mono.svg").read_text()
    assert "#" not in text and "currentColor" in text


def test_sidebar_tile_shows_the_mark_not_the_plane(make_window):
    window = make_window()
    tiles = [lbl for lbl in window.sidebar.findChildren(QLabel) if lbl.property("iconTile") == "small"]
    assert len(tiles) == 1
    shown = tiles[0].pixmap().toImage()
    assert shown == brand.mark_pixmap(22, 2).toImage()
    assert shown != icons.pixmap("plane", "#e8efff", 18, 2).toImage()


def test_lucide_icons_unchanged():
    assert len(icons.available()) == 30 and "plane" in icons.available()
    assert not any("rose" in name or "app_icon" in name for name in icons.available())


def test_icns_has_every_size(tmp_path):
    assert ICNS.exists()
    subprocess.run(["iconutil", "-c", "iconset", str(ICNS), "-o", str(tmp_path / "x.iconset")], check=True)
    names = {p.name for p in (tmp_path / "x.iconset").iterdir()}
    for size in (16, 32, 128, 256, 512):
        assert {f"icon_{size}x{size}.png", f"icon_{size}x{size}@2x.png"} <= names, size


def test_spec_uses_the_icon():
    spec = SPEC.read_text()
    assert 'APP_ICON = os.path.join(SPECPATH, "AppIcon.icns")' in spec and "icon=APP_ICON," in spec
