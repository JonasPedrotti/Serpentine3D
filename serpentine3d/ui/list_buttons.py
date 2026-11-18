"""The row of buttons under the Layers and Sheets lists."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QHBoxLayout, QPushButton

from . import icons

_STYLE = ("QPushButton { border: none; border-radius: 3px; padding: 0; }"
          "QPushButton:hover { background: rgba(255, 255, 255, 22); }"
          "QPushButton:pressed { background: rgba(255, 255, 255, 40); }")
_GAP = 10


def list_button(glyph: str, tip: str, slot) -> QPushButton:
    button = QPushButton()
    button.setIcon(icons.list_icon(glyph))
    button.setIconSize(QSize(16, 16))
    button.setFixedSize(26, 24)
    button.setFlat(True)
    button.setStyleSheet(_STYLE)
    button.setToolTip(tip)
    # a clicked signal hands its checked state to any slot that takes one
    button.clicked.connect(lambda _checked=False: slot())
    return button


def button_row(*groups) -> QHBoxLayout:
    """A row of (glyph, tip, slot) groups, a gap between each group."""
    row = QHBoxLayout()
    row.setContentsMargins(4, 3, 4, 4)
    row.setSpacing(2)
    for i, group in enumerate(groups):
        if i:
            row.addSpacing(_GAP)
        for glyph, tip, slot in group:
            row.addWidget(list_button(glyph, tip, slot))
    row.addStretch(1)
    return row
