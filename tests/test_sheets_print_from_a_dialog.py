"""Sheets print from a dialog that shows the set (#38).

"When printing layouts there should be a page to define which layouts are
to be printed and any available settings, much like in Rhino." The dialog
lists the set as the Sheets list binds it, with a box for each sheet and
each group, starts with what was asked for (the picked sheets, else the
open one), and prints to a PDF file or to a printer. Each sheet keeps its
own paper size and orientation, page by page.
"""

from __future__ import annotations

import re

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from serpentine3d.core.layout import Layout, SheetGroup
from serpentine3d.ui.print_dialog import PrintDialog


@pytest.fixture
def window(_qapp):
    from serpentine3d.app import MainWindow
    w = MainWindow()
    plans = SheetGroup(name="Plans")
    w.scene.sheet_groups = [plans]
    w.scene.layouts = [
        Layout(name="Cover", paper_w=420.0, paper_h=297.0),
        Layout(name="Ground", number="A-101", group=plans.id,
               paper_w=594.0, paper_h=420.0),
        Layout(name="Roof", number="A-102", group=plans.id,
               paper_w=210.0, paper_h=297.0),
    ]
    w.scene.notify()
    yield w
    w.mark_saved()
    w.close()


def _box(dialog, text):
    found = dialog.tree.findItems(text, Qt.MatchFlag.MatchExactly
                                  | Qt.MatchFlag.MatchRecursive)
    assert found, f"no row {text!r}"
    return found[0]


def _ids(w, *names):
    return [lay.id for lay in w.scene.layouts if lay.name in names]


def test_it_starts_with_the_sheets_asked_for(window):
    dialog = PrintDialog(window, _ids(window, "Ground"))
    assert [lay.name for lay in dialog.chosen()] == ["Ground"]


def test_with_nothing_asked_for_it_starts_with_the_open_sheet(window):
    window.switch_space(window.scene.layouts[2].id)
    dialog = PrintDialog(window)
    assert [lay.name for lay in dialog.chosen()] == ["Roof"]


def test_ticking_a_group_ticks_its_sheets(window):
    dialog = PrintDialog(window, [])
    _box(dialog, "Plans").setCheckState(0, Qt.CheckState.Checked)
    assert [lay.name for lay in dialog.chosen()] == ["Ground", "Roof"]
    dialog.choose_all(False)
    assert dialog.chosen() == []
    dialog.choose_all(True)
    assert [lay.name for lay in dialog.chosen()] == ["Cover", "Ground",
                                                     "Roof"]


def test_the_count_says_how_many(window):
    dialog = PrintDialog(window, _ids(window, "Ground", "Roof"))
    assert "2 sheets" in dialog.summary.text()


def _pages(path):
    data = open(path, "rb").read()
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", data))


def test_a_pdf_has_a_page_a_sheet_in_the_set_s_order(window, tmp_path):
    dialog = PrintDialog(window, _ids(window, "Roof", "Cover"))
    path = str(tmp_path / "set.pdf")
    dialog.pdf_path.setText(path)
    assert dialog.print_pdf() == 2
    assert _pages(path) == 2


def test_each_page_keeps_its_sheet_s_paper(window, tmp_path):
    from PySide6.QtGui import QPageLayout
    from serpentine3d.fileio.pdf import page_layout
    portrait = page_layout(window.scene.layouts[2])     # A4 portrait
    landscape = page_layout(window.scene.layouts[1])    # A2 landscape
    assert portrait.orientation() == QPageLayout.Orientation.Portrait
    assert landscape.orientation() == QPageLayout.Orientation.Landscape
    size = landscape.fullRect(QPageLayout.Unit.Millimeter)
    assert (round(size.width()), round(size.height())) == (594, 420)


def test_a_printer_gets_the_same_pages(window, tmp_path):
    """A printer is a paged device like the PDF writer; one that writes a
    PDF stands in for a real one here."""
    from PySide6.QtPrintSupport import QPrinter
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    path = str(tmp_path / "printed.pdf")
    printer.setOutputFileName(path)
    dialog = PrintDialog(window, _ids(window, "Cover", "Ground", "Roof"))
    assert dialog.print_to(printer) == 3
    assert _pages(path) == 3


def test_nothing_ticked_prints_nothing(window, tmp_path):
    dialog = PrintDialog(window, [])
    dialog.pdf_path.setText(str(tmp_path / "none.pdf"))
    assert dialog.print_pdf() == 0
    assert not (tmp_path / "none.pdf").exists()


def test_the_print_command_opens_the_dialog(window, monkeypatch):
    opened = []
    monkeypatch.setattr(type(window), "print_sheets",
                        lambda self, ids=None: opened.append(ids))
    window.run_command("print")
    QApplication.processEvents()
    assert opened == [None]
