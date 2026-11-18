"""Asking whether to save unsaved work before it is closed or replaced."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout,
)

SAVE, DISCARD, CANCEL = "save", "discard", "cancel"
_CLOSE_SIZE = 30
_CLOSE_INSET = 8

_STYLE = """
#card {
    background: #2e2f34; border: 1px solid #45464c; border-radius: 10px;
}
QLabel { background: transparent; }
#heading { font-size: 15px; font-weight: 600; color: #e8e8ea; }
#body { color: #a9aaae; }
QPushButton { min-width: 60px; padding: 6px 14px; border-radius: 6px; }
#closeX {
    min-width: 0; padding: 0; border: none; border-radius: 5px;
    background: transparent; color: #8d8e93; font-size: 17px;
}
#closeX:hover { background: #3f4047; color: #e8e8ea; }
#saveButton {
    background: #d9a441; border: 1px solid #d9a441; color: #1f1f22;
    font-weight: 600;
}
#saveButton:hover { background: #e6b75a; border-color: #e6b75a; }
#saveButton:pressed { background: #b98a33; }
"""


class SavePrompt(QDialog):
    def __init__(self, parent, name: str):
        super().__init__(parent)
        self.answer = CANCEL
        self.setWindowTitle("Unsaved changes")
        self.setWindowFlags(Qt.WindowType.Dialog
                            | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(_STYLE)
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

        col = QVBoxLayout(card)
        col.setContentsMargins(22, 20, 22, 18)
        col.setSpacing(6)
        heading = QLabel(f"Save changes to “{name}”?", card)
        heading.setObjectName("heading")
        heading.setContentsMargins(0, 0, _CLOSE_SIZE, 0)
        self._card = card
        self._close = QPushButton("✕", card)
        self._close.setObjectName("closeX")
        self._close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._close.setFixedSize(_CLOSE_SIZE, _CLOSE_SIZE)
        self._close.clicked.connect(self.reject)
        card.installEventFilter(self)
        heading.setMinimumWidth(340)
        col.setContentsMargins(22, 18, 22, 18)
        body = QLabel("Unsaved changes will be lost if you don't save them.",
                      card)
        body.setObjectName("body")
        body.setWordWrap(True)
        col.addWidget(heading)
        col.addWidget(body)
        col.addSpacing(14)

        row = QHBoxLayout()
        row.setSpacing(8)
        discard = QPushButton("Don't Save", card)
        cancel = QPushButton("Cancel", card)
        save = QPushButton("Save", card)
        save.setObjectName("saveButton")
        save.setDefault(True)
        for b in (save, discard, cancel):
            b.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Fixed)
            row.addWidget(b, 1)
        col.addLayout(row)

        discard.clicked.connect(lambda: self._finish(DISCARD))
        cancel.clicked.connect(self.reject)
        save.clicked.connect(lambda: self._finish(SAVE))
        save.setFocus()

    def eventFilter(self, obj, ev):
        if obj is self._card and ev.type() == QEvent.Type.Resize:
            # as far in from the top as from the right: on the corner's
            # diagonal
            self._close.move(obj.width() - _CLOSE_INSET - _CLOSE_SIZE,
                             _CLOSE_INSET)
            self._close.raise_()
        return super().eventFilter(obj, ev)

    def _finish(self, answer: str):
        self.answer = answer
        self.accept()

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


def ask_save_changes(parent, name: str) -> str:
    """SAVE, DISCARD or CANCEL."""
    dlg = SavePrompt(parent, name)
    dlg.exec()
    return dlg.answer
