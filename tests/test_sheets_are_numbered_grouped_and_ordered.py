"""Sheets have numbers, sit in groups that can nest, and keep one order
(#38).

Layouts were a strip of tabs along the bottom: fine for a few, lost once a
set runs to dozens. A set of drawings is organised the way Archicad and
Revit organise it: a number on each sheet (A-101), sheets gathered into
groups (Plans, Sections) that can sit inside each other, and one order
that is the order they print in. That order is still the tab strip's, so
nothing that reads `scene.layouts` changes: a group sits in the list where
its first sheet is, and an empty one at the end of where it was made.
"""

from __future__ import annotations

import pytest

from serpentine3d.core.history import History
from serpentine3d.core.layout import (DetailView, Layout, SheetGroup,
                                      flatten_sheets, sheet_label, sheet_tree)
from serpentine3d.core.scene import Scene
from serpentine3d.fileio import native


def _tree_names(tree):
    """A sheet tree as nested names, for comparing at a glance."""
    out = []
    for kind, item, children in tree:
        if kind == "group":
            out.append((item.name, _tree_names(children)))
        else:
            out.append(item.name)
    return out


@pytest.fixture
def book():
    plans = SheetGroup(name="Plans")
    level1 = SheetGroup(name="Level 1", parent=plans.id)
    sections = SheetGroup(name="Sections")
    cover = Layout(name="Cover")
    ground = Layout(name="Ground", group=level1.id)
    roof = Layout(name="Roof", group=plans.id)
    long_section = Layout(name="Long", group=sections.id)
    return ([cover, ground, roof, long_section], [plans, level1, sections])


def test_the_tree_follows_the_sheet_order(book):
    layouts, groups = book
    assert _tree_names(sheet_tree(layouts, groups)) == [
        "Cover",
        ("Plans", [("Level 1", ["Ground"]), "Roof"]),
        ("Sections", ["Long"]),
    ]


def test_an_empty_group_still_shows_where_it_was_made(book):
    layouts, groups = book
    groups.append(SheetGroup(name="Details"))
    assert _tree_names(sheet_tree(layouts, groups))[-1] == ("Details", [])


def test_a_sheet_in_a_group_that_is_gone_stands_on_its_own(book):
    layouts, groups = book
    groups = [g for g in groups if g.name != "Sections"]
    assert "Long" in _tree_names(sheet_tree(layouts, groups))


def test_a_group_that_contains_itself_does_not_hang():
    a = SheetGroup(name="A")
    b = SheetGroup(name="B", parent=a.id)
    a.parent = b.id
    sheet = Layout(name="S", group=b.id)
    names = _tree_names(sheet_tree([sheet], [a, b]))
    assert "S" in str(names)


def test_flattening_reads_the_tree_depth_first(book):
    layouts, groups = book
    order = [lay.name for lay in flatten_sheets(sheet_tree(layouts, groups))]
    assert order == ["Cover", "Ground", "Roof", "Long"]


def test_a_sheet_is_labelled_by_its_number_and_name():
    assert sheet_label(Layout(name="Ground floor", number="A-101")) \
        == "A-101  Ground floor"
    assert sheet_label(Layout(name="Ground floor")) == "Ground floor"


# -- saved and undone ---------------------------------------------------------

def test_numbers_groups_and_hidden_layers_survive_the_file(tmp_path):
    scene = Scene()
    plans = SheetGroup(name="Plans")
    level1 = SheetGroup(name="Level 1", parent=plans.id)
    scene.sheet_groups = [plans, level1]
    walls = scene.layers.create("Walls")
    lay = Layout(name="Ground", number="A-101", group=level1.id)
    lay.details.append(DetailView(hidden_layers=[walls.id]))
    scene.layouts.append(lay)
    path = str(tmp_path / "set.serp3d")
    native.save_scene(scene, path)

    out = Scene()
    native.load_scene(out, path)
    (back,) = out.layouts
    assert (back.number, back.name) == ("A-101", "Ground")
    names = {g.id: g for g in out.sheet_groups}
    assert names[back.group].name == "Level 1"
    assert names[names[back.group].parent].name == "Plans"
    hidden = back.details[0].hidden_layers
    assert [out.layers.get(i).name for i in hidden] == ["Walls"]


def test_a_file_from_before_has_no_numbers_or_groups(tmp_path):
    scene = Scene()
    scene.layouts.append(Layout(name="Old"))
    path = str(tmp_path / "old.serp3d")
    native.save_scene(scene, path)
    out = Scene()
    native.load_scene(out, path)
    (back,) = out.layouts
    assert (back.number, back.group, out.sheet_groups) == ("", None, [])


def test_undo_puts_groups_back():
    scene = Scene()
    history = History(scene)
    history.checkpoint("new group")
    scene.sheet_groups.append(SheetGroup(name="Plans"))
    history.undo()
    assert scene.sheet_groups == []
    history.redo()
    assert [g.name for g in scene.sheet_groups] == ["Plans"]


def test_a_new_drawing_has_no_groups():
    scene = Scene()
    scene.sheet_groups.append(SheetGroup(name="Plans"))
    scene.clear()
    assert scene.sheet_groups == []


# -- what a detail shows ------------------------------------------------------

def test_a_layer_hidden_in_a_detail_hides_its_sublayers_there_too():
    scene = Scene()
    walls = scene.layers.create("Walls")
    inner = scene.layers.create("Interior", parent=walls.id)
    other = scene.layers.create("Grid")
    hidden = scene.layers.with_descendants([walls.id])
    assert hidden == {walls.id, inner.id}
    assert other.id not in hidden
