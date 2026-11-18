"""A drop-down's open list leaves out what is already chosen, and the click
that enters a number field picks the whole number to be typed over."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox,
                               QLineEdit, QWidget, QVBoxLayout)

from serpentine3d.ui import theme, tooltips


@pytest.fixture
def styled():
    app = QApplication.instance() or QApplication([])
    style = app.style().name()      # setStyle deletes the one it replaces
    s = tooltips.install(app)
    app.setStyleSheet(theme.stylesheet())
    yield app
    app.setStyleSheet("")
    app.removeEventFilter(s)
    app.setStyle(style)
    del app._tooltip_shower


def _shown(combo):
    return [combo.itemText(r) for r in range(combo.count())
            if not combo.view().isRowHidden(r)]


def test_the_open_list_leaves_out_the_choice_already_made(styled):
    combo = QComboBox()
    combo.addItems(["Perspective", "Parallel", "Two-point"])
    combo.ensurePolished()

    assert _shown(combo) == ["Parallel", "Two-point"]
    combo.setCurrentIndex(1)
    assert _shown(combo) == ["Perspective", "Two-point"]


def test_an_item_added_later_is_offered_too(styled):
    combo = QComboBox()
    combo.addItem("Perspective")
    combo.ensurePolished()
    combo.addItem("Parallel")

    assert _shown(combo) == ["Parallel"]


def test_a_combo_you_can_type_in_keeps_every_row(styled):
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItems(["a", "b"])
    combo.ensurePolished()

    assert _shown(combo) == ["a", "b"]


def _field():
    host = QWidget()
    QVBoxLayout(host).addWidget(other := QLineEdit())
    spin = QDoubleSpinBox()
    spin.setRange(0, 1000)
    spin.setValue(25)
    host.layout().addWidget(spin)
    host.show()
    QTest.qWaitForWindowExposed(host)
    other.setFocus()
    return host, spin, spin.findChild(QLineEdit)


def test_clicking_into_a_number_field_picks_the_whole_number(styled):
    host, spin, edit = _field()

    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=QPoint(10, 5))
    QTest.qWait(20)

    assert edit.selectedText() == edit.text()
    QTest.keyClicks(edit, "40")
    assert spin.text().startswith("40")


def test_enter_takes_the_number_and_lets_go_of_the_selection(styled):
    host, spin, edit = _field()
    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=QPoint(10, 5))
    QTest.qWait(20)

    QTest.keyClicks(edit, "40")
    QTest.keyClick(edit, Qt.Key.Key_Return)
    QTest.qWait(20)

    assert spin.value() == 40
    assert edit.selectedText() == ""


def test_a_second_click_inside_places_the_cursor(styled):
    host, spin, edit = _field()
    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=QPoint(10, 5))
    QTest.qWait(20)

    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=QPoint(10, 5))
    QTest.qWait(20)

    assert edit.selectedText() == ""
