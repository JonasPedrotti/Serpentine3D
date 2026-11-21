"""Ctrl+Shift holds a point of a curve, a surface, a solid or a mesh.

Sub-object picking took edges and faces, and a point only with PointsOn
and only as a control point. Now a Ctrl+Shift click close to a corner
holds that corner: of a curve, its ends and where it turns; of a surface
or a solid, where its edges meet; of a mesh, one of its points. A point
is the smallest target, so it comes before the edge it ends and the face
it bounds, but one hidden behind a face or cut away by a clipping plane
is not there to be clicked. A held point is drawn gold and moves with the
gumball or a command: a curve's segments either side stretch to follow,
a solid's faces lean to follow where they can and refuse where they
would bend, and a mesh's triangles follow their point.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

import serpentine3d.commands  # registers all commands  # noqa: F401
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui.gumball import CONE1, SHAFT0
from serpentine3d.ui.viewport import Viewport

PART = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier


def _rect():
    return g.make_polyline([(0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0)],
                           closed=True)


def _sheet():
    return MeshShape(np.array([(0, 0, 0), (10, 0, 0), (10, 10, 0),
                               (0, 10, 0)], float), [[0, 1, 2], [0, 2, 3]])


@pytest.fixture
def pane(_qapp):
    scene = Scene()
    vp = Viewport(scene, SelectionManager(scene))
    vp.resize(800, 600)
    vp.set_view("top")
    vp.grid_snap = False
    vp.camera.target = np.array([5.0, 5.0, 0.0])
    vp.camera.distance = 40.0
    return vp


def _screen(vp, pt):
    scr = vp._eye().project(np.asarray([pt], float), vp.width(), vp.height())
    return float(scr[0][0]), float(scr[0][1])


def _click(vp, pt, mods=PART):
    x, y = _screen(vp, pt)
    for kind, held in ((QEvent.Type.MouseButtonPress,
                        Qt.MouseButton.LeftButton),
                       (QEvent.Type.MouseButtonRelease,
                        Qt.MouseButton.NoButton)):
        event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y),
                            Qt.MouseButton.LeftButton, held, mods)
        (vp.mousePressEvent if kind == QEvent.Type.MouseButtonPress
         else vp.mouseReleaseEvent)(event)


def _held_at(vp, obj):
    """Where each held point of `obj` is."""
    pts = vp.held_points(vp.scene.get(obj.id))
    return sorted(tuple(np.round(pts[i], 6))
                  for oid, kind, i in vp.selection.subobjects
                  if oid == obj.id and kind == "vertex")


# -- picked -------------------------------------------------------------------

def test_a_click_by_a_curve_s_corner_holds_the_corner(pane):
    curve = pane.scene.add(_rect())
    _click(pane, (4.05, 3.0, 0))
    assert _held_at(pane, curve) == [(4, 3, 0)]


def test_a_click_along_the_side_still_holds_the_segment(pane):
    curve = pane.scene.add(_rect())
    _click(pane, (2.0, 0.0, 0))
    [(oid, kind, _i)] = pane.selection.subobjects
    assert (oid, kind) == (curve.id, "edge")


def test_a_solid_s_corner_and_a_mesh_s_point_are_held_too(pane):
    box = pane.scene.add(g.make_box((0, 0, 0), 2, 2, 2))
    mesh = pane.scene.add(MeshShape(_sheet().vertices + [20, 0, 0],
                                    _sheet().triangles))
    _click(pane, (2.0, 2.0, 2.0))
    _click(pane, (30.0, 10.0, 0.0))
    assert _held_at(pane, box) == [(2, 2, 2)]
    assert _held_at(pane, mesh) == [(30, 10, 0)]


def test_a_point_behind_a_face_is_not_there_to_hold(pane):
    pane.set_view("front")
    pane.camera.target = np.zeros(3)
    pane.camera.distance = 40.0
    pane.set_display_mode("shaded")
    box = pane.scene.add(g.make_box((-3, -1, -3), 6, 2, 6))
    behind = pane.scene.add(g.make_line((-1, 5, 0), (1, 5, 0)))
    box.mesh
    _click(pane, (1.0, 5.0, 0.0))
    assert not any(oid == behind.id
                   for oid, _k, _i in pane.selection.subobjects)
    pane.set_display_mode("wireframe")
    pane.selection.set([])
    _click(pane, (1.0, 5.0, 0.0))
    assert _held_at(pane, behind) == [(1, 5, 0)]


# -- moved --------------------------------------------------------------------

@pytest.fixture
def env(_qapp):
    scene = Scene()
    sel = SelectionManager(scene)
    ctx = CommandContext(scene, sel, History(scene))
    return scene, sel, CommandProcessor(ctx)


def _index(shape, at):
    pts = g.vertex_points(shape)
    return pts.index(tuple(float(c) for c in at))


def test_move_takes_a_curve_s_corner_and_its_sides_follow(env):
    scene, sel, proc = env
    curve = scene.add(_rect())
    sel.set_subobjects([(curve.id, "vertex", _index(curve.shape, (4, 3, 0)))])
    proc.run("move")
    proc.provide_text("0,0,0")
    proc.provide_text("1,1,0")
    assert not proc.busy
    moved = scene.get(curve.id).shape
    assert sorted(g.vertex_points(moved)) == [(0, 0, 0), (0, 3, 0),
                                              (4, 0, 0), (5, 4, 0)]
    assert g.is_closed_curve(moved)


def test_move_lifts_a_box_s_top_corners_and_then_one(env):
    scene, sel, proc = env
    box = scene.add(g.make_box((0, 0, 0), 2, 2, 2))
    top = [i for i, p in enumerate(g.vertex_points(box.shape)) if p[2] == 2]
    sel.set_subobjects([(box.id, "vertex", i) for i in top])
    proc.run("move")
    proc.provide_text("0,0,0")
    proc.provide_text("0,0,1")
    assert g.bbox(scene.get(box.id).shape)[1][2] == pytest.approx(3.0)
    one = [i for i, p in enumerate(g.vertex_points(scene.get(box.id).shape))
           if p[2] == pytest.approx(3.0)][:1]
    lifted = g.vertex_points(scene.get(box.id).shape)[one[0]]
    sel.set_subobjects([(box.id, "vertex", one[0])])
    proc.run("move")
    proc.provide_text("0,0,0")
    proc.provide_text("0,0,1")
    shape = scene.get(box.id).shape
    assert g.is_valid(shape) and g.shape_kind(shape) == "solid"
    corners = {tuple(round(c, 6) for c in p) for p in g.vertex_points(shape)}
    assert (lifted[0], lifted[1], 4.0) in corners, \
        "one corner of a box rises alone, its sides bending to follow"
    assert sum(1 for p in corners if p[2] == 3.0) == 3


def test_move_takes_a_mesh_s_point_and_its_triangles_follow(env):
    scene, sel, proc = env
    mesh = scene.add(_sheet())
    sel.set_subobjects([(mesh.id, "vertex", 2)])
    at = tuple(scene.get(mesh.id).shape.points()[2])
    proc.run("move")
    proc.provide_text("0,0,0")
    proc.provide_text("0,0,4")
    points = {tuple(np.round(p, 6))
              for p in scene.get(mesh.id).shape.points()}
    assert (at[0], at[1], at[2] + 4) in points


def test_the_gumball_drags_a_curve_s_corner(pane):
    curve = pane.scene.add(_rect())
    _click(pane, (4.05, 3.0, 0))
    gb = pane.gumball
    assert gb.active()
    anchor, axes = gb.anchor_and_axes()
    assert np.allclose(anchor, (4, 3, 0))
    at = anchor + axes[0] * (SHAFT0 + CONE1) / 2 * gb._size_world(anchor)
    assert gb.begin_drag(("move", 0), *_screen(pane, at), NONE)
    gb.drag_to(*_screen(pane, at + np.array([2.0, 0, 0])), NONE)
    gb.end_drag()
    moved = pane.scene.get(curve.id).shape
    assert sorted(g.vertex_points(moved)) == [(0, 0, 0), (0, 3, 0),
                                              (4, 0, 0), (6, 3, 0)]
    assert _held_at(pane, curve) == [(6, 3, 0)], "still held where it went"


def test_the_gumball_leans_a_box_by_its_top_corners(pane):
    box = pane.scene.add(g.make_box((0, 0, 0), 2, 2, 2))
    top = [i for i, p in enumerate(g.vertex_points(box.shape)) if p[2] == 2]
    pane.selection.set_subobjects([(box.id, "vertex", i) for i in top])
    gb = pane.gumball
    anchor, axes = gb.anchor_and_axes()
    assert np.allclose(anchor, (1, 1, 2))
    at = anchor + axes[0] * (SHAFT0 + CONE1) / 2 * gb._size_world(anchor)
    assert gb.begin_drag(("move", 0), *_screen(pane, at), NONE)
    gb.drag_to(*_screen(pane, at + np.array([1.0, 0, 0])), NONE)
    gb.end_drag()
    leaned = pane.scene.get(box.id).shape
    corners = sorted(g.vertex_points(leaned))
    assert (3, 2, 2) in [tuple(np.round(c, 6)) for c in corners]
    assert (0, 0, 0) in [tuple(np.round(c, 6)) for c in corners]
    assert g.volume(leaned) == pytest.approx(8.0)
    assert len(_held_at(pane, box)) == 4, "the corners stay held"


def _one_edge_polyline(points):
    """A polyline kept as one edge of degree 1, as Rhino keeps one: its
    turns are kinks inside the edge, not corners between edges."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.Geom import Geom_BSplineCurve
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    n = len(points)
    poles = TColgp_Array1OfPnt(1, n)
    knots = TColStd_Array1OfReal(1, n)
    mults = TColStd_Array1OfInteger(1, n)
    for i, p in enumerate(points, 1):
        poles.SetValue(i, gp_Pnt(*p))
        knots.SetValue(i, float(i - 1))
        mults.SetValue(i, 2 if i in (1, n) else 1)
    return BRepBuilderAPI_MakeEdge(
        Geom_BSplineCurve(poles, knots, mults, 1)).Edge()


def test_a_kink_inside_one_edge_is_held_and_moved(pane):
    curve = pane.scene.add(_one_edge_polyline(
        [(0, 0, 0), (4, 0, 0), (4, 3, 0), (8, 3, 0)]))
    assert len(g.edges_of(curve.shape)) == 1
    _click(pane, (4.05, 3.0, 0))
    assert _held_at(pane, curve) == [(4, 3, 0)]
    gb = pane.gumball
    anchor, axes = gb.anchor_and_axes()
    at = anchor + axes[1] * (SHAFT0 + CONE1) / 2 * gb._size_world(anchor)
    assert gb.begin_drag(("move", 1), *_screen(pane, at), NONE)
    gb.drag_to(*_screen(pane, at + np.array([0, 2.0, 0])), NONE)
    gb.end_drag()
    moved = pane.scene.get(curve.id).shape
    pts = [tuple(np.round(p, 6)) for p in g.curve_points(moved)]
    assert (4, 5, 0) in pts and (4, 0, 0) in pts and (8, 3, 0) in pts
    assert _held_at(pane, curve) == [(4, 5, 0)]


def _band(vp, a, b):
    x0, y0 = _screen(vp, a)
    x1, y1 = _screen(vp, b)
    return vp._box_pick_subobjects(x0, y0, x1, y1, crossing=x1 < x0)


def test_a_band_holds_corners_kinks_and_mesh_points(pane):
    curve = pane.scene.add(_one_edge_polyline(
        [(0, 0, 0), (4, 0, 0), (4, 3, 0), (8, 3, 0)]))
    mesh = pane.scene.add(MeshShape(_sheet().vertices + [20, 0, 0],
                                    _sheet().triangles))
    caught = _band(pane, (3, -1, 0), (5, 4, 0))
    pts = pane.held_points(curve)
    held = sorted(tuple(np.round(pts[i], 6))
                  for oid, k, i in caught if oid == curve.id and k == "vertex")
    assert held == [(4, 0, 0), (4, 3, 0)]
    caught = _band(pane, (29, 9, 0), (31, 11, 0))
    assert [(oid, k) for oid, k, _i in caught] == [(mesh.id, "vertex")]
