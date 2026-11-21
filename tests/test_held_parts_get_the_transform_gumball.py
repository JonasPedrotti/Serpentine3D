"""Held faces, edges and corners of surfaces and solids get the whole
gumball, as in Rhino: its arrows, pads, rings and boxes move, turn and
scale them, the rest of the object following, near the origin or far
from it. While dragging only the edges that move are drawn; the faces are
rebuilt on release. Alt drags off a copy that is an object of its own.
Holding Ctrl brings back the other gumball (push/pull, fillet), and the
view says so."""

from __future__ import annotations

import math

import numpy as np
import pytest
from PySide6.QtCore import Qt

import serpentine3d.commands  # registers all commands  # noqa: F401
from serpentine3d.core import geometry as g
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui.gumball import CONE1, SHAFT0
from serpentine3d.ui.viewport import Viewport

NONE = Qt.KeyboardModifier.NoModifier
ALT = Qt.KeyboardModifier.AltModifier
FAR = [0.0, 100000.0]


@pytest.fixture
def pane(_qapp, request):
    off = getattr(request, "param", 0.0)
    scene = Scene()
    vp = Viewport(scene, SelectionManager(scene))
    vp.resize(800, 600)
    vp.set_view("top")
    vp.grid_snap = False
    vp.camera.target = np.array([off + 5.0, off + 3.0, 0.0])
    vp.camera.distance = 40.0
    vp.offset = off
    return vp


def _screen(vp, pt):
    scr = vp._eye().project(np.asarray([pt], float), vp.width(), vp.height())
    return float(scr[0][0]), float(scr[0][1])


def _box(vp):
    off = vp.offset
    return vp.scene.add(g.make_box((off, off, 0), 10, 6, 10), name="Box")


def _top(shape):
    faces = g.faces_of(shape)
    return max(range(len(faces)), key=lambda i: g.centroid(faces[i])[2])


def _corners(shape):
    return {tuple(round(c, 5) for c in p) for p in g.vertex_points(shape)}


def _arrow(gb, i):
    anchor, axes = gb.anchor_and_axes()
    return anchor, axes, anchor + axes[i] * (SHAFT0 + CONE1) / 2 \
        * gb._size_world(anchor)


@pytest.mark.parametrize("pane", FAR, indirect=True, ids=["near", "far"])
def test_a_held_face_gets_every_handle_and_a_hint(pane):
    box = _box(pane)
    pane.selection.toggle_subobject(box.id, "face", _top(box.shape))
    gb = pane.gumball
    assert gb.active()
    kinds = {kind for kind, _i in gb.handles()}
    assert kinds == {"move", "pad", "rot", "scale", "center"}
    anchor, _axes = gb.anchor_and_axes()
    assert np.allclose(anchor, (pane.offset + 5, pane.offset + 3, 10))
    assert gb.alternative_hint() == "Hold Ctrl for the push/pull gumball"


def test_a_held_edge_hints_at_the_fillet_gumball(pane):
    box = _box(pane)
    pane.selection.toggle_subobject(box.id, "edge", 0)
    assert pane.gumball.alternative_hint() == "Hold Ctrl for the fillet gumball"


def test_holding_ctrl_brings_back_the_push_pull_gumball(pane, monkeypatch):
    box = _box(pane)
    pane.selection.toggle_subobject(box.id, "face", _top(box.shape))
    monkeypatch.setattr("serpentine3d.ui.gumball._ctrl_down", lambda: True)
    gb = pane.gumball
    assert gb._tf_target() is None
    assert gb._pushpull_target() is not None
    assert gb.alternative_hint() is None


@pytest.mark.parametrize("pane", FAR, indirect=True, ids=["near", "far"])
def test_dragging_the_arrow_shows_edges_then_moves_the_face(pane):
    box = _box(pane)
    off = pane.offset
    before = box.shape
    pane.selection.toggle_subobject(box.id, "face", _top(box.shape))
    gb = pane.gumball
    _anchor, axes, at = _arrow(gb, 0)
    assert gb.begin_drag(("move", 0), *_screen(pane, at), NONE)
    gb.drag_to(*_screen(pane, at + axes[0] * 2.0), NONE)

    assert pane.scene.get(box.id).shape is before, "nothing rebuilt mid-drag"
    ghost = pane._ghost
    assert ghost is not None and not ghost.has_faces
    assert len(ghost.points) == 4
    assert np.allclose(sorted(ghost.points[:, 0]),
                       [off + 2, off + 2, off + 12, off + 12], atol=1e-4)

    gb.end_drag()
    assert pane._ghost is None
    shape = pane.scene.get(box.id).shape
    assert g.is_valid(shape) and g.shape_kind(shape) == "solid"
    corners = _corners(shape)
    for x in (0, 10):
        for y in (0, 6):
            assert (off + x + 2, off + y, 10.0) in corners
            assert (off + x, off + y, 0.0) in corners
    held = pane.selection.subobjects
    assert len(held) == 1 and held[0][1] == "face"
    face = g.faces_of(shape)[held[0][2]]
    assert g.centroid(face)[2] == pytest.approx(10.0), "the top stays held"


@pytest.mark.parametrize("pane", FAR, indirect=True, ids=["near", "far"])
def test_turning_a_held_face_twists_the_sides(pane):
    box = _box(pane)
    off = pane.offset
    pane.selection.toggle_subobject(box.id, "face", _top(box.shape))
    gb = pane.gumball
    anchor, axes = gb.anchor_and_axes()
    _a, _x, at = _arrow(gb, 0)
    assert gb.begin_drag(("move", 0), *_screen(pane, at), NONE)
    gb._turn_by(anchor, axes[2], 10.0)
    gb.drag["turned"] = 10.0
    gb.end_drag()

    shape = pane.scene.get(box.id).shape
    assert g.is_valid(shape) and g.shape_kind(shape) == "solid"
    a = math.radians(10)
    corners = _corners(shape)
    for x, y in ((0, 0), (10, 0), (10, 6), (0, 6)):
        u, v = x - 5, y - 3
        assert (round(off + 5 + u * math.cos(a) - v * math.sin(a), 5),
                round(off + 3 + u * math.sin(a) + v * math.cos(a), 5),
                10.0) in corners
        assert (off + x, off + y, 0.0) in corners


@pytest.mark.parametrize("pane", FAR, indirect=True, ids=["near", "far"])
def test_alt_dragging_a_held_face_copies_it_off_as_a_surface(pane):
    box = _box(pane)
    off = pane.offset
    before = g.shape_to_bytes(box.shape)
    pane.selection.toggle_subobject(box.id, "face", _top(box.shape))
    gb = pane.gumball
    _anchor, axes, at = _arrow(gb, 0)
    assert gb.begin_drag(("move", 0), *_screen(pane, at), ALT)
    gb.drag_to(*_screen(pane, at + axes[0] * 20.0), ALT)
    assert pane._ghost is not None and pane._ghost.has_faces
    gb.end_drag()

    assert g.shape_to_bytes(pane.scene.get(box.id).shape) == before
    new = [o for o in pane.scene.all() if o.id != box.id]
    assert len(new) == 1 and new[0].kind == "surface"
    assert {p[0] for p in _corners(new[0].shape)} == {off + 20.0, off + 30.0}


def test_escape_mid_drag_leaves_the_box_and_clears_the_edges(pane):
    box = _box(pane)
    before = box.shape
    pane.selection.toggle_subobject(box.id, "face", _top(box.shape))
    gb = pane.gumball
    _anchor, axes, at = _arrow(gb, 0)
    assert gb.begin_drag(("move", 0), *_screen(pane, at), NONE)
    gb.drag_to(*_screen(pane, at + axes[0] * 2.0), NONE)
    gb.cancel_drag()
    assert pane.scene.get(box.id).shape is before
    assert pane._ghost is None


def test_copy_and_paste_make_a_held_face_a_surface_of_its_own(_qapp):
    from serpentine3d.app import MainWindow
    w = MainWindow()
    try:
        box = w.scene.add(g.make_box((0, 0, 0), 10, 6, 10), name="Box")
        w.selection.toggle_subobject(box.id, "face", _top(box.shape))
        w._copy_selected()
        w._paste()
        new = [o for o in w.scene.all() if o.id != box.id]
        assert len(new) == 1 and new[0].kind == "surface"
        assert g.surface_area(new[0].shape) == pytest.approx(60.0)
        assert g.volume(w.scene.get(box.id).shape) == pytest.approx(600.0)
    finally:
        w.mark_saved()
        w.close()


@pytest.mark.parametrize("closed", [True, False], ids=["solid", "open"])
def test_a_held_polysurface_edge_draws_the_whole_gumball(pane, monkeypatch,
                                                         closed):
    """The edge's gumball is the transform gumball, drawn and hit as one;
    the fillet handles only come with Ctrl."""
    box = g.make_box((0, 0, 0), 10, 6, 10)
    if not closed:
        faces = g.faces_of(box)
        box = g.join_surfaces(faces[:-1])
    obj = pane.scene.add(box, name="Polysurface")
    pane.selection.toggle_subobject(obj.id, "edge", 0)
    gb = pane.gumball
    assert not gb._fillet_mode() and not gb._face_mode()
    assert {kind for kind, _i in gb.handles()} == {
        "move", "pad", "rot", "scale", "center"}
    monkeypatch.setattr("serpentine3d.ui.gumball._ctrl_down", lambda: True)
    assert gb._fillet_mode()


def test_ctrl_dragging_the_arrow_on_a_held_edge_fillets_it(pane, monkeypatch):
    """Ctrl shows the fillet gumball and stays down through the drag; the
    drag still fillets rather than growing a surface out of the edge."""
    box = _box(pane)
    faces = len(g.faces_of(box.shape))
    pane.selection.toggle_subobject(box.id, "edge", 0)
    monkeypatch.setattr("serpentine3d.ui.gumball._ctrl_down", lambda: True)
    gb = pane.gumball
    assert gb._fillet_mode()
    ctrl = Qt.KeyboardModifier.ControlModifier
    assert gb.begin_drag(("move", 2), 400.0, 300.0, ctrl)
    gb.apply_scalar(1.0)
    gb.end_drag()

    shape = pane.scene.get(box.id).shape
    assert [o.id for o in pane.scene.all()] == [box.id], "no surface grown"
    assert len(g.faces_of(shape)) == faces + 1
    assert g.volume(shape) < 600.0


def test_a_curved_face_has_no_push_pull_hint(pane):
    cyl = pane.scene.add(g.make_cylinder((0, 0, 0), 5, 10), name="Cylinder")
    wall = next(i for i, f in enumerate(g.faces_of(cyl.shape))
                if abs(g.face_point_normal(f)[1][2]) < 0.5)
    pane.selection.toggle_subobject(cyl.id, "face", wall)
    assert pane.gumball.active()
    assert pane.gumball.alternative_hint() is None


def test_a_fillet_that_cannot_be_built_says_why(pane, monkeypatch):
    """Rather than a size that is not there, the readout says why nothing
    rounds, and the shape is left as it was."""
    box = pane.scene.add(g.make_box((0, 0, 0), 1, 1, 1), name="Small")
    before = box.shape
    pane.selection.toggle_subobject(box.id, "edge", 0)
    monkeypatch.setattr("serpentine3d.ui.gumball._ctrl_down", lambda: True)
    gb = pane.gumball
    assert gb.begin_drag(("move", 2), 400.0, 300.0,
                         Qt.KeyboardModifier.ControlModifier)
    label = gb.apply_scalar(5.0)
    assert label.startswith("fillet: ")
    gb.end_drag()
    assert pane.scene.get(box.id).shape is before
    assert pane.selection.subobjects, "the edge stays held to try again"
