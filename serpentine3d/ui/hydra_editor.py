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
    QEvent, QMimeData, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QActionGroup, QColor, QCursor, QFont, QFontMetrics, QIcon, QKeySequence,
    QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDockWidget, QFileDialog, QFormLayout, QFrame, QGraphicsItem,
    QGraphicsPathItem, QGraphicsScene, QGraphicsView, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPushButton, QScrollArea, QStackedWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from ..core import hydra
from ..core.hydra import (
    CATEGORIES, COMPONENTS, GEOMETRY_KINDS, Graph, HydraError,
)
from .dialogs import untether
from .icons import command_icon, panel_icon

NODE_WIDTH = 110
NODE_HEIGHT = 28
PAN_SLOP = 4                # pixels a right drag moves before it pans
PORT_RADIUS = 5
PORT_REACH = 11             # how near a click or a wire's end has to be
SNAP_REACH = 26             # screen pixels a dropped wire finds a port within
PASTE_STEP = 30             # how far a paste lands from what it copied
SEARCH_ROWS = 12            # the most the search lists before it scrolls
CLIPBOARD = "application/x-serpentine-hydra"
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
         "vector": QColor("#f08a8a")}


_ICONS: dict = {}


def component_icon(comp):
    """The toolbar's icon for what a component holds, made once."""
    if comp.icon not in _ICONS:
        # the slider wears the Properties panel's mark: values on rails
        _ICONS[comp.icon] = (QIcon(panel_icon("properties"))
                             if comp.icon == "sliders"
                             else command_icon(comp.icon) if comp.icon
                             else None)
    return _ICONS[comp.icon]


def node_size(comp):
    """A component's input names column, width and height: as wide as the
    names in it need, and no wider."""
    small, bold = QFont(), QFont()
    small.setPointSizeF(8)
    bold.setPointSizeF(9)
    bold.setBold(True)
    labels = (max(QFontMetrics(small).horizontalAdvance(p.name)
                  for p in comp.inputs) + 20 if comp.inputs else 0)
    title = QFontMetrics(bold).horizontalAdvance(comp.title)
    width = (SLIDER_WIDTH if comp.key == "slider" else max(
        NODE_WIDTH, labels + NODE_HEIGHT + title + 18))
    height = max(NODE_HEIGHT, INPUT_ROW * len(comp.inputs) + 8)
    return labels, width, height


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
        self.setToolTip(port.name)

    def show_values(self, values, wired):
        """An input's tooltip: its name and what reaches it right now."""
        said = hydra.describe(values)
        picked = self.node_item.node.params.get("set", {})
        if not wired and self.port.name in picked:
            said += " (set in the model)"
        elif not wired and self.port.default is not None:
            said += " (default)"
        self.setToolTip(f"{self.port.name}: {said}")

    @property
    def node_id(self):
        return self.node_item.node.id

    def boundingRect(self):
        return QRectF(-PORT_REACH, -PORT_REACH, 2 * PORT_REACH, 2 * PORT_REACH)

    def shape(self):
        # what a click finds: a good deal more than the dot that is drawn
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), PORT_REACH, PORT_REACH)
        return path

    def set_highlight(self, on):
        """Lit as when hovered: where a dragged wire would dock."""
        if self._hover != on:
            self._hover = on
            self.update()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(217, 164, 65, 70))
            painter.drawEllipse(QPointF(0, 0), PORT_RADIUS + 4,
                                PORT_RADIUS + 4)
        painter.setPen(QPen(_ACCENT if self._hover else QColor("#1b1c1f"), 1.5))
        painter.setBrush(_PORT.get(self.port.kind, _WIRE))
        painter.drawEllipse(QPointF(0, 0), PORT_RADIUS, PORT_RADIUS)

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()


class WireItem(QGraphicsPathItem):
    def __init__(self, wire=None):
        super().__init__()
        self.wire = wire
        self.setZValue(-1)
        if wire is not None:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def set_ends(self, a: QPointF, b: QPointF):
        path = QPainterPath(a)
        bend = max(40.0, abs(b.x() - a.x()) * 0.5)
        path.cubicTo(a + QPointF(bend, 0), b - QPointF(bend, 0), b)
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        pen = QPen(_ACCENT if self.isSelected() else _WIRE, 2)
        if self.wire is None:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)
        painter.drawPath(self.path())

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path())


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
        self.is_slider = node.key == "slider"
        self.labels, self.width, self.height = node_size(comp)
        self._sliding = False
        self.inputs = [PortItem(self, p, False, i, len(comp.inputs))
                       for i, p in enumerate(comp.inputs)]
        self.outputs = [PortItem(self, p, True, i, len(comp.outputs))
                        for i, p in enumerate(comp.outputs)]

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
        if self.is_slider:
            self._paint_slider(painter)
            return
        left = self.labels + NODE_HEIGHT + 2
        painter.drawText(QRectF(left, 0, self.width - left - 8, self.height),
                         Qt.AlignmentFlag.AlignVCenter,
                         self.node.component.title)

    def can_hide(self):
        """Whether it shows anything in the viewports to hide."""
        return any(p.kind in GEOMETRY_KINDS or p.kind == "vector"
                   for p in self.node.component.outputs)

    def is_hidden(self):
        return self.can_hide() and not self.node.preview

    def _paint_labels(self, painter):
        painter.save()
        font = QFont(painter.font())
        font.setPointSizeF(8)
        painter.setFont(font)
        status = self.result.status if self.result else "ok"
        painter.setPen(_MUTED if status == "ok" else _TEXT)
        for port in self.inputs:
            painter.drawText(QRectF(10, port.y() - INPUT_ROW / 2,
                                    self.labels - 12, INPUT_ROW),
                             Qt.AlignmentFlag.AlignVCenter, port.port.name)
        painter.setPen(QPen(QColor("#1b1c1f"), 1))
        painter.drawLine(QPointF(self.labels, 5),
                         QPointF(self.labels, self.height - 5))
        painter.restore()

    def _rail(self):
        """Where the rail runs, left to right, along the middle."""
        return NODE_HEIGHT + 6, self.width - VALUE_WIDTH - VALUE_GAP - 12

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
            return
        super().mouseReleaseEvent(event)

    def summary(self):
        """How many objects it holds, said in words."""
        comp = self.node.component
        count = (sum(len(v) for v in self.result.outputs.values())
                 if self.result else 0)
        if not comp.picks:
            noun = {"point": "point", "vector": "vector"}.get(
                comp.outputs[0].kind, "object")
            return f"{count} {noun}" + ("" if count == 1 else "s")
        return f"{count} " + (comp.title.lower() if count == 1
                              else comp.plural)

    def set_result(self, result):
        self.result = result
        said = self.value_text() if self.is_slider else self.summary()
        tip = f"{self.node.component.description}\n\n{said}"
        if result is not None and result.message:
            tip += "\n" + result.message
        self.setToolTip(tip)
        for port in self.inputs:
            port.show_values(*self.editor.graph.input_values(
                self.node.id, port.port, self.editor.results))
        self.update()

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

        def fits(other):
            out, inp = (port, other) if port.is_output else (other, port)
            return hydra.takes(inp.port.kind, out.port.kind)

        ends = [other for item in self.canvas.node_items.values()
                if item is not mine
                for other in (item.inputs if port.is_output else item.outputs)]
        near = [o for o in ends if far(o) <= reach]
        if near:
            return min(near, key=far)
        node = self._node_at(pos)
        if node is None or node is mine:
            return None
        own = node.inputs if port.is_output else node.outputs
        fitting = [o for o in own if fits(o)] or own
        return min(fitting, key=far) if fitting else None

    def _show_target(self, target):
        if self._target is not target:
            if self._target is not None:
                self._target.set_highlight(False)
            self._target = target
            if target is not None:
                target.set_highlight(True)

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
            wire = (None if port.is_output
                    else self.canvas.editor.wire_into(port))
            if wire is not None:
                # picking up a wire by its end: it hangs from its source
                self.canvas.editor.disconnect(wire)
                port = self.canvas.node_items[wire.source].port(wire.output,
                                                               True)
            temp = WireItem()
            self.addItem(temp)
            temp.set_ends(port.scenePos(), event.scenePos())
            self._drag = (port, temp)
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
            port, temp = self._drag
            target = self._dock_at(event.scenePos(), port)
            self._show_target(target)
            end = event.scenePos() if target is None else target.scenePos()
            if port.is_output:
                temp.set_ends(port.scenePos(), end)
            else:
                temp.set_ends(end, port.scenePos())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._copying is not None:
            self._copying = None
            self.canvas.editor.changed()
            return
        if self._drag is not None:
            port, temp = self._drag
            self._drag = None
            self.removeItem(temp)
            other = self._dock_at(event.scenePos(), port)
            self._show_target(None)
            if other is not None and other.is_output != port.is_output:
                out, inp = (port, other) if port.is_output else (other, port)
                self.canvas.editor.connect(out.node_id, out.port.name,
                                           inp.node_id, inp.port.name)
            return
        super().mouseReleaseEvent(event)

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

    def add_item(self, node):
        item = NodeItem(self.editor, node)
        self.scene().addItem(item)
        self.node_items[node.id] = item
        return item

    def remove_item(self, node_id):
        item = self.node_items.pop(node_id, None)
        if item is not None:
            self.scene().removeItem(item)

    def sync_wires(self):
        for item in self.wire_items:
            self.scene().removeItem(item)
        self.wire_items = []
        for wire in self.editor.graph.wires:
            item = WireItem(wire)
            self.scene().addItem(item)
            self.wire_items.append(item)
        self.update_wires()

    def update_wires(self, moved=None):
        for item in self.wire_items:
            w = item.wire
            if moved is not None and moved.node.id not in (w.source, w.target):
                continue
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
        self.meshes = PreviewMeshes()
        self.search = None         # the find-a-component field, while open
        self.canvas = HydraCanvas(self)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        add = QToolButton()
        add.setText("Add Component")
        add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        add.setMenu(self.component_menu(None))
        bar.addWidget(add)
        for label, slot, tip in (
                ("New", self.new_graph, "Start an empty graph"),
                ("Open…", self.open_graph, "Open a .hydra file"),
                ("Save", self.save_graph,
                 "Save to the graph's file, asking where only the first time"),
                ("Save As…", self.save_graph_as,
                 "Save to a file you choose")):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            bar.addWidget(button)
        bar.addStretch(1)
        self.status = QLabel()
        self.status.setStyleSheet("color: #9a9b9e;")
        bar.addWidget(self.status)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(bar)
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

    # ------------------------------------------------------------- editing

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
        """A component's menu over a component, the add menu elsewhere."""
        item = self.canvas.scene()._node_at(scene_pos)
        if item is None:
            self.find_component(scene_pos, screen_pos)
            return
        self.node_menu(item).exec(screen_pos)

    def find_component(self, scene_pos, screen_pos):
        """A field to type a component's name into, opened where the
        canvas was clicked; what is chosen is put there."""
        search = ComponentSearch(self)
        search.chosen.connect(lambda key: self.add_component(key, scene_pos))
        search.move(screen_pos)
        search.show()
        search.field.setFocus()
        self.search = search
        return search

    def node_menu(self, item):
        menu = QMenu(self)
        node = item.node
        if node.component.sets:
            # Set Crv... for a curve, Set Vector... for a vector
            command = "hydraset" if node.component.picks else "hydravector"
            menu.addAction(f"{node.component.sets}...",
                           lambda: self.pick(node.id, command))
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
        if any(p.kind in GEOMETRY_KINDS for p in node.component.outputs):
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

    def add_component(self, key, at=None):
        if at is None:
            at = self.canvas.mapToScene(self.canvas.viewport().rect().center())
            at -= QPointF(
                (SLIDER_WIDTH if key == "slider" else NODE_WIDTH) / 2,
                NODE_HEIGHT / 2)
        x, y = (at.x(), at.y()) if isinstance(at, QPointF) else at
        node = self.graph.add_node(key, x, y)
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
        self.solve()

    def set_references(self, node_id, ids):
        node = self.graph.nodes.get(node_id)
        if node is None:
            return
        node.params["refs"] = list(ids)
        self.solve()

    def connect(self, source, output, target, input):
        try:
            wire = self.graph.connect(source, output, target, input)
        except HydraError as exc:
            self.status.setText(str(exc))
            return None
        self.canvas.sync_wires()
        self.changed()
        return wire

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
        # At most one solve per tick, not one once the changes stop: a
        # slider dragged without a pause has to show while it moves.
        if not self._timer.isActive():
            self._timer.start()

    def solve(self):
        self._timer.stop()
        self.results = self.graph.solve(self.window.scene)
        for nid, item in self.canvas.node_items.items():
            item.set_result(self.results.get(nid))
        self.shapes = self.graph.preview_shapes(self.results)
        self._show_preview()
        if not self.graph.nodes:
            self.status.setText("Double-click the canvas to add a component")
        else:
            self.status.setText("")

    def set_active(self, active: bool):
        """A closed editor shows nothing in the model."""
        self.active = active
        self._show_preview()

    def _show_preview(self):
        self.window.scene.hydra_preview = (
            self.meshes.overlay(self.shapes)
            if self.active and self.shapes else None)
        for viewport in self.window.all_viewports():
            viewport.update()

    # --------------------------------------------------------- persistence

    def load(self, data: dict):
        if hasattr(self, "pages"):
            self.show_canvas()
        for nid in list(self.canvas.node_items):
            self.canvas.remove_item(nid)
        self.graph = Graph.from_dict(data)
        for node in self.graph.nodes.values():
            self.canvas.add_item(node)
        self.canvas.sync_wires()
        self.solve()

    def new_graph(self):
        self.load({})
        self.set_path(None)

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
        empty canvas only when there is neither."""
        current = self.graph.to_dict() if self.graph.nodes else None
        recent = self.recent()
        if current is None and not recent:
            self.show_canvas()
            return False
        self.start.fill(current, recent)
        self.pages.setCurrentWidget(self.start)
        self.start.setFocus()
        return True

    def show_canvas(self):
        self.pages.setCurrentWidget(self.canvas)

    def starting(self):
        return self.pages.currentWidget() is self.start

    def shutdown(self):
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
        _labels, w, h = node_size(comp)
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

    def __init__(self, title, detail, data, open_it, parent=None):
        super().__init__(parent)
        self.setObjectName("hydraCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(self.PREVIEW[0] + 16)
        self.open_it = open_it
        picture = QLabel()
        picture.setPixmap(graph_preview(data, *self.PREVIEW))
        name = QLabel(title)
        name.setObjectName("cardName")
        about = QLabel(detail)
        about.setObjectName("cardDetail")
        about.setToolTip(detail)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.addWidget(picture)
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
        self.cards = []
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


class ComponentSearch(QFrame):
    """Type to find a component. Before anything is typed it offers the
    components every graph starts from; typing searches them all, and hides
    the ones whose name does not fit."""

    chosen = Signal(str)

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

    def _take(self, item):
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        self.close()
        self.chosen.emit(key)


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
    points = mesh.points.astype(float) if len(mesh.points) else empty
    return tris, segs, points
