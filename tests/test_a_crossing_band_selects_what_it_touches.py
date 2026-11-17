"""A band dragged right to left takes every object it touches.

It used to take an object only when one of its segment ends fell inside,
so a line passing clean through a small band, or a band dropped onto the
middle of a shaded surface, picked nothing.
"""

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


@pytest.fixture
def view():
    QApplication.instance() or QApplication([])
    from serpentine3d.ui.viewport import Viewport
    scene = Scene()
    vp = Viewport(scene, SelectionManager(scene))
    vp.resize(800, 600)
    return vp


def _band_at(view, at, crossing=True, pad=8.0):
    view.set_view("top")
    view.zoom_extents()
    x, y, _ = view.camera.project(np.array([at], float),
                                  view.width(), view.height())[0]
    return view._box_pick(x + pad, y - pad, x - pad, y + pad, crossing)


def test_a_band_through_the_middle_of_a_line_takes_it(view):
    line = view.scene.add(g.make_line((0, 0, 0), (100, 0, 0)))
    assert _band_at(view, (50, 0, 0)) == [line.id]


def test_a_band_inside_a_shaded_surface_takes_it(view):
    box = view.scene.add(g.make_box((0, 0, 0), 100, 100, 10))
    assert _band_at(view, (50, 50, 10)) == [box.id]


def test_a_wireframe_surface_is_taken_only_by_its_edges(view):
    box = view.scene.add(g.make_box((0, 0, 0), 100, 100, 10))
    view.display_mode = "wireframe"
    assert _band_at(view, (50, 50, 10)) == []
    assert _band_at(view, (50, 0, 10)) == [box.id]


def test_a_band_beside_a_line_leaves_it_alone(view):
    view.scene.add(g.make_line((0, 0, 0), (100, 0, 0)))
    view.scene.add(g.make_line((0, 60, 0), (1, 60, 0)))
    assert _band_at(view, (50, 30, 0)) == []


def test_a_window_band_still_wants_the_whole_object(view):
    view.scene.add(g.make_line((0, 0, 0), (100, 0, 0)))
    assert _band_at(view, (50, 0, 0), crossing=False) == []
