"""Colors, typography and widget styles for the desktop app.

The module owns every color decision: each theme starts from a base palette,
then the accent color (fixed or user-chosen) is blended into soft fills and
readable button text. :func:`build_stylesheet` produces the full Qt style
sheet; the display scale only touches typography and button padding.
"""

from __future__ import annotations

import re
from pathlib import Path

from silknet.config import DEFAULT_DARK_ACCENT, AppSettings

#: Themes whose colors follow the user-selected accent.
_ACCENT_THEMES = frozenset({"dark", "light"})
_FONT_STACK = "'Sora', 'Segoe UI Variable Text', 'Segoe UI', 'Noto Sans', sans-serif"
_DISPLAY_FONT_STACK = "'Sora', 'Segoe UI Variable Display', 'Segoe UI', 'Noto Sans', sans-serif"
_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"

#: Last theme colors used to build the application stylesheet. Combo popups are
#: top-level windows that do not inherit the application sheet on every
#: platform, so they are styled directly from this snapshot when they open.
_ACTIVE_COLORS: dict[str, str] | None = None


_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "window": "#F4F3F7",
        "sidebar": "#ECEBF1",
        "surface": "#FFFFFF",
        "surface_alt": "#F7F6FA",
        "border": "#DEDCE5",
        "text": "#1F1D25",
        "muted": "#615E69",
        "subtle": "#8A8792",
        "input": "#FFFFFF",
        "status": "#ECEBF1",
    },
    "pink": {
        "window": "#FFF4F8",
        "sidebar": "#FFE8F1",
        "surface": "#FFFFFF",
        "surface_alt": "#FFEFF5",
        "border": "#F4C3D5",
        "text": "#472733",
        "muted": "#8C5F70",
        "subtle": "#B4879A",
        "input": "#FFFFFF",
        "status": "#FFE8F1",
        "accent": "#EF7FA6",
    },
    "dark": {
        "window": "#141619",
        "sidebar": "#101215",
        "surface": "#1E2126",
        "surface_alt": "#262A30",
        "border": "#343A43",
        "text": "#F1F2F5",
        "muted": "#A9AEB8",
        "subtle": "#7F8791",
        "input": "#191C21",
        "status": "#101215",
    },
    "dark-red": {
        "window": "#1B1517",
        "sidebar": "#161113",
        "surface": "#251D20",
        "surface_alt": "#2E2427",
        "border": "#463639",
        "text": "#F2EAE9",
        "muted": "#B7A5A4",
        "subtle": "#8B7675",
        "input": "#211A1C",
        "status": "#161113",
        "accent": "#A45158",
    },
    "dark-purple": {
        "window": "#1B1720",
        "sidebar": "#16121B",
        "surface": "#241F2B",
        "surface_alt": "#2D2735",
        "border": "#443A50",
        "text": "#F0EBF5",
        "muted": "#B3A8BF",
        "subtle": "#867A94",
        "input": "#201B27",
        "status": "#16121B",
        "accent": "#805AA7",
    },
    "dark-green": {
        "window": "#151B17",
        "sidebar": "#111612",
        "surface": "#1D251F",
        "surface_alt": "#252E27",
        "border": "#37453B",
        "text": "#EAF2EC",
        "muted": "#A6B4AA",
        "subtle": "#7B8A80",
        "input": "#1A211C",
        "status": "#111612",
        "accent": "#5E9A72",
    },
}


def _to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, channel)) for channel in rgb))


def _blend(base: str, overlay: str, amount: float) -> str:
    """Mix ``overlay`` into ``base`` (0.0 keeps base, 1.0 returns overlay)."""
    amount = max(0.0, min(1.0, amount))
    base_rgb, overlay_rgb = _to_rgb(base), _to_rgb(overlay)
    mixed = tuple(
        round(base_channel * (1 - amount) + overlay_channel * amount)
        for base_channel, overlay_channel in zip(base_rgb, overlay_rgb, strict=True)
    )
    return _to_hex(mixed)


def _relative_luminance(color: str) -> float:
    channels = []
    for value in _to_rgb(color):
        channel = value / 255
        channels.append(
            channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _readable_text(background: str) -> str:
    """Pick ink or white text for the given background color."""
    return "#10141B" if _relative_luminance(background) > 0.32 else "#FFFFFF"


def _palette_for(settings: AppSettings) -> dict[str, str]:
    palette = dict(_PALETTES[settings.theme])
    light = settings.theme in {"light", "pink"}
    if settings.theme in _ACCENT_THEMES:
        accent = settings.accent_color or DEFAULT_DARK_ACCENT
    else:
        accent = palette["accent"]

    surface = palette["surface"]
    palette["accent"] = accent
    palette["accent_text"] = _readable_text(accent)
    palette["accent_soft"] = _blend(surface, accent, 0.16 if light else 0.26)
    palette["selection"] = _blend(surface, accent, 0.22 if light else 0.34)
    palette["accent_hover"] = _blend(accent, "#FFFFFF" if not light else "#000000", 0.12)
    palette["accent_pressed"] = _blend(accent, "#000000", 0.12 if not light else 0.08)
    palette["danger"] = "#B4453F" if light else "#E68A85"
    palette["canvas"] = palette["window"]
    palette["theme"] = settings.theme
    palette["verified"] = "#3F7F55" if light else "#7DC492"
    palette["disputed"] = "#B24A4A" if light else "#E58E8E"
    palette["inferred"] = "#96701F" if light else "#DCB675"
    return palette


def theme_colors(settings: AppSettings | None = None) -> dict[str, str]:
    """Resolved palette for custom-painted graph and pet surfaces."""
    return _palette_for(settings or AppSettings())


def graph_colors(settings: AppSettings | None = None) -> dict[str, str]:
    """Colors used by the graph and family canvases."""
    active = settings or AppSettings()
    palette = _palette_for(active)
    return {
        "theme": palette["theme"],
        "window": palette["window"],
        "canvas": palette["canvas"],
        "surface": palette["surface"],
        "surface_alt": palette["surface_alt"],
        "border": palette["border"],
        "text": palette["text"],
        "muted": palette["muted"],
        "accent": palette["accent"],
        "accent_text": palette["accent_text"],
        "accent_soft": palette["accent_soft"],
        "selection": palette["selection"],
        "verified": palette["verified"],
        "disputed": palette["disputed"],
        "inferred": palette["inferred"],
    }


def active_theme_colors() -> dict[str, str]:
    """Return the colors used by the most recently built application sheet."""
    return dict(_ACTIVE_COLORS or _palette_for(AppSettings()))


def combo_popup_stylesheet(colors: dict[str, str] | None = None) -> str:
    """Style the custom combo popup panel and its list.

    The popup is a translucent, frameless window owned by ``ComboBox``. The
    panel supplies the only visible surface, so Qt cannot draw a white native
    combo frame around it. The list stays transparent and its rows are painted
    by ``ComboItemDelegate``.
    """
    palette = dict(colors or active_theme_colors())
    return f"""
    QFrame#comboPopupPanel {{
        background: {palette["surface_alt"]};
        border: 1px solid {palette["border"]};
        border-radius: 12px;
    }}
    QListView#comboPopup {{
        background: transparent;
        color: {palette["text"]};
        border: none;
        outline: none;
        padding: 5px;
    }}
    QListView#comboPopup QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 4px 2px;
    }}
    QListView#comboPopup QScrollBar::handle:vertical {{
        background: {palette["border"]};
        border-radius: 5px;
        min-height: 26px;
    }}
    QListView#comboPopup QScrollBar::handle:vertical:hover {{
        background: {palette["subtle"]};
    }}
    QListView#comboPopup QScrollBar::add-line:vertical,
    QListView#comboPopup QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QListView#comboPopup QScrollBar::add-page:vertical,
    QListView#comboPopup QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    """


def _scale_stylesheet(stylesheet: str, ui_scale: float) -> str:
    """Scale typography and button padding without changing the layout frame.

    Window geometry, margins, cards, icons and controls keep their fixed sizes.
    Only font sizes and the padding/minimum widths of push buttons follow the
    preference, so a smaller setting cannot make the app reflow or grow.
    """
    if ui_scale == 1.0:
        return stylesheet

    def scale_font(match: re.Match[str]) -> str:
        value = float(match.group("value")) * ui_scale
        return f"{match.group('prefix')}{value:g}pt"

    stylesheet = re.sub(
        r"(?P<prefix>font-size:\s*)(?P<value>\d+(?:\.\d+)?)pt\b",
        scale_font,
        stylesheet,
    )

    def scale_button_block(match: re.Match[str]) -> str:
        block = match.group(0)

        def scale_padding(padding: re.Match[str]) -> str:
            values = [
                f"{float(value) * ui_scale:g}px"
                for value in re.findall(r"\d+(?:\.\d+)?", padding.group("values"))
            ]
            return f"{padding.group('prefix')}{' '.join(values)};"

        block = re.sub(
            r"(?P<prefix>padding:\s*)(?P<values>\d+(?:\.\d+)?px(?:\s+\d+(?:\.\d+)?px)*);",
            scale_padding,
            block,
        )
        block = re.sub(
            r"(?P<prefix>min-width:\s*)(?P<value>\d+(?:\.\d+)?)px",
            lambda match: f"{match.group('prefix')}{float(match.group('value')) * ui_scale:g}px",
            block,
        )
        return block

    return re.sub(
        r"(?s)[^{}]*QPushButton[^{}]*\{[^{}]*\}",
        scale_button_block,
        stylesheet,
    )


def build_stylesheet(settings: AppSettings) -> str:
    global _ACTIVE_COLORS
    colors = _palette_for(settings)
    _ACTIVE_COLORS = dict(colors)
    light = settings.theme in {"light", "pink"}
    arrow_file = "chevron-dark.png" if light else "chevron-light.png"
    arrow_url = (_ASSET_DIR / arrow_file).as_posix()
    stylesheet = f"""
    QMainWindow {{ background: transparent; }}
    QWidget#appRoot {{
        background: transparent;
        color: {colors["text"]};
        font-family: {_FONT_STACK};
        font-size: 10.5pt;
        font-weight: 600;
    }}
    QDialog, QMessageBox, QInputDialog {{
        background: {colors["window"]};
        color: {colors["text"]};
        font-family: {_FONT_STACK};
        font-size: 10.5pt;
        font-weight: 600;
    }}
    QMenu {{
        background: {colors["surface"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: 10px;
        padding: 6px;
        font-size: 10pt;
        font-weight: 600;
    }}
    QMenu::item {{ padding: 8px 22px; border-radius: 7px; }}
    QMenu::item:selected {{ background: {colors["selection"]}; }}
    QWidget#sidebar {{
        background: {colors["sidebar"]};
        border-right: 1px solid {colors["border"]};
        border-top-left-radius: 24px;
    }}
    QWidget#mainArea {{
        background: {colors["window"]};
        border-top-right-radius: 24px;
        border-bottom-right-radius: 24px;
    }}
    QWidget#appRoot {{ background: transparent; }}
    QWidget#topBar {{
        background: {colors["window"]};
        border-bottom: 1px solid {colors["border"]};
        border-top-right-radius: 24px;
    }}
    QWidget#sidebar[immersive="true"] {{
        border-top-left-radius: 0;
    }}
    QWidget#mainArea[immersive="true"] {{
        border-top-right-radius: 0;
        border-bottom-right-radius: 0;
    }}
    QWidget#topBar[immersive="true"] {{
        border-top: 1px solid {colors["accent"]};
        border-top-right-radius: 0;
    }}
    QLabel {{ color: {colors["text"]}; background: transparent; }}
    QLabel#brandLogo {{ background: transparent; border-radius: 12px; }}
    QLabel#brandName {{
        font-family: {_DISPLAY_FONT_STACK};
        font-size: 14pt;
        font-weight: 900;
        letter-spacing: 1px;
    }}
    QLabel#brandCaption {{ color: {colors["muted"]}; font-size: 9.5pt; font-weight: 600; }}
    QLabel#workspaceCaption {{
        color: {colors["subtle"]};
        font-size: 9pt;
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#localBadge {{
        color: {colors["muted"]};
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 12px;
        padding: 7px 12px;
        font-size: 9pt;
        font-weight: 700;
    }}
    QLabel#sidebarFooter {{ color: {colors["subtle"]}; font-size: 9pt; }}
    QLabel#pageTitle {{ font-size: 13pt; font-weight: 800; }}
    QLabel#pageEyebrow {{
        color: {colors["accent"]};
        font-size: 9pt;
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#pageHeading {{
        font-family: {_DISPLAY_FONT_STACK};
        font-size: 24pt;
        font-weight: 800;
    }}
    QLabel#pageHeadingCompact {{
        font-family: {_DISPLAY_FONT_STACK};
        font-size: 18.5pt;
        font-weight: 800;
    }}
    QLabel#entityDetailName {{
        font-family: {_DISPLAY_FONT_STACK};
        font-size: 22pt;
        font-weight: 800;
    }}
    QLabel#pageDescription {{ color: {colors["muted"]}; font-size: 10.5pt; font-weight: 600; }}
    QLabel#pageDescriptionCompact {{
        color: {colors["muted"]};
        font-size: 9.5pt;
        font-weight: 600;
    }}
    QLabel#dialogHeading {{
        font-family: {_DISPLAY_FONT_STACK};
        font-size: 17pt;
        font-weight: 800;
    }}
    QLabel#emptyTitle {{ font-size: 16pt; font-weight: 800; }}
    QLabel#emptyDescription {{ color: {colors["muted"]}; font-size: 10.5pt; }}
    QLabel#mutedText {{ color: {colors["muted"]}; font-size: 10pt; }}
    QLabel#subtleText {{ color: {colors["subtle"]}; font-size: 9.5pt; }}
    QLabel#graphEmptyHint {{
        color: {colors["muted"]};
        font-size: 11pt;
        font-weight: 600;
        background: transparent;
    }}
    QLabel#graphRemoveHint {{
        color: {colors["text"]};
        background: {colors["surface"]};
        border: 1px solid {colors["accent"]};
        border-radius: 12px;
        padding: 8px 14px;
        font-size: 9.5pt;
        font-weight: 700;
    }}
    QLabel#graphDetailTitle {{
        font-family: {_DISPLAY_FONT_STACK};
        font-size: 15pt;
        font-weight: 800;
    }}
    QLabel#statValue {{
        font-family: {_DISPLAY_FONT_STACK};
        font-size: 26pt;
        font-weight: 800;
    }}
    QLabel#statLabel {{
        color: {colors["muted"]};
        font-size: 9.5pt;
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#cardTitle {{ font-size: 12.5pt; font-weight: 800; }}
    QLabel#cardDescription {{ color: {colors["muted"]}; font-size: 10.5pt; font-weight: 600; }}
    QLabel#sectionLabel {{
        color: {colors["subtle"]};
        font-size: 9.5pt;
        font-weight: 800;
        letter-spacing: 1px;
    }}
    QLabel#settingValue {{ color: {colors["accent"]}; font-weight: 800; }}
    QLabel#detailChip {{
        color: {colors["text"]};
        background: {colors["accent_soft"]};
        border: 1px solid {colors["accent"]};
        border-radius: 8px;
        padding: 3px 9px;
        font-size: 8.5pt;
        font-weight: 800;
    }}
    QLabel#detailSocial {{
        color: {colors["muted"]};
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 12px;
        padding: 10px 12px;
        font-size: 9.5pt;
        font-weight: 600;
    }}
    QLabel#imagePreview {{
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 16px;
    }}
    QLabel#detailAvatar {{
        background: transparent;
        border: none;
    }}
    QLabel#platformMark {{ background: transparent; }}
    QPushButton {{
        color: {colors["text"]};
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 11px;
        padding: 9px 16px;
        font-size: 10.5pt;
        font-weight: 700;
    }}
    QPushButton:hover {{ border-color: {colors["accent"]}; }}
    QPushButton:pressed {{ background: {colors["selection"]}; }}
    QPushButton:disabled {{ color: {colors["subtle"]}; }}
    QPushButton#navButton {{
        color: {colors["muted"]};
        background: transparent;
        border: none;
        border-left: 3px solid transparent;
        border-radius: 12px;
        padding: 12px 14px;
        text-align: left;
        font-size: 10.5pt;
        font-weight: 700;
    }}
    QPushButton#navButton:hover {{
        color: {colors["text"]};
        background: {colors["surface_alt"]};
    }}
    QPushButton#navButton:checked {{
        color: {colors["text"]};
        background: {colors["accent_soft"]};
        border-left-color: {colors["accent"]};
        font-weight: 700;
    }}
    QPushButton#actionButton {{
        color: {colors["accent_text"]};
        background: {colors["accent"]};
        border: 1px solid {colors["accent"]};
        border-radius: 12px;
        padding: 10px 18px;
        font-size: 10.5pt;
        font-weight: 800;
    }}
    QPushButton#actionButton:hover {{
        background: {colors["accent_hover"]};
        border-color: {colors["accent_hover"]};
    }}
    QPushButton#actionButton:pressed {{ background: {colors["accent_pressed"]}; }}
    QPushButton#actionButton:disabled {{
        color: {colors["subtle"]};
        background: {colors["surface_alt"]};
        border-color: {colors["border"]};
    }}
    QPushButton#quietButton, QPushButton#dangerButton {{
        color: {colors["text"]};
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 11px;
        padding: 9px 15px;
        font-weight: 700;
    }}
    QPushButton#quietButton:hover {{ border-color: {colors["accent"]}; }}
    QPushButton#quietButton:checked {{
        color: {colors["accent_text"]};
        background: {colors["accent"]};
        border-color: {colors["accent"]};
    }}
    QPushButton#quietButton:checked:hover {{ background: {colors["accent_hover"]}; }}
    QPushButton#toolButton {{
        color: {colors["text"]};
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 9px;
        padding: 6px 10px;
        font-size: 9.5pt;
        font-weight: 700;
    }}
    QPushButton#toolButton:hover {{ border-color: {colors["accent"]}; }}
    QPushButton#toolButton:checked {{
        color: {colors["accent_text"]};
        background: {colors["accent"]};
        border-color: {colors["accent"]};
    }}
    QPushButton#toolButton:disabled {{ color: {colors["subtle"]}; }}
    QPushButton#toolAction {{
        color: {colors["accent_text"]};
        background: {colors["accent"]};
        border: 1px solid {colors["accent"]};
        border-radius: 9px;
        padding: 6px 12px;
        font-size: 9.5pt;
        font-weight: 800;
    }}
    QPushButton#toolAction:hover {{
        background: {colors["accent_hover"]};
        border-color: {colors["accent_hover"]};
    }}
    QFrame#graphToolbar {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 14px;
    }}
    QPushButton#dangerButton:hover {{
        color: {colors["danger"]};
        border-color: {colors["danger"]};
    }}
    QPushButton#windowControlButton, QPushButton#windowCloseButton {{
        color: {colors["muted"]};
        background: transparent;
        border: none;
        border-radius: 10px;
        padding: 0px;
        font-size: 13pt;
        font-weight: 800;
    }}
    QPushButton#windowControlButton:hover {{
        color: {colors["text"]};
        background: {colors["surface_alt"]};
    }}
    QPushButton#windowCloseButton:hover {{
        color: #FFFFFF;
        background: #D64545;
    }}
    QPushButton#workspaceCard {{
        color: {colors["text"]};
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 18px;
        text-align: left;
        padding: 18px 20px;
        font-weight: 700;
    }}
    QPushButton#workspaceCard:hover {{
        border-color: {colors["accent"]};
        background: {colors["surface_alt"]};
    }}
    QFrame#surfaceCard, QFrame#entityDetails {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 18px;
    }}
    QFrame#emptyCanvas {{
        background: {colors["surface"]};
        border: 1px dashed {colors["border"]};
        border-radius: 18px;
    }}
    QFrame#divider {{
        background: {colors["border"]};
        border: none;
        min-height: 1px;
        max-height: 1px;
    }}
    QStackedWidget#entityStack {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 18px;
    }}
    QGraphicsView {{
        background: {colors["canvas"]};
        border: 1px solid {colors["border"]};
        border-radius: 18px;
    }}
    QLineEdit, QTextEdit, QComboBox, QListWidget {{
        color: {colors["text"]};
        background: {colors["input"]};
        border: 1px solid {colors["border"]};
        border-radius: 11px;
        padding: 9px 12px;
        font-size: 10.5pt;
        selection-background-color: {colors["accent"]};
        selection-color: {colors["accent_text"]};
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QListWidget:focus {{
        border-color: {colors["accent"]};
    }}
    QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled {{ color: {colors["subtle"]}; }}
    QComboBox QAbstractItemView {{
        background: {colors["surface_alt"]};
        color: {colors["text"]};
        border: 1px solid {colors["border"]};
        border-radius: 10px;
        padding: 6px;
        outline: 0;
        selection-background-color: {colors["selection"]};
        selection-color: {colors["text"]};
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 26px;
        padding: 5px 8px;
        border-radius: 7px;
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {colors["selection"]};
        color: {colors["text"]};
    }}
    QComboBox QAbstractItemView::item:hover {{ background: {colors["input"]}; }}
    QComboBoxPrivateContainer {{
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 10px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 30px;
        subcontrol-origin: padding;
        subcontrol-position: center right;
    }}
    QComboBox::down-arrow {{
        image: url("{arrow_url}");
        width: 11px;
        height: 7px;
    }}
    QComboBox::down-arrow:on {{ top: 1px; }}
    QListWidget#entityList {{ padding: 8px; border: 1px solid {colors["border"]}; }}
    QListWidget#graphPalette {{ padding: 6px; border: 1px solid {colors["border"]}; }}
    QListWidget#entityList::item, QListWidget#graphPalette::item {{
        padding: 0px;
        margin: 0px;
        background: transparent;
        border: none;
    }}
    QListWidget#entityList::item:hover, QListWidget#entityList::item:selected {{
        background: transparent;
    }}
    QListWidget#graphPalette::item:hover, QListWidget#graphPalette::item:selected {{
        background: transparent;
    }}
    QListWidget#graphPalette::item {{ padding: 0px; }}
    QListWidget::item {{ padding: 9px; border-radius: 8px; }}
    QListWidget::item:hover {{ background: {colors["surface_alt"]}; }}
    QListWidget::item:selected {{ color: {colors["text"]}; background: {colors["selection"]}; }}
    QListWidget::item:disabled {{ color: {colors["subtle"]}; }}
    QSplitter::handle {{ background: transparent; width: 10px; height: 10px; }}
    QSplitter::handle:hover {{ background: {colors["border"]}; }}
    QRadioButton {{
        color: {colors["text"]};
        spacing: 10px;
        padding: 7px;
        font-size: 10.5pt;
        font-weight: 700;
    }}
    QRadioButton::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {colors["subtle"]};
        border-radius: 11px;
        background: {colors["surface"]};
    }}
    QRadioButton::indicator:hover {{ border-color: {colors["accent"]}; }}
    QRadioButton::indicator:checked {{
        border: 2px solid {colors["accent"]};
        background: qradialgradient(
            cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
            stop:0 {colors["surface"]}, stop:0.34 {colors["surface"]},
            stop:0.40 {colors["accent"]}, stop:1 {colors["accent"]}
        );
    }}
    QSlider::groove:horizontal {{
        height: 7px;
        background: {colors["border"]};
        border-radius: 4px;
    }}
    QSlider::sub-page:horizontal {{ background: {colors["accent"]}; border-radius: 4px; }}
    QSlider::handle:horizontal {{
        width: 20px;
        height: 20px;
        margin: -7px 0;
        border: 3px solid {colors["surface"]};
        border-radius: 10px;
        background: {colors["accent"]};
    }}
    QSlider::handle:horizontal:hover {{ background: {colors["accent_hover"]}; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{
        background: {colors["border"]};
        border-radius: 5px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {colors["subtle"]}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{
        background: {colors["border"]};
        border-radius: 5px;
        min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {colors["subtle"]}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QFrame#toast {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 14px;
    }}
    QLabel#toastText {{
        color: {colors["text"]};
        background: transparent;
        font-size: 10pt;
        font-weight: 700;
    }}
    QToolTip {{
        color: {colors["text"]};
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        padding: 7px 10px;
        font-size: 9.5pt;
        font-weight: 600;
    }}
    QDialogButtonBox QPushButton {{ min-width: 92px; }}
    """

    if settings.theme == "pink":
        stylesheet += f"""
        QWidget#sidebar {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1, stop:0 #FFE2EE, stop:1 #FFF1F7
            );
            border-right: 1px solid {colors["border"]};
        }}
        QWidget#mainArea {{ background: #FFF7FA; }}
        QWidget#topBar {{ background: #FFF7FA; }}
        QFrame#surfaceCard, QFrame#entityDetails, QFrame#emptyCanvas,
        QStackedWidget#entityStack {{
            background: #FFFFFF;
            border: 1px solid {colors["border"]};
        }}
        QPushButton#actionButton {{
            color: {colors["accent_text"]};
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1, stop:0 #F592B4, stop:1 #EC6F9B
            );
            border: 1px solid #E76A96;
        }}
        QPushButton#actionButton:hover {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1, stop:0 #F7A1C0, stop:1 #F07BA5
            );
            border-color: #F07BA5;
        }}
        QPushButton#actionButton:pressed {{ background: #E76692; }}
        QPushButton#navButton:checked {{
            background: #FFD9E7;
            border-left-color: #EF7FA6;
        }}
        QLabel#pageEyebrow {{ color: #E05C89; }}
        QLabel#brandCaption {{ color: #A5697F; }}
        QFrame#toast {{ background: #FFFAFC; border-color: #F1B7CB; }}
        QSlider::sub-page:horizontal, QSlider::handle:horizontal {{ background: #F48FB2; }}
        """

    return _scale_stylesheet(stylesheet, settings.ui_scale)
