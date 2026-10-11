"""A Sheets list beside Layers organises a drawing set (#38).

The issue asked for Rhino's layout panel and more: the sheets as a list on
the right, toggled like a tab with Layers, groups that can nest the way
Archicad and Revit bind a set, and the order you see being the order they
print in. A click picks a sheet (Properties shows it), a double-click
opens it, and the sheet on screen carries the gold dot the current layer
does in Layers.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from serpentine3d.core.history import History
from serpentine3d.core.layout import Layout, SheetGroup
from serpentine3d.core.scene import Scene
from serpentine3d.ui.sheets_panel import SheetsPanel


@pytest.fixture
def set_of_sheets(_qapp):
    scene = Scene()
    plans = SheetGroup(name="Plans")
    scene.sheet_groups = [plans]
    cover = Layout(name="Cover")
    ground = Layout(name="Ground", number="A-101", group=plans.id)
    roof = Layout(name="Roof", number="A-102", group=plans.id)
    scene.layouts = [cover, ground, roof]
    history = History(scene)
    panel = SheetsPanel(scene, history)
    panel.resize(300, 400)
    panel.show()
    QApplication.processEvents()
    return scene, history, panel, plans, (cover, ground, roof)


def _rows(panel):
    """Every row as (depth, text), top to bottom."""
    out = []

    def walk(item, depth):
        out.append((depth, item.text(0)))
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)

    for i in range(panel.tree.topLevelItemCount()):
        walk(panel.tree.topLevelItem(i), 0)
    return out


def _item(panel, text):
    found = panel.tree.findItems(text, Qt.MatchFlag.MatchExactly
                                 | Qt.MatchFlag.MatchRecursive)
    assert found, f"no row {text!r}: {_rows(panel)}"
    return found[0]


def test_the_list_shows_the_set_as_it_is_bound(set_of_sheets):
    _scene, _h, panel, _plans, _sheets = set_of_sheets
    assert _rows(panel) == [(0, "Cover"), (0, "Plans"),
                            (1, "A-101  Ground"), (1, "A-102  Roof")]


def test_a_double_click_opens_the_sheet(set_of_sheets):
    _scene, _h, panel, _plans, (_cover, ground, _roof) = set_of_sheets
    opened = []
    panel.openRequested.connect(opened.append)
    panel.tree.itemDoubleClicked.emit(_item(panel, "A-101  Ground"), 0)
    assert opened == [ground.id]


def test_the_sheet_on_screen_carries_the_dot(set_of_sheets):
    _scene, _h, panel, _plans, (_cover, ground, _roof) = set_of_sheets
    panel.set_open(ground.id)
    assert panel.is_open_row(_item(panel, "A-101  Ground"))
    assert not panel.is_open_row(_item(panel, "Cover"))


def test_picking_tells_whoever_is_listening(set_of_sheets):
    _scene, _h, panel, _plans, (cover, _ground, roof) = set_of_sheets
    heard = []
    panel.pickedChanged.connect(lambda: heard.append(panel.picked_sheet_ids()))
    _item(panel, "Cover").setSelected(True)
    _item(panel, "A-102  Roof").setSelected(True)
    assert heard[-1] == [cover.id, roof.id]
    panel.clear_picked()
    assert panel.picked_sheet_ids() == []


def test_a_new_sheet_goes_into_the_picked_group(set_of_sheets):
    scene, history, panel, plans, _sheets = set_of_sheets
    _item(panel, "Plans").setSelected(True)
    panel.new_sheet()
    made = scene.layouts[-1]
    assert made.group == plans.id
    assert (1, made.name) in _rows(panel)
    history.undo()
    assert made.id not in {lay.id for lay in scene.layouts}


def test_a_new_group_nests_in_the_picked_one(set_of_sheets):
    scene, history, panel, plans, _sheets = set_of_sheets
    _item(panel, "Plans").setSelected(True)
    group = panel.new_group()
    assert group.parent == plans.id
    assert group in scene.sheet_groups
    history.undo()
    assert group.id not in {g.id for g in scene.sheet_groups}


def test_moving_a_sheet_up_reorders_the_set(set_of_sheets):
    scene, history, panel, _plans, (cover, ground, roof) = set_of_sheets
    _item(panel, "A-102  Roof").setSelected(True)
    panel.move_picked(-1)
    assert [lay.name for lay in scene.layouts] == ["Cover", "Roof", "Ground"]
    history.undo()
    assert [lay.name for lay in scene.layouts] == ["Cover", "Ground", "Roof"]


def test_a_drop_is_read_back_as_the_new_binding(set_of_sheets):
    """What a drag leaves in the tree is what the set becomes: here Cover is
    dropped into Plans, after Roof."""
    scene, history, panel, plans, (cover, ground, roof) = set_of_sheets
    tree = panel.tree
    row = tree.takeTopLevelItem(tree.indexOfTopLevelItem(_item(panel,
                                                               "Cover")))
    _item(panel, "Plans").addChild(row)
    panel.sync_from_tree()
    assert scene.get_layout(cover.id).group == plans.id
    assert [lay.name for lay in scene.layouts] == ["Ground", "Roof", "Cover"]
    history.undo()
    assert [lay.name for lay in scene.layouts] == ["Cover", "Ground", "Roof"]
    assert scene.get_layout(cover.id).group is None


def test_a_group_dropped_into_another_nests(set_of_sheets):
    scene, _h, panel, plans, _sheets = set_of_sheets
    details = SheetGroup(name="Details")
    scene.sheet_groups.append(details)
    scene.notify()
    tree = panel.tree
    row = tree.takeTopLevelItem(tree.indexOfTopLevelItem(_item(panel,
                                                               "Details")))
    _item(panel, "Plans").addChild(row)
    panel.sync_from_tree()
    assert details.parent == plans.id or next(
        g for g in scene.sheet_groups if g.id == details.id).parent == plans.id


def test_deleting_a_group_keeps_its_sheets(set_of_sheets):
    scene, history, panel, plans, (cover, ground, roof) = set_of_sheets
    _item(panel, "Plans").setSelected(True)
    panel.delete_picked()
    assert scene.sheet_groups == []
    assert [lay.name for lay in scene.layouts] == ["Cover", "Ground", "Roof"]
    assert all(lay.group is None for lay in scene.layouts)


def test_renaming_a_sheet_keeps_its_number(set_of_sheets):
    scene, _h, panel, _plans, (_cover, ground, _roof) = set_of_sheets
    panel.rename_row(_item(panel, "A-101  Ground"), "Ground floor")
    assert (scene.get_layout(ground.id).number,
            scene.get_layout(ground.id).name) == ("A-101", "Ground floor")
    assert (1, "A-101  Ground floor") in _rows(panel)


def test_sheets_cannot_hold_other_sheets(set_of_sheets):
    _scene, _h, panel, _plans, _sheets = set_of_sheets
    sheet = _item(panel, "Cover")
    group = _item(panel, "Plans")
    assert not sheet.flags() & Qt.ItemFlag.ItemIsDropEnabled
    assert group.flags() & Qt.ItemFlag.ItemIsDropEnabled


def test_the_editor_offers_the_name_and_renames_through_the_panel(
        set_of_sheets):
    """F2 edits the name, not "A-101  Ground", and keeps the number."""
    from PySide6.QtWidgets import QStyleOptionViewItem
    scene, _h, panel, _plans, (_cover, ground, _roof) = set_of_sheets
    item = _item(panel, "A-101  Ground")
    index = panel.tree.indexFromItem(item)
    delegate = panel.tree.itemDelegate()
    editor = delegate.createEditor(panel.tree.viewport(),
                                   QStyleOptionViewItem(), index)
    delegate.setEditorData(editor, index)
    assert editor.text() == "Ground"
    editor.setText("Ground floor")
    delegate.setModelData(editor, panel.tree.model(), index)
    lay = scene.get_layout(ground.id)
    assert (lay.number, lay.name) == ("A-101", "Ground floor")
