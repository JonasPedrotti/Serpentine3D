"""Rotate3D, as in Rhino: the construction circle about the axis while the
first reference is picked, then the reference swings freely in the plane it
turns in, with only the part of the circle turned so far drawn."""

import math

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow
from serpentine3d.core import geometry as g


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_NO_RECOVER", "1")
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    QApplication.processEvents()
    yield w
    w.processor.cancel()
    w.mark_saved()
    w.close()


def _ready(win):
    line = win.scene.add(g.make_line((2, 0, 0), (2, 5, 0)))
    win.selection.set([line.id])
    win.run_command("rotate3d")
    for p in ("0,0,0", "10,0,0"):                  # an axis along x
        win.processor.provide_text(p)
    QApplication.processEvents()
    return line


def test_the_first_reference_shows_the_circle_round_the_axis(win):
    _ready(win)
    lines = win.processor.request.guide_fn((3.0, 0.0, 4.0))
    ring = np.asarray(lines[-1], float)
    assert np.allclose(ring[:, 0], 3.0), "the circle stands square to x"
    assert np.allclose(np.hypot(ring[:, 1], ring[:, 2]), 4.0)


def test_the_second_reference_lands_in_the_turning_plane_with_no_snap(win):
    line = _ready(win)
    win.processor.provide_text("2,5,0")
    QApplication.processEvents()
    vp = win.viewport
    assert vp.point_plane is not None
    vp.snaps.enabled = False
    above = (2.0, 0.0, 5.0)
    px, py, _ = vp._eye().project(np.array([above], float),
                                  vp.width(), vp.height())[0]
    p = vp.world_point_at(px, py)
    assert p == pytest.approx(above, abs=1e-6), "not dropped to the CPlane"
    swept = np.asarray(win.processor.request.guide_fn(p)[-1], float)
    assert np.allclose(np.hypot(swept[:, 1], swept[:, 2]), 5.0)
    assert np.allclose(swept[-1], above, atol=1e-6)
    turned = math.atan2(swept[len(swept) // 2, 2], swept[len(swept) // 2, 1])
    assert turned == pytest.approx(math.pi / 4, abs=0.05), \
        "only the quarter turned is drawn"
    win.processor.provide(p)
    lo, hi = g.bbox(win.scene.get(line.id).shape)
    assert hi[2] == pytest.approx(5.0, abs=1e-6)


def test_the_guides_are_drawn_in_the_panes(win):
    _ready(win)
    win._refresh_rubber((3.0, 0.0, 4.0))
    segs = win.viewport._preview_data
    assert len(segs) > 60, "axis and circle drawn as the band"
