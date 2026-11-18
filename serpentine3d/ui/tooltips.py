"""Tooltips that are simply there: sooner, with no fade, slide or shadow,
and round at the corners.

Qt's own tooltip window keeps the shadow and the square corners whatever
its flags are set to, so a widget's tooltip is shown here instead. A view
that works out a tooltip per row has none of its own to show, and still
goes through Qt, dark from the style sheet like everything else.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QProxyStyle, QStyle

from . import fields, popups

WAKE_UP_MS = 250
_BG = QColor("#1f2023")
_BORDER = QColor("#3d3e44")
_TEXT = "#cfd0d2"
_RADIUS = 5.0
_OFFSET = QPoint(12, 18)


class _Timing(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, data=None):
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return WAKE_UP_MS
        return super().styleHint(hint, option, widget, data)

    def polish(self, widget):
        fields.polish(widget)
        popups.polish(widget)
        return super().polish(widget)


class _Tip(QLabel):
    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setObjectName("serpentineTip")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet(f"QLabel#serpentineTip {{ background: transparent;"
                           f" border: none; color: {_TEXT};"
                           f" padding: 5px 8px; }}")
        self.owner = None

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(_BORDER, 1))
        p.setBrush(_BG)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                          _RADIUS, _RADIUS)
        p.end()
        super().paintEvent(ev)

    def show_for(self, owner, text: str, at: QPoint):
        self.owner = owner
        self.setText(text)
        self.adjustSize()
        pos = at + _OFFSET
        screen = QGuiApplication.screenAt(at) or QGuiApplication.primaryScreen()
        room = screen.availableGeometry()
        if pos.x() + self.width() > room.right():
            pos.setX(max(room.left(), at.x() - self.width() - 4))
        if pos.y() + self.height() > room.bottom():
            pos.setY(max(room.top(), at.y() - self.height() - 4))
        self.move(pos)
        self.show()
        self.raise_()

    def drop(self):
        self.owner = None
        self.hide()


_GONE = {QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.MouseButtonPress,
         QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel,
         QEvent.Type.KeyPress, QEvent.Type.WindowDeactivate,
         QEvent.Type.DragEnter}


class _Shower(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.tip = _Tip()

    def eventFilter(self, obj, ev):
        kind = ev.type()
        if kind == QEvent.Type.ToolTip:
            text = obj.toolTip() if hasattr(obj, "toolTip") else ""
            if text and obj.isEnabled():
                self.tip.show_for(obj, text, ev.globalPos())
                return True
            if self.tip.owner is not None:
                self.tip.drop()
            return False
        if self.tip.owner is not None:
            if kind == QEvent.Type.MouseButtonPress or (
                    obj is self.tip.owner and kind in _GONE):
                self.tip.drop()
            elif kind == QEvent.Type.ApplicationDeactivate:
                self.tip.drop()
        return False


def install(app: QApplication):
    app.setEffectEnabled(Qt.UIEffect.UI_AnimateTooltip, False)
    app.setEffectEnabled(Qt.UIEffect.UI_FadeTooltip, False)
    app.setStyle(_Timing())
    shower = _Shower(app)
    app.installEventFilter(shower)
    app._tooltip_shower = shower
    return shower


def showing():
    """The tooltip on screen, if one of ours is."""
    shower = getattr(QApplication.instance(), "_tooltip_shower", None)
    if shower is None or not shower.tip.isVisible():
        return None
    return shower.tip

