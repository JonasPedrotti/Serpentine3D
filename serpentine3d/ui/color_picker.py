"""The app's colour picker: a hue ring around a saturation/value disc, the
colour as RGB, HSV or CMYK numbers and as a hex code, a screen-wide
eyedropper, the last eight colours picked and a set of fixed colours."""

from __future__ import annotations

import json
import math
import os
import re
import sys

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QConicalGradient, QCursor, QGuiApplication, QIcon, QImage,
    QPainter, QPainterPath, QPen, QPixmap, QRegion, QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLineEdit, QPushButton, QSizePolicy,
    QSpinBox, QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from ..utils.config import CONFIG_PATH
from .card_dialog import STYLE as CARD_STYLE
from .card_dialog import CardDialog
from .theme import ACCENT, SEAM

HISTORY_SIZE = 8
PREVIEW_SIZE = 30
PREVIEW_MS = 30
FIXED_COLORS = (
    ("#ff0000", "#ff8000", "#ffff00", "#00ff00",
     "#00ffff", "#0000ff", "#8000ff", "#ff00ff"),
    ("#000000", "#404040", "#808080", "#c0c0c0",
     "#ffffff", "#5c3a1e", "#8b5a2b", "#c49a6c"),
)

STYLE = CARD_STYLE + """
QToolButton#iconButton {
    min-width: 0; padding: 0; border-radius: 5px;
    background: #3a3b41; border: 1px solid #4a4b52;
}
QToolButton#iconButton:hover { background: #45464d; }
QToolButton#iconButton:pressed { background: #d9a441; }
"""


def get_color(initial: QColor, parent=None, title: str = "Colour",
              preview=None) -> QColor:
    """The colour picked, or an invalid QColor if the picker was cancelled.

    `preview`, if given, is called with each colour as it changes, so the
    caller can show it live, and with None once the picker closes, to put
    things back before the caller applies the answer for real."""
    dialog = ColorPicker(initial, parent, title)
    # a drag changes the colour on every mouse move; redraw at most this often
    pending = QTimer(dialog, singleShot=True, interval=PREVIEW_MS)
    if preview is not None:
        pending.timeout.connect(lambda: preview(dialog.color()))
        dialog.colorChanged.connect(
            lambda _c: pending.isActive() or pending.start())
    try:
        accepted = dialog.exec() == ColorPicker.DialogCode.Accepted
    finally:
        pending.stop()
        if preview is not None:
            preview(None)
    return dialog.color() if accepted else QColor()


# ---- history ---------------------------------------------------------------

def _history_path() -> str:
    config = os.environ.get("SERP3D_CONFIG", CONFIG_PATH)
    return os.path.join(os.path.dirname(config), "color_history.json")


def load_history() -> list[str]:
    try:
        with open(_history_path(), encoding="utf-8") as f:
            names = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(names, list):
        return []
    return [n for n in names
            if isinstance(n, str) and QColor(n).isValid()][:HISTORY_SIZE]


def remember(color: QColor) -> list[str]:
    name = color.name()
    names = [name] + [n for n in load_history() if n != name]
    names = names[:HISTORY_SIZE]
    path = _history_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(names, f)
    except OSError:
        pass
    return names


def parse_hex(text: str) -> QColor | None:
    """A colour from '#RRGGBB', 'RRGGBB', '#RGB' or 'RGB', else None."""
    digits = text.strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}", digits):
        return None
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return QColor("#" + digits)


# ---- the wheel -------------------------------------------------------------

def _square_to_disc(x, y):
    return x * math.sqrt(1 - y * y / 2), y * math.sqrt(1 - x * x / 2)


def _disc_to_square(u, v):
    """Inverse of the elliptical grid mapping; arrays or floats."""
    r2 = 2 * math.sqrt(2)
    uu, vv = u * u, v * v
    x = (0.5 * np.sqrt(np.maximum(2 + uu - vv + r2 * u, 0))
         - 0.5 * np.sqrt(np.maximum(2 + uu - vv - r2 * u, 0)))
    y = (0.5 * np.sqrt(np.maximum(2 - uu + vv + r2 * v, 0))
         - 0.5 * np.sqrt(np.maximum(2 - uu + vv - r2 * v, 0)))
    return np.clip(x, -1, 1), np.clip(y, -1, 1)


class ColorWheel(QWidget):
    """Hue on the ring, saturation left to right and value bottom to top on
    the disc. The disc is a square stretched onto a circle, so every corner
    of the square, pure hue included, can still be reached."""

    changed = Signal()

    def __init__(self, parent=None, size: int = 220):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.h, self.s, self.v = 0.0, 1.0, 1.0
        self._drag = None
        self._disc = None
        self._disc_hue = None

    # geometry
    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _ring(self):
        """Outer radius and width of the hue ring."""
        outer = min(self.width(), self.height()) / 2 - 7
        return outer, max(6.0, round(outer * 0.10))

    def _disc_radius(self) -> float:
        outer, width = self._ring()
        return outer - width - 12

    def set_hsv(self, h: float, s: float, v: float):
        self.h, self.s, self.v = h % 1.0, s, v
        self.update()

    # painting
    def _disc_image(self) -> QImage:
        if self._disc is not None and self._disc_hue == self.h:
            return self._disc
        n = int(math.ceil(self._disc_radius() * 2))
        ratio = self.devicePixelRatioF()
        px = max(1, int(n * ratio))
        coords = (np.arange(px) + 0.5) / px * 2 - 1
        u, v = np.meshgrid(coords, -coords)
        x, y = _disc_to_square(u, v)
        s = (x + 1) / 2
        val = (y + 1) / 2
        hue = QColor.fromHsvF(self.h, 1.0, 1.0)
        base = np.array([hue.redF(), hue.greenF(), hue.blueF()])
        rgb = val[..., None] * (1 - s[..., None] * (1 - base))
        rgba = np.empty((px, px, 4), dtype=np.uint8)
        rgba[..., :3] = np.clip(rgb * 255 + 0.5, 0, 255)
        rgba[..., 3] = 255
        image = QImage(rgba.tobytes(), px, px, px * 4,
                       QImage.Format.Format_RGBA8888).copy()
        image.setDevicePixelRatio(ratio)
        self._disc, self._disc_hue = image, self.h
        return image

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self._center()
        outer, width = self._ring()

        gradient = QConicalGradient(c, 90)
        for i in range(13):
            gradient.setColorAt(i / 12, QColor.fromHsvF((i / 12) % 1.0, 1, 1))
        ring = QPainterPath()
        ring.addEllipse(c, outer, outer)
        ring.addEllipse(c, outer - width, outer - width)
        p.fillPath(ring, QBrush(gradient))

        r = self._disc_radius()
        p.setPen(QPen(QColor(0, 0, 0, 90), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, r + 1.5, r + 1.5)
        image = self._disc_image()
        brush = QBrush(image)
        ratio = image.devicePixelRatio()
        brush.setTransform(QTransform().translate(c.x() - r, c.y() - r)
                           .scale(1 / ratio, 1 / ratio))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(brush)
        p.drawEllipse(c, r, r)

        # hue handle: a dot of the pure hue, a little wider than the ring
        angle = math.radians(90 + self.h * 360)
        mid = outer - width / 2
        hp = QPointF(c.x() + mid * math.cos(angle),
                     c.y() - mid * math.sin(angle))
        hr = width / 2 + 5
        p.setPen(QPen(QColor(0, 0, 0, 110), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(hp, hr + 1.5, hr + 1.5)
        p.setPen(QPen(QColor("white"), 2.5))
        p.setBrush(QColor.fromHsvF(self.h, 1, 1))
        p.drawEllipse(hp, hr, hr)

        # disc handle: a small ring
        du, dv = _square_to_disc(self.s * 2 - 1, self.v * 2 - 1)
        dp = QPointF(c.x() + du * r, c.y() - dv * r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 140), 1))
        p.drawEllipse(dp, 7.5, 7.5)
        p.setPen(QPen(QColor("white"), 2))
        p.drawEllipse(dp, 6, 6)
        p.end()

    # mouse
    def _hit(self, pos: QPointF):
        c = self._center()
        d = math.hypot(pos.x() - c.x(), pos.y() - c.y())
        outer, width = self._ring()
        if d > outer:
            return None
        if d >= outer - width - 6:
            return "ring"
        return "disc"

    def _apply(self, pos: QPointF):
        c = self._center()
        dx, dy = pos.x() - c.x(), c.y() - pos.y()
        if self._drag == "ring":
            angle = math.degrees(math.atan2(dy, dx))
            self.h = ((angle - 90) % 360) / 360
        else:
            r = self._disc_radius()
            u, v = dx / r, dy / r
            length = math.hypot(u, v)
            if length > 1:
                u, v = u / length, v / length
            x, y = _disc_to_square(u, v)
            self.s = float((x + 1) / 2)
            self.v = float((y + 1) / 2)
        self.update()
        self.changed.emit()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = self._hit(ev.position())
            if self._drag:
                self._apply(ev.position())

    def mouseMoveEvent(self, ev):
        if self._drag:
            self._apply(ev.position())

    def mouseReleaseEvent(self, ev):
        self._drag = None


# ---- swatches --------------------------------------------------------------

class SwatchRow(QWidget):
    """A row of colour cells; an empty cell is drawn as a dashed outline."""

    picked = Signal(QColor)
    chosen = Signal(QColor)          # double click

    CELL = 26
    GAP = 4

    def __init__(self, names=(), parent=None):
        super().__init__(parent)
        self.names = list(names)
        width = HISTORY_SIZE * self.CELL + (HISTORY_SIZE - 1) * self.GAP
        self.setFixedSize(width, self.CELL)
        self.setMouseTracking(True)
        self._hover = -1

    def set_names(self, names):
        self.names = list(names)
        self.update()

    def _cell(self, i) -> QRectF:
        return QRectF(i * (self.CELL + self.GAP) + 0.5, 0.5,
                      self.CELL - 1, self.CELL - 1)

    def _index_at(self, pos) -> int:
        for i in range(HISTORY_SIZE):
            if self._cell(i).contains(pos):
                return i if i < len(self.names) else -1
        return -1

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i in range(HISTORY_SIZE):
            rect = self._cell(i)
            if i < len(self.names):
                p.setBrush(QColor(self.names[i]))
                edge = "#e8e8ea" if i == self._hover else "#55565c"
                p.setPen(QPen(QColor(edge), 1.5 if i == self._hover else 1))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                pen = QPen(QColor("#4a4b50"), 1, Qt.PenStyle.DashLine)
                p.setPen(pen)
            p.drawRoundedRect(rect, 5, 5)
        p.end()

    def mouseMoveEvent(self, ev):
        i = self._index_at(ev.position())
        if i != self._hover:
            self._hover = i
            self.setToolTip(self.names[i].upper() if i >= 0 else "")
            self.update()

    def leaveEvent(self, _ev):
        self._hover = -1
        self.update()

    def mousePressEvent(self, ev):
        i = self._index_at(ev.position())
        if i >= 0 and ev.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(QColor(self.names[i]))

    def mouseDoubleClickEvent(self, ev):
        i = self._index_at(ev.position())
        if i >= 0:
            self.chosen.emit(QColor(self.names[i]))


class Preview(QWidget):
    """The colour being picked, as a dot."""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.new = QColor(color)
        self.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#55565c"), 1))
        p.setBrush(self.new)
        p.drawEllipse(rect)
        p.end()


# ---- eyedropper ------------------------------------------------------------

def grab_screen(pos, half: int) -> QPixmap | None:
    """The square of screen around a global position, `half` pixels to each
    side, outside this app too."""
    screen = QGuiApplication.screenAt(pos)
    if screen is None:
        return None
    top_left = screen.geometry().topLeft()
    side = max(1, 2 * half)
    pixmap = screen.grabWindow(0, pos.x() - top_left.x() - half,
                               pos.y() - top_left.y() - half, side, side)
    return None if pixmap.isNull() else pixmap


def screen_color(pos) -> QColor | None:
    """The colour on screen at a global position, outside this app too."""
    pixmap = grab_screen(pos, 0)
    if pixmap is None:
        return None
    return QColor(pixmap.toImage().pixel(0, 0))


def _exclude_from_capture(widget) -> bool:
    """Keep a window out of screen grabs, so a magnifier does not magnify
    itself. Windows 10 2004 and later only."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        exclude_from_capture = 0x11
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(
            int(widget.winId()), exclude_from_capture))
    except (AttributeError, OSError):
        return False


class DropperRing(QWidget):
    """A ring in the colour under the pointer, drawn around it while the
    eyedropper is held, with the screen inside it magnified twice. Clicks
    pass through it.

    A mask shapes it rather than a translucent background, as Windows
    cannot keep a translucent window out of screen grabs. A mask cannot
    smooth its edge, so the mask reaches a little past the ring and that
    margin shows the screen behind it, copied from the grab: the cut falls
    where nothing differs, and the ring is drawn smoothly over the copy.
    Where the window cannot be kept out of grabs there is no copy and no
    magnifier, only the ring."""

    RADIUS = 39
    WIDTH = 5
    OUTLINE = 1
    MARGIN = 3
    ZOOM = 2

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        edge = self.RADIUS + self.WIDTH / 2 + self.OUTLINE
        half = math.ceil(edge) + self.MARGIN
        self.setFixedSize(2 * half, 2 * half)
        self.color = QColor("white")
        self.backdrop = None
        self.zoom = _exclude_from_capture(self)
        outer = half if self.zoom else math.ceil(edge)
        shape = QRegion(half - outer, half - outer, 2 * outer, 2 * outer,
                        QRegion.RegionType.Ellipse)
        if not self.zoom:
            inner = round(self.RADIUS - self.WIDTH / 2)
            shape -= QRegion(half - inner, half - inner, 2 * inner,
                             2 * inner, QRegion.RegionType.Ellipse)
        self.setMask(shape)

    def follow(self, pos, color: QColor | None = None):
        if color is not None:
            self.color = QColor(color)
        if self.zoom:
            self.backdrop = grab_screen(pos, self.width() // 2)
        self.update()
        self.move(pos.x() - self.width() // 2, pos.y() - self.height() // 2)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        r = self.RADIUS
        target = QRectF(self.rect())
        if self.backdrop is not None:
            source = QRectF(self.backdrop.rect())
            p.drawPixmap(target, self.backdrop, source)
            clip = QPainterPath()
            inner = r - self.WIDTH / 2
            clip.addEllipse(c, inner, inner)
            p.setClipPath(clip)
            zoomed = QRectF(0, 0, source.width() / self.ZOOM,
                            source.height() / self.ZOOM)
            zoomed.moveCenter(source.center())
            p.drawPixmap(target, self.backdrop, zoomed)
            p.setClipping(False)
        else:
            p.fillRect(target, QColor(SEAM))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(SEAM), self.OUTLINE))
        p.drawEllipse(c, r + (self.WIDTH + self.OUTLINE) / 2,
                      r + (self.WIDTH + self.OUTLINE) / 2)
        p.setPen(QPen(self.color, self.WIDTH))
        p.drawEllipse(c, r, r)
        p.end()


class Eyedropper(QToolButton):
    """Hold the button down and move anywhere on screen: the colour under the
    pointer follows along and is kept on release. Escape puts the colour
    back to what it was."""

    started = Signal()
    hovered = Signal(QColor)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self.ring = None
        self.setToolTip("Hold and drag anywhere on screen, release to pick")

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        self._active = True
        self.started.emit()
        self.setDown(True)
        self.grabMouse(QCursor(Qt.CursorShape.CrossCursor))
        self.grabKeyboard()
        if self.ring is None:
            self.ring = DropperRing(self.window())
        pos = ev.globalPosition().toPoint()
        self.ring.follow(pos, screen_color(pos))
        self.ring.show()

    def mouseMoveEvent(self, ev):
        if self._active:
            pos = ev.globalPosition().toPoint()
            color = screen_color(pos)
            if self.ring is not None:
                self.ring.follow(pos, color)
            if color is not None:
                self.hovered.emit(color)

    def mouseReleaseEvent(self, ev):
        if self._active:
            self.mouseMoveEvent(ev)
            self._stop()

    def keyPressEvent(self, ev):
        if self._active and ev.key() == Qt.Key.Key_Escape:
            self._stop()
            self.cancelled.emit()
            return
        super().keyPressEvent(ev)

    def _stop(self):
        self._active = False
        self.setDown(False)
        self.releaseMouse()
        self.releaseKeyboard()
        if self.ring is not None:
            self.ring.hide()

    def hideEvent(self, ev):
        if self._active:
            self._stop()
        super().hideEvent(ev)


def _icon(draw, size: int = 18) -> QIcon:
    ratio = 2
    pix = QPixmap(QSize(size, size) * ratio)
    pix.setDevicePixelRatio(ratio)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 18, size / 18)
    pen = QPen(QColor("#d4d5d8"), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    draw(p)
    p.end()
    return QIcon(pix)


def _draw_check(p):
    pen = p.pen()
    pen.setColor(QColor(ACCENT))
    pen.setWidthF(2)
    p.setPen(pen)
    p.drawPolyline([QPointF(4, 9.5), QPointF(7.5, 13), QPointF(14, 5.5)])


def _draw_copy(p):
    p.drawRoundedRect(QRectF(6.5, 6.5, 8, 9), 1.5, 1.5)
    p.drawPolyline([QPointF(4, 11.5), QPointF(3.5, 11.5), QPointF(3.5, 3.5),
                    QPointF(11, 3.5), QPointF(11, 4)])


def _draw_pipette(p):
    p.save()
    p.translate(9, 9)
    p.rotate(45)
    p.drawRoundedRect(QRectF(-2.5, -8, 5, 4), 1.5, 1.5)
    p.drawLine(QPointF(-3.5, -3.5), QPointF(3.5, -3.5))
    path = QPainterPath(QPointF(-1.6, -3.5))
    path.lineTo(-1.6, 4.5)
    path.lineTo(0, 7.5)
    path.lineTo(1.6, 4.5)
    path.lineTo(1.6, -3.5)
    p.drawPath(path)
    p.restore()


# ---- the dialog ------------------------------------------------------------

# On the field itself: the app's arrow images outrank the dialog's sheet.
_FIELD_STYLE = """
QSpinBox { padding: 3px 6px; }
QSpinBox::up-button, QSpinBox::down-button { image: none; width: 0px; }
QSpinBox::up-arrow, QSpinBox::down-arrow { image: url(none.png); }
"""

_MODES = {
    "RGB": (("R", 255), ("G", 255), ("B", 255)),
    "HSV": (("H", 359), ("S", 100), ("V", 100)),
    "CMYK": (("C", 100), ("M", 100), ("Y", 100), ("K", 100)),
}


_NAMES = {"R": "Red", "G": "Green", "B": "Blue", "H": "Hue",
          "S": "Saturation %", "V": "Value %", "C": "Cyan %",
          "M": "Magenta %", "Y": "Yellow %", "K": "Black %"}


class ColorPicker(CardDialog):

    colorChanged = Signal(QColor)

    def __init__(self, initial: QColor, parent=None, title: str = "Colour"):
        super().__init__(parent, title)
        self.setStyleSheet(STYLE)
        card = self.card
        col = self.column
        margins = col.contentsMargins()
        width = (SwatchRow.CELL * HISTORY_SIZE
                 + SwatchRow.GAP * (HISTORY_SIZE - 1))
        card.setFixedWidth(width + margins.left() + margins.right())
        col.setSpacing(8)
        start = QColor(initial) if initial.isValid() else QColor("white")
        self._updating = False

        self.wheel = ColorWheel(card, size=width)
        col.addWidget(self.wheel, 0, Qt.AlignmentFlag.AlignHCenter)
        # the free corners beside the round wheel
        self.preview = Preview(start, self.wheel)
        corner = self.wheel.width() - PREVIEW_SIZE
        self.preview.move(0, corner)
        self.eyedropper = Eyedropper(self.wheel)
        self.eyedropper.setObjectName("iconButton")
        self.eyedropper.setIcon(_icon(_draw_pipette, 22))
        self.eyedropper.setIconSize(QSize(22, 22))
        self.eyedropper.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.eyedropper.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        col.addSpacing(4)

        numbers = QHBoxLayout()
        numbers.setSpacing(SwatchRow.GAP)
        self.fields = []
        for _ in range(4):
            box = QSpinBox(card)
            box.setStyleSheet(_FIELD_STYLE)
            box.setSizePolicy(QSizePolicy.Policy.Expanding,
                              QSizePolicy.Policy.Fixed)
            box.setMinimumWidth(30)
            box.valueChanged.connect(self._from_fields)
            numbers.addWidget(box, 1)
            self.fields.append(box)
        col.addLayout(numbers)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(SwatchRow.GAP)
        self.mode = QComboBox(card)
        self.mode.addItems(list(_MODES))
        self.mode.setFixedWidth(86)
        self.mode.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        mode_row.addWidget(self.mode)
        self.hex = QLineEdit(card)
        self.hex.setMaxLength(9)
        self.hex.setPlaceholderText("#RRGGBB")
        self.hex.setToolTip("Hex code: type or paste, with or without #")
        mode_row.addWidget(self.hex, 1)
        self.copy_button = QToolButton(card)
        self.copy_button.setObjectName("iconButton")
        self.copy_button.setIcon(_icon(_draw_copy))
        self.copy_button.setToolTip("Copy the hex code")
        self._copy_icon = self.copy_button.icon()
        self._check_icon = _icon(_draw_check)
        self._copied = QTimer(self, singleShot=True, interval=1200)
        self._copied.timeout.connect(
            lambda: self.copy_button.setIcon(self._copy_icon))
        mode_row.addWidget(self.copy_button)
        self.copy_button.setFixedSize(28, 26)
        self.copy_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.eyedropper.move(corner, corner)
        col.addLayout(mode_row)

        col.addSpacing(4)
        swatches = QVBoxLayout()
        swatches.setSpacing(SwatchRow.GAP)
        self.history = SwatchRow(load_history(), card)
        self.history.setToolTip("Recently picked")
        swatches.addWidget(self.history)
        swatches.addSpacing(SwatchRow.GAP)
        self.fixed = [SwatchRow(row, card) for row in FIXED_COLORS]
        for row in self.fixed:
            swatches.addWidget(row)
        col.addLayout(swatches)

        col.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        cancel = QPushButton("Cancel", card)
        ok = QPushButton("OK", card)
        ok.setObjectName("primaryButton")
        ok.setDefault(True)
        for b in (ok, cancel):
            b.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Fixed)
            buttons.addWidget(b, 1)
        col.addLayout(buttons)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        ok.setFocus()

        self.wheel.changed.connect(self._from_wheel)
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.hex.textEdited.connect(self._from_hex)
        self.hex.editingFinished.connect(self._show_hex)
        self.copy_button.clicked.connect(self.copy_hex)
        self.eyedropper.hovered.connect(self.set_color)
        self.eyedropper.cancelled.connect(self._back_to_before_dropper)
        self.eyedropper.started.connect(self._remember_before_dropper)
        for row in (self.history, *self.fixed):
            row.picked.connect(self.set_color)
            row.chosen.connect(self._choose)

        self._color = QColor(start)
        self._before_dropper = QColor(start)
        self._mode_changed(self.mode.currentText())
        self.set_color(start)

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor, source=None):
        color = QColor(color)
        color.setAlpha(255)
        self._color = color
        if source is not self.wheel:
            h, s, v, _a = color.getHsvF()
            if h < 0:                       # grey: keep the hue it had
                h = self.wheel.h
            self.wheel.set_hsv(h, s, v)
        self._updating = True
        try:
            if source is not self.fields:
                self._show_fields()
            if source is not self.hex:
                self._show_hex()
        finally:
            self._updating = False
        self.preview.new = QColor(color)
        self.preview.update()
        self.colorChanged.emit(QColor(color))

    def copy_hex(self):
        text = self._color.name().upper()
        QApplication.clipboard().setText(text)
        button = self.copy_button
        button.setIcon(self._check_icon)
        QToolTip.showText(button.mapToGlobal(QPoint(0, button.height())),
                          f"Copied {text}", button)
        self._copied.start()

    def accept(self):
        remember(self._color)
        super().accept()

    def _choose(self, color):
        self.set_color(color)
        self.accept()

    def _remember_before_dropper(self):
        self._before_dropper = QColor(self._color)

    def _back_to_before_dropper(self):
        self.set_color(self._before_dropper)

    def _from_wheel(self):
        w = self.wheel
        self.set_color(QColor.fromHsvF(w.h, w.s, w.v), source=self.wheel)

    def _from_hex(self, text):
        color = parse_hex(text)
        if color is not None:
            self.set_color(color, source=self.hex)

    def _show_hex(self):
        self.hex.setText(self._color.name().upper())

    def _mode_changed(self, mode):
        spec = _MODES[mode]
        self._updating = True
        try:
            for i, box in enumerate(self.fields):
                box.setVisible(i < len(spec))
                if i < len(spec):
                    letter, top = spec[i]
                    box.setRange(0, top)
                    box.setPrefix(letter + " ")
                    box.setSuffix("°" if letter == "H" else "")
                    box.setToolTip(_NAMES[letter])
            self._show_fields()
        finally:
            self._updating = False

    def _values(self) -> list[int]:
        c = self._color
        mode = self.mode.currentText()
        if mode == "RGB":
            return [c.red(), c.green(), c.blue()]
        if mode == "HSV":
            return [round(self.wheel.h * 360) % 360, round(self.wheel.s * 100),
                    round(self.wheel.v * 100)]
        cyan, magenta, yellow, black, _a = c.getCmykF()
        return [round(x * 100) for x in (cyan, magenta, yellow, black)]

    def _show_fields(self):
        for box, value in zip(self.fields, self._values()):
            box.setValue(value)

    def _from_fields(self):
        if self._updating:
            return
        n = [box.value() for box in self.fields]
        mode = self.mode.currentText()
        if mode == "RGB":
            color = QColor(n[0], n[1], n[2])
        elif mode == "HSV":
            self.wheel.set_hsv(n[0] / 360, n[1] / 100, n[2] / 100)
            self._from_wheel()
            return
        else:
            color = QColor.fromCmykF(*(x / 100 for x in n))
        self.set_color(color, source=self.fields)
