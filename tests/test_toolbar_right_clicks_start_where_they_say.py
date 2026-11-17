"""Each right-click on the tool strip starts its command's other way in."""

import pytest

import serpentine3d.commands  # registers all commands  # noqa: F401
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


@pytest.mark.parametrize(("macro", "prompt"), [
    ("circle 3point", "First point on circle"),
    ("ellipse diameter", "Start of first axis"),
    ("rectangle 3point", "Start of edge"),
    ("arc endsfirst", "Start of arc"),
    ("rotate3d", "Select objects"),
    ("copy", "Select objects"),
    ("orient3pt", "Select objects to orient"),
])
def test_the_right_click_lands_on_its_first_pick(macro, prompt):
    scene = Scene()
    proc = CommandProcessor(
        CommandContext(scene, SelectionManager(scene), History(scene)))
    proc.run(macro)
    assert prompt in proc.prompt_text()
    proc.cancel()


def test_a_3_point_rectangle_keeps_its_edge_and_both_ends_snap(tmp_path,
                                                                monkeypatch):
    from PySide6.QtWidgets import QApplication
    from serpentine3d.app import MainWindow
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_NO_RECOVER", "1")
    win = MainWindow()
    try:
        win.run_command("rectangle 3point")
        win.processor.provide_text("0,0,0")
        win.processor.provide_text("10,0,0")
        QApplication.processEvents()
        req = win.processor.request
        assert [tuple(p) for p in req.rubber_pts] == [
            (0.0, 0.0, 0.0), (10.0, 0.0, 0.0)], "the first point went"
        vp = win.viewport
        offered = {p for p, _kind in vp.snaps._pending_candidates(
            vp.pending_points, vp.picked_points)}
        assert {(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)} <= offered
        win.processor.provide_text("0,5,0")
        assert not win.processor.busy and len(win.scene.all()) == 1
    finally:
        win.processor.cancel()
        win.mark_saved()
        win.close()


def test_a_3_point_rectangle_stands_up_off_a_point_above_an_end():
    from serpentine3d.core import geometry as g
    scene = Scene()
    proc = CommandProcessor(
        CommandContext(scene, SelectionManager(scene), History(scene)))
    proc.run("rectangle 3point")
    for p in ("0,0,0", "10,0,0", "10,0,4"):
        proc.provide_text(p)
    (obj,) = scene.all()
    lo, hi = g.bbox(obj.shape)
    assert tuple(round(v, 6) for v in lo) == (0, 0, 0)
    assert tuple(round(v, 6) for v in hi) == (10, 0, 4)


def test_an_ellipse_keeps_its_first_axis_where_it_was_clicked():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    scene = Scene()
    proc = CommandProcessor(
        CommandContext(scene, SelectionManager(scene), History(scene)))
    proc.run("ellipse")
    proc.provide_text("0,0,0")
    proc.provide_text("6,8,0")                  # 10 out, at a slant
    req = proc.request
    assert req.axis_lock is not None, "the second axis is held square"
    assert tuple(req.rubber_pts[-1]) == (0.0, 0.0, 0.0),         "the band runs from the center"
    proc.provide_text("-4,3,0")                 # 5 out, square to the first
    (obj,) = scene.all()

    def gap(p):
        v = BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex()
        return BRepExtrema_DistShapeShape(obj.shape, v).Value()

    assert gap((6.0, 8.0, 0.0)) < 1e-6, "it runs through the clicked point"
    assert gap((-4.0, 3.0, 0.0)) < 1e-6
