"""A click on the one picked layer or sheet opens its name for typing, as in
a file browser, after the double-click interval, so a double-click still
only makes the layer current or opens the sheet. A sheet's name field fills
its row, as a layer's does, so the letters are not cut off."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from serpentine3d.core.history import History
from serpentine3d.core.layout import Layout
from serpentine3d.core.scene import Scene
from serpentine3d.ui.layers_panel import LayersPanel
from serpentine3d.ui.sheets_panel import SheetsPanel


def _wait_out_double_click():
    QTest.qWait(QApplication.doubleClickInterval() + 150)


def _editor(tree):
    return next((e for e in tree.viewport().findChildren(QLineEdit)
                 if e.isVisible()), None)


def _layers():
    scene = Scene()
    walls = scene.layers.create("Walls")
    scene.notify()
    panel = LayersPanel(scene, History(scene))
    panel.resize(400, 300)
    panel.show()
    QApplication.processEvents()
    item = next(it for it in panel._all_rows().values()
                if panel._layer_id(it) == walls.id)
    return scene, panel, walls, item


def _sheets():
    scene = Scene()
    lay = Layout(name="Ground floor plan")
    scene.layouts.append(lay)
    panel = SheetsPanel(scene, History(scene))
    panel.resize(300, 300)
    panel.show()
    scene.notify("layouts")
    QApplication.processEvents()
    item = panel.tree.topLevelItem(0)
    return scene, panel, lay, item


def _name_point(tree, item, column=0):
    rect = tree.visualItemRect(item)
    x = tree.header().sectionPosition(column) + 40
    return QPoint(x, rect.center().y())


def _click(tree, at):
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, at)


def _double_click(tree, at):
    QTest.mouseDClick(tree.viewport(), Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, at)


def test_a_second_click_on_a_picked_layer_opens_its_name():
    _scene, panel, _walls, item = _layers()
    at = _name_point(panel.tree, item)
    _click(panel.tree, at)
    _wait_out_double_click()
    assert _editor(panel.tree) is None, "the first click only picks"
    _click(panel.tree, at)
    assert _editor(panel.tree) is None, "renaming must wait out a double-click"
    _wait_out_double_click()
    editor = _editor(panel.tree)
    assert editor is not None and editor.text() == "Walls"


def test_a_double_click_on_a_picked_layer_only_makes_it_current():
    scene, panel, walls, item = _layers()
    at = _name_point(panel.tree, item)
    _click(panel.tree, at)
    _wait_out_double_click()
    _double_click(panel.tree, at)
    _wait_out_double_click()
    assert scene.layers.current_id == walls.id
    assert _editor(panel.tree) is None


def test_a_second_click_on_a_picked_sheet_opens_its_name():
    _scene, panel, _lay, item = _sheets()
    at = _name_point(panel.tree, item)
    _click(panel.tree, at)
    _wait_out_double_click()
    _click(panel.tree, at)
    _wait_out_double_click()
    editor = _editor(panel.tree)
    assert editor is not None and editor.text() == "Ground floor plan"


def test_a_double_click_on_a_picked_sheet_only_opens_it():
    _scene, panel, lay, item = _sheets()
    opened = []
    panel.openRequested.connect(opened.append)
    at = _name_point(panel.tree, item)
    _click(panel.tree, at)
    _wait_out_double_click()
    _double_click(panel.tree, at)
    _wait_out_double_click()
    assert opened == [lay.id]
    assert _editor(panel.tree) is None


def test_a_sheet_name_field_fills_its_row():
    _scene, panel, _lay, item = _sheets()
    panel.edit_row(item)
    QApplication.processEvents()
    editor = _editor(panel.tree)
    row = panel.tree.visualItemRect(item)
    assert editor.geometry().height() == row.height()
    assert "padding: 0px 8px" in editor.styleSheet()
