"""Block: pick the objects, then the base point, then name it in a popup.

The definition is kept relative to the base point, so 'insert' puts that
point where it is asked to. What cannot go into an instance's compound
(a hatch, a mesh) is turned away at the pick rather than lost.
"""

from __future__ import annotations

import pytest

from serpentine3d.commands.base import FormReq, PointReq, TextReq
from serpentine3d.core import geometry as g


def _start(proc, *objs):
    proc.run("block")
    for o in objs:
        proc.click_object(o.id)
    proc.finish_selection()


def test_block_asks_for_the_base_point_before_the_name(env):
    scene, _sel, _hist, _ctx, proc = env
    a = scene.add(g.make_box((5, 5, 0), 1, 1, 1), name="A")
    _start(proc, a)
    assert isinstance(proc.request, PointReq)
    proc.provide_text("5,5,0")
    assert isinstance(proc.form, FormReq)
    assert proc.form.title == "Block"
    assert isinstance(proc.request, TextReq)


def test_the_instance_stays_and_insert_places_the_base_point(env):
    scene, sel, _hist, _ctx, proc = env
    a = scene.add(g.make_box((5, 5, 0), 1, 1, 1), name="A")
    b = scene.add(g.make_box((7, 5, 0), 1, 1, 1), name="B")
    _start(proc, a, b)
    proc.provide_text("5,5,0")
    proc.provide_form({"name": "Crate"})

    inst = [o for o in scene.all() if o.block_id]
    assert len(inst) == 1 and len(scene.all()) == 1
    mn, _ = g.bbox(inst[0].shape)
    assert mn[0] == pytest.approx(5, abs=1e-6) and mn[1] == pytest.approx(5, abs=1e-6)
    assert sel.ids == [inst[0].id]

    proc.run("insert")
    proc.provide_text("Crate")
    proc.provide_text("100,0,0")
    placed = [o for o in scene.all() if o.block_id][-1]
    mn, _ = g.bbox(placed.shape)
    assert mn[0] == pytest.approx(100, abs=1e-6) and mn[1] == pytest.approx(0, abs=1e-6)


def test_an_empty_name_takes_the_default(env):
    scene, _sel, _hist, _ctx, proc = env
    a = scene.add(g.make_box((0, 0, 0), 1, 1, 1))
    _start(proc, a)
    proc.provide_text("0,0,0")
    proc.provide_form({"name": "  "})
    assert [bd["name"] for bd in scene.block_defs.values()] == ["Block 1"]


def test_a_taken_name_asks_again(env):
    scene, _sel, _hist, _ctx, proc = env
    a = scene.add(g.make_box((0, 0, 0), 1, 1, 1))
    b = scene.add(g.make_box((5, 0, 0), 1, 1, 1))
    _start(proc, a)
    proc.provide_text("0,0,0")
    proc.provide_form({"name": "Crate"})
    _start(proc, b)
    proc.provide_text("5,0,0")
    proc.provide_form({"name": "crate"})
    assert proc.busy and isinstance(proc.form, FormReq)
    proc.provide_form({"name": "Box"})
    assert sorted(bd["name"] for bd in scene.block_defs.values()) == [
        "Box", "Crate"]


def test_a_hatch_is_not_taken_into_a_block(env):
    scene, _sel, _hist, _ctx, proc = env
    outline = scene.add(g.make_polyline(
        [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], closed=True))
    proc.run("hatch")
    proc.click_object(outline.id)
    proc.finish_selection()
    proc.provide_form({"pattern": "Lines", "spacing": 0.5, "angle": 30.0})
    hatch = next(o for o in scene.all() if o.kind == "hatch")

    proc.run("block")
    proc.click_object(hatch.id)
    proc.finish_selection()
    assert not scene.block_defs
    assert scene.get(hatch.id) is not None


def test_the_window_shows_the_name_as_a_popup(_qapp):
    from serpentine3d.ui.form_dialog import FormDialog
    from serpentine3d.commands.organize import _block_name_form
    dialog = FormDialog(_block_name_form("Block 3"))
    assert dialog.values() == {"name": "Block 3"}
