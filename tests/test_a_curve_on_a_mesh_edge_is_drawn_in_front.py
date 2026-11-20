"""A curve lying on a mesh's edge is drawn in front of it.

A curve and the edge it lies on have the same depth, so the two fought
for every pixel and the curve came and went along its length. A curve is
drawn a hair nearer than it is, by narrowing the depth range it is drawn
into. The range is switched only where a curve follows something else or
the other way round, since setting it for every object cost two GL calls
each, and it is put back once the objects are drawn.
"""

from __future__ import annotations

import numpy as np

from serpentine3d.core import geometry as g
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui import gpu_share
from serpentine3d.ui import viewport as vp_mod


class _GL:
    def __init__(self):
        self.ranges = []

    def __getattr__(self, name):
        if name.startswith("GL_"):
            return 0
        if name == "glDepthRange":
            return lambda near, far: self.ranges.append((near, far))
        return lambda *a, **k: 0


def test_curves_are_drawn_nearer_and_the_range_is_put_back(_qapp,
                                                           monkeypatch):
    gl = _GL()
    monkeypatch.setattr(vp_mod, "GL", gl)
    monkeypatch.setattr(vp_mod, "_current_share_group", lambda: None)
    gpu_share.reset()
    try:
        scene = Scene()
        v = np.array([(0, 0, 0), (10, 0, 0), (10, 10, 3)], float)
        scene.add(MeshShape(v, [[0, 1, 2]], faceted=True))
        for i in range(3):
            scene.add(g.make_line((0, i, 0), (10, i, 0)))
        view = vp_mod.Viewport(scene, SelectionManager(scene))
        view.resize(800, 600)
        view._mesh_prog, view._line_prog = 11, 12
        view._thick_prog, view._point_prog = 13, 14
        view._max_line_width = 1.0
        for obj in scene.all():
            obj.mesh
        view._sync_gpu()
        view.zoom_extents()
        w, h = view.width(), view.height()
        v = view.camera.view_matrix()
        view._draw_objects(view.camera.proj_matrix(w, h) @ v, v)
    finally:
        gpu_share.reset()
    nearer = [r for r in gl.ranges if r[1] < 1.0]
    assert nearer, "no curve was drawn nearer"
    assert nearer[0][1] == 1.0 - vp_mod.CURVE_DEPTH_NUDGE
    assert len(gl.ranges) <= 4, "switched for every object"
    assert gl.ranges[-1] == (0.0, 1.0), "the range was left narrowed"
