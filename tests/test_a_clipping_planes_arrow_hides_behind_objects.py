"""A clipping plane behind an object hides its arrow with it.

The arrow is drawn over everything, so a plane lying flat on a face still
says which way it cuts. But a plane an object stands in front of is out of
sight, and its arrow, or the ring standing in for it, goes with it. In
wireframe and ghosted every plane shows, and so does every arrow.
"""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui.viewport import Viewport

SIZE = (900, 700)


def _plane(scene, y, corners):
    rect = g.planar_face(g.make_polyline(
        [(x, y, z) for x, z in corners], closed=True))
    obj = scene.add(rect, name="Clip")
    scene.update(obj.id, clip_plane={"enabled": True})
    return obj


def _box(scene):
    """A box meshed, as the pane has it once it has drawn it."""
    box = scene.add(g.make_box((-5, -2, -5), 10, 4, 10))
    box.mesh
    return box


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


def _behind_a_box(vp):
    """A plane square to the line of sight behind a box, cutting away
    the far side so the box stays."""
    corners = [(-20, -20), (20, -20), (20, 20), (-20, 20)]
    plane = _plane(vp.scene, 10, corners)
    eq = vp._clip_vectors()[0]
    if np.dot(eq[:3], (0, 0, 0)) + eq[3] < 0:
        vp.scene.remove(plane.id)
        plane = _plane(vp.scene, 10, corners[::-1])
    _box(vp.scene)
    return plane


def test_a_plane_behind_a_box_shows_no_arrow(pane):
    _behind_a_box(pane)
    assert pane._clip_frames(shown=True)
    assert pane._clip_frames_in_sight() == []


def test_a_plane_in_the_open_keeps_its_arrow(pane):
    _plane(pane.scene, 10, [(30, -20), (70, -20), (70, 20), (30, 20)])
    _box(pane.scene)
    assert len(pane._clip_frames_in_sight()) == 1


def test_a_plane_on_a_face_keeps_its_arrow(pane):
    corners = [(-20, -20), (20, -20), (20, 20), (-20, 20)]
    _plane(pane.scene, -2, corners)
    _box(pane.scene)
    assert len(pane._clip_frames_in_sight()) == 1


@pytest.mark.parametrize("mode", ["wireframe", "ghosted"])
def test_every_arrow_shows_where_every_edge_shows(pane, mode):
    _behind_a_box(pane)
    pane.set_display_mode(mode)
    assert len(pane._clip_frames_in_sight()) == 1


def test_the_arrow_meshes_nothing_that_is_not_meshed_yet(pane):
    """Meshing the whole drawing to look behind the arrow froze the
    window on a large file: what has no mesh yet hides nothing."""
    _behind_a_box(pane)
    late = pane.scene.add(g.make_box((-5, -6, -5), 10, 2, 10))
    pane._occluders_held = None
    assert pane._clip_frames_in_sight() == []
    assert not late.mesh_ready



def _floor(scene, z, keep_below=True, at=(0.0, 0.0)):
    """A horizontal plane at `z`, taking away what is above it, or what
    is below it when `keep_below` is False."""
    corners = [(-60, -60), (60, -60), (60, 60), (-60, 60)]
    if not keep_below:
        corners = corners[::-1]
    rect = g.planar_face(g.make_polyline(
        [(at[0] + x, at[1] + y, z) for x, y in corners], closed=True))
    obj = scene.add(rect, name="Clip")
    scene.update(obj.id, clip_plane={"enabled": True})
    return obj


@pytest.mark.parametrize("mode", ["shaded", "wireframe"])
def test_a_plane_another_plane_cut_away_shows_no_arrow(pane, mode):
    pane.set_display_mode(mode)
    _floor(pane.scene, 0)
    _floor(pane.scene, 20)
    shown = pane._clip_frames_in_sight()
    assert [f[0][2] for f in shown] == [pytest.approx(0.0)]


def test_a_plane_on_the_side_another_keeps_shows_its_arrow(pane):
    _floor(pane.scene, 0)
    _floor(pane.scene, -20, keep_below=False)
    assert len(pane._clip_frames_in_sight()) == 2


def test_planes_far_from_home_judge_each_other_in_doubles(pane):
    far = 5_000_000.0
    pane.camera.target = np.array([far, far, far])
    _floor(pane.scene, far, at=(far, far))
    _floor(pane.scene, far - 0.001, keep_below=False, at=(far, far))
    assert len(pane._clip_frames_in_sight()) == 2
