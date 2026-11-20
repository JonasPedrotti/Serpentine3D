"""Ctrl+Shift on an object in a group asks: the part, or the whole object.

A click on a member of a group takes the whole group, which left no way to
take one of its objects short of ungrouping. Ctrl+Shift on a grouped object
now offers its part, the segment, edge, face, triangle or point under the
cursor, and the object itself, alone. Where the part is all of the object,
the one segment of a curve or the one face of a surface, there is nothing
to choose and the object is taken straight away. Outside a group nothing
changes: the part is held as before.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from serpentine3d.core import geometry as g
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui.viewport import Viewport

PART = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


@pytest.fixture
def pane(_qapp):
    scene = Scene()
    vp = Viewport(scene, SelectionManager(scene))
    vp.resize(800, 600)
    vp.set_view("top")
    vp.camera.target = np.array([5.0, 5.0, 0.0])
    vp.camera.distance = 40.0
    yield vp
    if vp._chooser is not None:
        vp._chooser.close()


def _click(vp, pt):
    scr = vp._eye().project(np.asarray([pt], float), vp.width(), vp.height())
    x, y = float(scr[0][0]), float(scr[0][1])
    for kind, held in ((QEvent.Type.MouseButtonPress,
                        Qt.MouseButton.LeftButton),
                       (QEvent.Type.MouseButtonRelease,
                        Qt.MouseButton.NoButton)):
        event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y),
                            Qt.MouseButton.LeftButton, held, PART)
        (vp.mousePressEvent if kind == QEvent.Type.MouseButtonPress
         else vp.mouseReleaseEvent)(event)


def _grouped(scene, *shapes):
    objs = [scene.add(s) for s in shapes]
    for obj in objs:
        scene.update(obj.id, group_id="g1")
    return [scene.get(o.id) for o in objs]


def _rows(vp):
    return [w.row for w in vp._chooser._widgets.values()]


def _rect():
    return g.make_polyline([(0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0)],
                           closed=True)


def test_a_grouped_polyline_s_segment_offers_the_segment_or_the_curve(pane):
    curve, other = _grouped(pane.scene, _rect(),
                            g.make_line((8, 0, 0), (9, 0, 0)))
    _click(pane, (2.0, 0.0, 0.0))
    assert pane._chooser is not None
    rows = _rows(pane)
    assert [r.name for r in rows] == ["Segment", "Whole curve"]
    pane._chooser.objectChosen.emit("whole")
    assert pane.selection.ids == [curve.id], "the curve alone, not its group"
    assert pane.selection.subobjects == []


def test_choosing_the_part_holds_the_segment(pane):
    curve, _other = _grouped(pane.scene, _rect(),
                             g.make_line((8, 0, 0), (9, 0, 0)))
    _click(pane, (2.0, 0.0, 0.0))
    pane._chooser.objectChosen.emit("part")
    [(oid, kind, _i)] = pane.selection.subobjects
    assert (oid, kind) == (curve.id, "edge")
    assert pane.selection.ids == []


def test_a_one_segment_curve_is_taken_without_asking(pane):
    line, _other = _grouped(pane.scene, g.make_line((0, 0, 0), (4, 0, 0)),
                            g.make_line((8, 0, 0), (9, 0, 0)))
    _click(pane, (2.0, 0.0, 0.0))
    assert pane._chooser is None
    assert pane.selection.ids == [line.id]


def test_a_one_face_surface_is_taken_without_asking(pane):
    face = g.planar_face(_rect())
    surf, _other = _grouped(pane.scene, face,
                            g.make_line((8, 0, 0), (9, 0, 0)))
    pane.set_display_mode("shaded")
    _click(pane, (2.0, 1.5, 0.0))
    assert pane._chooser is None
    assert pane.selection.ids == [surf.id]


@pytest.mark.parametrize("make, at, part", [
    (lambda: g.make_box((0, 0, 0), 4, 3, 2), (2.0, 1.5, 2.0), "Face"),
    (lambda: MeshShape(np.array([(0, 0, 0), (4, 0, 0), (4, 3, 0),
                                 (0, 3, 0)], float), [[0, 1, 2], [0, 2, 3]]),
     (3.0, 0.8, 0.0), "Triangle"),
    (lambda: g.make_line((0, 0, 0), (4, 0, 0)), (4.0, 0.0, 0.0), "Point"),
], ids=["solid face", "mesh triangle", "point of a line"])
def test_a_part_of_a_grouped_solid_mesh_or_line_offers_the_choice(
        pane, make, at, part):
    obj, _other = _grouped(pane.scene, make(),
                           g.make_line((8, 0, 0), (9, 0, 0)))
    pane.set_display_mode("shaded")
    _click(pane, at)
    assert pane._chooser is not None
    assert [r.name for r in _rows(pane)][0] == part
    pane._chooser.objectChosen.emit("whole")
    assert pane.selection.ids == [obj.id]


def test_outside_a_group_the_part_is_held_as_before(pane):
    curve = pane.scene.add(_rect())
    _click(pane, (2.0, 0.0, 0.0))
    assert pane._chooser is None
    [(oid, kind, _i)] = pane.selection.subobjects
    assert (oid, kind) == (curve.id, "edge")


def test_points_of_two_curves_in_one_place_ask_whose(pane):
    a = pane.scene.add(g.make_line((0, 0, 0), (4, 0, 0)), name="A")
    b = pane.scene.add(g.make_line((4, 0, 0), (4, 3, 0)), name="B")
    _click(pane, (4.0, 0.0, 0.0))
    assert pane._chooser is not None
    rows = _rows(pane)
    assert sorted(r.obj_id for r in rows) == sorted([a.id, b.id])
    hovered = []
    pane.set_choice_hover = hovered.append
    pane._chooser.rowHovered.disconnect()
    pane._chooser.rowHovered.connect(pane.set_choice_hover)
    pane._chooser.rowHovered.emit(b.id)
    assert hovered == [b.id], "pointing at a row lights its curve"
    pane._chooser.objectChosen.emit(b.id)
    [(oid, kind, i)] = pane.selection.subobjects
    assert (oid, kind) == (b.id, "vertex")
    assert tuple(pane.held_points(b)[i]) == (4, 0, 0)


def test_a_lone_point_is_held_without_asking(pane):
    a = pane.scene.add(g.make_line((0, 0, 0), (4, 0, 0)))
    _click(pane, (4.0, 0.0, 0.0))
    assert pane._chooser is None
    assert pane.selection.subobjects[0][:2] == (a.id, "vertex")


def test_points_drawn_in_one_place_ask_even_millimetres_apart(pane):
    """A line ending a hair short of a box's corner is the same place to
    the eye, so the list offers both, far from home or not."""
    x0, y0 = 683872.0, 5140950.0
    pane.camera.target = np.array([x0 + 2, y0, 0.0])
    pane.camera.distance = 40.0
    box = pane.scene.add(g.make_box((x0 + 4, y0, -2), 3, 3, 2))
    line = pane.scene.add(g.make_line((x0, y0, 0), (x0 + 4.003, y0, 0)))
    pane.set_display_mode("shaded")
    box.mesh
    _click(pane, (x0 + 4.0, y0, 0.0))
    assert pane._chooser is not None
    assert sorted(r.obj_id for r in _rows(pane)) == sorted([box.id, line.id])


def test_points_apart_on_the_screen_do_not_ask(pane):
    x0, y0 = 683872.0, 5140950.0
    pane.camera.target = np.array([x0 + 2, y0, 0.0])
    pane.camera.distance = 10.0
    a = pane.scene.add(g.make_line((x0, y0, 0), (x0 + 4, y0, 0)))
    pane.scene.add(g.make_line((x0 + 4.3, y0, 0), (x0 + 4.3, y0 + 3, 0)))
    _click(pane, (x0 + 4.0, y0, 0.0))
    assert pane._chooser is None
    assert pane.selection.subobjects[0][:2] == (a.id, "vertex")
