"""Menus with round corners and a faint drop shadow, drawn by the app
rather than the system so the shadow follows the corners."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QMenu

SHADOW = 8
RADIUS = 8.0
_DROP = 2


class _Shadow(QObject):
    def eventFilter(self, menu, ev):
        t = ev.type()
        if t == QEvent.Type.Paint:
            _paint_shadow(menu)
        elif t == QEvent.Type.Show and not menu.property("_shadowPlaced"):
            # the menu's box sits SHADOW in from its edge, so it would
            # otherwise open that far off from where it was asked to
            menu.setProperty("_shadowPlaced", True)
            menu.move(menu.pos() - QPoint(SHADOW, SHADOW - _DROP))
        elif t == QEvent.Type.Hide:
            menu.setProperty("_shadowPlaced", False)
        return False


_filter = _Shadow()


def _paint_shadow(menu):
    p = QPainter(menu)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    box = QRectF(menu.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)
    box.translate(0, _DROP)
    for i in range(SHADOW, 0, -1):
        p.setBrush(QColor(0, 0, 0, 3))
        p.drawRoundedRect(box.adjusted(-i, -i, i, i), RADIUS + i, RADIUS + i)
    p.end()


def polish(widget):
    if not isinstance(widget, QMenu) or widget.property("_roundPopup"):
        return
    widget.setProperty("_roundPopup", True)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    widget.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    widget.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
    widget.installEventFilter(_filter)
