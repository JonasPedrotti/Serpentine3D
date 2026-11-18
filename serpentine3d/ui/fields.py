"""What the style sheet cannot say about drop-downs and number fields."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (QAbstractSpinBox, QComboBox, QLineEdit,
                               QListView)

SPIN_TEXT_INSET = 7


def polish(widget) -> None:
    if isinstance(widget, QAbstractSpinBox):
        _inset_spin_text(widget)
    elif isinstance(widget, QComboBox):
        _leave_out_current(widget)


class _SelectOnClickIn(QObject):
    """The click that enters a number field picks the whole number, so what
    is typed next replaces it. Clicks once inside place the cursor."""

    def eventFilter(self, spin, ev):
        if (ev.type() == QEvent.Type.FocusIn
                and ev.reason() == Qt.FocusReason.MouseFocusReason):
            # after the press has put the cursor down, or it undoes this
            QTimer.singleShot(0, spin.selectAll)
        return False


def _inset_spin_text(spin: QAbstractSpinBox) -> None:
    edit = spin.findChild(QLineEdit)
    if edit is None or spin.property("_fields_polished"):
        return
    spin.setProperty("_fields_polished", True)
    spin.installEventFilter(_SelectOnClickIn(spin))
    # Style sheets cannot pad a spin box's text on the left. A field with
    # no arrows centres its text itself.
    if spin.buttonSymbols() != QAbstractSpinBox.ButtonSymbols.NoButtons:
        edit.setTextMargins(SPIN_TEXT_INSET, 0, 0, 0)


def _leave_out_current(combo: QComboBox) -> None:
    """The open list offers only the other choices: the one already made
    is in the field above it."""
    if combo.property("_leaves_out_current") or combo.isEditable():
        return
    combo.setProperty("_leaves_out_current", True)

    def refresh(*_):
        view = combo.view()
        if not isinstance(view, QListView):
            return
        current = combo.currentIndex()
        for row in range(combo.count()):
            view.setRowHidden(row, row == current)

    combo.currentIndexChanged.connect(refresh)
    model = combo.model()
    model.rowsInserted.connect(refresh)
    model.rowsRemoved.connect(refresh)
    model.modelReset.connect(refresh)
    refresh()
