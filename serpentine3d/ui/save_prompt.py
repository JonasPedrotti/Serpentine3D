"""Asking whether to save unsaved work before it is closed or replaced."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy

from .card_dialog import CardDialog

SAVE, DISCARD, CANCEL = "save", "discard", "cancel"


class SavePrompt(CardDialog):
    def __init__(self, parent, name: str):
        super().__init__(parent, f"Save changes to “{name}”?",
                         title="Unsaved changes")
        self.answer = CANCEL
        card = self.card
        col = self.column
        self.heading.setMinimumWidth(340)
        body = QLabel("Unsaved changes will be lost if you don't save them.",
                      card)
        body.setObjectName("body")
        body.setWordWrap(True)
        col.addWidget(body)
        col.addSpacing(14)

        row = QHBoxLayout()
        row.setSpacing(8)
        discard = QPushButton("Don't Save", card)
        cancel = QPushButton("Cancel", card)
        save = QPushButton("Save", card)
        save.setObjectName("primaryButton")
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

    def _finish(self, answer: str):
        self.answer = answer
        self.accept()


def ask_save_changes(parent, name: str) -> str:
    """SAVE, DISCARD or CANCEL."""
    dlg = SavePrompt(parent, name)
    dlg.exec()
    return dlg.answer
