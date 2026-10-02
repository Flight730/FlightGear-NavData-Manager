"""The application style sheet, generated from tokens.

Widgets opt into variants with dynamic properties instead of per-widget
style sheets, e.g.:

    button.setProperty("variant", "primary")    # primary | secondary | ghost | danger
    label.setProperty("role", "secondary")      # pageTitle | cardTitle | secondary | tertiary | mono | ...
    frame.setProperty("card", True)

`images` maps the few glyphs the style sheet needs as files (arrows,
check marks) to recolored SVG paths -- see icons.write_recolored().
"""

from __future__ import annotations

from pathlib import Path

from .tokens import COLORS as C
from .tokens import CONTROL_HEIGHT, FONT, RADIUS, SPACING

# (key, icon name, color) for every image the style sheet references.
IMAGES = [
    ("chevron_down", "chevron-down", C.text_secondary),
    ("chevron_up", "chevron-up", C.text_secondary),
    ("chevron_down_disabled", "chevron-down", C.text_tertiary),
    ("chevron_up_disabled", "chevron-up", C.text_tertiary),
    ("check", "check", C.text_on_accent),
]


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def _tone_rules() -> str:
    tones = {
        "success": (C.accent, C.accent_soft),
        "warning": (C.warning, C.warning_soft),
        "danger": (C.danger, C.danger_soft),
        "info": (C.info, C.info_soft),
        "neutral": (C.text_secondary, C.surface_raised),
    }
    rules = []
    for tone, (fg, bg) in tones.items():
        rules.append(
            f'QLabel[pill="{tone}"] {{ color: {fg}; background: {bg}; '
            f'border: 1px solid {_rgba(fg, 0.35)}; border-radius: 9px; '
            f'padding: 1px 9px; font-size: {FONT.small}px; font-weight: 600; }}'
        )
        rules.append(
            f'QFrame[banner="{tone}"] {{ background: {bg}; '
            f'border: 1px solid {_rgba(fg, 0.35)}; border-radius: {RADIUS.md}px; }}'
        )
    return "\n".join(rules)


def build_qss(images: dict[str, Path]) -> str:
    url = {key: Path(p).as_posix() for key, p in images.items()}
    control_inner = CONTROL_HEIGHT - 2   # minus the 1px border, top and bottom
    return f"""
/* ---- Base ------------------------------------------------------------ */
QWidget {{
    color: {C.text_primary};
    font-size: {FONT.body}px;
}}
QMainWindow, QDialog, QMessageBox, QInputDialog {{
    background: {C.bg_content};
}}
QLabel {{ background: transparent; }}
QLabel[role="pageTitle"] {{ font-size: {FONT.page_title}px; font-weight: 600; }}
QLabel[role="cardTitle"] {{ font-size: {FONT.card_title}px; font-weight: 600; }}
QLabel[role="secondary"] {{ color: {C.text_secondary}; }}
QLabel[role="tertiary"] {{ color: {C.text_tertiary}; font-size: {FONT.small}px; }}
QLabel[role="small"] {{ color: {C.text_secondary}; font-size: {FONT.small}px; }}
QLabel[role="mono"] {{ font-family: "{FONT.mono_family}"; font-size: {FONT.small}px; color: {C.text_secondary}; }}
QLabel[role="stat"] {{ font-size: {FONT.stat}px; font-weight: 600; }}
QLabel[role="statText"] {{ font-size: 22px; font-weight: 600; }}
QLabel[role="statLabel"] {{ color: {C.text_secondary}; font-size: {FONT.small}px; font-weight: 600; }}
QLabel[role="fieldKey"] {{ color: {C.text_secondary}; }}
QLabel[role="fieldValue"] {{ font-family: "{FONT.mono_family}"; font-size: {FONT.small}px; }}
QLabel[role="fieldValueMissing"] {{ color: {C.text_tertiary}; }}
QLabel[role="headline"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="fieldLabel"] {{ font-weight: 600; }}
QLabel[role="helper"] {{ color: {C.text_tertiary}; font-size: {FONT.small}px; }}
QLabel[role="sectionTitle"] {{
    color: {C.text_secondary};
    font-size: {FONT.small}px;
    font-weight: 600;
    margin-top: 4px;   /* section_title() sets indent 0: any box gives a QLabel an automatic indent */
}}
QToolTip {{
    background: {C.surface_raised};
    color: {C.text_primary};
    border: 1px solid {C.border_strong};
    border-radius: {RADIUS.sm}px;
    padding: 4px 8px;
}}

/* ---- Cards ------------------------------------------------------------- */
QFrame[card="true"] {{
    background: {C.surface_card};
    border: 1px solid {C.border};
    border-radius: {RADIUS.lg}px;
}}
QGroupBox {{
    background: {C.surface_card};
    border: 1px solid {C.border};
    border-radius: {RADIUS.lg}px;
    margin-top: 0px;
    padding: 44px {SPACING.xl - 4}px {SPACING.xl - 4}px {SPACING.xl - 4}px;
    font-size: {FONT.card_title}px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: {SPACING.xl - 4}px;
    top: {SPACING.lg + 2}px;
    color: {C.text_primary};
}}
QGroupBox QLabel {{ font-size: {FONT.body}px; font-weight: 400; }}

/* ---- Status pills and inline banners ------------------------------ */
{_tone_rules()}
QFrame[banner] QLabel {{ background: transparent; }}
QLabel[chip="true"] {{
    color: {C.text_secondary};
    background: {C.surface_inset};
    border: 1px solid {C.border_strong};
    border-radius: {RADIUS.sm}px;
    padding: 2px 8px;
    font-size: {FONT.small}px;
    font-weight: 500;
}}

/* ---- Buttons ----------------------------------------------------------- */
QPushButton {{
    background: {C.surface_raised};
    color: {C.text_primary};
    border: 1px solid {C.border_strong};
    border-radius: {RADIUS.md}px;
    padding: 0px 14px;
    min-height: {control_inner}px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {C.surface_pressed}; border-color: {C.text_tertiary}; }}
QPushButton:pressed {{ background: {C.surface_card}; }}
QPushButton:focus {{ border-color: {C.focus}; }}
QPushButton:disabled {{ color: {C.text_tertiary}; background: {C.surface_card}; border-color: {C.border}; }}

QPushButton[variant="primary"] {{
    background: {C.accent};
    color: {C.text_on_accent};
    border: 1px solid {C.accent};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background: {C.accent_hover}; border-color: {C.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {C.accent_pressed}; border-color: {C.accent_pressed}; }}
QPushButton[variant="primary"]:focus {{ border-color: {C.text_primary}; }}
QPushButton[variant="primary"]:disabled {{
    background: {C.surface_raised}; color: {C.text_tertiary}; border-color: {C.border};
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {C.text_secondary};
}}
QPushButton[variant="ghost"]:hover {{ background: {C.surface_raised}; color: {C.text_primary}; }}
QPushButton[variant="ghost"]:focus {{ border-color: {C.focus}; }}

QPushButton[variant="link"] {{
    background: transparent;
    border: none;
    color: {C.focus};
    padding: 0px 2px;
    min-height: 0px;
}}
QPushButton[variant="link"]:hover {{ color: {C.text_primary}; text-decoration: underline; }}

QPushButton[variant="danger"] {{
    background: transparent;
    color: {C.danger};
    border: 1px solid {C.danger};
}}
QPushButton[variant="danger"]:hover {{ background: {C.danger_soft}; }}

/* Segmented control (e.g. NDB | VOR | DME). */
QFrame#Segmented {{
    background: {C.surface_inset};
    border: 1px solid {C.border};
    border-radius: {RADIUS.md}px;
}}
QPushButton[segment="true"] {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {RADIUS.sm}px;
    color: {C.text_secondary};
    min-height: 26px;
    padding: 0px 16px;
    font-weight: 600;
}}
QPushButton[segment="true"]:hover {{ color: {C.text_primary}; background: {C.surface_raised}; }}
QPushButton[segment="true"]:checked {{
    color: {C.text_primary};
    background: {C.focus_soft};
    border-color: {_rgba(C.focus, 0.6)};
}}
QPushButton[segment="true"]:focus {{ border-color: {C.focus}; }}

/* Dialog buttons: the default (Enter) button gets the focus ring color. */
QDialogButtonBox QPushButton {{ min-width: 84px; }}
QDialogButtonBox QPushButton:default {{ border-color: {C.focus}; }}

/* ---- Text inputs ------------------------------------------------------- */
QLineEdit, QAbstractSpinBox, QComboBox {{
    background: {C.surface_inset};
    color: {C.text_primary};
    border: 1px solid {C.border};
    border-radius: {RADIUS.md}px;
    padding: 0px 10px;
    min-height: {control_inner}px;
    selection-background-color: {C.focus_soft};
    selection-color: {C.text_primary};
}}
QLineEdit:hover, QAbstractSpinBox:hover, QComboBox:hover {{ border-color: {C.border_strong}; }}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {{ border-color: {C.focus}; }}
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {{
    color: {C.text_tertiary}; background: {C.bg_content};
}}
QLineEdit[readOnly="true"] {{ color: {C.text_secondary}; }}
QLineEdit[role="path"] {{ font-family: "{FONT.mono_family}"; font-size: {FONT.small}px; }}
QLineEdit[invalid="true"], QAbstractSpinBox[invalid="true"] {{ border-color: {C.danger}; }}

QAbstractSpinBox {{ padding-right: 24px; }}
QAbstractSpinBox[arrows="false"] {{ padding-right: 10px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border;
    width: 22px;
    border: none;
    background: transparent;
}}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; margin: 3px 3px 0px 0px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0px 3px 3px 0px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
    background: {C.surface_raised}; border-radius: 4px;
}}
QAbstractSpinBox::up-arrow {{ image: url("{url['chevron_up']}"); width: 11px; height: 11px; }}
QAbstractSpinBox::down-arrow {{ image: url("{url['chevron_down']}"); width: 11px; height: 11px; }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{ image: url("{url['chevron_up_disabled']}"); }}
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{
    image: url("{url['chevron_down_disabled']}");
}}

QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    border: none;
}}
QComboBox::down-arrow {{ image: url("{url['chevron_down']}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {C.surface_card};
    border: 1px solid {C.border_strong};
    border-radius: {RADIUS.md}px;
    padding: 4px;
    outline: none;
    selection-background-color: {C.focus_soft};
    selection-color: {C.text_primary};
}}

QTextEdit, QPlainTextEdit {{
    background: {C.surface_inset};
    color: {C.text_primary};
    border: 1px solid {C.border};
    border-radius: {RADIUS.md}px;
    padding: 8px 10px;
    selection-background-color: {C.focus_soft};
    selection-color: {C.text_primary};
}}
QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {C.focus}; }}
QTextEdit[role="log"] {{ font-family: "{FONT.mono_family}"; font-size: {FONT.small}px; }}

/* ---- Check boxes (stand-alone and in tables) ------------------------- */
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QTableView::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {C.border_strong};
    border-radius: 4px;
    background: {C.surface_inset};
}}
QCheckBox::indicator:hover, QTableView::indicator:hover {{ border-color: {C.focus}; }}
QCheckBox::indicator:checked, QTableView::indicator:checked {{
    background: {C.accent};
    border-color: {C.accent};
    image: url("{url['check']}");
}}

/* ---- Shell: sidebar and page frame ---------------------------------- */
QFrame#Sidebar {{
    background: {C.bg_sidebar};
    border: none;
    border-right: 1px solid {C.border_subtle};
}}
QFrame#SidebarFooter {{ background: transparent; border: none; border-top: 1px solid {C.border_subtle}; }}
QLabel[role="navGroup"] {{
    color: {C.text_tertiary};
    font-size: 11px;
    font-weight: 600;
    padding-left: 12px;
}}
QLabel[role="brandTitle"] {{ font-size: 13px; font-weight: 600; }}
QLabel[role="brandSubtitle"] {{ font-size: 11px; color: {C.text_tertiary}; }}
QLabel[role="footerTitle"] {{ font-size: 12px; font-weight: 500; color: {C.text_secondary}; }}
QLabel[iconTile="small"], QLabel[iconTile="page"] {{
    background: {C.surface_card};
    border: 1px solid {C.border};
    border-radius: {RADIUS.md}px;
}}
QLabel[iconTile="page"] {{ border-radius: 10px; }}
QLabel[statusDot="ok"] {{ background: {C.accent}; border-radius: 4px; }}
QLabel[statusDot="warn"] {{ background: {C.warning}; border-radius: 4px; }}
QFrame#PageDivider {{ background: {C.border_subtle}; border: none; }}
QScrollArea#PageScroll, QScrollArea#PageScroll > QWidget > QWidget {{ background: {C.bg_content}; }}

/* ---- Tables ------------------------------------------------------------ */
QTableView {{
    background: {C.surface_inset};
    alternate-background-color: {C.surface_inset};
    border: 1px solid {C.border};
    border-radius: {RADIUS.lg}px;
    gridline-color: {C.border_subtle};
    selection-background-color: {C.focus_soft};
    selection-color: {C.text_primary};
    outline: none;
}}
/* Row backgrounds (hover, selection) are painted by the record delegates. */
QTableView::item {{ padding: 0px; border: none; background: transparent; }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{
    background: {C.surface_card};
    color: {C.text_secondary};
    border: none;
    border-bottom: 1px solid {C.border};
    padding: 8px 10px;
    font-size: {FONT.small}px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {C.surface_card}; border: none; }}

/* ---- Scroll bars (thin, no arrows) ----------------------------------- */
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {C.border_strong}; border-radius: 3px; }}
QScrollBar::handle:hover {{ background: {C.text_tertiary}; }}
QScrollBar::handle:vertical {{ min-height: 32px; }}
QScrollBar::handle:horizontal {{ min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ---- Menus and item lists -------------------------------------------- */
QMenu {{
    background: {C.surface_card};
    border: 1px solid {C.border_strong};
    border-radius: {RADIUS.md}px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 14px; border-radius: {RADIUS.sm}px; }}
QMenu::item:selected {{ background: {C.focus_soft}; }}
QListView, QListWidget {{
    background: {C.surface_inset};
    border: 1px solid {C.border};
    border-radius: {RADIUS.md}px;
    outline: none;
    selection-background-color: {C.focus_soft};
    selection-color: {C.text_primary};
}}

/* ---- Dialogs ----------------------------------------------------------- */
/* No min-width here: it makes QMessageBox turn off word wrap and clip
   long messages (e.g. the delete confirmation). */
QMessageBox QLabel#qt_msgbox_label {{ font-size: 14px; font-weight: 400; }}
QMessageBox QLabel#qt_msgbox_label[msgRole="headline"] {{ font-size: {FONT.card_title}px; font-weight: 600; }}
QMessageBox QLabel#qt_msgbox_informativelabel {{ color: {C.text_secondary}; }}
"""
