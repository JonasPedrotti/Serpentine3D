"""Drawing an arc from its center, the end snaps to where the arc itself
crosses the drawing, not to where other curves cross each other."""

import math

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

import serpentine3d.commands  # registers all commands  # noqa: F401
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.core.snaps import SnapIndex


@pytest.fixture
def vp():
    QApplication.instance() or QApplication([])
    from serpentine3d.ui.viewport import Viewport
    scene = Scene()
    v = Viewport(scene, SelectionManager(scene))
    v.resize(800, 600)
    # a line the arc's circle (r 10 about the origin) crosses at (6, 8),
    # and a second line crossing the first well inside the circle
    scene.add(g.make_line((6, -20, 0), (6, 20, 0)))
    scene.add(g.make_line((0, 4, 0), (12, 4, 0)))
    v.set_view("top")
    v.zoom_extents()
    return v


def _snap_near(vp, world, on_curve=None):
    idx = SnapIndex(vp.scene)
    px, py, _ = vp.camera.project(np.array([world], float),
                                  vp.width(), vp.height())[0]
    return idx.find(vp.camera, px, py, vp.width(), vp.height(),
                    radius_px=60.0, on_curve=on_curve)


def test_without_an_arc_the_curves_crossing_is_the_intersection(vp):
    hit = _snap_near(vp, (6, 6, 0))
    assert hit[1] == "int"
    assert hit[0] == pytest.approx((6, 4, 0), abs=1e-6)


def test_with_the_arc_only_its_own_crossing_counts(vp):
    ring = g.make_circle((0, 0, 0), 10.0)
    hit = _snap_near(vp, (6, 6, 0), on_curve=ring)
    assert hit[1] == "int"
    assert hit[0] == pytest.approx((6, 8, 0), abs=1e-6)


def test_the_arc_command_hands_its_circle_to_the_snaps():
    scene = Scene()
    proc = CommandProcessor(
        CommandContext(scene, SelectionManager(scene), History(scene)))
    proc.run("arc")
    proc.provide_text("0,0,0")
    proc.provide_text("10,0,0")
    ring = proc.request.snap_on
    assert ring is not None
    assert g.curve_length(ring) == pytest.approx(2 * math.pi * 10, rel=1e-6)
