"""A clipping plane edges everything it cuts, in its own colour.

A solid's cap had a line round it in the hatch's ink, and a surface or a
mesh the plane cut through had nothing: where it ended was left to the
eye. Now the line runs wherever the plane meets the faces of a solid, a
surface or a mesh, in the colour the plane is drawn in. A solid's section
still says how wide, and none where it says none; a picked object's cut
is gold as before.
"""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui import section_caps as caps
from serpentine3d.ui import viewport as vp_mod
from serpentine3d.ui.viewport import Viewport

RED = (0.9, 0.1, 0.1)


class _NoGL:
    """Stands in for OpenGL: the lines are caught before they reach it."""

    def __getattr__(self, name):
        if name.startswith("GL_"):
            return 0
        return lambda *a, **k: None


@pytest.fixture
def pane(_qapp, monkeypatch):
    monkeypatch.setattr(vp_mod, "GL", _NoGL())
    scene = Scene()
    vp = Viewport(scene, SelectionManager(scene))
    vp.resize(900, 700)
    return vp


def _clip(scene, z=3.0, color=RED):
    rect = g.planar_face(g.make_polyline(
        [(-60, -60, z), (60, -60, z), (60, 60, z), (-60, 60, z)],
        closed=True))
    obj = scene.add(rect, name="Clip")
    scene.update(obj.id, clip_plane={"enabled": True}, color=color)
    return obj


def _lines(vp, objects, color=RED, z=3.0):
    """What `_draw_cut_lines` draws: ((rgba), width) per batch of lines."""
    drawn = []
    vp._draw_thick_segments = lambda segs, mvp, rgba, width: drawn.append(
        (tuple(rgba), width, len(segs)))
    (plane,) = caps.cap_planes([((0.0, 0.0, z), (0.0, 0.0, 1.0), True)])
    vp._draw_cut_lines(np.eye(4), plane, [], [(o, None) for o in objects],
                       color)
    return drawn


def _wall(scene):
    return scene.add(g.extrude(g.make_line((0, 0, 0), (6, 6, 0)),
                               (0, 0, 1), 6))


def _mesh(scene):
    v = np.array([(0, 0, 0), (6, 0, 0), (6, 6, 6), (0, 6, 6)], float)
    return scene.add(MeshShape(v, np.array([(0, 1, 2), (0, 2, 3)])))


@pytest.mark.parametrize("make", [
    lambda s: s.add(g.make_box((0, 0, 0), 6, 6, 6)), _wall, _mesh],
    ids=["solid", "surface", "mesh"])
def test_the_cut_is_edged_in_the_planes_colour(pane, make):
    obj = make(pane.scene)
    drawn = _lines(pane, [obj])
    assert len(drawn) == 1
    rgba, width, count = drawn[0]
    assert rgba == pytest.approx((*RED, 1.0))
    assert width >= 1.0 and count > 0


def test_a_solid_whose_section_has_no_line_keeps_none(pane):
    box = pane.scene.add(g.make_box((0, 0, 0), 6, 6, 6))
    pane.scene.update(box.id, section_fill={
        "pattern": "solid", "angle": 0.0, "spacing": 1.0,
        "color": "layer", "cut_line_width": 0.0})
    assert _lines(pane, [pane.scene.get(box.id)]) == []


def test_a_picked_object_s_cut_is_gold(pane):
    wall = _wall(pane.scene)
    pane.selection.set([wall.id])
    ((rgba, width, _count),) = _lines(pane, [wall])
    assert rgba[:3] != pytest.approx(RED)
    assert width >= 2.2


def test_each_plane_lends_its_own_colour(pane):
    _clip(pane.scene, 3.0, RED)
    _clip(pane.scene, -3.0, (0.1, 0.2, 0.9))
    colors = pane._clip_plane_colors()
    assert sorted(c[2] for c in colors.values()) == pytest.approx([0.1, 0.9])
    by_height = {round(o[2]): c for (o, _n), c in colors.items()}
    assert by_height[3] == pytest.approx(RED)


def test_without_a_section_the_line_is_the_default_width():
    style = caps.cut_line_style(None)
    assert style is not None and style[1] >= 1.0


def test_a_colour_the_section_names_is_kept(pane):
    box = pane.scene.add(g.make_box((0, 0, 0), 6, 6, 6))
    pane.scene.layers.set_cut_line_color(box.layer_id, "#00ff00")
    ((rgba, _width, _count),) = _lines(pane, [box])
    assert rgba == pytest.approx((0.0, 1.0, 0.0, 1.0))
