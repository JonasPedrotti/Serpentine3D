"""Plane corner to corner, Plane from 3 points and a surface from corners."""

import pytest

import serpentine3d.commands  # registers all commands  # noqa: F401
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


@pytest.fixture
def env():
    scene = Scene()
    ctx = CommandContext(scene, SelectionManager(scene), History(scene))
    return scene, CommandProcessor(ctx)


def _run(proc, command, *answers):
    proc.run(command)
    for a in answers:
        proc.provide_text(a)
    assert not proc.busy


def _only(scene):
    objs = scene.all()
    assert len(objs) == 1
    return objs[0]


def _box_of(obj):
    lo, hi = g.bbox(obj.shape)
    return tuple(round(v, 6) for v in lo), tuple(round(v, 6) for v in hi)


def test_a_plane_corner_to_corner(env):
    scene, proc = env
    _run(proc, "plane", "0,0,0", "10,5,0")
    obj = _only(scene)
    assert obj.kind == "surface"
    assert g.surface_area(obj.shape) == pytest.approx(50)
    assert _box_of(obj) == ((0, 0, 0), (10, 5, 0))


def test_a_plane_with_no_width_is_not_made(env):
    scene, proc = env
    _run(proc, "plane", "0,0,0", "10,0,0")
    assert scene.all() == []


@pytest.mark.parametrize("command", [("plane", "3Points"), ("plane3pt",)])
def test_a_third_point_above_an_end_stands_the_plane_up(env, command):
    scene, proc = env
    _run(proc, *command, "0,0,0", "10,0,0", "10,0,4")
    obj = _only(scene)
    assert g.surface_area(obj.shape) == pytest.approx(40)
    assert _box_of(obj) == ((0, 0, 0), (10, 0, 4))


def test_the_third_point_counts_only_square_off_the_edge(env):
    scene, proc = env
    _run(proc, "plane3pt", "0,0,0", "10,0,0", "25,3,0")
    assert _box_of(_only(scene)) == ((0, 0, 0), (10, 3, 0))


def test_four_corners_make_a_surface_through_them_all(env):
    scene, proc = env
    _run(proc, "srfpt", "0,0,0", "10,0,0", "10,10,5", "0,10,0")
    obj = _only(scene)
    assert obj.kind == "surface"
    assert _box_of(obj) == ((0, 0, 0), (10, 10, 5))


def test_enter_after_three_corners_makes_a_triangle(env):
    scene, proc = env
    _run(proc, "srfpt", "0,0,0", "10,0,0", "0,10,0", "")
    assert g.surface_area(_only(scene).shape) == pytest.approx(50)


def test_corners_in_a_line_make_nothing(env):
    scene, proc = env
    _run(proc, "srfpt", "0,0,0", "5,0,0", "10,0,0", "")
    assert scene.all() == []


def test_the_edge_stays_drawn_and_both_ends_snap_for_the_third_point(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from serpentine3d.app import MainWindow
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_NO_RECOVER", "1")
    win = MainWindow()
    try:
        win.run_command("plane3pt")
        win.processor.provide_text("0,0,0")
        win.processor.provide_text("10,0,0")
        QApplication.processEvents()
        vp = win.viewport
        offered = {p for p, _kind in vp.snaps._pending_candidates(
            vp.pending_points, vp.picked_points)}
        assert {(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)} <= offered
        req = win.processor.request
        assert [tuple(p) for p in req.rubber_pts] == [
            (0.0, 0.0, 0.0), (10.0, 0.0, 0.0)], "the first point went"
    finally:
        win.processor.cancel()
        win.mark_saved()
        win.close()
