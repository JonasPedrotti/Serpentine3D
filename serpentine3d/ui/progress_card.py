"""The popup a long job shows while it runs: the app's own card with what is
happening, a slim bar of its own and a way out."""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget,
)

from .card_dialog import STYLE, CardDialog

_TRACK = QColor("#3a3b41")
_FILL = QColor("#d9a441")
_WIDTH = 400

# Cancel is the way out, not the thing the card is for: a quiet button
# beside the bar, never the default one an accent ring calls out.
_QUIET = """
#quietButton {
    min-width: 0; padding: 5px 14px; border-radius: 6px;
    background: transparent; border: 1px solid #4a4b52; color: #c4c5c9;
}
#quietButton:hover { background: #3a3b41; color: #e8e8ea; }
#quietButton:pressed { background: #33343a; }
#quietButton:disabled { color: #6f7075; border-color: #3d3e44; }
#percent { color: #8d8e93; }
"""


class ProgressBar(QWidget):
    """A rounded track filling in the accent colour, 0..100."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_value(self, value: int):
        value = max(0, min(100, int(value)))
        if value != self.value:
            self.value = value
            self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = QRectF(self.rect())
        radius = r.height() / 2
        p.setBrush(_TRACK)
        p.drawRoundedRect(r, radius, radius)
        if self.value > 0:
            fill = QRectF(r.x(), r.y(),
                          max(r.height(), r.width() * self.value / 100),
                          r.height())
            p.setBrush(_FILL)
            p.drawRoundedRect(fill, radius, radius)
        p.end()


class ProgressCard(CardDialog):
    """What QProgressDialog offered the open: a label, a value, a cancel
    that is asked about, and a wait before it shows at all, so a quick
    file does not flash a popup up."""

    def __init__(self, parent, heading: str, delay: float = 0.5):
        super().__init__(parent, heading, title="Opening")
        if sys.platform.startswith("linux"):
            # GNOME glues a dialog-type window to its parent, so dragging
            # one dragged the main window too (ui/dialogs.untether)
            self.setWindowFlags(Qt.WindowType.Window
                                | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self._canceled = False
        self._started = time.monotonic()
        self._delay = delay
        self.setStyleSheet(STYLE + _QUIET)
        # Cancel and Escape are the way out; a cross as well said it twice
        self._close.hide()
        self.heading.setContentsMargins(0, 0, 0, 0)
        card, col = self.card, self.column
        col.setContentsMargins(22, 18, 22, 18)
        col.setSpacing(0)
        self.heading.setFixedWidth(_WIDTH)

        self.label = QLabel("", card)
        self.label.setObjectName("body")
        # one line of a fixed width: the card does not jump as it reads
        self.label.setFixedWidth(_WIDTH)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        col.addSpacing(4)
        col.addWidget(self.label)
        col.addSpacing(16)

        bar_row = QHBoxLayout()
        bar_row.setContentsMargins(0, 0, 0, 0)
        bar_row.setSpacing(12)
        self.bar = ProgressBar(card)
        self.percent = QLabel("0%", card)
        self.percent.setObjectName("percent")
        self.percent.setFixedWidth(self.percent.fontMetrics()
                                   .horizontalAdvance("100%") + 2)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
        self.cancel_button = QPushButton("Cancel", card)
        self.cancel_button.setObjectName("quietButton")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setDefault(False)
        self.cancel_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.cancel)
        bar_row.addWidget(self.bar, 1, Qt.AlignmentFlag.AlignVCenter)
        bar_row.addWidget(self.percent, 0, Qt.AlignmentFlag.AlignVCenter)
        bar_row.addWidget(self.cancel_button, 0,
                          Qt.AlignmentFlag.AlignVCenter)
        col.addLayout(bar_row)

    def cancel(self):
        self._canceled = True
        self.label.setText("Cancelling…")
        self.cancel_button.setEnabled(False)

    def reject(self):
        # the corner cross and Escape ask the job to stop; the job closes
        # the card once it has
        self.cancel()

    def finish(self):
        """Close for good, the job done or stopped."""
        self.done(0)

    def wasCanceled(self) -> bool:
        return self._canceled

    def labelText(self) -> str:
        return self.label.text()

    def setLabelText(self, text: str):
        if not self._canceled and text:
            self.label.setText(self.label.fontMetrics().elidedText(
                text, Qt.TextElideMode.ElideMiddle, _WIDTH))

    def setValue(self, value: int):
        self.bar.set_value(value)
        self.percent.setText(f"{self.bar.value}%")
        if not self.isVisible() and \
                time.monotonic() - self._started >= self._delay:
            self.show()
