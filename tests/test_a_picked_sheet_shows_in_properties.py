"""Properties shows a sheet picked in the Sheets list, and a detail's own
hidden layers (#38).

A sheet is a subject the way a layer is: pick it in the list and
Properties says what it is (its number and name, its paper, how many
details, which group) and edits it, with a tab beside the selection's.
One look at a time: picking a sheet lets go of a picked layer and the
other way round. A detail picked on a sheet lists the layers it leaves
out, with Show beside each, and a way to leave another out.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.layout import DetailView, Layout, SheetGroup
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui.layers_panel import LayersPanel
from serpentine3d.ui.properties import PropertiesPanel
from serpentine3d.ui.sheets_panel import SheetsPanel


@pytest.fixture
def panels(_qapp):
    scene = Scene()
    plans = SheetGroup(name="Plans")
    scene.sheet_groups = [plans]
    ground = Layout(name="Ground", number="A-101", group=plans.id,
                    paper_w=420.0, paper_h=297.0)
    ground.details.append(DetailView())
    ground.details.append(DetailView())
    roof = Layout(name="Roof", number="A-102", paper_w=297.0, paper_h=420.0)
    scene.layouts = [ground, roof]
    selection = SelectionManager(scene)
    history = History(scene)
    props = PropertiesPanel(scene, selection, history)
    layers = LayersPanel(scene, history, selection=selection)
    sheets = SheetsPanel(scene, history)
    props.follow_layers(layers)
    props.follow_sheets(sheets)
    props.show()
    QApplication.processEvents()
    return scene, history, props, layers, sheets, (ground, roof), plans


def test_a_picked_sheet_says_what_it_is(panels):
    scene, _h, props, _l, sheets, (ground, _roof), _plans = panels
    sheets.pick([ground.id])
    assert props.shown() == "sheets"
    said = props.describe("sheets")
    assert (said.kind, said.title) == ("Sheet", "A-101  Ground")
    assert said.detail == "A3 landscape · 2 details · in Plans"
    assert props.pages.currentWidget() is props.sheet_page
    assert props.sheet_number.text() == "A-101"
    assert props.sheet_name.text() == "Ground"
    assert props.sheet_paper.currentText() == "A3"
    assert props.sheet_orientation.currentText() == "Landscape"
    assert props.sheet_group.currentText() == "Plans"


def test_editing_the_sheet(panels):
    scene, history, props, _l, sheets, (ground, _roof), plans = panels
    sheets.pick([ground.id])
    props.sheet_number.setText("A-201")
    props.sheet_number.editingFinished.emit()
    assert ground.number == "A-201"
    props.sheet_orientation.setCurrentText("Portrait")
    assert (ground.paper_w, ground.paper_h) == (297.0, 420.0)
    props.sheet_paper.setCurrentText("A4")
    assert (ground.paper_w, ground.paper_h) == (210.0, 297.0)
    props.sheet_group.setCurrentIndex(props.sheet_group.findData(None))
    assert scene.get_layout(ground.id).group is None
    history.undo()
    assert scene.get_layout(ground.id).group == plans.id, \
        "the group change was not an undo step of its own"


def test_several_sheets_share_what_they_can(panels):
    scene, _h, props, _l, sheets, (ground, roof), _plans = panels
    sheets.pick([ground.id, roof.id])
    said = props.describe("sheets")
    assert (said.kind, said.title) == ("Sheets", "2 sheets")
    assert not props.sheet_number.isEnabled()
    assert props.sheet_orientation.currentIndex() == -1, "they differ"
    props.sheet_paper.setCurrentText("A2")
    assert {(lay.paper_w, lay.paper_h) for lay in scene.layouts} \
        == {(594.0, 420.0), (420.0, 594.0)}, "each kept its orientation"


def test_one_look_at_a_time(panels):
    scene, _h, props, layers, sheets, (ground, _roof), _plans = panels
    item = layers.tree.topLevelItem(0)
    item.setSelected(True)
    assert props.shown() == "layers"
    sheets.pick([ground.id])
    assert props.shown() == "sheets"
    assert not layers.picked_layer_ids(), "the layer stayed picked"
    item = layers.tree.topLevelItem(0)
    item.setSelected(True)
    assert sheets.picked_sheet_ids() == [], "the sheet stayed picked"


def test_the_open_link_opens_the_sheet(panels):
    _s, _h, props, _l, sheets, (ground, _roof), _plans = panels
    opened = []
    sheets.openRequested.connect(opened.append)
    sheets.pick([ground.id])
    props.sheet_open.click()
    assert opened == [ground.id]


def test_the_print_link_offers_the_picked_sheets(panels):
    _s, _h, props, _l, sheets, (ground, roof), _plans = panels
    asked = []
    sheets.printRequested.connect(asked.append)
    sheets.pick([ground.id, roof.id])
    props.sheet_print.click()
    assert asked == [[ground.id, roof.id]]


# -- a detail's own hidden layers ---------------------------------------------

@pytest.fixture
def detail_sheet(_qapp):
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w.resize(1200, 800)
    walls = w.scene.layers.create("Walls")
    grid = w.scene.layers.create("Grid")
    box = w.scene.add(g.make_box((0, 0, 0), 10, 10, 10))
    w.scene.update(box.id, layer_id=walls.id)
    lay = Layout(name="Sheet")
    det = DetailView(x=20, y=20, w=200, h=150)
    lay.details.append(det)
    w.scene.layouts.append(lay)
    w.switch_space(lay.id)
    lv = w.viewport.layout_view
    lv.selected = [("detail", det)]
    w.viewport.layoutSelectionChanged.emit()
    QApplication.processEvents()
    yield w, w.properties, det, walls, grid
    w.mark_saved()
    w.close()


def test_a_detail_lists_no_hidden_layers_at_first(detail_sheet):
    w, props, det, walls, grid = detail_sheet
    assert props.form.isRowVisible(props.detail_layers)
    assert props.detail_layers.hidden_names() == []
    assert props.detail_layers.offered() == ["Default", "Walls", "Grid"]


def test_leaving_a_layer_out_and_showing_it_again(detail_sheet):
    w, props, det, walls, grid = detail_sheet
    props.detail_layers.hide_layer(walls.id)
    assert det.hidden_layers == [walls.id]
    assert props.detail_layers.hidden_names() == ["Walls"]
    assert "Walls" not in props.detail_layers.offered()
    props.detail_layers.hide_layer(grid.id)
    props.detail_layers.show_layer(walls.id)
    assert det.hidden_layers == [grid.id]
    w.history.undo()
    assert det_now(w).hidden_layers == [walls.id, grid.id]


def det_now(w):
    """The detail as the sheet now holds it (undo swaps in clones)."""
    return w.scene.layouts[0].details[0]


def test_show_all_puts_every_layer_back(detail_sheet):
    w, props, det, walls, grid = detail_sheet
    props.detail_layers.hide_layer(walls.id)
    props.detail_layers.hide_layer(grid.id)
    props.detail_layers.show_all()
    assert det.hidden_layers == []


def test_a_model_object_has_no_such_row(detail_sheet):
    w, props, det, walls, grid = detail_sheet
    lv = w.viewport.layout_view
    lv.selected = []
    w.viewport.layoutSelectionChanged.emit()
    w.switch_space("model")
    w.selection.set([w.scene.all()[0].id])
    QApplication.processEvents()
    assert not props.form.isRowVisible(props.detail_layers)
