"""Serpentine3D dark theme: muted greys with a warm serpentine3d-gold accent."""

# viewport colors (linear-ish RGB floats)
from ..core.view_settings import BG_BOTTOM as VIEWPORT_BG_BOTTOM
from ..core.view_settings import BG_TOP as VIEWPORT_BG_TOP
# A text background is the drawing's own colour, the middle of its gradient,
# so it reads as a gap cut out of whatever lies behind the lettering.
TEXT_BACKGROUND = tuple((a + b) / 2 for a, b in zip(VIEWPORT_BG_TOP,
                                                    VIEWPORT_BG_BOTTOM))
GRID_MINOR = (1.0, 1.0, 1.0, 0.055)
GRID_MAJOR = (1.0, 1.0, 1.0, 0.11)
GRID_AXIS_X = (0.75, 0.33, 0.32, 0.85)
GRID_AXIS_Y = (0.38, 0.65, 0.36, 0.85)
# Plaster display: every surface one matte white, as a plaster model is,
# on a light ground of its own, so the grid turns dark to stay visible.
PLASTER_FILL = (0.93, 0.93, 0.92)
PLASTER_EDGE = (0.42, 0.42, 0.44, 1.0)
PLASTER_BG_TOP = (0.97, 0.97, 0.98)
PLASTER_BG_BOTTOM = (0.84, 0.85, 0.87)
PLASTER_GRID_MINOR = (0.0, 0.0, 0.0, 0.06)
PLASTER_GRID_MAJOR = (0.0, 0.0, 0.0, 0.12)
SELECTION_COLOR = (1.0, 0.78, 0.25)          # warm gold
# The selection while Properties shows something else, a picked layer say:
# still selected, still gold, but about half way back towards the background,
# so full gold keeps meaning "this is what Properties is editing".
HELD_SELECTION_COLOR = (0.62, 0.50, 0.22)
ACCENT = "#d9a441"

# Control points, when they are on. Cool, because everything else in the
# viewport is not: curves are white or their layer colour and the selection is
# gold, so a cool blue marker cannot be mistaken for a bit of the drawing.
# White markers were the trouble to begin with — a control point drawn white
# sits on a white curve and disappears into it. EDGE is the dark border drawn
# round each marker, which is what keeps it legible on a pale object as well
# as against the background; NET is the control polygon joining them, kept
# quiet so the points read louder than the lines between them.
CONTROL_POINT = (0.36, 0.80, 1.0)
CONTROL_POINT_EDGE = (0.04, 0.06, 0.09, 0.95)
CONTROL_NET = (0.34, 0.44, 0.56, 0.6)

# Direction arrows, while Dir is running. Green, because the two things it can
# be showing you at once are a curve's direction and a surface's normal, and
# both have to stand out against a drawing that is already white, gold and
# control point blue.
DIRECTION_ARROW = (0.40, 0.95, 0.50, 0.95)
# What a command such as Join or Explode just made lights up white for a
# moment and settles back to gold, so a change that looks like nothing on
# screen is still seen.
CHANGE_FLASH = (1.0, 1.0, 1.0)
CHANGE_FLASH_HOLD = 0.06          # fully white this long
CHANGE_FLASH_SECONDS = 0.19       # back to gold by then

# The arrow on a clipping plane, pointing at the half of the model it takes
# away. Magenta because it is the one colour left: the drawing is white, the
# selection gold, control points blue and direction arrows green, and this
# arrow has to be readable while sitting on top of a plane that is often
# selected and being dragged. PAUSED is the same arrow on a plane that has
# been switched off: half strength reads as a plan rather than a cut, and
# any fainter than this disappears entirely against a pale face, which is
# where a paused plane usually sits.
CLIP_NORMAL = (0.95, 0.40, 0.85, 0.95)
CLIP_NORMAL_PAUSED = (0.95, 0.40, 0.85, 0.55)

ACCENT_DIM = "#8a6a2f"
# Secondary text: a heading, a hint, a row that is switched off.
# The same grey QSS spells out below for headers and placeholders,
# named here because a widget that dims a row has to reach for it in
# code, and Qt's own disabled grey is not what this window paints.
TEXT_MUTED = "#9a9b9e"

# Panel spacing, shared so Properties and Layers line up with each other and
# with the layers mockup they were drawn from: a page stands this far in from
# its sides, and a list row is this tall.
PANEL_INSET = 10
LIST_ROW_HEIGHT = 28
SEAM = "#1b1c1f"               # the dark line between two parts of a panel

# Shaded-mode lighting. SHADED_AMBIENT mirrors a constant hardcoded in
# viewport.MESH_FRAG (`uColor * (0.30 + 0.70 * diff)`); a test pins the two
# together. FILL_FLOOR is what a pure black object is shaded as, and colours
# at or above FILL_KNEE are left exactly as they are. The floor must stay
# below the knee: the two ends define a ramp, and a floor above the knee tips
# it backwards, rendering pure black lighter than dark grey.
SHADED_AMBIENT = 0.30
FILL_FLOOR = 0.42
FILL_KNEE = 0.50
# Below this on every channel a colour is black, and is shaded white.
BLACK_BELOW = 0.5 / 255.0


def shaded_fill(color):
    """The colour to shade a surface with, lifted clear of black.

    Shading is multiplicative, so a black object has nothing left to shade: it
    came out flat black against a background that is itself nearly black
    (0.10-0.18) and read as a hole rather than a solid — you had to change the
    layer colour to see the model at all. Rhino keeps black-layer objects
    legible in shaded mode; this does the same, adding grey to colours below
    the knee and more of it the darker they are.

    Gated on the largest channel rather than luminance, so saturated hues that
    are dark in luminance but perfectly visible — pure blue most of all — are
    left alone. Only the fill is lifted: edges keep the object's true colour,
    so a black object still draws black wireframe over a grey surface.
    """
    r, g, b = color[0], color[1], color[2]
    v = max(r, g, b)
    if v < BLACK_BELOW:
        # Black is what most models are left in, not a colour anyone chose
        # to see a surface in: Rhino shades it white, and so does this.
        return (1.0, 1.0, 1.0)
    if v >= FILL_KNEE:
        return (r, g, b)
    lift = FILL_FLOOR * (1.0 - v / FILL_KNEE)
    return (min(1.0, r + lift), min(1.0, g + lift), min(1.0, b + lift))


# Fixed-pitch faces to name in a style sheet where the "monospace" alias names
# nothing, each platform's own coding font first.
MONO_FAMILIES = ("Menlo", "SF Mono", "Consolas", "Cascadia Mono",
                 "DejaVu Sans Mono", "Liberation Mono", "Courier New")


def _monospace_alias():
    """The installed family the "monospace" alias comes to, or None.

    Linux has fontconfig's alias, which someone may have pointed at a face
    of their own. Windows has no font by that name, and Qt's stand-in there
    is the proportional default, so it counts only when it is fixed pitch.
    """
    from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
    asked = QFont("monospace")
    asked.setStyleHint(QFont.StyleHint.Monospace)
    found = QFontInfo(asked)
    if found.fixedPitch() and QFontDatabase.hasFamily(found.family()):
        return found.family()
    return None


def mono_family() -> str:
    """An installed fixed-pitch family, for a style sheet's font-family.

    A style sheet that says `font-family: monospace` drew in the proportional
    default on Windows: the alias names nothing there, and a style sheet
    carries no style hint for Qt to fall back on. A family that is really
    installed is matched exactly everywhere.
    """
    from PySide6.QtGui import QFontDatabase
    alias = _monospace_alias()
    if alias:
        return alias
    for family in MONO_FAMILIES:
        if (QFontDatabase.hasFamily(family)
                and QFontDatabase.isFixedPitch(family)):
            return family
    return "monospace"

QSS = """
* { outline: none; }

QMainWindow, QWidget {
    background-color: #26272b;
    color: #cfd0d2;
    font-size: 13px;
}

QMainWindow::separator {
    background: #1b1c1f;
    /* 3px was nearly ungrabbable — the panels read as fixed-width (#5) */
    width: 6px; height: 6px;
}

QMainWindow::separator:hover {
    background: #8a6a2f;
}

QDockWidget {
    color: #9a9b9e;
    titlebar-close-icon: none;
    font-size: 12px;
}
QDockWidget::title {
    background: #2e2f34;
    padding: 5px 8px;
    border-bottom: 1px solid #1b1c1f;
}

QToolBar {
    background: #2b2c30;
    border: none;
    spacing: 2px;
    padding: 3px;
}
QToolBar::separator {
    background: #3d3e44;
    width: 1px; margin: 4px 3px;
}

QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px;
    color: #cfd0d2;
}
QToolButton:hover {
    background: #3a3b41;
    border-color: #4a4b52;
}
QToolButton:pressed, QToolButton:checked {
    background: #4a3f28;
    border-color: #d9a441;
    color: #f0d9a8;
}

QLineEdit {
    background: #1e1f22;
    border: 1px solid #3a3b41;
    border-radius: 4px;
    padding: 5px 8px;
    color: #e8e9ea;
    selection-background-color: #8a6a2f;
}
QLineEdit:focus { border-color: #d9a441; }

QListWidget, QTreeWidget, QTableWidget, QTreeView {
    background: #232427;
    border: 1px solid #1b1c1f;
    alternate-background-color: #26272b;
}
QListWidget::item, QTreeWidget::item {
    padding: 3px;
}
QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected {
    background: #4a3f28;
    color: #f0d9a8;
}
QTableWidget QLineEdit { padding: 0 6px; border-radius: 0; }
QHeaderView::section {
    background: #2e2f34;
    border: none;
    border-right: 1px solid #1b1c1f;
    border-bottom: 1px solid #1b1c1f;
    padding: 4px 6px;
    color: #9a9b9e;
}

QPushButton {
    background: #35363c;
    border: 1px solid #45464d;
    border-radius: 4px;
    padding: 5px 14px;
}
QPushButton:hover { background: #3f4047; border-color: #55565e; }
QPushButton:pressed { background: #2b2c30; }
QPushButton:default { border-color: #d9a441; }

/* A tool button that reads as a button before the pointer reaches it,
   like Join and Explode at the top of the middle-click popup. */
QToolButton[framed="true"] {
    background: #35363c;
    border: 1px solid #45464d;
    padding: 4px 8px;
}
/* The row Join and Explode sit in is the menu itself, not a strip on it. */
QWidget#popupButtons { background: transparent; }
QToolButton[framed="true"]:hover { background: #3f4047; border-color: #55565e; }
QToolButton[framed="true"]:pressed { background: #4a3f28; border-color: #d9a441; }

/* Styled here so a slider looks the same everywhere: left to the platform,
   macOS drew no track on this dark theme and Linux filled it with the
   desktop's highlight colour instead of ours. */
QSlider::groove:horizontal {
    height: 4px;
    background: #1e1f22;
    border: 1px solid #3a3b41;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #8a6a2f;
    border: 1px solid #8a6a2f;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #cfd0d2;
    border: 1px solid #45464d;
    width: 14px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover { background: #e6e7e9; border-color: #d9a441; }

QMenuBar { background: #2b2c30; }
QMenuBar::item { padding: 5px 10px; background: transparent; }
QMenuBar::item:selected { background: #3a3b41; }
QToolTip {
    background-color: #1f2023;
    color: #cfd0d2;
    border: 1px solid #3d3e44;
    padding: 4px 6px;
}

QMenu {
    background: #2e2f34;
    border: 1px solid #45464c;
    border-radius: 8px;
    margin: 8px;
    padding: 4px;
}
QMenu::item { padding: 5px 24px 5px 12px; border-radius: 5px; }
QMenu::item:selected { background: #4a3f28; color: #f0d9a8; }
QMenu::separator { height: 1px; background: #3d3e44; margin: 4px 6px; }

QStatusBar {
    background: #2b2c30;
    border-top: 1px solid #1b1c1f;
    color: #9a9b9e;
}

QScrollBar:vertical {
    background: #232427; width: 10px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #45464d; border-radius: 5px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #55565e; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar:horizontal {
    background: #232427; height: 10px; margin: 0;
}
QScrollBar::handle:horizontal {
    background: #45464d; border-radius: 5px; min-width: 24px;
}

QComboBox, QAbstractSpinBox {
    background: #1e1f22;
    border: 1px solid #3a3b41;
    border-radius: 4px;
    color: #e8e9ea;
    selection-background-color: #8a6a2f;
}
QComboBox { padding: 4px 22px 4px 8px; combobox-popup: 0; }
QAbstractSpinBox { padding: 4px 20px 4px 8px; }
QComboBox:hover, QAbstractSpinBox:hover { border-color: #55565e; }
QComboBox:focus, QComboBox:on, QAbstractSpinBox:focus {
    border-color: #d9a441;
}
QComboBox:disabled, QLineEdit:disabled, QAbstractSpinBox:disabled {
    color: #6b6c72; border-color: #2e2f34;
}

QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 18px; border: none; background: transparent;
}
QComboBox QAbstractItemView {
    background: #2e2f34;
    border: 1px solid #1b1c1f;
    padding: 4px;
    outline: none;
    selection-background-color: #4a3f28;
    selection-color: #f0d9a8;
}
QComboBox QAbstractItemView::item {
    padding: 4px 8px; min-height: 18px; border-radius: 3px;
}

QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    subcontrol-origin: border; width: 15px;
    border: none; border-radius: 3px; background: transparent;
}
QAbstractSpinBox::up-button {
    subcontrol-position: top right; margin: 3px 3px 0 0;
}
QAbstractSpinBox::down-button {
    subcontrol-position: bottom right; margin: 0 3px 3px 0;
}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {
    background: #2f3035;
}

QLabel#commandPrompt {
    color: #d9a441;
    font-weight: bold;
}
QPushButton[link="true"] {
    background: transparent; border: none; padding: 2px 0; min-height: 0;
    color: #d9a441; text-align: left;
}
QPushButton[link="true"]:hover { color: #f0d9a8; text-decoration: underline; }
QPushButton[link="true"]:disabled { color: #8a6a2f; }
QLabel#commandEcho {
    color: #85868a;
    font-family: monospace;
}

QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #55565e;
    border-radius: 3px;
    background: #1e1f22;
}
QCheckBox::indicator:checked {
    background: #d9a441;
    border-color: #d9a441;
}
"""

# Chevrons for drop-downs and spin boxes. Qt style sheets take arrows only as
# image files, and nothing ships as a file, so they are written out on start.
_CHEVRONS = {
    "down": (10, 6, "M1.5 1.25 L5 4.75 L8.5 1.25"),
    "spin-up": (8, 5, "M1.25 4 L4 1.25 L6.75 4"),
    "spin-down": (8, 5, "M1.25 1 L4 3.75 L6.75 1"),
}
_CHEVRON_TONES = {"": "#9a9b9e", "-hot": ACCENT, "-off": "#4a4b50"}

_ARROW_QSS = """
QComboBox::down-arrow {{ image: url("{d}/down.svg"); width: 10px; height: 6px; }}
QComboBox::down-arrow:hover, QComboBox::down-arrow:on {{
    image: url("{d}/down-hot.svg");
}}
QComboBox::down-arrow:disabled {{ image: url("{d}/down-off.svg"); }}
QAbstractSpinBox::up-arrow {{
    image: url("{d}/spin-up.svg"); width: 8px; height: 5px;
}}
QAbstractSpinBox::down-arrow {{
    image: url("{d}/spin-down.svg"); width: 8px; height: 5px;
}}
QAbstractSpinBox::up-arrow:hover {{ image: url("{d}/spin-up-hot.svg"); }}
QAbstractSpinBox::down-arrow:hover {{ image: url("{d}/spin-down-hot.svg"); }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{
    image: url("{d}/spin-up-off.svg");
}}
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{
    image: url("{d}/spin-down-off.svg");
}}
"""


def stylesheet() -> str:
    """QSS with its arrow images written out where it can find them."""
    import tempfile
    from pathlib import Path
    folder = Path(tempfile.gettempdir()) / "serpentine3d-ui"
    try:
        folder.mkdir(exist_ok=True)
        for name, (w, h, path) in _CHEVRONS.items():
            for suffix, tone in _CHEVRON_TONES.items():
                svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" '
                       f'height="{h}" viewBox="0 0 {w} {h}"><path d="{path}" '
                       f'fill="none" stroke="{tone}" stroke-width="1.5" '
                       'stroke-linecap="round" stroke-linejoin="round"/></svg>')
                file = folder / f"{name}{suffix}.svg"
                if not file.exists() or file.read_text() != svg:
                    file.write_text(svg)
    except OSError:
        return QSS
    return QSS + _ARROW_QSS.format(d=folder.as_posix())


def apply_interface_font(app, family: str) -> None:
    """The interface font onto the whole app ("" = system default).

    Live-safe: widgets repolish on the font-change event. The kind line
    sets its own fixed-pitch font and keeps it — tests say so.
    """
    from PySide6.QtGui import QFont
    app.setFont(QFont(family))


def apply_saved_interface_font(app) -> None:
    """The saved interface font (Settings → Display) onto the app.

    Called at startup, before any window is built, so everything inherits
    it from the beginning.
    """
    from ..utils.config import Config
    family = Config().get("display", "interface_font", default="") or ""
    if family:
        apply_interface_font(app, family)
