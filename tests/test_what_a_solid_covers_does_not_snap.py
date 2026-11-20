"""What a face in front covers cannot be snapped to.

In a shaded view an end, a midpoint or an edge behind a solid is out of
sight, so it does not catch the cursor. What lies on the face in front
still snaps, and in wireframe and ghosted, where every edge shows, so
does everything behind.
"""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui.viewport import Viewport

SIZE = (900, 700)


@pytest.fixture
def pane(_qapp):
    scene = Scene()
    vp = Viewport(scene, SelectionManager(scene))
    vp.resize(*SIZE)
    vp.set_view("front")
    vp.camera.target = np.zeros(3)
    vp.camera.distance = 80.0
    vp.set_display_mode("shaded")
    scene.add(g.make_box((-5, -2, -5), 10, 4, 10))
    return vp


def _pick(vp, point):
    px, py = vp._eye().project(np.asarray([point], float), vp.width(),
                              vp.height())[0, :2]
    vp.world_point_at(px, py)
    return vp._active_snap


def test_an_end_behind_a_solid_does_not_snap(pane):
    pane.scene.add(g.make_line((0, 10, 0), (20, 10, 0)))
    assert _pick(pane, (0, 10, 0)) is None
    hit = _pick(pane, (20, 10, 0))
    assert hit[1] == "end"
    assert hit[0] == pytest.approx((20, 10, 0))


def test_the_front_of_the_solid_and_what_lies_on_it_snap(pane):
    pane.scene.add(g.make_line((-3, -2, 1), (3, -2, 1)))
    assert _pick(pane, (-5, -2, 5))[1] == "end"
    hit = _pick(pane, (-3, -2, 1))
    assert hit[1] == "end"
    assert hit[0] == pytest.approx((-3, -2, 1))


def test_near_skips_a_covered_curve(pane):
    pane.snaps.types["near"] = True
    pane.scene.add(g.make_line((-30, 10, 2), (30, 10, 2)))
    assert _pick(pane, (1, 10, 2)) is None
    assert _pick(pane, (15, 10, 2))[1] == "near"


@pytest.mark.parametrize("mode", ["wireframe", "ghosted"])
def test_every_edge_snaps_where_every_edge_shows(pane, mode):
    pane.set_display_mode(mode)
    pane.scene.add(g.make_line((0, 10, 0), (20, 10, 0)))
    assert _pick(pane, (0, 10, 0))[1] == "end"
