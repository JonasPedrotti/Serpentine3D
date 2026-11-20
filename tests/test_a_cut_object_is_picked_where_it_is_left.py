"""What a clipping plane cuts away cannot be clicked on.

An object the plane cuts through is picked where it is still in sight and
not where it was taken away: not by a cut-away end of a curve, not by the
cut-away half of a solid, not by a point above the plane. The plane itself
stays pickable, and a crossing band over the cut-away half alone catches
nothing.
"""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui.viewport import Viewport

SIZE = (900, 700)


def _plane(scene):
    """A plane in world XY taking away everything above it."""
    rect = g.planar_face(g.make_polyline(
        [(-60, -60, 0), (60, -60, 0), (60, 60, 0), (-60, 60, 0)],
        closed=True))
    obj = scene.add(rect, name="Clip")
    scene.update(obj.id, clip_plane={"enabled": True})
    return obj


@pytest.fixture
def pane(_qapp):
    scene = Scene()
    vp = Viewport(scene, SelectionManager(scene))
    vp.resize(*SIZE)
    vp.set_view("front")
    vp.camera.target = np.zeros(3)
    vp.camera.distance = 80.0
    vp.set_display_mode("shaded")
    return vp


def _at(vp, point):
    return vp._eye().project(np.asarray([point], float), vp.width(),
                             vp.height())[0, :2]


def _picks(vp, point):
    return vp.pick_objects(*_at(vp, point))


def test_a_curve_is_picked_only_below_the_plane(pane):
    line = pane.scene.add(g.make_line((20, 0, -10), (20, 0, 10)))
    assert line.id in _picks(pane, (20, 0, 8))
    _plane(pane.scene)
    assert line.id not in _picks(pane, (20, 0, 8))
    assert line.id in _picks(pane, (20, 0, -8))


def test_a_solid_is_picked_only_where_it_is_left(pane):
    box = pane.scene.add(g.make_box((-5, -2, -5), 10, 4, 10))
    _plane(pane.scene)
    assert box.id not in _picks(pane, (0, 0, 3))
    assert box.id in _picks(pane, (0, 0, -3))


def test_a_point_above_the_plane_is_not_picked(pane):
    dot = pane.scene.add(g.make_point((-20, 0, 6)))
    _plane(pane.scene)
    assert dot.id not in _picks(pane, (-20, 0, 6))


def test_the_plane_itself_is_still_picked(pane):
    plane = _plane(pane.scene)
    pane.set_view("top")
    pane.camera.target = np.zeros(3)
    pane.camera.distance = 80.0
    assert plane.id in _picks(pane, (30, 30, 0))


def test_a_crossing_band_over_the_cut_away_half_catches_nothing(pane):
    box = pane.scene.add(g.make_box((-5, -2, -5), 10, 4, 10))
    line = pane.scene.add(g.make_line((20, 0, -10), (20, 0, 10)))
    _plane(pane.scene)
    x0, y0 = _at(pane, (-30, 0, 9))
    x1, y1 = _at(pane, (30, 0, 2))
    assert pane._box_pick(x0, y0, x1, y1, crossing=True) == []
    x1, y1 = _at(pane, (30, 0, -2))
    caught = pane._box_pick(x0, y0, x1, y1, crossing=True)
    assert box.id in caught and line.id in caught


def test_a_window_takes_a_cut_curve_by_what_is_left(pane):
    line = pane.scene.add(g.make_line((20, 0, -4), (20, 0, 30)))
    _plane(pane.scene)
    x0, y0 = _at(pane, (15, 0, 1))
    x1, y1 = _at(pane, (25, 0, -6))
    assert line.id in pane._box_pick(x0, y0, x1, y1, crossing=False)


def test_a_cut_away_face_is_not_picked_as_a_subobject(pane):
    box = pane.scene.add(g.make_box((-5, -2, -5), 10, 4, 10))
    _plane(pane.scene)
    assert pane.pick_subobject(*_at(pane, (0, 0, 3))) is None
    hit = pane.pick_subobject(*_at(pane, (0, 0, -3)))
    assert hit is not None and hit[0] == box.id
