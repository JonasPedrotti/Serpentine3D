"""Near leaves mesh edges alone, and a snap marker is the same size on
screen wherever the snap is.

A terrain or a scan is every one of its triangles' edges, and Near on them
caught the cursor wherever it went. A marker measured as a share of the
distance to the camera's target came out a metre wide on a snap near the
eye, which a file's own view, aimed far off, makes common.
"""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.core.snaps import SNAP_TYPES, SnapIndex
from serpentine3d.ui.camera import Camera
from serpentine3d.ui.viewport import Viewport

SIZE = (900, 700)


def _top():
    cam = Camera()
    cam.set_standard_view("top")
    cam.target = np.zeros(3)
    cam.distance = 40.0
    return cam


def _near_only(scene):
    index = SnapIndex(scene)
    index.types = {k: k == "near" for k in SNAP_TYPES}
    return index


def _at(cam, point):
    return cam.project(np.asarray([point], float), *SIZE)[0, :2]


def test_near_does_not_catch_a_mesh_edge():
    scene, cam = Scene(), _top()
    scene.add(MeshShape(np.array([[-5.0, -5.0, 0.0], [5.0, -5.0, 0.0],
                                  [0.0, 5.0, 0.0]]),
                        np.array([[0, 1, 2]], np.uint32), faceted=True))
    px, py = _at(cam, (0.0, -5.0, 0.0))
    assert _near_only(scene).find(cam, px, py, *SIZE) is None


def test_a_mesh_offers_its_corners_and_not_its_middles():
    scene, cam = Scene(), _top()
    scene.add(MeshShape(np.array([[-5.0, -5.0, 0.0], [5.0, -5.0, 0.0],
                                  [0.0, 5.0, 0.0]]),
                        np.array([[0, 1, 2]], np.uint32)))
    index = SnapIndex(scene)
    index.types = {k: k in ("end", "mid") for k in SNAP_TYPES}
    px, py = _at(cam, (0.0, -5.0, 0.0))
    assert index.find(cam, px, py, *SIZE) is None, "the middle of an edge"
    px, py = _at(cam, (5.0, -5.0, 0.0))
    assert index.find(cam, px, py, *SIZE)[1] == "end"


def test_near_still_catches_a_curve():
    scene, cam = Scene(), _top()
    scene.add(g.make_line((-5.0, -5.0, 0.0), (5.0, -5.0, 0.0)))
    px, py = _at(cam, (1.0, -5.0, 0.0))
    hit = _near_only(scene).find(cam, px, py, *SIZE)
    assert hit is not None and hit[1] == "near"


def test_a_pixel_is_measured_where_the_snap_is(_qapp):
    vp = Viewport(Scene(), SelectionManager(Scene()))
    vp.resize(*SIZE)
    cam = vp.camera
    cam.projection = "perspective"
    cam.target = np.zeros(3)
    cam.distance = 1000.0
    eye = np.asarray(cam.position, float)
    toward = -eye / np.linalg.norm(eye)
    near = eye + toward * 10.0
    far = eye + toward * 1000.0
    # ten units from the eye, a pixel is a hundredth of one at the target
    assert vp._world_per_pixel(near) == pytest.approx(
        vp._world_per_pixel(far) / 100.0, rel=1e-6)
