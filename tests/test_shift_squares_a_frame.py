"""Shift on the second corner of a frame draws a square.

Shift is the momentary ortho override, and ortho holds a pick to the axis
through the last point: right for a line, no use for a frame. The second
corner of a rectangle landed on a line through the first, so the frame
came out a line. A clipping plane drawn that way made nothing at all, a
dot on screen, and only letting go of Shift made anything.

On a frame (a prompt that drags out sides, `rubber_sides`), ortho now does
the frame's version of square: equal sides, as long as the longer of the
two the cursor spans, on whichever side of the first corner it is. Lines
and the rest still go square to the axes.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from serpentine3d.core import geometry as g
from tests.test_a_picture_can_be_dropped_onto_paper import (  # noqa: F401
    paper_window)


@pytest.fixture
def top(_qapp):
    from serpentine3d.app import MainWindow
    win = MainWindow()
    win.resize(1200, 800)
    win.set_view_layout("single")
    vp = win.viewport
    vp.resize(800, 600)
    vp.set_view("top")
    vp.snaps.enabled = False
    vp.grid_snap = False
    vp.ortho = False
    yield win, vp
    if win.processor.busy:
        win.processor.cancel()
    win.mark_saved()
    win.close()


def _shift(monkeypatch, held):
    monkeypatch.setattr(QApplication, "queryKeyboardModifiers", staticmethod(
        lambda: (Qt.KeyboardModifier.ShiftModifier if held
                 else Qt.KeyboardModifier.NoModifier)))


def _pixel(vp, point):
    (x, y, _w), = vp.camera.project(np.asarray([point], float),
                                    vp.width(), vp.height())
    return float(x), float(y)


def _click(vp, point, shift=False):
    """A left click on the pixel `point` shows at, as the hand makes it."""
    pos = QPointF(*_pixel(vp, point))
    mods = (Qt.KeyboardModifier.ShiftModifier if shift
            else Qt.KeyboardModifier.NoModifier)
    for kind, buttons in ((QMouseEvent.Type.MouseButtonPress,
                           Qt.MouseButton.LeftButton),
                          (QMouseEvent.Type.MouseButtonRelease,
                           Qt.MouseButton.NoButton)):
        QApplication.sendEvent(vp, QMouseEvent(
            kind, pos, vp.mapToGlobal(pos), Qt.MouseButton.LeftButton,
            buttons, mods))


def _size(shape):
    lo, hi = g.bbox(shape)
    return (round(hi[0] - lo[0], 6), round(hi[1] - lo[1], 6))


def test_shift_on_a_clipping_plane_s_second_corner_draws_a_square(
        top, monkeypatch):
    """What was reported: first corner, then Shift and click."""
    win, vp = top
    win.processor.run("clippingplane")
    _shift(monkeypatch, False)
    _click(vp, (0.0, 0.0, 0.0))
    _shift(monkeypatch, True)
    _click(vp, (10.0, 4.0, 0.0), shift=True)
    assert not win.processor.busy
    planes = [o for o in win.scene.all() if o.clip_plane]
    assert len(planes) == 1, "no clipping plane was made"
    assert _size(planes[0].shape) == pytest.approx((10.0, 10.0), abs=0.05)


@pytest.mark.parametrize("cursor, corner", [
    ((10.0, 4.0), (10.0, 10.0)),
    ((-3.0, -8.0), (-8.0, -8.0)),
    ((6.0, -2.0), (6.0, -6.0)),
    ((-1.0, 7.0), (-7.0, 7.0)),
])
def test_the_square_takes_the_longer_side_on_the_cursor_s_side(
        top, monkeypatch, cursor, corner):
    win, vp = top
    win.processor.run("clippingplane")
    win.processor.provide((0.0, 0.0, 0.0))
    _shift(monkeypatch, True)
    point = vp.world_point_at(*_pixel(vp, (*cursor, 0.0)))
    assert point[:2] == pytest.approx(corner, abs=0.05)


def test_shift_squares_a_rectangle_and_a_box_s_base(top, monkeypatch):
    win, vp = top
    _shift(monkeypatch, True)
    win.processor.run("rectangle")
    win.processor.provide((0.0, 0.0, 0.0))
    win.processor.provide(vp.world_point_at(*_pixel(vp, (9.0, -3.0, 0.0))))
    rect = win.scene.all()[-1]
    assert _size(rect.shape) == pytest.approx((9.0, 9.0), abs=0.05)

    win.processor.run("box")
    win.processor.provide((20.0, 0.0, 0.0))
    win.processor.provide(vp.world_point_at(*_pixel(vp, (24.0, 7.0, 0.0))))
    win.processor.provide_text("5")
    box = win.scene.all()[-1]
    assert box.kind == "solid"
    assert _size(box.shape) == pytest.approx((7.0, 7.0), abs=0.05)


def test_a_frame_from_its_middle_squares_about_the_middle(top, monkeypatch):
    win, vp = top
    _shift(monkeypatch, True)
    win.processor.run("rectangle")
    win.processor.provide_text("Center")
    win.processor.provide((0.0, 0.0, 0.0))
    win.processor.provide(vp.world_point_at(*_pixel(vp, (2.0, 5.0, 0.0))))
    assert _size(win.scene.all()[-1].shape) == pytest.approx((10.0, 10.0),
                                                             abs=0.05)


def test_ortho_left_on_squares_frames_and_shift_lets_go(top, monkeypatch):
    win, vp = top
    vp.ortho = True
    win.processor.run("clippingplane")
    win.processor.provide((0.0, 0.0, 0.0))
    _shift(monkeypatch, False)
    assert vp.world_point_at(*_pixel(vp, (10.0, 4.0, 0.0)))[:2] == \
        pytest.approx((10.0, 10.0), abs=0.05)
    _shift(monkeypatch, True)
    assert vp.world_point_at(*_pixel(vp, (10.0, 4.0, 0.0)))[:2] == \
        pytest.approx((10.0, 4.0), abs=0.05)


def test_a_line_still_goes_square_to_the_axes(top, monkeypatch):
    """Only a frame is squared; a line under Shift keeps to an axis."""
    win, vp = top
    win.processor.run("clippingplane")
    win.processor.provide((0.0, 0.0, 0.0))
    win.processor.provide((6.0, 6.0, 0.0))
    win.processor.run("line")
    win.processor.provide((0.0, 0.0, 0.0))
    _shift(monkeypatch, True)
    assert vp.world_point_at(*_pixel(vp, (10.0, 4.0, 0.0)))[:2] == \
        pytest.approx((10.0, 0.0), abs=0.05)


def test_the_frame_is_let_go_when_the_command_ends(top, monkeypatch):
    win, vp = top
    win.processor.run("clippingplane")
    win.processor.provide((0.0, 0.0, 0.0))
    assert vp.point_frame
    win.processor.cancel()
    assert not vp.point_frame


def test_on_a_sheet_shift_squares_a_frame_too(paper_window, monkeypatch):
    """Paper has its own ortho, in paper millimetres, and the same fault."""
    win, _layout = paper_window
    vp = win.viewport
    lv = vp.layout_view
    vp.snaps.enabled = False
    vp.grid_snap = False
    vp.ortho = False
    win.processor.run("rectangle")
    win.processor.provide((40.0, 60.0, 0.0))
    assert vp.point_frame
    _shift(monkeypatch, True)
    assert vp.world_point_at(*lv.paper_to_screen(85.0, 67.0)) == \
        pytest.approx((85.0, 105.0, 0.0), abs=0.05)
    win.processor.run("line")
    win.processor.provide((40.0, 60.0, 0.0))
    assert vp.world_point_at(*lv.paper_to_screen(85.0, 67.0)) == \
        pytest.approx((85.0, 60.0, 0.0), abs=0.05), \
        "a line on paper no longer keeps to an axis"
