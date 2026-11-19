"""The app's own popup: a frameless card with a shadow, a heading, a close
cross in its corner and a highlighted main button, dragged by its body."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QFrame, QGraphicsDropShadowEffect, QLabel, QPushButton,
    QVBoxLayout,
)

_CLOSE_SIZE = 30
_CLOSE_INSET = 8

STYLE = """
#card {
    background: #2e2f34; border: 1px solid #45464c; border-radius: 10px;
}
QLabel { background: transparent; }
#heading { font-size: 15px; font-weight: 600; color: #e8e8ea; }
#body { color: #a9aaae; }
#fieldLabel { color: #c4c5c9; }
QPushButton { min-width: 60px; padding: 6px 14px; border-radius: 6px; }
#closeX {
    min-width: 0; padding: 0; border: none; border-radius: 5px;
    background: transparent; color: #8d8e93; font-size: 17px;
}
#closeX:hover { background: #3f4047; color: #e8e8ea; }
#primaryButton {
    background: #d9a441; border: 1px solid #d9a441; color: #1f1f22;
    font-weight: 600;
}
#primaryButton:hover { background: #e6b75a; border-color: #e6b75a; }
#primaryButton:pressed { background: #b98a33; }
"""


class CardDialog(QDialog):
    """Subclasses fill `self.column`, under the heading."""

    def __init__(self, parent, heading: str, title: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title or heading)
        self.setWindowFlags(Qt.WindowType.Dialog
                            | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self._drag = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        card = QFrame(self)
        card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        self.card = card

        col = QVBoxLayout(card)
        col.setContentsMargins(22, 18, 22, 18)
        col.setSpacing(6)
        self.heading = QLabel(heading, card)
        self.heading.setObjectName("heading")
        self.heading.setContentsMargins(0, 0, _CLOSE_SIZE, 0)
        col.addWidget(self.heading)
        self.column = col

        self._close = QPushButton("✕", card)
        self._close.setObjectName("closeX")
        self._close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._close.setFixedSize(_CLOSE_SIZE, _CLOSE_SIZE)
        self._close.clicked.connect(self.reject)
        card.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.card and ev.type() == QEvent.Type.Resize:
            # as far in from the top as from the right: on the corner's
            # diagonal
            self._close.move(obj.width() - _CLOSE_INSET - _CLOSE_SIZE,
                             _CLOSE_INSET)
            self._close.raise_()
        return super().eventFilter(obj, ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        parent = self.parentWidget()
        if parent is not None:
            g = self.frameGeometry()
            g.moveCenter(parent.window().frameGeometry().center())
            self.move(g.topLeft())

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag is not None:
            self.move(ev.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag = None
        super().mouseReleaseEvent(ev)
