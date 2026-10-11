"""A clipping plane can be clicked from the side, survives being scaled,
and says which way it cuts when you look at it head on.

Three ways it broke in use:

- From the side it could not be clicked: in a shaded view a click asked
  only an object's faces, and a flat plane seen edge on has none on
  screen. Only a band over a corner caught it. Any flat surface had the
  same trouble, so a click that misses every face now tries the edges.
- Scaled along one axis (the gumball's single handles), it stopped
  cutting and lost its arrow: OpenCASCADE's general transform turned the
  plane into a NURBS surface, still flat, and the code that reads a plane
  gave up on it. Reading the normal off the NURBS surface would not do: a
  flipped plane would quietly turn back round. So a flat polygon stays a
  true plane under any linear map, its normal carried across the way a
  plane's normal goes (the inverse transpose), sense and all.
- Seen head on, its arrow is a dot, and nothing said which way it cut.
  Now a ring stands at its middle: a cross in it when the arrow goes into
  the screen (the visible half is beyond the plane, so the cut is toward
  you), a dot when it comes out. That is how a vector square to a drawing
  has always been drawn.
"""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui import viewport as vp_mod
from serpentine3d.ui.camera import Camera
from serpentine3d.ui.viewport import (clip_end_on_marks, clip_equation,
                                      clip_normal_arrows, clip_plane_frames)


def _rect(z=0.0):
    return g.planar_face(g.make_polyline(
        [(-5, -5, z), (5, -5, z), (5, 5, z), (-5, 5, z)], closed=True))


def _plane(scene, flipped=False, z=0.0):
    face = _rect(z)
    if flipped:
        face = g.mirror(face, (0, 0, z), (0, 0, 1))
    obj = scene.add(face, name="Clipping Plane 01")
    scene.update(obj.id, clip_plane={"enabled": True})
    return scene.get(obj.id)


def _cut_side(scene):
    """+1 when the plane cuts away what is above it, -1 below."""
    (origin, normal, _on), = clip_plane_frames(
        [o for o in scene.all() if o.clip_plane])
    eq = clip_equation(origin, normal)
    above = float(np.dot(eq, [origin[0], origin[1], origin[2] + 1.0, 1.0]))
    return 1 if above < 0 else -1


# -- clicked from the side -------------------------------------------------------

@pytest.fixture
def front(_qapp):
    scene = Scene()
    view = vp_mod.Viewport(scene, SelectionManager(scene))
    view.resize(800, 600)
    view.set_view("front")
    return scene, view


def _on_screen(view, point):
    (x, y, _w), = view.camera.project(np.asarray([point], float),
                                      view.width(), view.height())
    return float(x), float(y)


def test_a_plane_seen_edge_on_can_be_clicked(front):
    scene, view = front
    plane = _plane(scene)
    view.zoom_extents()
    x, y = _on_screen(view, (2.0, 0.0, 0.0))
    assert view.pick_object(x, y) == plane.id
    assert view.pick_object(x, y + 3) == plane.id, "a near miss missed"


def test_a_flat_surface_seen_edge_on_can_be_clicked_too(front):
    scene, view = front
    surface = scene.add(_rect(), name="Floor")
    view.zoom_extents()
    x, y = _on_screen(view, (-3.0, 0.0, 0.0))
    assert view.pick_object(x, y) == surface.id


def test_a_click_well_clear_of_it_still_picks_nothing(front):
    scene, view = front
    _plane(scene)
    view.zoom_extents()
    x, y = _on_screen(view, (2.0, 0.0, 0.0))
    assert view.pick_object(x, y - 60) is None


def test_a_face_in_front_still_wins_over_an_edge_behind(front):
    scene, view = front
    plane = _plane(scene)
    box = scene.add(g.make_box((-8, -20, -3), 16, 4, 6), name="In front")
    view.zoom_extents()
    x, y = _on_screen(view, (2.0, 0.0, 0.0))
    assert view.pick_objects(x, y)[:2] == [box.id, plane.id]


@pytest.fixture
def top(_qapp):
    scene = Scene()
    view = vp_mod.Viewport(scene, SelectionManager(scene))
    view.resize(800, 600)
    view.set_view("top")
    return scene, view


def _patch(x0, x1):
    return g.planar_face(g.make_polyline(
        [(x0, -5, 0), (x1, -5, 0), (x1, 5, 0), (x0, 5, 0)], closed=True))


def test_a_click_beside_a_seam_keeps_to_the_surface_clicked(top):
    """Only a face seen edge on hands the click to its edges. Two surfaces
    side by side, a click on one just beside the seam they share: the other
    misses with its faces in plain view, and its edge on the seam is no
    excuse to take the click."""
    scene, view = top
    left = scene.add(_patch(-10, 0), name="Left")
    scene.add(_patch(0, 10), name="Right")
    view.zoom_extents()
    x, y = _on_screen(view, (0.0, 0.0, 0.0))
    assert view.pick_object(x - 3, y) == left.id


def test_a_click_on_the_floor_beside_a_box_keeps_to_the_floor(top):
    scene, view = top
    floor = scene.add(_rect(), name="Floor")
    scene.add(g.make_box((-2, -2, 0), 4, 4, 4), name="Box")
    view.zoom_extents()
    x, y = _on_screen(view, (2.0, 0.0, 4.0))
    assert view.pick_object(x + 3, y) == floor.id


# -- scaled ----------------------------------------------------------------------

@pytest.mark.parametrize("flipped", [False, True])
@pytest.mark.parametrize("scale", [
    lambda s: g.scale_along_axis(s, (0, 0, 0), (1, 0, 0), 2.0),
    lambda s: g.scale_along_axis(s, (0, 0, 0), (0, 1, 0), 0.4),
    lambda s: g.scale_along_axis(s, (0, 0, 0), (0.6, 0.8, 0), 1.7),
    lambda s: g.scale(s, (0, 0, 0), 3.0),
])
def test_scaling_keeps_it_cutting_the_same_way(flipped, scale):
    scene = Scene()
    plane = _plane(scene, flipped=flipped)
    before = _cut_side(scene)
    scene.replace_shape(plane.id, scale(plane.shape))
    assert clip_plane_frames([scene.get(plane.id)]), \
        "the scaled plane stopped cutting"
    assert _cut_side(scene) == before, "scaling turned the cut round"


@pytest.mark.parametrize("command, inputs", [
    ("scale1d", ["0,0,0", "1,0,0", "2.5,0,0"]),
    ("scale2d", ["0,0,0", "1,0,0", "3,0,0"]),
    ("scalenu", ["0,0,0", "2", "0.5", "1"]),
])
def test_the_scale_commands_keep_it_cutting_too(env, command, inputs):
    scene, sel, _h, _ctx, proc = env
    plane = _plane(scene, flipped=True)
    before = _cut_side(scene)
    sel.set([plane.id])
    proc.run(command)
    for text in inputs:
        proc.provide_text(text)
    assert not proc.busy
    assert g.bbox(scene.get(plane.id).shape) != g.bbox(_rect()), \
        "the command scaled nothing"
    assert clip_plane_frames([scene.get(plane.id)]), \
        "the scaled plane stopped cutting"
    assert _cut_side(scene) == before, "scaling turned the cut round"


@pytest.mark.parametrize("axis, factor", [(0, 2.0), (1, 0.5), (2, 3.0)])
def test_the_gumball_s_scale_handles_keep_it_cutting_too(_qapp, axis,
                                                         factor):
    """What was reported: a scale handle on the gumball, one axis at a
    time, each through the gumball's own drag. Seen at a slant, so no
    handle points straight at the eye, which the gumball would refuse."""
    from PySide6.QtCore import Qt
    scene = Scene()
    view = vp_mod.Viewport(scene, SelectionManager(scene))
    view.resize(800, 600)
    plane = _plane(scene, flipped=True)
    view.zoom_extents()
    before = _cut_side(scene)
    view.selection.set([plane.id])
    assert view.gumball.begin_drag(("scale", axis), view.width() / 2,
                                   view.height() / 2,
                                   Qt.KeyboardModifier.NoModifier)
    view.gumball.apply_scalar(factor)
    view.gumball.end_drag()
    assert clip_plane_frames([scene.get(plane.id)]), \
        "the scaled plane stopped cutting"
    assert _cut_side(scene) == before, "scaling turned the cut round"


def test_a_scaled_plane_is_still_a_plane():
    scaled = g.scale_along_axis(_rect(), (0, 0, 0), (1, 0, 0), 2.0)
    face = next(iter(g.faces_of(scaled)))
    assert g.face_normal(face) == pytest.approx((0.0, 0.0, 1.0))
    (lo, hi) = g.bbox(scaled)
    assert (hi[0] - lo[0], hi[1] - lo[1]) == pytest.approx((20.0, 10.0))


def test_a_shear_that_tilts_the_plane_turns_its_normal_with_it():
    """The normal goes by the inverse transpose, not by the matrix: under a
    shear in z along x, a level plane tilts, and its normal with it."""
    m = np.eye(4)
    m[2, 0] = 0.5                       # z' = z + 0.5 x
    sheared = g.apply_matrix(_rect(), m)
    face = next(iter(g.faces_of(sheared)))
    expected = np.array([-0.5, 0.0, 1.0]) / np.linalg.norm([-0.5, 0, 1])
    assert g.face_normal(face) == pytest.approx(tuple(expected), abs=1e-9)


def test_a_plane_turned_to_nurbs_elsewhere_still_cuts():
    """A file saved after an earlier build scaled its plane holds a NURBS
    face; the plane is still read rather than dropped."""
    scene = Scene()
    plane = _plane(scene)
    from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
    nurbs = BRepBuilderAPI_NurbsConvert(plane.shape, True).Shape()
    scene.replace_shape(plane.id, nurbs)
    assert clip_plane_frames([scene.get(plane.id)])


# -- seen head on -----------------------------------------------------------------

def _looking_down():
    cam = Camera()
    cam.set_view("top") if hasattr(cam, "set_view") else None
    from serpentine3d.ui.camera import STANDARD_VIEWS
    cam.azimuth, cam.elevation = STANDARD_VIEWS["top"]
    cam.projection = "parallel"
    cam.target = np.zeros(3)
    cam.distance = 80.0
    return cam


def _oblique():
    cam = Camera()
    cam.target = np.zeros(3)
    cam.distance = 80.0
    return cam


def test_head_on_a_cut_toward_you_shows_a_cross():
    scene = Scene()
    _plane(scene)                       # cuts away above: toward a Top eye
    frames = clip_plane_frames(scene.all())
    (kind, _segments, _color), = clip_end_on_marks(frames, _looking_down(),
                                                   800, 600)
    assert kind == "cross"


def test_head_on_a_cut_away_from_you_shows_a_dot():
    scene = Scene()
    _plane(scene, flipped=True)
    frames = clip_plane_frames(scene.all())
    (kind, _segments, _color), = clip_end_on_marks(frames, _looking_down(),
                                                   800, 600)
    assert kind == "dot"


def test_the_mark_is_a_ring_a_fixed_size_on_screen():
    scene = Scene()
    _plane(scene)
    cam = _looking_down()
    (_kind, segments, _color), = clip_end_on_marks(
        clip_plane_frames(scene.all()), cam, 800, 600)
    scr = cam.project(np.asarray(segments, float), 800, 600)
    middle = cam.project(np.zeros((1, 3)), 800, 600)[0]
    reach = np.hypot(scr[:, 0] - middle[0], scr[:, 1] - middle[1]).max()
    assert reach == pytest.approx(vp_mod.CLIP_MARK_PX, rel=0.05)


def test_seen_at_a_slant_the_arrow_says_it_and_no_mark_is_needed():
    scene = Scene()
    _plane(scene)
    frames = clip_plane_frames(scene.all())
    assert clip_end_on_marks(frames, _oblique(), 800, 600) == []
    assert clip_normal_arrows(frames, _oblique(), 800, 600)


def test_head_on_the_arrow_that_would_be_a_dot_is_left_out():
    scene = Scene()
    _plane(scene)
    frames = clip_plane_frames(scene.all())
    assert clip_normal_arrows(frames, _looking_down(), 800, 600) == []
