"""While the cursor moves, SetPt on held faces of a polysurface draws only
the edges that move, at once, as Rhino does; the faces are rebuilt on the
click, and what is built has its edges where the draft drew them."""

from __future__ import annotations

import time

import numpy as np
import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.tessellate import tessellate


@pytest.fixture
def window():
    from serpentine3d.app import MainWindow
    w = MainWindow()
    try:
        yield w
    finally:
        if w.processor.busy:
            w.processor.cancel()
        w.mark_saved()
        w.close()


def _top(shape):
    faces = g.faces_of(shape)
    return max(range(len(faces)), key=lambda i: g.centroid(faces[i])[2])


@pytest.mark.parametrize("offset", [0.0, 100000.0], ids=["near", "far"])
def test_the_cursor_moves_only_the_edges_and_the_click_builds_them(window, offset):
    w = window
    box = w.scene.add(g.make_box((offset, offset, 0), 10, 6, 10))
    w.selection.toggle_subobject(box.id, "face", _top(box.shape))
    w.run_command("setpt")
    req = w.processor.request
    assert req.draft_fn is not None

    started = time.perf_counter()
    for z in (11.0, 12.0, 13.0, 15.0):
        w._on_mouse_world((offset + 3.0, offset + 2.0, z))
    assert time.perf_counter() - started < 0.1, "a draft must keep up"

    for pane in w.all_viewports():
        ghost = pane._ghost
        assert ghost is not None and not ghost.has_faces, "edges alone"
        segments = ghost.edge_segments.reshape(-1, 3)
        assert segments[:, 2].max() == pytest.approx(15.0, abs=1e-5)
        assert segments[:, 2].min() == pytest.approx(0.0, abs=1e-5)
        corners = {tuple(np.round(c, 6)) for c in ghost.points}
        assert corners == {(offset + x, offset + y, 15.0)
                           for x in (0.0, 10.0) for y in (0.0, 6.0)}, (
            "the moving corners are marked where they go, and only they")
    drawn = w.viewport._ghost.edge_segments.reshape(-1, 3)
    assert len(drawn) < len(box.mesh.edge_segments.reshape(-1, 3)), (
        "the bottom edges do not move and are not drawn again")

    w.processor.provide((offset + 3.0, offset + 2.0, 15.0))
    built = w.scene.get(box.id).shape
    assert g.volume(built) == pytest.approx(900.0, abs=1e-6)
    edges = tessellate(built).edge_segments.reshape(-1, 3)
    for p in drawn:
        assert np.linalg.norm(edges - p, axis=1).min() < 1e-4
    assert all(pane._ghost is None for pane in w.all_viewports())
