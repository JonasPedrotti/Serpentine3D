"""Hydra's canvas: components as boxes, wires from outputs to inputs, and a
preview of what the graph holds in every model viewport.

Double-click or right-click the canvas to find a component by typing its
name; right-click a component to set it to objects picked in the model, to
cast it or to hide it, or a slider to change its range and decimals. Ctrl+H
hides the selection in the viewports and Ctrl+Shift+H shows it again, as
for the model's own objects; Delete removes it, dragging with the right
button pans and the wheel zooms.
"""

from __future__ import annotations

import json
import os
import uuid

import numpy as np
from PySide6.QtCore import (
    QEvent, QMimeData, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer,
    Signal,
)
from PySide6.QtGui import (
    QActionGroup, QColor, QCursor, QDrag, QFont, QFontMetrics, QIcon,
    QKeySequence, QPainter, QPainterPath, QPainterPathStroker, QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDockWidget, QFileDialog, QFormLayout, QFrame, QGraphicsItem,
    QGraphicsPathItem, QGraphicsScene, QGraphicsView, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMenuBar, QPlainTextEdit, QScrollArea, QSizePolicy, QStackedWidget,
    QTabBar,
    QTabWidget, QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)

from ..core import hydra
from ..core.hydra import (
    CATEGORIES, COMPONENTS, GEOMETRY_KINDS, Graph, HydraError,
)
from .dialogs import untether
from .icons import command_icon, sliders_icon

NODE_WIDTH = 110
NODE_HEIGHT = 28
PAN_SLOP = 4                # pixels a right drag moves before it pans
PORT_RADIUS = 5
MARK_STEP = 13              # from one Graft, Flatten or Reverse mark on
MARK_FROM = 13              # the first mark's middle, in from the edge
PORT_REACH = 11             # how near a click or a wire's end has to be
SNAP_REACH = 26             # screen pixels a dropped wire finds a port within
PASTE_STEP = 30             # how far a paste lands from what it copied
SEARCH_ROWS = 12            # the most the search lists before it scrolls
UNDO_STEPS = 100            # how far back Ctrl+Z reaches
PANEL_WIDTH = 220           # a panel's size: room for a few lines of text
PANEL_HEIGHT = 130
PANEL_HEAD = 22             # its title strip, over the text
MESH_WIRES_UP_TO = 50000    # triangles a mesh may have to show all its edges
CLIPBOARD = "application/x-serpentine-hydra"
COMPONENT_MIME = "application/x-serpentine-hydra-component"
SLIDER_WIDTH = 240
VALUE_WIDTH = 66
VALUE_GAP = 14              # between the value and the output
INPUT_ROW = 20              # height each input takes down the left

_BODY = QColor("#34363b")
_STATUS = {"warning": QColor("#a8742a"), "error": QColor("#a83a35")}
_TEXT = QColor("#e4e5e7")
_MUTED = QColor("#9a9b9e")
_WIRE = QColor("#b9bcc4")
_ACCENT = QColor("#d9a441")
_PORT = {"point": QColor("#8fd18a"), "curve": QColor("#7fb3e6"),
         "brep": QColor("#e6c27f"), "mesh": QColor("#c9a6f0"),
         "number": QColor("#e4e5e7"), "geometry": QColor("#6fd0c0"),
         "vector": QColor("#f08a8a"), "any": QColor("#b9bcc4"),
         "boolean": QColor("#e6e07f"), "text": QColor("#e4e5e7")}


_ICONS: dict = {}


def component_icon(comp):
    """The toolbar's icon for what a component holds, made once."""
    if comp.icon not in _ICONS:
        # the slider wears the Properties panel's mark: values on rails
        _ICONS[comp.icon] = (sliders_icon()
                             if comp.icon == "sliders"
                             else command_icon(comp.icon) if comp.icon
                             else None)
    return _ICONS[comp.icon]


def marks(comp, flags, output):
    """How many Graft, Flatten or Reverse marks the most marked input, or
    output, carries."""
    ports = comp.outputs if output else comp.inputs
    return max((len(hydra.flags_of((flags or {}).get(
        hydra.flag_key(p.name, output)))) for p in ports), default=0)


def mark_room(count):
    return count * MARK_STEP + 4 if count else 0


def node_size(comp, flags=None, title=None):
    """A component's input names column, width and height: as wide as the
    names in it need, its title, given or its own, and the marks of its
    flagged ports, and no wider."""
    small, bold = QFont(), QFont()
    small.setPointSizeF(8)
    bold.setPointSizeF(9)
    bold.setBold(True)
    names = 10 + mark_room(marks(comp, flags, False))
    labels = (names + max(QFontMetrics(small).horizontalAdvance(p.name)
                          for p in comp.inputs) + 10 if comp.inputs else 0)
    if comp.key == "panel":
        # wider by the room its marks take, so the text keeps its room
        return 0, (PANEL_WIDTH + mark_room(marks(comp, flags, False))
                   + mark_room(marks(comp, flags, True))), PANEL_HEIGHT
    named = QFontMetrics(bold).horizontalAdvance(title or comp.title)
    if comp.key in ("slider", "toggle") and title and title != comp.title:
        # a slider or a toggle shows no title, but one it was given
        extra = named + 12
        return labels, (SLIDER_WIDTH if comp.key == "slider"
                        else NODE_WIDTH) + extra, NODE_HEIGHT
    title = named
    width = (SLIDER_WIDTH if comp.key == "slider" else max(
        NODE_WIDTH, labels + NODE_HEIGHT + title + 18
        + mark_room(marks(comp, flags, True))))
    height = max(NODE_HEIGHT, INPUT_ROW * len(comp.inputs) + 8)
    return labels, width, height


_FLAG = QColor("#e4e5e7")
_HINT = {None: _ACCENT, "add": QColor("#6fcf7a"),
         "remove": QColor("#e0605a")}


def _undo_key(event):
    """"undo" for Ctrl+Z, "redo" for Ctrl+Y or Ctrl+Shift+Z."""
    ctrl = Qt.KeyboardModifier.ControlModifier
    shift = Qt.KeyboardModifier.ShiftModifier
    mods = event.modifiers()
    if event.key() == Qt.Key.Key_Z:
        return {ctrl: "undo", ctrl | shift: "redo"}.get(mods)
    if event.key() == Qt.Key.Key_Y and mods == ctrl:
        return "redo"
    return None


def _save_key(event):
    """"save" for Ctrl+S, "as" for Ctrl+Shift+S, None for anything else."""
    if event.key() != Qt.Key.Key_S:
        return None
    ctrl = Qt.KeyboardModifier.ControlModifier
    shift = Qt.KeyboardModifier.ShiftModifier
    return {ctrl: "save", ctrl | shift: "as"}.get(event.modifiers())


_MODIFIER_OF = {Qt.Key.Key_Shift: Qt.KeyboardModifier.ShiftModifier,
                Qt.Key.Key_Control: Qt.KeyboardModifier.ControlModifier}


def wiring_mode(modifiers):
    """"add" with Shift, a wire beside the ones already in; "remove" with
    Ctrl, taking a wire away; None otherwise, a wire in place of the old."""
    shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
    ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
    if shift and not ctrl:
        return "add"
    if ctrl and not shift:
        return "remove"
    return None


class PortItem(QGraphicsItem):
    def __init__(self, node_item, port, is_output, row, count):
        super().__init__(node_item)
        self.node_item = node_item
        self.port = port
        self.is_output = is_output
        x = node_item.width if is_output else 0
        self.setPos(x, node_item.height * (row + 1) / (count + 1))
        self.setAcceptHoverEvents(True)
        self._hover = False
        self._mode = None          # set while a dragged wire would dock here
        self.setToolTip(port.name)

    def show_values(self, values, wired):
        """A port's tooltip, kept simple: what it takes, how much it holds
        and where that came from, then the items themselves, so it shows
        how the data comes in."""
        lines = [self.port.what, self._connected(values, wired)]
        if len(values):
            lines.append("")
            lines.extend(hydra.list_tree(values))
        self.setToolTip("\n".join(lines))

    def _connected(self, values, wired):
        """What is connected right now: how much comes by wire, or, with
        no wire, where the value comes from."""
        count = hydra.count_said(values)
        if self.is_output or wired:
            return count
        node = self.node_item.node
        if self.port.name in node.params.get("internal", {}):
            return f"Internalized · {count}"
        if self.port.name in node.params.get("set", {}):
            return f"Set in the model · {count}"
        if len(values):
            return f"Default · {count}"
        if self.port.optional:
            return "Optional · nothing connected"
        return "Nothing connected"

    def flags(self):
        """This port's Graft, Flatten and Reverse, in the order applied."""
        flags = self.node_item.node.params.get("flags", {})
        return hydra.flags_of(
            flags.get(hydra.flag_key(self.port.name, self.is_output)))

    def flag(self):
        """This port's Graft or Flatten, or None."""
        return next((f for f in self.flags() if f != "reverse"), None)

    @property
    def node_id(self):
        return self.node_item.node.id

    def boundingRect(self):
        # room for the + or - badge beside the dot
        r = PORT_REACH + 6
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self):
        # what a click finds: a good deal more than the dot that is drawn
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), PORT_REACH, PORT_REACH)
        return path

    def set_highlight(self, on, mode=None):
        """Lit as when hovered: where a dragged wire would dock, green when
        it would be added, red when it would be taken away."""
        if (self._hover, self._mode) != (on, mode):
            self._hover, self._mode = on, mode
            self.update()

    def hint(self, modifiers=None):
        """What lighting it up says: None, "add" or "remove"."""
        if self._mode is not None:
            return self._mode
        if modifiers is None:
            scene = self.scene()
            modifiers = (scene.modifiers if scene is not None
                         else QApplication.keyboardModifiers())
        return wiring_mode(modifiers)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hint = self.hint() if self._hover else None
        colour = _HINT[hint]
        if self._hover:
            glow = QColor(colour)
            glow.setAlpha(70)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(0, 0), PORT_RADIUS + 4,
                                PORT_RADIUS + 4)
        painter.setPen(QPen(colour if self._hover else QColor("#1b1c1f"),
                            1.5))
        painter.setBrush(_PORT.get(self.port.kind, _WIRE))
        painter.drawEllipse(QPointF(0, 0), PORT_RADIUS, PORT_RADIUS)
        if hint is not None:
            self._paint_badge(painter, colour, hint)

    def _paint_badge(self, painter, colour, hint):
        """A small + or - above the port, on the side away from its node."""
        side = 1 if self.is_output else -1
        at = QPointF(side * (PORT_RADIUS + 5), -(PORT_RADIUS + 5))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawEllipse(at, 5.5, 5.5)
        painter.setPen(QPen(QColor("#1b1c1f"), 1.6))
        painter.drawLine(at - QPointF(3, 0), at + QPointF(3, 0))
        if hint == "add":
            painter.drawLine(at - QPointF(0, 3), at + QPointF(0, 3))

    def hoverEnterEvent(self, event):
        self._hover = True
        self.scene().modifiers = event.modifiers()
        self.update()

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()


class WireItem(QGraphicsPathItem):
    def __init__(self, wire=None):
        super().__init__()
        self.wire = wire
        self.mode = None           # a dragged wire's "add" or "remove"
        self.carries = "item"      # item | list | tree, from the last solve
        self.setZValue(-1)
        if wire is not None:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def set_ends(self, a: QPointF, b: QPointF):
        path = QPainterPath(a)
        bend = max(40.0, abs(b.x() - a.x()) * 0.5)
        path.cubicTo(a + QPointF(bend, 0), b - QPointF(bend, 0), b)
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        colour = _ACCENT if self.isSelected() else _WIRE
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.wire is None:
            pen = QPen(_HINT[self.mode] if self.mode is not None else colour,
                       2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawPath(self.path())
            return
        if self.carries == "item":
            # one item: a single line
            painter.setPen(QPen(colour, 2))
            painter.drawPath(self.path())
            return
        # a list: two lines side by side; a tree: the two lines dashed
        stroker = QPainterPathStroker()
        stroker.setWidth(5)
        stroker.setCapStyle(Qt.PenCapStyle.FlatCap)
        outline = stroker.createStroke(self.path())
        pen = QPen(colour, 1.3)
        if self.carries == "tree":
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(outline)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path())


def _shown_order(flags):
    """The marks left to right: Graft or Flatten, then Reverse."""
    return [f for f in flags if f != "reverse"] + [
        f for f in flags if f == "reverse"]


def _paint_flag(painter, flag, at):
    """A fork for Graft, one line splitting into three; for Flatten, three
    lines meeting in one, read left to right the way data runs; for Reverse
    two arrows the opposite ways."""
    painter.save()
    painter.setPen(QPen(_FLAG, 1.3, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap))
    x, y = at.x(), at.y()
    if flag == "reverse":
        for dy, way in ((-2.5, 1), (2.5, -1)):
            tip = QPointF(x + 3.5 * way, y + dy)
            painter.drawLine(QPointF(x - 3.5 * way, y + dy), tip)
            painter.drawLine(tip, tip + QPointF(-2 * way, -1.8))
            painter.drawLine(tip, tip + QPointF(-2 * way, 1.8))
    else:
        one, many = x - 3.5, x + 3.5
        if flag == "flatten":
            one, many = many, one
        for dy in (-3, 0, 3):
            painter.drawLine(QPointF(one, y), QPointF(many, y + dy))
    painter.restore()


class NodeItem(QGraphicsItem):
    """One line: the component's icon, then its name, or for a slider its
    rail and value. Inputs are named down the left, beside their ports."""

    def __init__(self, editor, node):
        super().__init__()
        self.editor = editor
        self.node = node
        self.result = None
        comp = node.component
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(node.x, node.y)
        self.setToolTip(comp.description)
        self.setAcceptHoverEvents(True)
        self.is_slider = node.key == "slider"
        self.labels, self.width, self.height = node_size(
            comp, node.params.get("flags"), node.title)
        self._sliding = False
        self.inputs = [PortItem(self, p, False, i, len(comp.inputs))
                       for i, p in enumerate(comp.inputs)]
        self.outputs = [PortItem(self, p, True, i, len(comp.outputs))
                        for i, p in enumerate(comp.outputs)]

    def relayout(self):
        """Sized again, after a port's marks changed what it needs."""
        self.prepareGeometryChange()
        self.labels, self.width, self.height = node_size(
            self.node.component, self.node.params.get("flags"),
            self.node.title)
        for port in self.outputs:
            port.setX(self.width)
        self.update()
        self.editor.canvas.update_wires(self)

    def names_at(self):
        """Where the input names start: past the marks, the same for all,
        so the names stand in a column."""
        return 10 + mark_room(marks(self.node.component,
                                    self.node.params.get("flags"), False))

    def port_at(self, pos):
        """The port a click at `pos`, in the component, means: an input by
        its name as well as its dot, an output by its marks beside it."""
        for port in self.inputs:
            if (pos.x() < self.labels
                    and abs(pos.y() - port.y()) <= INPUT_ROW / 2):
                return port
        room = mark_room(marks(self.node.component,
                               self.node.params.get("flags"), True))
        for port in self.outputs:
            if (pos.x() > self.width - room - 8
                    and abs(pos.y() - port.y()) <= NODE_HEIGHT / 2):
                return port
        return None

    def boundingRect(self):
        return QRectF(-PORT_RADIUS - 3, 0, self.width + 2 * PORT_RADIUS + 6,
                      self.height)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        status = self.result.status if self.result else "ok"
        selected = self.isSelected()
        body = _BODY if status == "ok" else _STATUS[status]
        hidden = self.is_hidden()
        outline = QPen(_ACCENT if selected else
                       (_MUTED if hidden else QColor("#1b1c1f")),
                       1.5 if selected else 1)
        if hidden:
            # hidden in the viewports: dark, dashed and faded, at a glance
            outline.setStyle(Qt.PenStyle.DashLine)
            body = body.darker(165)
        painter.setPen(outline)
        painter.setBrush(body)
        painter.drawRoundedRect(QRectF(0, 0, self.width, self.height), 5, 5)
        if hidden:
            painter.setOpacity(0.45)
        if self.node.key == "panel":
            self._paint_panel(painter)
            return
        if self.inputs:
            self._paint_labels(painter)
        top = int((self.height - NODE_HEIGHT) / 2)
        icon = component_icon(self.node.component)
        if icon is not None:
            icon.paint(painter, QRect(self.labels + 6, top + 4,
                                      NODE_HEIGHT - 8, NODE_HEIGHT - 8))
        font = QFont(painter.font())
        font.setPointSizeF(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(_TEXT)
        self._paint_flags(painter)
        if self.is_slider:
            self._paint_given_name(painter)
            self._paint_slider(painter)
            return
        if self.node.key == "toggle":
            # its value is what it shows, True lit up
            room = self._paint_given_name(painter)
            on = bool(self.node.params.get("value"))
            painter.setPen(_ACCENT if on else _MUTED)
            left = NODE_HEIGHT + 2 + room
            painter.drawText(QRectF(left, 0, self.width - left - 12,
                                    self.height),
                             Qt.AlignmentFlag.AlignVCenter,
                             "True" if on else "False")
            return
        left = self.labels + NODE_HEIGHT + 2
        room = mark_room(marks(self.node.component,
                               self.node.params.get("flags"), True))
        painter.drawText(QRectF(left, 0, self.width - left - 8 - room,
                                self.height),
                         Qt.AlignmentFlag.AlignVCenter,
                         self.node.title)

    def can_hide(self):
        """Whether it shows anything in the viewports to hide."""
        return any(p.kind in GEOMETRY_KINDS or p.kind in ("vector", "any")
                   for p in self.node.component.outputs)

    def is_hidden(self):
        return self.can_hide() and not self.node.preview

    def _paint_flags(self, painter):
        """Graft, Flatten and Reverse marked inside the component beside
        their port, as Grasshopper does: before an input's name, beside an
        output. Reverse always stands right of Graft or Flatten."""
        for port in self.inputs:
            for k, flag in enumerate(_shown_order(port.flags())):
                _paint_flag(painter, flag,
                            QPointF(MARK_FROM + k * MARK_STEP, port.y()))
        for port in self.outputs:
            shown = _shown_order(port.flags())
            for k, flag in enumerate(shown):
                _paint_flag(painter, flag, QPointF(
                    self.width - MARK_FROM
                    - (len(shown) - 1 - k) * MARK_STEP, port.y()))

    def panel_area(self):
        """Where a panel's text goes, under its title strip, clear of the
        marks of its ports' flags."""
        flags = self.node.params.get("flags")
        comp = self.node.component
        left = 6 + mark_room(marks(comp, flags, False))
        right = 6 + mark_room(marks(comp, flags, True))
        return QRectF(left, PANEL_HEAD, self.width - left - right,
                      self.height - PANEL_HEAD - 6)

    def panel_lines(self):
        """What a panel shows: what comes in, listed as tooltips list it,
        or the text typed into it; a word on what to do when empty."""
        port = self.inputs[0].port
        tree, wired = self.editor.graph.input_values(
            self.node.id, port, self.editor.results)
        if wired:
            return hydra.list_tree(tree, most=40) or ["empty"], True
        text = self.node.params.get("text", "")
        if not text.strip():
            return ["Double-click to type"], False
        return text.splitlines(), True

    def _paint_panel(self, painter):
        icon = component_icon(self.node.component)
        if icon is not None:
            icon.paint(painter, QRect(6, 3, PANEL_HEAD - 6, PANEL_HEAD - 6))
        font = QFont(painter.font())
        font.setPointSizeF(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(_TEXT)
        painter.drawText(QRectF(PANEL_HEAD + 2, 0, self.width, PANEL_HEAD),
                         Qt.AlignmentFlag.AlignVCenter, self.node.title)
        area = self.panel_area()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#25272b"))
        painter.drawRoundedRect(area, 3, 3)
        lines, filled = self.panel_lines()
        font.setBold(False)
        font.setPointSizeF(8.5)
        painter.setFont(font)
        painter.setPen(_TEXT if filled else _MUTED)
        painter.save()
        painter.setClipRect(area)
        painter.drawText(area.adjusted(6, 4, -6, -4),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         "\n".join(lines))
        painter.restore()
        self._paint_flags(painter)

    def _paint_labels(self, painter):
        painter.save()
        font = QFont(painter.font())
        font.setPointSizeF(8)
        painter.setFont(font)
        status = self.result.status if self.result else "ok"
        painter.setPen(_MUTED if status == "ok" else _TEXT)
        for port in self.inputs:
            left = self.names_at()
            painter.drawText(QRectF(left, port.y() - INPUT_ROW / 2,
                                    self.labels - left, INPUT_ROW),
                             Qt.AlignmentFlag.AlignVCenter, port.port.name)
        painter.setPen(QPen(QColor("#1b1c1f"), 1))
        painter.drawLine(QPointF(self.labels, 5),
                         QPointF(self.labels, self.height - 5))
        painter.restore()

    def _given_name_room(self):
        """What a name given to a slider or a toggle takes before it."""
        if "name" not in self.node.params:
            return 0
        bold = QFont()
        bold.setPointSizeF(9)
        bold.setBold(True)
        return QFontMetrics(bold).horizontalAdvance(self.node.title) + 12

    def _paint_given_name(self, painter):
        room = self._given_name_room()
        if room:
            painter.setPen(_TEXT)
            painter.drawText(QRectF(NODE_HEIGHT + 2, 0, room, self.height),
                             Qt.AlignmentFlag.AlignVCenter, self.node.title)
        return room

    def _rail(self):
        """Where the rail runs, left to right, along the middle."""
        return (NODE_HEIGHT + 6 + self._given_name_room(),
                self.width - VALUE_WIDTH - VALUE_GAP - 12)

    def _paint_slider(self, painter):
        p = self.node.params
        x0, x1 = self._rail()
        y = NODE_HEIGHT / 2
        span = p["max"] - p["min"]
        knob = x0 + (x1 - x0) * ((p["value"] - p["min"]) / span
                                 if span > 0 else 0.0)
        painter.setPen(QPen(QColor("#1b1c1f"), 4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(x0, y), QPointF(x1, y))
        painter.setPen(QPen(_ACCENT, 4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(x0, y), QPointF(knob, y))
        painter.setPen(QPen(QColor("#1b1c1f"), 1))
        painter.setBrush(_TEXT)
        painter.drawEllipse(QPointF(knob, y), 6, 6)
        painter.setPen(_TEXT)
        font = QFont(painter.font())
        font.setPointSizeF(10.5)
        painter.setFont(font)
        painter.drawText(self.value_rect(),
                         Qt.AlignmentFlag.AlignVCenter
                         | Qt.AlignmentFlag.AlignRight, self.value_text())

    def value_rect(self):
        """Where the value is written, clear of the output on the right."""
        return QRectF(self.width - VALUE_WIDTH - VALUE_GAP, 0, VALUE_WIDTH,
                      NODE_HEIGHT)

    def mouseDoubleClickEvent(self, event):
        if self.is_slider:
            self.editor.type_value(self)
            return
        if self.node.key == "toggle":
            self.editor.flip(self.node.id)
            return
        if self.node.key == "panel":
            self.editor.type_panel(self)
            return
        super().mouseDoubleClickEvent(event)

    def value_text(self):
        p = self.node.params
        return hydra.format_number(p["value"], p["decimals"])

    def slide_to(self, x):
        p = self.node.params
        x0, x1 = self._rail()
        t = min(max((x - x0) / (x1 - x0), 0.0), 1.0)
        hydra.set_slider(p, p["min"] + (p["max"] - p["min"]) * t)
        self.set_result(self.result)
        self.editor.changed()

    def _on_rail(self, pos):
        x0, x1 = self._rail()
        return x0 - 8 <= pos.x() <= x1 + 8

    def mousePressEvent(self, event):
        if (self.is_slider and event.button() == Qt.MouseButton.LeftButton
                and self._on_rail(event.pos())):
            self._sliding = True
            self.slide_to(event.pos().x())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._sliding:
            self.slide_to(event.pos().x())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._sliding:
            self._sliding = False
            self.editor.record()
            return
        super().mouseReleaseEvent(event)

    def summary(self):
        """How many objects it holds, said in words."""
        comp = self.node.component
        count = (sum(len(v) for v in self.result.outputs.values())
                 if self.result else 0)
        if self.node.key == "toggle":
            return "True" if self.node.params.get("value") else "False"
        if self.node.key == "pipeline":
            return f"{count} object" + ("" if count == 1 else "s") + (
                " · " + _pipe_said(self.node.params))
        if not comp.picks:
            noun = {"point": "point", "vector": "vector"}.get(
                comp.outputs[0].kind, "object")
            return f"{count} {noun}" + ("" if count == 1 else "s")
        said = f"{count} " + (comp.title.lower() if count == 1
                              else comp.plural)
        if "out" in self.node.params.get("internal", {}):
            said += " (internalized)"
        return said

    def set_result(self, result):
        self.result = result
        said = self.value_text() if self.is_slider else self.summary()
        tip = f"{self.node.component.description}\n\n{said}"
        if result is not None and result.message:
            tip += "\n" + result.message
        self._tip = tip
        self.setToolTip(tip)
        for port in self.inputs:
            port.show_values(*self.editor.graph.input_values(
                self.node.id, port.port, self.editor.results))
        for port in self.outputs:
            if result is not None:
                port.show_values(result.outputs.get(port.port.name,
                                                    hydra.Tree()), True)
        self.update()

    def hoverMoveEvent(self, event):
        # over an input's name, or an output's marks, the port's own tooltip
        port = self.port_at(event.pos())
        self.setToolTip(port.toolTip() if port is not None
                        else getattr(self, "_tip", ""))
        super().hoverMoveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.node.x, self.node.y = self.pos().x(), self.pos().y()
            self.editor.canvas.update_wires(self)
        return super().itemChange(change, value)

    def port(self, name, output):
        for item in self.outputs if output else self.inputs:
            if item.port.name == name:
                return item
        return None


class HydraScene(QGraphicsScene):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self._drag = None          # (fixed PortItem, WireItem)
        self._target = None        # the port a dragged wire would dock on
        self._mode = None          # what letting the dragged wire go would do
        self._last = None          # where the cursor last was, dragging
        # Shift and Ctrl as they stand, kept here rather than asked of Qt,
        # whose answer lags a key let go
        self.modifiers = Qt.KeyboardModifier.NoModifier
        self._copying = None       # (press point, {NodeItem: start}) Alt-drag
        self.setBackgroundBrush(QColor("#232427"))

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        step = 24
        painter.setPen(QPen(QColor(255, 255, 255, 14), 1))
        x = int(rect.left()) - int(rect.left()) % step
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = int(rect.top()) - int(rect.top()) % step
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step

    def _port_at(self, pos):
        for item in self.items(pos):
            if isinstance(item, PortItem):
                return item
        return None

    def _node_at(self, pos):
        for item in self.items(pos):
            while item is not None and not isinstance(item, NodeItem):
                item = item.parentItem()
            if item is not None:
                return item
        return None

    def _dock_at(self, pos, port):
        """Where a wire dragged from `port` would dock if let go at `pos`:
        the nearest port of the other kind within reach of the cursor, or,
        over a component, its nearest port that takes what the wire
        carries."""
        reach = SNAP_REACH / max(self.canvas.transform().m11(), 1e-6)
        mine = port.node_item

        def far(other):
            d = other.scenePos() - pos
            return (d.x() ** 2 + d.y() ** 2) ** 0.5

        def wired(other):
            out, inp = (port, other) if port.is_output else (other, port)
            return self.canvas.editor.graph.wire_between(
                out.node_id, out.port.name, inp.node_id, inp.port.name)

        def fits(other):
            # to take a wire away, the end it runs to is the one that fits
            if self._mode == "remove":
                return wired(other) is not None
            out, inp = (port, other) if port.is_output else (other, port)
            return hydra.takes(inp.port.kind, out.port.kind)

        ends = [other for item in self.canvas.node_items.values()
                if item is not mine
                for other in (item.inputs if port.is_output else item.outputs)]
        near = [o for o in ends if far(o) <= reach]
        if near:
            # aimed at, a port is the one meant; only a wire being taken
            # away looks past it for the end the wire runs to
            if self._mode == "remove":
                near = [o for o in near if fits(o)] or near
            return min(near, key=far)
        node = self._node_at(pos)
        if node is None or node is mine:
            return None
        own = node.inputs if port.is_output else node.outputs
        fitting = [o for o in own if fits(o)] or own
        return min(fitting, key=far) if fitting else None

    def _show_target(self, target):
        if self._target is not None and self._target is not target:
            self._target.set_highlight(False)
        self._target = target
        if target is not None:
            target.set_highlight(True, self._mode)

    def modifiers_changed(self, modifiers):
        """Shift or Ctrl pressed or let go: hovered ports and a dragged wire
        show at once what they would do now."""
        self.modifiers = modifiers
        if self._drag is not None:
            self._mode = wiring_mode(modifiers)
            self._drag[1].mode = self._mode
            self._drag[1].update()
            if self._last is not None:
                self._follow(self._last)
        self.update()

    def mousePressEvent(self, event):
        left = event.button() == Qt.MouseButton.LeftButton
        alt = event.modifiers() & Qt.KeyboardModifier.AltModifier
        node = self._node_at(event.scenePos())
        if left and alt and node is not None:
            self._start_copy(node, event.scenePos())
            event.accept()
            return
        port = self._port_at(event.scenePos())
        if port is not None and left:
            self._mode = wiring_mode(event.modifiers())
            # with Shift or Ctrl a wire is drawn, not one picked up
            wire = (None if port.is_output or self._mode is not None
                    else self.canvas.editor.wire_into(port))
            if wire is not None:
                # picking up a wire by its end: it hangs from its source
                self.canvas.editor.disconnect(wire)
                port = self.canvas.node_items[wire.source].port(wire.output,
                                                               True)
            temp = WireItem()
            temp.mode = self._mode
            self.addItem(temp)
            temp.set_ends(port.scenePos(), event.scenePos())
            self._drag = (port, temp)
            self._last = event.scenePos()
            # taken, or the view starts a selection box under the wire
            event.accept()
            return
        super().mousePressEvent(event)

    def _start_copy(self, node, at):
        """Alt-drag: the copies go with the cursor, the originals stay."""
        editor = self.canvas.editor
        chosen = ([i.node.id for i in self.selectedItems()
                   if isinstance(i, NodeItem)] if node.isSelected()
                  else [node.node.id])
        copies = editor.duplicate(chosen)
        self.clearSelection()
        items = [self.canvas.node_items[nid] for nid in copies]
        for item in items:
            item.setSelected(True)
        self._copying = (at, {item: item.pos() for item in items})

    def mouseMoveEvent(self, event):
        if self._copying is not None:
            at, starts = self._copying
            for item, start in starts.items():
                item.setPos(start + event.scenePos() - at)
            return
        if self._drag is not None:
            mode = wiring_mode(event.modifiers())
            if mode != self._mode:
                self._mode = self._drag[1].mode = mode
                self._drag[1].update()
            self._follow(event.scenePos())
            return
        super().mouseMoveEvent(event)

    def _follow(self, pos):
        port, temp = self._drag
        self._last = pos
        target = self._dock_at(pos, port)
        self._show_target(target)
        end = pos if target is None else target.scenePos()
        if port.is_output:
            temp.set_ends(port.scenePos(), end)
        else:
            temp.set_ends(end, port.scenePos())

    def mouseReleaseEvent(self, event):
        if self._copying is not None:
            self._copying = None
            self.canvas.editor.changed()
            return
        if self._drag is not None:
            port, temp = self._drag
            self._mode = wiring_mode(event.modifiers())
            other = self._dock_at(event.scenePos(), port)
            self._drag = self._last = None
            self.removeItem(temp)
            self._show_target(None)
            if other is not None and other.is_output != port.is_output:
                out, inp = (port, other) if port.is_output else (other, port)
                ends = (out.node_id, out.port.name, inp.node_id, inp.port.name)
                if self._mode == "remove":
                    self.canvas.editor.remove_wire(*ends)
                else:
                    self.canvas.editor.connect(*ends,
                                               add=self._mode == "add")
            self._mode = None
            return
        super().mouseReleaseEvent(event)
        # components dragged to a new place
        self.canvas.editor.record()

    def mouseDoubleClickEvent(self, event):
        if self._node_at(event.scenePos()) is None:
            self.canvas.editor.find_component(event.scenePos(),
                                              event.screenPos())
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.canvas.editor.show_menu(event.scenePos(), event.screenPos())


def _hide_key(event):
    """"hide" for Ctrl+H, "show" for Ctrl+Shift+H, as in the model."""
    if event.key() != Qt.Key.Key_H:
        return None
    ctrl = Qt.KeyboardModifier.ControlModifier
    shift = Qt.KeyboardModifier.ShiftModifier
    return {ctrl: "hide", ctrl | shift: "show"}.get(event.modifiers())


class HydraCanvas(QGraphicsView):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.node_items: dict[str, NodeItem] = {}
        self.wire_items: list[WireItem] = []
        self.setScene(HydraScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setSceneRect(-5000, -5000, 10000, 10000)
        for policy in (self.setHorizontalScrollBarPolicy,
                       self.setVerticalScrollBarPolicy):
            policy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._pan = None
        self.setAcceptDrops(True)

    def _dropped(self, event):
        return event.mimeData().hasFormat(COMPONENT_MIME)

    def dragEnterEvent(self, event):
        if self._dropped(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._dropped(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self._dropped(event):
            key = bytes(event.mimeData().data(COMPONENT_MIME)).decode()
            if key in COMPONENTS:
                at = self.mapToScene(event.position().toPoint())
                # the component's middle where it was let go
                _labels, width, height = node_size(COMPONENTS[key])
                self.editor.add_component(
                    key, at - QPointF(width / 2, height / 2))
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def add_item(self, node):
        item = NodeItem(self.editor, node)
        self.scene().addItem(item)
        self.node_items[node.id] = item
        return item

    def remove_item(self, node_id):
        item = self.node_items.pop(node_id, None)
        if item is not None:
            self.scene().removeItem(item)

    def style_wires(self, results):
        """Each wire drawn by what it carries: a line for one item, two for
        a list, two dashed for a tree."""
        for item in self.wire_items:
            result = results.get(item.wire.source)
            tree = (result.outputs.get(item.wire.output)
                    if result is not None else None)
            carries = tree.shape() if tree is not None else "item"
            if carries != item.carries:
                item.carries = carries
                item.update()

    def sync_wires(self):
        for item in self.wire_items:
            self.scene().removeItem(item)
        self.wire_items = []
        for wire in self.editor.graph.wires:
            item = WireItem(wire)
            self.scene().addItem(item)
            self.wire_items.append(item)
        self.update_wires()
        self.style_wires(self.editor.results)

    def update_wires(self, moved=None):
        for item in self.wire_items:
            w = item.wire
            if moved is not None and moved.node.id not in (w.source, w.target):
                continue
            if not (w.source in self.node_items
                    and w.target in self.node_items):
                continue             # an end gone, while the graph is rebuilt
            src = self.node_items[w.source].port(w.output, True)
            dst = self.node_items[w.target].port(w.input, False)
            item.set_ends(src.scenePos(), dst.scenePos())

    def event(self, event):
        # Delete, Copy and Paste here are the graph's, not the model's
        if event.type() == QEvent.Type.ShortcutOverride and (
                event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
                or event.matches(QKeySequence.StandardKey.Copy)
                or event.matches(QKeySequence.StandardKey.Paste)
                or _hide_key(event)):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.editor.remove_selected()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.editor.copy_selected()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.editor.paste()
            return
        which = _hide_key(event)
        if which == "hide":
            self.editor.hide()
            return
        if which == "show":
            self.editor.show_hidden()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if 0.2 < self.transform().m11() * factor < 3.0:
            self.scale(factor, factor)

    # The right button pans when dragged and opens a menu when only
    # clicked, so the menu waits for the release to know which it was.
    def contextMenuEvent(self, event):
        if event.reason() != event.Reason.Mouse:
            super().contextMenuEvent(event)

    def mousePressEvent(self, event):
        if self.editor.placing is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self.editor.place(self.mapToScene(event.position().toPoint()))
            else:
                self.editor.stop_placing()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._pan = (event.position(), False)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan is not None:
            last, dragged = self._pan
            delta = event.position() - last
            if not dragged and delta.manhattanLength() < PAN_SLOP:
                return
            if not dragged:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._pan = (event.position(), True)
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (self._pan is not None
                and event.button() == Qt.MouseButton.RightButton):
            _last, dragged = self._pan
            self._pan = None
            self.unsetCursor()
            if not dragged:
                self.editor.show_menu(self.mapToScene(event.position().toPoint()),
                                      event.globalPosition().toPoint())
            return
        super().mouseReleaseEvent(event)


class HydraEditor(QWidget):
    """The graph, its canvas, and what it shows in the model."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.graph = Graph()
        self.results: dict = {}
        self.shapes: list = []
        self.active = True
        self.picking = None        # the node a Set action picks for
        self.value_field = None    # typing into a slider, while it lasts
        self.panel_field = None    # typing into a panel, while it lasts
        self.placing = None        # a component waiting on the cursor
        self.meshes = PreviewMeshes()
        self.selected_meshes = PreviewMeshes()
        self.search = None         # the find-a-component field, while open
        self.canvas = HydraCanvas(self)
        self.canvas.scene().selectionChanged.connect(self._selection_changed)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 6, 0)
        self.menus = self._menu_bar()
        bar.addWidget(self.menus)
        bar.addStretch(1)
        self.status = QLabel()
        self.status.setStyleSheet("color: #9a9b9e;")
        bar.addWidget(self.status)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(bar)
        self.nodes_bar = NodeBar(self)
        root.addWidget(self.nodes_bar)
        self.start = HydraStart(self)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.canvas)
        self.pages.addWidget(self.start)
        root.addWidget(self.pages, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self.solve)
        # picked objects that move or go away show so straight away
        window.scene.add_listener(self.changed, kinds=("objects",))
        # Shift and Ctrl are heard wherever the keyboard is, not only on the
        # canvas: hovering a port gives it no focus, and the hint has to
        # come and go with the key all the same
        QApplication.instance().installEventFilter(self)

        # The graph last worked on, kept from the session before. One that
        # belonged to a file since deleted is let go with its file, rather
        # than coming back from nowhere under a name that is gone.
        saved = window.cfg.get("hydra_graph", default=None)
        path = window.cfg.get("hydra_path", default=None)
        path = path if isinstance(path, str) else None
        if path is not None and not os.path.exists(path):
            saved, path = None, None
        self.load(saved if isinstance(saved, dict) else {})
        self.path = path
        self._restoring = False
        self.forget_steps()

    # ------------------------------------------------------------- editing

    def _menu_bar(self):
        """File and Edit, then a menu for each category of component."""
        menus = QMenuBar()
        menus.setNativeMenuBar(False)       # in Hydra, not the system's
        file = menus.addMenu("File")
        _command(file, "New", self.new_graph, "Start an empty graph")
        _command(file, "Open…", self.open_graph, "Open a .hydra file")
        file.addSeparator()
        _command(file, "Save", self.save_graph,
                 "Save to the graph's file, asking where only the first time",
                 "Ctrl+S")
        _command(file, "Save As…", self.save_graph_as,
                 "Save to a file you choose", "Ctrl+Shift+S")
        edit = menus.addMenu("Edit")
        _command(edit, "Undo", self.undo, "", "Ctrl+Z")
        _command(edit, "Redo", self.redo, "", "Ctrl+Y")
        edit.addSeparator()
        _command(edit, "Copy", self.copy_selected, "", "Ctrl+C")
        _command(edit, "Paste", self.paste, "", "Ctrl+V")
        _command(edit, "Delete", self.remove_selected, "", "Del")
        edit.addSeparator()
        _command(edit, "Hide", self.hide,
                 "Hide the selected components in the viewports", "Ctrl+H")
        _command(edit, "Show", self.show_hidden,
                 "Show them again; all hidden ones with none selected",
                 "Ctrl+Shift+H")
        return menus

    def component_menu(self, at):
        menu = QMenu(self)
        for category in CATEGORIES:
            menu.addSection(category)
            for comp in COMPONENTS.values():
                if comp.category == category:
                    action = menu.addAction(comp.title)
                    icon = component_icon(comp)
                    if icon is not None:
                        action.setIcon(icon)
                    action.setToolTip(comp.description)
                    action.triggered.connect(
                        lambda checked=False, k=comp.key:
                        self.add_component(k, at))
        return menu

    def show_menu(self, scene_pos, screen_pos):
        """A port's menu over a port, a component's over a component, the
        add menu elsewhere."""
        port = self.canvas.scene()._port_at(scene_pos)
        item = self.canvas.scene()._node_at(scene_pos)
        if port is None and item is not None:
            # an input's name counts as the input
            port = item.port_at(item.mapFromScene(scene_pos))
        if port is not None:
            self.port_menu(port).exec(screen_pos)
            return
        if item is None:
            self.find_component(scene_pos, screen_pos)
            return
        self.node_menu(item).exec(screen_pos)

    def find_component(self, scene_pos, screen_pos):
        """A field to type a component's name into, opened where the
        canvas was clicked; what is chosen is put there."""
        search = ComponentSearch(self)
        search.chosen.connect(
            lambda key, params: self.add_component(key, scene_pos, params))
        search.move(screen_pos)
        search.show()
        search.field.setFocus()
        self.search = search
        return search

    def port_menu(self, port):
        """Graft, Flatten or Reverse what passes the port."""
        menu = QMenu(self)
        flag = port.flag()
        for name, tip in (("Graft", "Every item on a branch of its own"),
                          ("Flatten", "Every item on one branch")):
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(flag == name.lower())
            action.setToolTip(tip)
            action.triggered.connect(
                lambda on, f=name.lower(): self.set_flag(port, f if on
                                                         else None))
        menu.addSeparator()
        reverse = menu.addAction("Reverse")
        reverse.setCheckable(True)
        reverse.setChecked("reverse" in port.flags())
        reverse.setToolTip("Each branch the other way round")
        reverse.triggered.connect(lambda on: self.set_reverse(port, on))
        if not port.is_output:
            menu.addSeparator()
            keep = menu.addAction("Internalize",
                                  lambda: self.internalize_input(port))
            keep.setToolTip("Keep what comes in as the input's own, "
                            "and let the wires go")
            keep.setEnabled(bool(len(self.graph.wired_tree(
                port.node_id, port.port.name, self.results))))
        return menu

    def set_flag(self, port, flag):
        """Graft, Flatten, or neither, on a port; a Reverse stays."""
        keep = [f for f in port.flags() if f == "reverse"]
        self._store_flags(port, keep + ([flag] if flag else []))

    def set_reverse(self, port, on):
        """Reverse on a port, or off, beside its Graft or Flatten."""
        keep = [f for f in port.flags() if f != "reverse"]
        self._store_flags(port, keep + (["reverse"] if on else []))

    def _store_flags(self, port, names):
        node = port.node_item.node
        flags = node.params.setdefault("flags", {})
        key = hydra.flag_key(port.port.name, port.is_output)
        names = hydra.flags_of(names)
        if not names:
            flags.pop(key, None)
        else:
            # one flag as its name, as files have kept it, more as a list
            flags[key] = names[0] if len(names) == 1 else names
        if not flags:
            node.params.pop("flags")
        port.node_item.relayout()
        self.solve()

    def node_menu(self, item):
        menu = QMenu(self)
        node = item.node
        field = NameField(node.title)
        field.setToolTip("Its name: type another, Enter to keep it; left "
                         "empty, the component's own comes back")
        named = QWidgetAction(menu)
        named.setDefaultWidget(field)
        menu.addAction(named)

        def keep():
            self.rename(node.id, field.text())
        field.editingFinished.connect(keep)
        field.returnPressed.connect(menu.close)
        menu.addSeparator()
        menu.name_field = field
        if node.component.sets:
            # Set Crv... for a curve, Set Vector... for a vector
            command = "hydraset" if node.component.picks else "hydravector"
            menu.addAction(f"{node.component.sets}...",
                           lambda: self.pick(node.id, command))
            if node.component.picks:
                keep = menu.addAction("Internalize",
                                      lambda: self.internalize(node.id))
                keep.setToolTip("Keep the picked objects as the graph's own "
                                "copy, whatever happens to them in the model")
                keep.setEnabled(any(
                    self.window.scene.get(oid) is not None
                    for oid in node.params.get("refs", [])))
            menu.addSeparator()
        if node.key == "toggle":
            menu.addAction("Switch", lambda: self.flip(node.id))
            menu.addSeparator()
        if node.key == "pipeline":
            self._pipe_menus(menu, node)
            menu.addSeparator()
        if item.is_slider:
            menu.addAction("Change Range...", lambda: self.change_range(item))
            places = menu.addMenu("Decimal Places")
            group = QActionGroup(places)
            for n in range(hydra.MAX_DECIMALS + 1):
                action = places.addAction(str(n))
                action.setCheckable(True)
                action.setChecked(n == node.params["decimals"])
                group.addAction(action)
                action.triggered.connect(
                    lambda checked=False, n=n: self.set_decimals(item, n))
            menu.addSeparator()
        if any(p.kind in GEOMETRY_KINDS or p.kind == "any"
               for p in node.component.outputs):
            cast = menu.addAction("Cast...", lambda: self.cast(node.id))
            cast.setToolTip("Add what this component makes to the model")
            cast.setEnabled(bool(self.cast_shapes(self._casting(node.id))))
            menu.addSeparator()
        if item.can_hide():
            if item.is_hidden():
                act = menu.addAction(
                    "Show", lambda: self.show_hidden(self._casting(node.id)))
                act.setShortcut(QKeySequence("Ctrl+Shift+H"))
                act.setToolTip("Show it in the viewports again")
            else:
                act = menu.addAction(
                    "Hide", lambda: self.hide(self._casting(node.id)))
                act.setShortcut(QKeySequence("Ctrl+H"))
                act.setToolTip("Hide it in the viewports")
        menu.addAction("Delete", lambda: self.remove_nodes([node.id]))
        return menu

    # -------------------------------------------------------------- casting

    def _casting(self, node_id):
        """The component right-clicked, with the rest of the selection when
        it is one of several selected."""
        selected = self.selected_ids()
        return selected if node_id in selected else [node_id]

    def cast_shapes(self, node_ids):
        """The geometry these components hand on, ready to be cast."""
        shapes = []
        for nid in node_ids:
            result = self.results.get(nid)
            if result is None:
                continue
            for port in self.graph.nodes[nid].component.outputs:
                if port.kind in GEOMETRY_KINDS:
                    shapes.extend(result.outputs.get(port.name, []))
                elif port.kind == "any":
                    # only what it carries that is geometry can be cast
                    shapes.extend(v for v in result.outputs.get(port.name, [])
                                  if hydra.fits("geometry", v))
        return shapes

    def cast(self, node_id):
        """Ask for a layer, and whether to group, then cast."""
        node_ids = self._casting(node_id)
        shapes = self.cast_shapes(node_ids)
        if not shapes:
            return []
        dialog = CastDialog(self.window.scene.layers, len(shapes),
                            bool(self.window.cfg.get("hydra_cast_group",
                                                     default=False)), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return []
        group = dialog.group.isChecked()
        if len(shapes) > 1:
            self.window.cfg.set("hydra_cast_group", group)
        return self.cast_into(node_ids, dialog.layer_id(), group)

    def cast_into(self, node_ids, layer_id, group=False):
        """Cast onto a layer, as one undo step: the objects are the model's
        from then on, and no longer follow the graph."""
        shapes = self.cast_shapes(node_ids)
        if not shapes:
            return []
        if self.window.processor.busy:
            self.status.setText("Finish or cancel the active command first")
            return []
        from ..script_runtime import isolated_copy
        scene = self.window.scene
        self.window.history.checkpoint("Hydra: Cast")
        objects = [scene.add(isolated_copy(shape), layer_id=layer_id)
                   for shape in shapes]
        ids = [obj.id for obj in objects]
        if group and len(ids) > 1:
            scene.update_many(ids, group_id=uuid.uuid4().hex[:8])
        self.window.selection.set(ids)
        said = f"{len(ids)} object" + ("" if len(ids) == 1 else "s")
        where = scene.layers.full_path(layer_id)
        self.window.command_line.echo(
            f"Hydra cast {said} onto {where}"
            + (", grouped" if group and len(ids) > 1 else ""))
        self.status.setText(f"Cast {said}")
        return objects

    def type_panel(self, item):
        """A field over a panel to type its text into; a panel that shows
        what is wired into it has nothing of its own to type."""
        if self.graph.input_values(item.node.id, item.inputs[0].port,
                                   self.results)[1]:
            self.status.setText("It shows what comes in: take the wire "
                                "away to type into it")
            return None
        view = self.canvas
        field = PanelField(item.node.params.get("text", ""), view.viewport())
        field.setGeometry(view.mapFromScene(
            item.mapToScene(item.panel_area())).boundingRect())
        field.show()
        field.setFocus()
        self.panel_field = field

        def done(keep):
            if self.panel_field is not field:
                return
            self.panel_field = None
            if keep and field.toPlainText() != item.node.params.get("text"):
                item.node.params["text"] = field.toPlainText()
                item.update()
                self.changed()
            field.deleteLater()
            view.setFocus()

        field.finished.connect(done)
        return field

    def rename(self, node_id, name):
        """A component's own name, shown beside its icon; empty, it has its
        component's again."""
        node = self.graph.nodes.get(node_id)
        if node is None:
            return
        before = node.title
        node.rename(name)
        if node.title == before:
            return
        item = self.canvas.node_items[node_id]
        item.relayout()
        item.set_result(item.result)
        self.changed()

    def flip(self, node_id):
        """A Boolean Toggle switched to the other value."""
        node = self.graph.nodes[node_id]
        node.params["value"] = not node.params.get("value")
        self.canvas.node_items[node_id].update()
        self.changed()

    def _pipe_menus(self, menu, node):
        """A Geometry Pipeline's layer and its types to take."""
        scene = self.window.scene
        layers = menu.addMenu("Layer")
        group = QActionGroup(layers)
        chosen = node.params.get("layer")
        for path in [None] + [scene.layers.full_path(layer.id)
                              for layer in scene.layers.all()]:
            action = layers.addAction("All layers" if path is None else path)
            action.setCheckable(True)
            action.setChecked(path == chosen)
            group.addAction(action)
            action.triggered.connect(
                lambda checked=False, p=path: self.set_pipe(node.id, layer=p))
        types = menu.addMenu("Types")
        for key, title in (("point", "Points"), ("curve", "Curves"),
                           ("brep", "Breps"), ("mesh", "Meshes")):
            action = types.addAction(title)
            action.setCheckable(True)
            action.setChecked(key in node.params.get("types", ()))
            action.triggered.connect(
                lambda on, k=key: self.set_pipe(node.id, kind=k, on=on))

    def set_pipe(self, node_id, layer=..., kind=None, on=True):
        """A Geometry Pipeline's layer (None: all of them), or one of its
        types taken or left."""
        params = self.graph.nodes[node_id].params
        if layer is not ...:
            params["layer"] = layer
        if kind is not None:
            kept = [t for t in params.get("types", []) if t != kind]
            params["types"] = [t for t in hydra.PIPE_TYPES
                               if t in kept or (on and t == kind)]
        self.changed()

    def change_range(self, item):
        dialog = RangeDialog(item.node.params, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_range(item, *dialog.values())

    def set_range(self, item, low, high, places):
        # the decimal places are the ones the range was typed to
        hydra.set_range(item.node.params, low, high)
        self.set_decimals(item, places)

    def type_value(self, item):
        """A field over the slider to type a value, or a range as 0.0-12."""
        view = self.canvas
        field = ValueField(item.value_text(), view.viewport())
        x0, _x1 = item._rail()
        area = QRectF(x0, 2, item.width - x0 - VALUE_GAP, NODE_HEIGHT - 4)
        field.setGeometry(view.mapFromScene(
            item.mapToScene(area)).boundingRect())
        field.show()
        field.setFocus()
        field.selectAll()
        self.value_field = field

        def close():
            field._done = True
            self.value_field = None
            field.deleteLater()
            view.setFocus()

        def commit(leaving):
            try:
                self.status.objectName()
            except RuntimeError:
                return               # Hydra closed while the field was open
            if self.canvas.node_items.get(item.node.id) is not item:
                close()              # its component gone, by undo or delete
                return
            try:
                hydra.type_into_slider(item.node.params, field.text())
            except (ValueError, HydraError):
                if leaving:
                    close()
                    return
                self.status.setText("Type a number such as 5, or a range "
                                    "such as 0.0-12")
                field.selectAll()
                return
            self.status.setText("")
            item.set_result(item.result)
            self.changed()
            close()

        field.committed.connect(commit)
        field.cancelled.connect(close)
        return field

    def set_decimals(self, item, places):
        hydra.set_decimals(item.node.params, places)
        item.set_result(item.result)
        self.changed()

    def start_placing(self, key):
        """A component clicked in the node bar waits on the cursor, its icon
        with a plus, until the canvas is clicked where it is to go; Escape
        or the right button puts it back."""
        self.placing = key
        self.canvas.viewport().setCursor(placing_cursor(COMPONENTS[key]))
        self.status.setText(f"Click on the canvas to place "
                            f"{COMPONENTS[key].title} · Esc to cancel")

    def stop_placing(self):
        if self.placing is None:
            return
        self.placing = None
        self.canvas.viewport().unsetCursor()
        self.status.setText("")

    def place(self, at):
        """The component waiting on the cursor, put down with its middle at
        `at`."""
        key = self.placing
        self.stop_placing()
        _labels, width, height = node_size(COMPONENTS[key])
        return self.add_component(key, at - QPointF(width / 2, height / 2))

    def add_component(self, key, at=None, params=None):
        """A component on the canvas, at `at` or in the middle, set up
        with `params` when given, as one step."""
        if at is None:
            at = self.canvas.mapToScene(self.canvas.viewport().rect().center())
            at -= QPointF(
                (SLIDER_WIDTH if key == "slider" else NODE_WIDTH) / 2,
                NODE_HEIGHT / 2)
        x, y = (at.x(), at.y()) if isinstance(at, QPointF) else at
        node = self.graph.add_node(key, x, y, params)
        self.show_canvas()
        self.canvas.add_item(node)
        self.changed()
        return node

    def pick(self, node_id, command="hydraset"):
        """Set a component by picking in the model: objects with the usual
        selection, or for a Vector its two points."""
        self.picking = node_id
        self.window.activateWindow()
        self.window.run_command(command)

    def set_inputs(self, node_id, values):
        """Points picked in the model for inputs no wire feeds."""
        node = self.graph.nodes.get(node_id)
        if node is None:
            return
        node.params["set"] = {name: list(v) for name, v in values.items()}
        for name in values:
            # picked anew, it no longer holds what was internalized
            node.set_internal(name, None)
        self.solve()

    def set_references(self, node_id, ids):
        node = self.graph.nodes.get(node_id)
        if node is None:
            return
        node.params["refs"] = list(ids)
        node.set_internal("out", None)       # the model's objects again
        self.solve()

    def internalize(self, node_id):
        """A geometry component's objects kept as the graph's own copy."""
        try:
            count = self.graph.internalize(node_id, self.window.scene)
        except HydraError as exc:
            self.status.setText(str(exc))
            return 0
        self.status.setText(f"Internalized {count} object"
                            + ("" if count == 1 else "s"))
        self.solve()
        return count

    def internalize_input(self, port):
        """What comes into an input kept as its own, the wires let go."""
        try:
            count = self.graph.internalize_input(port.node_id,
                                                 port.port.name, self.results)
        except HydraError as exc:
            self.status.setText(str(exc))
            return 0
        self.canvas.sync_wires()
        self.status.setText(f"Internalized {count} item"
                            + ("" if count == 1 else "s")
                            + f" into {port.port.name}")
        self.solve()
        return count

    def connect(self, source, output, target, input, add=False):
        """A wire into an input, in place of the one there, or with `add`
        beside it."""
        try:
            wire = self.graph.connect(source, output, target, input, add=add)
        except HydraError as exc:
            self.status.setText(str(exc))
            return None
        self.canvas.sync_wires()
        self.changed()
        return wire

    def remove_wire(self, source, output, target, input):
        """Take away the wire from that output into that input: what a wire
        drawn over it with Ctrl does."""
        wire = self.graph.wire_between(source, output, target, input)
        if wire is None:
            self.status.setText("No wire runs there to take away")
            return False
        self.disconnect(wire)
        self.status.setText("Wire taken away")
        return True

    def disconnect(self, wire):
        self.graph.disconnect(wire)
        self.canvas.sync_wires()
        self.changed()

    def wire_into(self, port_item):
        for wire in reversed(self.graph.wires):
            if (wire.target == port_item.node_id
                    and wire.input == port_item.port.name):
                return wire
        return None

    def remove_nodes(self, node_ids):
        for nid in node_ids:
            self.graph.remove_node(nid)
            self.canvas.remove_item(nid)
        self.canvas.sync_wires()
        self.changed()

    def selected_ids(self):
        return [i.node.id for i in self.canvas.scene().selectedItems()
                if isinstance(i, NodeItem)]

    def copy_selected(self):
        """The selected components and the wires between them, onto the
        clipboard."""
        ids = self.selected_ids()
        if not ids:
            return False
        data = QMimeData()
        data.setData(CLIPBOARD, json.dumps(self.graph.part(ids)).encode())
        QApplication.clipboard().setMimeData(data)
        self.status.setText(f"Copied {len(ids)} component"
                            + ("" if len(ids) == 1 else "s"))
        return True

    def paste(self):
        """What was copied, under the cursor if it is over the canvas, a
        step down and right of where it was if not."""
        mime = QApplication.clipboard().mimeData()
        if mime is None or not mime.hasFormat(CLIPBOARD):
            return []
        try:
            part = json.loads(bytes(mime.data(CLIPBOARD)).decode())
        except ValueError:
            return []
        nodes = part.get("nodes", [])
        if not nodes:
            return []
        left = min(n.get("x", 0.0) for n in nodes)
        top = min(n.get("y", 0.0) for n in nodes)
        cursor = self.canvas.mapFromGlobal(QCursor.pos())
        if self.canvas.viewport().rect().contains(cursor):
            at = self.canvas.mapToScene(cursor)
            dx, dy = at.x() - left, at.y() - top
        else:
            dx = dy = PASTE_STEP
        return self._place(part, dx, dy)

    def duplicate(self, node_ids, dx=0.0, dy=0.0):
        """Copies of components where they stand, wired among themselves."""
        return self._place(self.graph.part(node_ids), dx, dy)

    def _place(self, part, dx, dy):
        fresh = self.graph.paste(part, dx, dy)
        self.canvas.scene().clearSelection()
        for nid in fresh:
            self.canvas.add_item(self.graph.nodes[nid]).setSelected(True)
        self.canvas.sync_wires()
        self.solve()
        return fresh

    def remove_selected(self):
        selected = self.canvas.scene().selectedItems()
        for wire in [i.wire for i in selected if isinstance(i, WireItem)]:
            self.graph.disconnect(wire)
        self.remove_nodes([i.node.id for i in selected
                           if isinstance(i, NodeItem)])

    def set_preview(self, node_id, shown):
        self.graph.nodes[node_id].preview = shown
        self.canvas.node_items[node_id].update()
        self.changed()

    def hide(self, node_ids=None):
        """Take these components out of the viewports: the selection if
        none are named."""
        self._set_hidden(self.selected_ids() if node_ids is None
                         else node_ids, True)

    def show_hidden(self, node_ids=None):
        """Put these components back in the viewports. With none named, the
        selection, or every hidden one when nothing is selected, as Show
        does for the model's objects."""
        if node_ids is None:
            node_ids = self.selected_ids() or list(self.graph.nodes)
        self._set_hidden(node_ids, False)

    def _set_hidden(self, node_ids, hidden):
        items = [self.canvas.node_items[nid] for nid in node_ids]
        items = [item for item in items
                 if item.can_hide() and item.is_hidden() != hidden]
        if not items:
            return
        for item in items:
            item.node.preview = not hidden
            item.update()
        self.status.setText(("Hidden" if hidden else "Shown")
                            + f" {len(items)} component"
                            + ("" if len(items) == 1 else "s"))
        self.changed()

    # ------------------------------------------------------------- solving

    def changed(self):
        # a step for Ctrl+Z at once, so two changes in quick succession
        # stay two steps
        self.record()
        # At most one solve per tick, not one once the changes stop: a
        # slider dragged without a pause has to show while it moves.
        if not self._timer.isActive():
            self._timer.start()

    def solve(self):
        self._timer.stop()
        self.results = self.graph.solve(self.window.scene)
        for nid, item in self.canvas.node_items.items():
            item.set_result(self.results.get(nid))
        self.canvas.style_wires(self.results)
        self.shapes = self.graph.preview_shapes(self.results)
        self._show_preview()
        if not self.graph.nodes:
            self.status.setText("Double-click the canvas to add a component")
        else:
            self.status.setText("")
        self.record()

    # ------------------------------------------------------------ undo, redo

    def record(self):
        """A step for Ctrl+Z when the graph is not as it was after the last
        one. A knob still being dragged is not a step yet: the drag as a
        whole is, when it is let go."""
        if not hasattr(self, "_undo") or self._restoring:
            return
        if any(item._sliding for item in self.canvas.node_items.values()):
            return
        now = self.graph.to_dict()
        if now == self._state:
            return
        self._undo.append(self._state)
        del self._undo[:-UNDO_STEPS]
        self._redo.clear()
        self._state = now

    def forget_steps(self):
        """A graph opened or begun anew starts a history of its own."""
        self._undo, self._redo = [], []
        self._state = self.graph.to_dict()

    def undo(self):
        return self._step(self._undo, self._redo, "Undone")

    def redo(self):
        return self._step(self._redo, self._undo, "Redone")

    def _step(self, source, target, said):
        self.record()                # a change not yet a step becomes one
        if not source:
            self.status.setText("Nothing to " + said[:-2].lower())
            return False
        target.append(self._state)
        self._state = source.pop()
        self._restoring = True
        try:
            self.load(self._state)
        finally:
            self._restoring = False
        self.status.setText(said)
        return True

    def set_active(self, active: bool):
        """A closed editor shows nothing in the model."""
        self.active = active
        self._show_preview()

    def _selection_changed(self):
        try:
            self._show_preview()
        except RuntimeError:
            pass                     # the window this belonged to is gone

    def _show_preview(self):
        """The graph in the model: violet, and what the selected components
        make in green instead, hidden ones too, so the selection shows."""
        scene = self.window.scene
        chosen = set(self.selected_ids()) if self.active else set()
        shown = self.graph.preview_shapes(
            self.results, only=set(self.graph.nodes) - chosen)
        picked = (self.graph.preview_shapes(self.results, only=chosen,
                                            hidden=True) if chosen else [])
        scene.hydra_preview = (self.meshes.overlay(shown)
                               if self.active and shown else None)
        scene.hydra_selected = (self.selected_meshes.overlay(picked)
                                if picked else None)
        for viewport in self.window.all_viewports():
            viewport.update()

    # --------------------------------------------------------- persistence

    def load(self, data: dict):
        if hasattr(self, "pages"):
            self.show_canvas()
        for nid in list(self.canvas.node_items):
            self.canvas.remove_item(nid)
        for item in self.canvas.wire_items:
            self.canvas.scene().removeItem(item)
        self.canvas.wire_items = []
        self.graph = Graph.from_dict(data)
        for node in self.graph.nodes.values():
            self.canvas.add_item(node)
        self.canvas.sync_wires()
        self.solve()

    def new_graph(self):
        self.load({})
        self.set_path(None)
        self.forget_steps()

    def set_path(self, path):
        """The file Save writes to, named in the Hydra window's title."""
        self.path = path
        dock = self.parentWidget()
        if isinstance(dock, QDockWidget):
            dock.setWindowTitle("Hydra" if path is None
                                else f"Hydra · {os.path.basename(path)}")

    def save_graph(self):
        """Into the graph's own file once it has one, asking only before."""
        if self.path and os.path.exists(self.path):
            return self._write(self.path)
        return self.save_graph_as()

    def save_graph_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Hydra Graph", self.path or "", "Hydra graph (*.hydra)")
        if not path:
            return False
        return self._write(path)

    def _write(self, path):
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.graph.to_dict(), fh, indent=1)
        except OSError as exc:
            self.status.setText(f"Could not save: {exc}")
            return False
        self.set_path(path)
        self._remember(path)
        self.status.setText(f"Saved {os.path.basename(path)}")
        return True

    def open_graph(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Hydra Graph", os.path.dirname(self.path or ""),
            "Hydra graph (*.hydra)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        """A .hydra file, from the dialog or double-clicked outside."""
        path = os.path.abspath(path)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            self.status.setText(f"Could not open: {exc}")
            return False
        self.load(data if isinstance(data, dict) else {})
        self.set_path(path)
        self._remember(path)
        self.forget_steps()
        return True

    # ---------------------------------------------------------- start page

    def recent(self):
        """The .hydra files last saved or opened, newest first, those still
        there."""
        paths = self.window.cfg.get("hydra_recent", default=[])
        return [p for p in paths if isinstance(p, str) and os.path.exists(p)]

    def _remember(self, path):
        from ..utils.config import push_recent
        self.window.cfg.set("hydra_recent", push_recent(
            self.window.cfg.get("hydra_recent", default=[]), path))

    def show_start(self):
        """The graph being worked on and the recent ones, as cards; the
        empty canvas only when there is neither. The graph being worked on
        is offered to continue only when it is not its file's as saved:
        then the file's own card is the same thing."""
        current = (self.graph.to_dict()
                   if self.graph.nodes and self.unsaved() else None)
        recent = self.recent()
        if current is None and not recent:
            self.show_canvas()
            return False
        self.start.fill(current, recent)
        self.pages.setCurrentWidget(self.start)
        self.start.setFocus()
        return True

    def unsaved(self):
        """Whether the graph holds anything its file does not: never saved,
        its file gone, or changed since it was saved."""
        if self.path is None or not os.path.exists(self.path):
            return True
        saved = _read_graph(self.path)
        return saved != json.loads(json.dumps(self.graph.to_dict()))

    def show_canvas(self):
        self.pages.setCurrentWidget(self.canvas)

    def starting(self):
        return self.pages.currentWidget() is self.start

    def eventFilter(self, obj, event):
        kind = event.type()
        if (kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape
                and getattr(self, "placing", None) is not None):
            self.stop_placing()
            return True
        # Ctrl+S, and Ctrl+Shift+S, typed anywhere in Hydra save the graph,
        # not the model the main window would
        if kind in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            save = _save_key(event)
            if save is not None and self._holds(obj):
                if kind == QEvent.Type.KeyPress and save == "as":
                    self.save_graph_as()
                elif kind == QEvent.Type.KeyPress:
                    self.save_graph()
                event.accept()
                return True
            # in a text field they undo the typing, as they always do
            step = _undo_key(event)
            if (step is not None and self._holds(obj)
                    and not isinstance(obj, QLineEdit)):
                if kind == QEvent.Type.KeyPress and step == "undo":
                    self.undo()
                elif kind == QEvent.Type.KeyPress:
                    self.redo()
                event.accept()
                return True
        if kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            flag = _MODIFIER_OF.get(event.key())
            if flag is not None and not event.isAutoRepeat():
                mods = event.modifiers()
                # whether the key's own flag is in yet differs by platform
                mods = (mods | flag if kind == QEvent.Type.KeyPress
                        else mods & ~flag)
                self._modifiers_changed(mods)
        elif kind == QEvent.Type.ApplicationDeactivate:
            # let go in another program, a key would stay held here
            self._modifiers_changed(Qt.KeyboardModifier.NoModifier)
        return False

    def _holds(self, obj):
        """Whether a widget is Hydra's: the editor or anything in it, the
        search and the value field that float above it included."""
        try:
            floating = (getattr(self, "search", None),
                        getattr(self, "value_field", None))
            return isinstance(obj, QWidget) and (
                obj is self or self.isAncestorOf(obj)
                or any(obj is f for f in floating if f is not None))
        except RuntimeError:
            return False

    def _modifiers_changed(self, mods):
        try:
            self.canvas.scene().modifiers_changed(mods)
        except RuntimeError:
            pass        # the window this belonged to is gone

    def shutdown(self):
        QApplication.instance().removeEventFilter(self)
        self.window.cfg.set("hydra_graph", self.graph.to_dict())
        self.window.cfg.set("hydra_path", self.path)
        self.set_active(False)


def graph_preview(data, width, height):
    """A small picture of a saved graph: its components where they stand,
    with their icons, and the wires between them."""
    pix = QPixmap(width, height)
    pix.fill(QColor("#232427"))
    nodes = [n for n in (data or {}).get("nodes", [])
             if n.get("key") in COMPONENTS]
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if not nodes:
        painter.setPen(_MUTED)
        painter.drawText(QRectF(0, 0, width, height),
                         Qt.AlignmentFlag.AlignCenter, "empty")
        painter.end()
        return pix
    boxes = {}
    for n in nodes:
        comp = COMPONENTS[n["key"]]
        params = n.get("params", {})
        _labels, w, h = node_size(comp, params.get("flags"),
                                  params.get("name"))
        boxes[n["id"]] = (QRectF(n.get("x", 0.0), n.get("y", 0.0), w, h),
                          comp)
    bounds = QRectF()
    for rect, _comp in boxes.values():
        bounds = bounds.united(rect)
    margin = 14
    scale = min((width - 2 * margin) / max(bounds.width(), 1.0),
                (height - 2 * margin) / max(bounds.height(), 1.0), 1.0)
    painter.translate(width / 2, height / 2)
    painter.scale(scale, scale)
    painter.translate(-bounds.center())
    painter.setPen(QPen(_WIRE, 2 / scale))
    for source, _out, target, _in in (data or {}).get("wires", []):
        if source in boxes and target in boxes:
            a = QPointF(boxes[source][0].right(), boxes[source][0].center().y())
            b = QPointF(boxes[target][0].left(), boxes[target][0].center().y())
            bend = max(40.0, abs(b.x() - a.x()) * 0.5)
            path = QPainterPath(a)
            path.cubicTo(a + QPointF(bend, 0), b - QPointF(bend, 0), b)
            painter.drawPath(path)
    for rect, comp in boxes.values():
        painter.setPen(QPen(QColor("#4a4d55"), 1 / scale))
        painter.setBrush(_BODY)
        painter.drawRoundedRect(rect, 5, 5)
        icon = component_icon(comp)
        if icon is not None:
            # where the component draws it: after its input names
            labels = node_size(comp)[0]
            side = NODE_HEIGHT - 8
            icon.paint(painter, QRect(int(rect.left() + labels + 6),
                                      int(rect.center().y() - side / 2),
                                      side, side))
    painter.end()
    return pix


class GraphCard(QFrame):
    """One graph on the start page: its picture, name, folder and date.
    A double-click opens it."""

    PREVIEW = (210, 118)

    def __init__(self, title, detail, data, open_it, parent=None,
                 picture=None):
        super().__init__(parent)
        self.setObjectName("hydraCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(self.PREVIEW[0] + 16)
        self.open_it = open_it
        shown = QLabel()
        shown.setPixmap(picture if picture is not None
                        else graph_preview(data, *self.PREVIEW))
        name = QLabel(title)
        name.setObjectName("cardName")
        about = QLabel(detail)
        about.setObjectName("cardDetail")
        about.setToolTip(detail)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.addWidget(shown)
        layout.addWidget(name)
        layout.addWidget(about)
        self.title = title

    def mouseDoubleClickEvent(self, event):
        self.open_it()


class HydraStart(QScrollArea):
    """What Hydra opens on: the graph being worked on to continue, and the
    graphs last saved or opened, as cards. Escape continues."""

    COLUMNS = 3

    _QSS = (
        "HydraStart, #hydraStartPage { background: #1b1c20; }"
        "QLabel#startTitle { color: #85868a; font-family: monospace;"
        " letter-spacing: 1.5px; }"
        "QFrame#hydraCard { background: #232428; border: 1px solid #34353a;"
        " border-radius: 8px; }"
        "QFrame#hydraCard:hover { border-color: %s; }"
        "QLabel#cardName { color: #ececee; font-weight: bold; }"
        "QLabel#cardDetail { color: #85868a; }") % _ACCENT.name()

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(self._QSS)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.cards: list[GraphCard] = []

    def fill(self, current, recent):
        page = QWidget()
        page.setObjectName("hydraStartPage")
        root = QVBoxLayout(page)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(14)
        # a new graph first, then the one being worked on, then the recent
        self.cards = [GraphCard("New Graph", "Start from an empty canvas",
                                None, self.editor.new_graph,
                                picture=_new_picture(*GraphCard.PREVIEW))]
        if current is not None:
            self.cards.append(GraphCard(
                "Continue", "Where you left off", current,
                self.editor.show_canvas))
        for path in recent:
            self.cards.append(GraphCard(
                os.path.splitext(os.path.basename(path))[0],
                _card_detail(path), _read_graph(path),
                lambda p=path: self.editor.open_path(p)))
        title = QLabel("RECENT GRAPHS")
        title.setObjectName("startTitle")
        root.addWidget(title)
        for i, card in enumerate(self.cards):
            grid.addWidget(card, i // self.COLUMNS, i % self.COLUMNS)
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft
                          | Qt.AlignmentFlag.AlignTop)
        root.addLayout(grid)
        root.addStretch(1)
        self.setWidget(page)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.editor.show_canvas()
            return
        super().keyPressEvent(event)


def _new_picture(width, height):
    """The New Graph card's picture: a plus on an empty canvas."""
    pix = QPixmap(width, height)
    pix.fill(QColor("#232427"))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(_ACCENT, 3, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap))
    cx, cy, arm = width / 2, height / 2, 18
    painter.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
    painter.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))
    painter.end()
    return pix


def _read_graph(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _card_detail(path):
    """The folder a graph is in and when it was last saved."""
    import time
    folder = os.path.basename(os.path.dirname(path)) or path
    when = time.strftime("%d.%m.%Y %H:%M",
                         time.localtime(os.path.getmtime(path)))
    return f"{folder} · {when}"


def placing_cursor(comp):
    """The cursor a component waits on: a small node, its icon, title and
    ports, with a plus at its corner, its middle where it will go."""
    bold = QFont()
    bold.setPointSizeF(8)
    bold.setBold(True)
    metrics = QFontMetrics(bold)
    title = metrics.elidedText(comp.title, Qt.TextElideMode.ElideRight, 110)
    ports = max(len(comp.inputs), len(comp.outputs), 1)
    body = QRectF(6, 4, 37 + metrics.horizontalAdvance(title),
                  max(26, ports * 9 + 8))
    pix = QPixmap(int(body.right()) + 9, int(body.bottom()) + 9)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#1b1c1f"), 1))
    painter.setBrush(_BODY)
    painter.drawRoundedRect(body, 4, 4)
    icon = component_icon(comp)
    if icon is not None:
        icon.paint(painter, QRect(int(body.left()) + 5,
                                  int(body.center().y()) - 9, 18, 18))
    painter.setFont(bold)
    painter.setPen(_TEXT)
    painter.drawText(body.adjusted(27, 0, 0, 0),
                     Qt.AlignmentFlag.AlignVCenter, title)
    painter.setPen(QPen(QColor("#1b1c1f"), 1))
    for x, side in ((body.left(), comp.inputs), (body.right(), comp.outputs)):
        for i, port in enumerate(side):
            y = body.top() + body.height() * (i + 1) / (len(side) + 1)
            painter.setBrush(_PORT.get(port.kind, _WIRE))
            painter.drawEllipse(QPointF(x, y), 3, 3)
    corner = body.bottomRight()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_ACCENT)
    painter.drawEllipse(corner, 6.5, 6.5)
    painter.setPen(QPen(QColor("#1b1c1f"), 2, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap))
    painter.drawLine(corner - QPointF(3, 0), corner + QPointF(3, 0))
    painter.drawLine(corner - QPointF(0, 3), corner + QPointF(0, 3))
    painter.end()
    middle = body.center()
    return QCursor(pix, int(middle.x()), int(middle.y()))


class NodeButton(QToolButton):
    """A component in the node bar: clicked, it goes in the middle of the
    canvas; dragged, it goes where it is let go."""

    def __init__(self, editor, comp):
        super().__init__()
        self.editor = editor
        self.key = comp.key
        self.setText(comp.title)
        icon = component_icon(comp)
        if icon is not None:
            self.setIcon(icon)
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setToolTip(comp.description)
        self.clicked.connect(lambda: editor.start_placing(self.key))
        self._pressed = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._pressed is not None
                and (event.position() - self._pressed).manhattanLength()
                >= QApplication.startDragDistance()):
            self._pressed = None
            self.setDown(False)
            drag = QDrag(self)
            data = QMimeData()
            data.setData(COMPONENT_MIME, self.key.encode())
            drag.setMimeData(data)
            drag.setPixmap(self.icon().pixmap(24, 24))
            drag.exec(Qt.DropAction.CopyAction)
            return
        super().mouseMoveEvent(event)


class NodeRow(QScrollArea):
    """One tab's components side by side; too many to fit, the wheel
    scrolls them sideways."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        for policy in (self.setHorizontalScrollBarPolicy,
                       self.setVerticalScrollBarPolicy):
            policy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def wheelEvent(self, event):
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - event.angleDelta().y())


class CardTabs(QTabBar):
    """Tabs drawn as file cards, by their fills alone: the chosen one in
    the colour of the panel it opens onto, its top corners rounded and its
    foot flaring out into the panel; the others darker, lower, behind."""

    ROUND = 5                  # the top corners
    FLARE = 5                  # where the chosen tab's foot meets the edge

    def __init__(self, panel):
        super().__init__()
        self.panel = QColor(panel)
        self.setMouseTracking(True)
        self._hovered = -1

    def mouseMoveEvent(self, event):
        hovered = self.tabAt(event.position().toPoint())
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        chosen = self.currentIndex()
        for i in range(self.count()):
            if i != chosen:
                self._paint_tab(painter, i, False)
        if chosen >= 0:
            self._paint_tab(painter, chosen, True)
        painter.end()

    def _paint_tab(self, painter, i, chosen):
        rect = QRectF(self.tabRect(i))
        if not chosen:
            rect.adjust(2, 0, -2, 0)        # a little air between them
        foot = self.height()                # where the panel begins
        left, right = rect.left(), rect.right() + 1
        top = rect.top() + (0 if chosen else 3)
        r, f = self.ROUND, self.FLARE
        outline = QPainterPath()
        if chosen:
            # a flare out into the edge on each side, but where the tab
            # stands at the panel's own corner, a straight drop into it
            if left - f >= 0:
                outline.moveTo(left - f, foot)
                outline.quadTo(left, foot, left, foot - f)
            else:
                outline.moveTo(left, foot)
            outline.lineTo(left, top + r)
        else:
            outline.moveTo(left, foot)
            outline.lineTo(left, top + r)
        outline.quadTo(left, top, left + r, top)
        outline.lineTo(right - r, top)
        outline.quadTo(right, top, right, top + r)
        if chosen:
            outline.lineTo(right, foot - f)
            outline.quadTo(right, foot, right + f, foot)
        else:
            outline.lineTo(right, foot)
        body = QPainterPath(outline)
        body.lineTo(body.currentPosition().x(), self.height())
        body.lineTo(outline.elementAt(0).x, self.height())
        body.closeSubpath()
        hovered = i == self._hovered
        fill = (self.panel if chosen
                else QColor("#2c2e33") if hovered else QColor("#26282c"))
        painter.fillPath(body, fill)
        painter.setPen(QColor("#e4e5e7") if chosen or hovered
                       else QColor("#9a9b9e"))
        text = QRectF(rect.left(), top, rect.width(), foot - top)
        painter.drawText(text, Qt.AlignmentFlag.AlignCenter, self.tabText(i))


class NodeBar(QWidget):
    """The components a tab at a time, a tab for each category, as in
    Grasshopper: file-card tabs above, the chosen one joined to the panel
    of its components below, as tabs are in any program. The tab last
    chosen is the one it opens on."""

    _PANEL = "#2f3136"         # the chosen tab and the panel it opens onto
    _QSS = (
        # no outlines anywhere: the shapes are told apart by their fills,
        # which stay sharp however the screen is scaled
        "NodeBar { background: #1f2023; }"
        "QTabWidget::pane { background: %(panel)s; border: none;"
        " border-radius: 6px; border-top-left-radius: 0; top: 0px; }"
        # the tabs draw themselves; this only gives them their size
        "QTabBar::tab { padding: 6px 18px; margin-right: 8px;"
        " border: none; background: transparent; }"
        # the pages show the pane's colour through, as one with the tab
        "QTabWidget QStackedWidget, #nodeBarRow, NodeRow"
        " { background: transparent; }"
        # each component a button of its own, in the colours of a node
        "QToolButton { color: #e4e5e7; background: #3a3d44;"
        " border: 1px solid #1b1c1f; border-radius: 4px; padding: 5px 12px; }"
        "QToolButton:hover { background: #454850; border-color: #d9a441; }"
        "QToolButton:pressed { background: #26282c; }"
    ) % {"panel": _PANEL}

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(self._QSS)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.tabs = QTabWidget()
        self.tabs.setTabBar(CardTabs(self._PANEL))
        self.tabs.setDocumentMode(False)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.buttons: dict[str, NodeButton] = {}
        self.groups: dict[str, list[str]] = {}
        for category in CATEGORIES:
            self.tabs.addTab(self._page(category), category)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self._chosen)
        shown = editor.window.cfg.get("hydra_tab", default=CATEGORIES[0])
        self.tabs.setCurrentIndex(
            CATEGORIES.index(shown) if shown in CATEGORIES else 0)
        self.setFixedHeight(self.sizeHint().height())

    def _page(self, category):
        row = QWidget()
        row.setObjectName("nodeBarRow")
        buttons = QHBoxLayout(row)
        buttons.setContentsMargins(12, 10, 12, 10)
        buttons.setSpacing(6)
        self.groups[category] = []
        for comp in COMPONENTS.values():
            if comp.category == category:
                button = NodeButton(self.editor, comp)
                buttons.addWidget(button)
                self.buttons[comp.key] = button
                self.groups[category].append(comp.key)
        buttons.addStretch(1)
        page = NodeRow()
        page.setWidget(row)
        page.setFixedHeight(row.sizeHint().height())
        return page

    def category(self) -> str:
        """The tab being shown."""
        return CATEGORIES[self.tabs.currentIndex()]

    def show_category(self, category):
        self.tabs.setCurrentIndex(CATEGORIES.index(category))

    def _chosen(self, index):
        self.editor.window.cfg.set("hydra_tab", CATEGORIES[index])


class ComponentSearch(QFrame):
    """Type to find a component. Before anything is typed it offers the
    components every graph starts from; typing searches them all, and hides
    the ones whose name does not fit."""

    chosen = Signal(str, object)     # a component, and settings if typed

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("hydraSearch")
        self.setStyleSheet(
            "#hydraSearch { background: #2b2d31; border: 1px solid #1b1c1f;"
            " border-radius: 5px; }"
            "QLineEdit { background: #25272b; color: #e4e5e7;"
            " border: 1px solid #d9a441; border-radius: 3px;"
            " padding: 3px 6px; }"
            "QListWidget { background: transparent; color: #e4e5e7;"
            " border: none; outline: none; }"
            "QListWidget::item { padding: 3px 4px; border-radius: 3px; }"
            "QListWidget::item:selected { background: #4a4d55; }")
        self.field = QLineEdit()
        self.field.setPlaceholderText("Type to find a component")
        self.list = QListWidget()
        self.list.setIconSize(QSize(18, 18))
        self.list.setFixedWidth(230)
        # sized to what it lists, so it has nothing to scroll; past
        # SEARCH_ROWS the wheel still walks it, without a bar
        for policy in (self.list.setVerticalScrollBarPolicy,
                       self.list.setHorizontalScrollBarPolicy):
            policy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)
        root.addWidget(self.field)
        root.addWidget(self.list)
        self.field.textChanged.connect(self.show_found)
        self.field.installEventFilter(self)
        self.list.itemClicked.connect(self._take)
        self.show_found("")

    def show_found(self, text):
        self.list.clear()
        # a number or a range typed is a slider set to it, offered first
        typed = hydra.slider_from_text(text)
        if typed is not None:
            self.list.addItem(self._typed_slider(typed))
        note = hydra.panel_from_text(text)
        if note is not None:
            self.list.addItem(self._typed_panel(note))
        for key in hydra.find_components(text):
            comp = COMPONENTS[key]
            item = QListWidgetItem(comp.title)
            icon = component_icon(comp)
            if icon is not None:
                item.setIcon(icon)
            item.setToolTip(comp.description)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        row = max(self.list.sizeHintForRow(0), 1) if self.list.count() else 26
        rows = min(max(self.list.count(), 1), SEARCH_ROWS)
        self.list.setFixedHeight(rows * row + 2 * self.list.frameWidth() + 2)
        self.adjustSize()

    def eventFilter(self, obj, event):
        # the arrows walk the list while the typing stays in the field
        if obj is self.field and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                step = 1 if key == Qt.Key.Key_Down else -1
                row = self.list.currentRow() + step
                if 0 <= row < self.list.count():
                    self.list.setCurrentRow(row)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._take(self.list.currentItem())
                return True
            if key == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def _typed_slider(self, params):
        comp = COMPONENTS["slider"]
        places = params["decimals"]
        low, high = (hydra.format_number(params[k], places)
                     for k in ("min", "max"))
        value = hydra.format_number(params["value"], places)
        item = QListWidgetItem(f"Number Slider  {low} to {high}, at {value}")
        icon = component_icon(comp)
        if icon is not None:
            item.setIcon(icon)
        item.setToolTip("A slider set to what was typed")
        item.setData(Qt.ItemDataRole.UserRole, "slider")
        item.setData(Qt.ItemDataRole.UserRole + 1, params)
        return item

    def _typed_panel(self, params):
        comp = COMPONENTS["panel"]
        item = QListWidgetItem(f"Panel  \u201c{params['text']}\u201d")
        icon = component_icon(comp)
        if icon is not None:
            item.setIcon(icon)
        item.setToolTip("A panel holding what was typed")
        item.setData(Qt.ItemDataRole.UserRole, "panel")
        item.setData(Qt.ItemDataRole.UserRole + 1, params)
        return item

    def _take(self, item):
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        params = item.data(Qt.ItemDataRole.UserRole + 1)
        self.close()
        self.chosen.emit(key, params)


def _pipe_said(params) -> str:
    """A Geometry Pipeline's filter in words."""
    names = {"point": "points", "curve": "curves", "brep": "breps",
             "mesh": "meshes"}
    types = [names[t] for t in params.get("types", [])]
    layer = params.get("layer") or "all layers"
    return f"{', '.join(types) or 'no types'} on {layer}"


def _command(menu, text, slot, tip="", keys=""):
    """A menu entry, with its keys shown beside it but not taken: the keys
    are Hydra's already, and taken here too they would clash with the main
    window's."""
    action = menu.addAction(f"{text}\t{keys}" if keys else text)
    action.triggered.connect(lambda checked=False: slot())
    if tip:
        action.setToolTip(tip)
    menu.setToolTipsVisible(True)
    return action


class NameField(QLineEdit):
    """A component's name, at the top of its menu: clicked into, the whole
    of it is chosen, to be typed over."""

    def __init__(self, text):
        super().__init__(text)
        self.setMinimumWidth(180)
        self.setStyleSheet(
            "QLineEdit { background: #25272b; color: #e4e5e7;"
            " border: 1px solid #45484f; border-radius: 3px;"
            " padding: 3px 6px; margin: 4px 6px; font-weight: bold; }"
            "QLineEdit:focus { border-color: #d9a441; }")

    def mousePressEvent(self, event):
        chosen = self.hasSelectedText() and len(self.selectedText()) == len(
            self.text())
        super().mousePressEvent(event)
        if not chosen and not getattr(self, "_typed_in", False):
            self.selectAll()
            self._typed_in = True

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)


class PanelField(QPlainTextEdit):
    """Typing into a panel: Ctrl+Enter or a click elsewhere keeps the text,
    Escape leaves the panel as it was. Enter alone starts a new line."""

    finished = Signal(bool)          # True to keep what was typed

    def __init__(self, text, parent):
        super().__init__(text, parent)
        self._done = False
        self.setStyleSheet(
            "QPlainTextEdit { background: #25272b; color: #e4e5e7;"
            " border: 1px solid #d9a441; border-radius: 3px; }")
        self.setPlaceholderText("One item a line")

    def event(self, event):
        if (event.type() == QEvent.Type.ShortcutOverride
                and event.key() == Qt.Key.Key_Escape):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish(False)
            return
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._finish(True)
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._finish(True)

    def _finish(self, keep):
        if not self._done:
            self._done = True
            self.finished.emit(keep)


class ValueField(QLineEdit):
    """Typing into a slider: Enter or a click elsewhere keeps what is
    typed, Escape leaves the slider as it was."""

    committed = Signal(bool)        # True when focus is leaving
    cancelled = Signal()

    def __init__(self, text, parent):
        super().__init__(text, parent)
        self._done = False
        self.setStyleSheet(
            "QLineEdit { background: #25272b; color: #e4e5e7;"
            " border: 1px solid #d9a441; border-radius: 3px;"
            " padding: 0 4px; font-size: 10.5pt; }")
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setPlaceholderText("5 or 0.0-12")
        self.setToolTip("A number sets the value, a range such as 0.0-12 "
                        "sets the range and its decimal places")

    def event(self, event):
        # Escape here is this field's, not a command's to cancel
        if (event.type() == QEvent.Type.ShortcutOverride
                and event.key() == Qt.Key.Key_Escape):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish(self.cancelled)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.committed.emit(False)
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if not self._done:
            self._done = True
            self.committed.emit(True)

    def _finish(self, signal):
        self._done = True
        signal.emit()


class CastDialog(QDialog):
    """Where cast geometry goes: a layer, and for more than one object
    whether they go as one group."""

    def __init__(self, layers, count, grouped, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cast")
        self.layers = QComboBox()
        for layer in layers.all():
            self.layers.addItem(layers.full_path(layer.id), layer.id)
        self.layers.setCurrentIndex(
            max(self.layers.findData(layers.current_id), 0))
        said = f"{count} object" + ("" if count == 1 else "s")
        self.group = QCheckBox(f"Group the {said}")
        self.group.setChecked(grouped)
        self.group.setVisible(count > 1)
        form = QFormLayout()
        form.addRow("Layer", self.layers)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            f"Cast {said}")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.group)
        root.addWidget(buttons)
        untether(self, over=QWidget.window(parent) if parent else None)

    def layer_id(self):
        return self.layers.currentData()


class RangeDialog(QDialog):
    """A slider's minimum and maximum, typed. A number keeps the decimal
    places it is typed to, with a comma or a point."""

    def __init__(self, params, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Range")
        places = params["decimals"]
        self.low = QLineEdit(hydra.format_number(params["min"], places))
        self.high = QLineEdit(hydra.format_number(params["max"], places))
        self.hint = QLabel()
        self.hint.setStyleSheet("color: #d9824a;")
        form = QFormLayout()
        form.addRow("Minimum", self.low)
        form.addRow("Maximum", self.high)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.hint)
        root.addWidget(self.buttons)
        for field in (self.low, self.high):
            field.textChanged.connect(self._check)
        self._check()
        # the editor's own `window` is the main window, so ask Qt for the
        # floating one it sits in
        untether(self, over=QWidget.window(parent) if parent else None)

    def values(self):
        """Minimum, maximum and the most decimal places either was typed to."""
        (low, a), (high, b) = (hydra.parse_number(f.text())
                               for f in (self.low, self.high))
        return low, high, max(a, b)

    def _check(self):
        try:
            low, high, _places = self.values()
            problem = ("" if low < high
                       else "The minimum has to be below the maximum")
        except ValueError:
            problem = "Type a number in both fields"
        self.hint.setText(problem)
        self.hint.setVisible(bool(problem))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            not problem)


class PreviewMeshes:
    """The preview's triangles, segments and points, as the viewport's
    overlay draw takes them.

    Meshing is what a preview costs, so each shape is meshed once, without
    its placement, and only turned into place on every solve after. A
    rotated shape keeps its surfaces and changes only its placement, which
    is what makes dragging a slider into a Rotate run smoothly.
    """

    def __init__(self):
        self._kept: dict = {}

    def overlay(self, shapes):
        kept, parts = {}, ([], [], [])
        for shape in shapes:
            base, matrix = _unplaced(shape)
            key = hash(base) if matrix is not None else ("obj", id(shape))
            entry = self._kept.get(key) or kept.get(key)
            if entry is None or not _same(entry[0], base):
                entry = (base, _mesh_arrays(base))
            kept[key] = entry
            for part, arr in zip(parts, entry[1]):
                if len(arr):
                    part.append(arr if matrix is None
                                else arr @ matrix[:3, :3].T + matrix[:3, 3])
        self._kept = kept
        return tuple(np.concatenate(part) if part
                     else np.empty((0, 3), np.float32) for part in parts)


def _unplaced(shape):
    """An OCC shape without its placement, and the placement as a matrix;
    anything else as it is, with no matrix."""
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS_Shape
    if not isinstance(shape, TopoDS_Shape):
        return shape, None
    trsf = shape.Location().Transformation()
    matrix = np.array([[trsf.Value(r, c) for c in range(1, 5)]
                       for r in range(1, 4)] + [[0.0, 0.0, 0.0, 1.0]])
    return shape.Located(TopLoc_Location()), matrix


def _same(a, b):
    from OCP.TopoDS import TopoDS_Shape
    return a.IsEqual(b) if isinstance(a, TopoDS_Shape) else a is b


def _mesh_arrays(shape):
    from ..core.tessellate import tessellate
    empty = np.empty((0, 3))
    try:
        mesh = tessellate(shape)
    except Exception:                                      # noqa: BLE001
        return empty, empty, empty
    tris = (mesh.vertices[mesh.triangles.ravel()].astype(float)
            if len(mesh.triangles) else empty)
    segs = (mesh.edge_segments.reshape(-1, 3).astype(float)
            if len(mesh.edge_segments) else empty)
    wires = _mesh_wires(shape)
    if wires is not None:
        segs = wires
    points = mesh.points.astype(float) if len(mesh.points) else empty
    return tris, segs, points


def _mesh_wires(shape):
    """Every edge of a mesh's triangles, for a mesh small enough to show
    them all: the model shows a mesh's rim and creases only, which hides how
    a mesh Hydra made, a Delaunay one say, is triangulated. None for other
    shapes, and for a mesh as big as a scan."""
    from ..core.mesh import MeshShape
    if not isinstance(shape, MeshShape) or not (
            0 < len(shape.triangles) <= MESH_WIRES_UP_TO):
        return None
    tris = shape.triangles.astype(np.int64)
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]],
                            tris[:, [2, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    return shape.vertices[edges].reshape(-1, 3).astype(float)
