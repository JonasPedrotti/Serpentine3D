"""Lining up picked objects from the viewport: two small bars at its bottom
right, shown while two or more objects are picked. The row aligns across
the view, the column up and down it, both on the view's own CPlane."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QBoxLayout, QFrame, QToolButton

from .icons import align_icon

ACROSS = (("left", "Align left edges"),
          ("center", "Align centres, one above the other"),
          ("right", "Align right edges"),
          ("across", "Space evenly from left to right"))
UPDOWN = (("top", "Align top edges"),
          ("middle", "Align middles, side by side"),
          ("bottom", "Align bottom edges"),
          ("down", "Space evenly from top to bottom"))
MARGIN = 8
SPREADS = ("across", "down")


def _bar(vp, entries, direction):
    bar = QFrame(vp)
    bar.setObjectName("alignBar")
    bar.setStyleSheet(
        "#alignBar { background: #2b2d31; border: 1px solid #45484f;"
        " border-radius: 5px; }"
        "QToolButton { border: none; border-radius: 3px; padding: 3px; }"
        "QToolButton:hover { background: #3a3d43; }"
        "QToolButton:disabled { background: transparent; }")
    box = QBoxLayout(direction, bar)
    box.setContentsMargins(3, 3, 3, 3)
    box.setSpacing(1)
    bar.buttons = {}
    for how, tip in entries:
        button = QToolButton(bar)
        button.setIcon(align_icon(how))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(
            lambda _checked=False, how=how: vp.alignRequested.emit(how))
        box.addWidget(button)
        bar.buttons[how] = button
    bar.hide()
    return bar


class AlignBars:
    """The row across the bottom right corner and the column above it."""

    def __init__(self, vp):
        self.vp = vp
        self.row = _bar(vp, ACROSS, QBoxLayout.Direction.LeftToRight)
        self.column = _bar(vp, UPDOWN, QBoxLayout.Direction.TopToBottom)

    def follow(self):
        vp = self.vp
        picked = len(vp.selection.ids)
        if picked < 2 or vp.space != "model":
            self.row.hide()
            self.column.hide()
            return
        for bar in (self.row, self.column):
            # spacing evenly needs one between the first and the last
            for how in SPREADS:
                if how in bar.buttons:
                    bar.buttons[how].setEnabled(picked > 2)
            bar.adjustSize()
        w, h = vp.width(), vp.height()
        self.row.move(w - self.row.width() - MARGIN,
                      h - self.row.height() - MARGIN)
        self.column.move(w - self.column.width() - MARGIN,
                         self.row.y() - self.column.height() - 4)
        for bar in (self.row, self.column):
            bar.show()
            bar.raise_()
