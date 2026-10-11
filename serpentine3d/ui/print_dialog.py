"""Print sheets: which, and where to (#38).

"When printing layouts there should be a page to define which layouts are
to be printed and any available settings, much like in Rhino." The set is
listed the way the Sheets list binds it, a box for every sheet and every
group, and prints to a PDF file or to a printer. Each sheet goes out on its
own paper, page by page, the same drawing the PDF export makes.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout,
)

from ..core.layout import sheet_label, sheet_tree
from . import theme

_ID_ROLE = Qt.ItemDataRole.UserRole


class PrintDialog(QDialog):
    """`ids`: the sheets to start with; None for the open one, or every
    sheet when none is open."""

    def __init__(self, window, ids=None, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.scene = window.scene
        self.setWindowTitle("Print sheets")
        self.resize(420, 520)
        if ids is None:
            space = getattr(window, "space", "model")
            ids = ([space] if self.scene.get_layout(space) is not None
                   else [lay.id for lay in self.scene.layouts])
        wanted = set(ids)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        for node in sheet_tree(self.scene.layouts, self.scene.sheet_groups):
            self.tree.addTopLevelItem(self._row(node, wanted))
        self.tree.expandAll()
        self.tree.itemChanged.connect(self._recount)

        everything = QPushButton("All")
        everything.clicked.connect(lambda: self.choose_all(True))
        nothing = QPushButton("None")
        nothing.clicked.connect(lambda: self.choose_all(False))
        picks = QHBoxLayout()
        picks.addWidget(everything)
        picks.addWidget(nothing)
        picks.addStretch(1)

        self.destination = QComboBox()
        self.destination.addItems(["PDF file", "Printer"])
        self.destination.currentTextChanged.connect(self._destination_set)
        self.pdf_path = QLineEdit(self._default_path())
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        self._file_row = QHBoxLayout()
        self._file_row.addWidget(self.pdf_path, 1)
        self._file_row.addWidget(browse)
        self._browse_button = browse
        form = QFormLayout()
        form.addRow("To", self.destination)
        form.addRow("File", self._file_row)
        self._form = form

        self.summary = QLabel()
        self.summary.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._go)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Sheets"))
        layout.addWidget(self.tree, 1)
        layout.addLayout(picks)
        layout.addLayout(form)
        layout.addWidget(self.summary)
        layout.addWidget(self.buttons)
        self._destination_set(self.destination.currentText())
        self._recount()

    def _row(self, node, wanted):
        kind, thing, children = node
        item = QTreeWidgetItem([thing.name if kind == "group"
                                else sheet_label(thing)])
        flags = (Qt.ItemFlag.ItemIsEnabled
                 | Qt.ItemFlag.ItemIsUserCheckable)
        if kind == "group":
            flags |= Qt.ItemFlag.ItemIsAutoTristate
            for child in children:
                item.addChild(self._row(child, wanted))
        else:
            item.setData(0, _ID_ROLE, thing.id)
            item.setCheckState(0, Qt.CheckState.Checked if thing.id in wanted
                               else Qt.CheckState.Unchecked)
        item.setFlags(flags)
        if kind == "group" and not children:
            item.setCheckState(0, Qt.CheckState.Unchecked)
        return item

    # ------------------------------------------------------------- choosing

    def _sheet_rows(self):
        out = []
        stack = [self.tree.topLevelItem(i)
                 for i in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop(0)
            if item.data(0, _ID_ROLE) is not None:
                out.append(item)
            stack[0:0] = [item.child(i) for i in range(item.childCount())]
        return out

    def chosen(self) -> list:
        """The ticked sheets, in the set's order."""
        ids = {it.data(0, _ID_ROLE) for it in self._sheet_rows()
               if it.checkState(0) == Qt.CheckState.Checked}
        return [lay for lay in self.scene.layouts if lay.id in ids]

    def choose_all(self, on: bool):
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for item in self._sheet_rows():
            item.setCheckState(0, state)

    def _recount(self, *_args):
        n = len(self.chosen())
        self.summary.setText("No sheets ticked" if n == 0 else
                             f"{n} sheet{'s' if n != 1 else ''}, a page each")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            n > 0)

    # ---------------------------------------------------------- destination

    def _default_path(self) -> str:
        current = getattr(getattr(self.window, "ctx", None),
                          "current_path", None)
        if current:
            return os.path.splitext(current)[0] + ".pdf"
        return os.path.join(os.path.expanduser("~"), "sheets.pdf")

    def _destination_set(self, text: str):
        to_file = text == "PDF file"
        self.pdf_path.setVisible(to_file)
        self._browse_button.setVisible(to_file)
        self._form.setRowVisible(1, to_file)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Save PDF" if to_file else "Print…")

    def _browse(self):
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save sheets as PDF", self.pdf_path.text(), "PDF (*.pdf)")
        if path:
            self.pdf_path.setText(path)

    # ------------------------------------------------------------- printing

    def print_pdf(self) -> int:
        """Write the ticked sheets to the PDF file. Returns the pages."""
        from ..fileio.pdf import export_layouts_pdf
        sheets = self.chosen()
        if not sheets:
            return 0
        path = os.path.abspath(os.path.expanduser(
            self.pdf_path.text().strip()))
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        export_layouts_pdf(self.window, sheets, path)
        self.written = path
        return len(sheets)

    def print_to(self, device) -> int:
        """Paint the ticked sheets onto a paged device (a printer)."""
        from ..fileio.pdf import paint_layouts
        return paint_layouts(device, self.window, self.chosen())

    def _go(self):
        if self.destination.currentText() == "PDF file":
            n = self.print_pdf()
            echo = getattr(getattr(self.window, "command_line", None),
                           "echo", None)
            if n and echo is not None:
                echo(f"Saved {n} sheet{'s' if n != 1 else ''} to "
                     f"{self.written}.")
            self.accept()
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted:
            return
        self.print_to(printer)
        self.accept()
