"""Click a curve and its control points are there to pick; click away and
they go. F10 keeps them on after the curve is let go, until Escape."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow
from serpentine3d.core import geometry as g

CORNERS = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0),
           (20.0, 10.0, 0.0)]


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_NO_RECOVER", "1")
    win = MainWindow()
    win.resize(1200, 800)
    win.show()
    QApplication.processEvents()
    yield win
    win.processor.cancel()
    win.mark_saved()
    win.close()
    QApplication.processEvents()


def _curve(win):
    obj = win.scene.add(g.make_polyline(CORNERS))
    vp = win.viewport
    vp.set_view("top")
    vp.zoom_extents()
    QApplication.processEvents()
    return obj, vp


def _click(vp, at, modifiers=Qt.KeyboardModifier.NoModifier):
    x, y, _depth = vp._eye().project(np.array([at], float),
                                     vp.width(), vp.height())[0]
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, modifiers,
                     QPoint(int(round(x)), int(round(y))))
    QApplication.processEvents()


EMPTY = (60.0, -40.0, 0.0)


def test_clicking_a_curve_shows_its_points_and_clicking_away_hides_them(win):
    obj, vp = _curve(win)
    _click(vp, (5.0, 0.0, 0.0))
    assert win.selection.ids == [obj.id]
    assert obj.id in vp.cv_enabled
    _click(vp, EMPTY)
    assert win.selection.ids == []
    assert obj.id not in vp.cv_enabled


def test_a_shown_point_can_be_picked_and_stays_shown(win):
    obj, vp = _curve(win)
    _click(vp, (5.0, 0.0, 0.0))
    _click(vp, CORNERS[1])
    assert win.selection.subobjects == [(obj.id, "cv", 1)]
    assert obj.id in vp.cv_enabled, "picking a point let go of the curve"
    _click(vp, EMPTY)
    assert obj.id not in vp.cv_enabled


def test_f10_keeps_the_points_after_the_curve_is_let_go_until_escape(win):
    obj, vp = _curve(win)
    _click(vp, (5.0, 0.0, 0.0))
    win.run_command("pointson")
    QApplication.processEvents()
    _click(vp, EMPTY)
    assert obj.id in vp.cv_enabled
    _click(vp, CORNERS[2])
    assert win.selection.subobjects == [(obj.id, "cv", 2)]
    win._cancel()
    assert not vp.cv_enabled


def test_escape_lets_go_of_a_picked_curve_and_its_points_at_once(win):
    obj, vp = _curve(win)
    _click(vp, (5.0, 0.0, 0.0))
    win._cancel()
    assert win.selection.ids == []
    assert not vp.cv_enabled


def test_escape_with_points_kept_hides_them_all_the_picked_curve_too(win):
    obj, vp = _curve(win)
    kept = win.scene.add(g.make_line((0, 20, 0), (10, 20, 0)))
    win.selection.set([kept.id])
    win.run_command("pointson")
    _click(vp, (5.0, 0.0, 0.0))
    assert vp.cv_enabled == {obj.id, kept.id}
    win._cancel()
    assert win.selection.ids == [obj.id]
    assert not vp.cv_enabled
    win.selection.set_held(True)          # any later notify leaves them off
    win.selection.set_held(False)
    assert not vp.cv_enabled


def test_curves_caught_in_a_window_show_no_points(win):
    obj, vp = _curve(win)
    other = win.scene.add(g.make_line((0, 5, 0), (10, 5, 0)))
    win._on_box_selected([obj.id, other.id], Qt.KeyboardModifier.NoModifier)
    assert set(win.selection.ids) == {obj.id, other.id}
    assert not vp.cv_enabled


def test_a_curve_clicked_then_widened_by_a_window_keeps_its_points(win):
    obj, vp = _curve(win)
    other = win.scene.add(g.make_line((0, 5, 0), (10, 5, 0)))
    _click(vp, (5.0, 0.0, 0.0))
    win._on_box_selected([other.id], Qt.KeyboardModifier.ShiftModifier)
    assert vp.cv_enabled == {obj.id}


def test_a_surface_picked_shows_no_points(win):
    box = win.scene.add(g.make_box((0, 0, 0), 5, 5, 5))
    win.selection.set([box.id])
    assert not win.viewport.cv_enabled


def test_a_select_all_of_many_curves_shows_no_points(win):
    ids = [win.scene.add(g.make_line((0, i, 0), (5, i, 0))).id
           for i in range(MainWindow.AUTO_POINTS_UP_TO + 1)]
    win.selection.set(ids)
    assert not win.viewport.cv_enabled
