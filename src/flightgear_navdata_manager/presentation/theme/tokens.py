"""Design tokens: the single source of truth for the app's colors, type
scale, spacing and corner radii. Everything visual (the stylesheet, the
palette, painted delegates, icons) reads from here.

Dark-only by design (MVP). The palette was sampled from the visual
reference: deep navy surfaces, muted blue-gray secondary text, a soft
periwinkle for selection/focus and a teal accent for primary actions and
"on" states.
"""

from __future__ import annotations

from types import SimpleNamespace

COLORS = SimpleNamespace(
    # Surfaces, darkest to lightest.
    bg_window="#060b17",
    bg_sidebar="#080c1c",
    bg_content="#040c18",
    surface_inset="#070e1a",     # inputs, log, table body
    surface_card="#0f1724",
    surface_raised="#141d2c",    # hover, active nav item
    surface_pressed="#1a2436",
    # Lines.
    border="#1f2837",
    border_strong="#2a3547",
    border_subtle="#121725",
    # Text.
    text_primary="#e8efff",
    text_secondary="#9097a6",
    text_tertiary="#5b6273",
    text_on_accent="#04121a",
    # Accents.
    accent="#1be3ad",            # primary actions, "on" states
    accent_hover="#4debc1",
    accent_pressed="#15b88c",
    accent_soft="#0f2a2a",       # tinted background for success banners
    focus="#7696e0",             # selection and keyboard focus
    focus_soft="#16213a",        # selected rows, active nav fill
    # Semantic.
    danger="#f0717a",
    danger_soft="#2a1219",
    warning="#e8b45a",
    warning_soft="#2a2012",
    info="#7696e0",
    info_soft="#121c33",
)

# Pixel sizes (Qt style sheets take px; on macOS 1px == 1pt).
FONT = SimpleNamespace(
    page_title=22,
    card_title=15,
    body=13,
    small=12,
    stat=28,
    mono_family="Menlo",          # SF Mono isn't exposed by name to Qt; Menlo is its sibling
)

SPACING = SimpleNamespace(xs=4, sm=8, md=12, lg=16, xl=24, xxl=32)

RADIUS = SimpleNamespace(sm=6, md=8, lg=12, pill=999)

CONTROL_HEIGHT = 34
