"""Align lines up the picked objects on the view's plane, the way a layout
program does: edges or middles to the bounds of the pick, or spaced evenly
with the first and the last left where they are. Two bars at the bottom
right of the view do it with a click while two or more are picked."""

import pytest
from PySide6.QtWidgets import QApplication

import serpentine3d.commands  # registers all commands  # noqa: F401
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


def _boxes():
    scene = Scene()
    sel = SelectionManager(scene)
    proc = CommandProcessor(CommandContext(scene, sel, History(scene)))
    objs = [scene.add(g.make_box(c, w, h, 1)) for c, w, h in
            (((0, 0, 0), 2, 2), ((5, 3, 0), 4, 1), ((14, 7, 0), 2, 3))]
    sel.set([o.id for o in objs])
    return scene, proc, objs


def _box(scene, o):
    lo, hi = g.bbox(scene.get(o.id).shape)
    return tuple(round(v, 6) for v in (lo[0], lo[1], hi[0], hi[1]))


@pytest.mark.parametrize(("how", "expect"), [
    ("left", [0, 0, 0]),
    ("right", [14, 12, 14]),
    ("center", [7, 6, 7]),
])
def test_across_the_view(how, expect):
    scene, proc, objs = _boxes()
    proc.run(f"align {how}")
    assert not proc.busy
    assert [_box(scene, o)[0] for o in objs] == expect
    assert [_box(scene, o)[1] for o in objs] == [0, 3, 7], "up and down kept"


@pytest.mark.parametrize(("how", "expect"), [
    ("top", [8, 9, 7]),
    ("bottom", [0, 0, 0]),
    ("middle", [4, 4.5, 3.5]),
])
def test_up_and_down_the_view(how, expect):
    scene, proc, objs = _boxes()
    proc.run(f"align {how}")
    assert [_box(scene, o)[1] for o in objs] == expect
    assert [_box(scene, o)[0] for o in objs] == [0, 5, 14], "across kept"


def test_spacing_evenly_leaves_the_ends_and_evens_the_gaps():
    scene, proc, objs = _boxes()
    proc.run("align across")
    xs = [_box(scene, o) for o in objs]
    assert xs[0][0] == 0 and xs[2][2] == 16
    assert xs[1][0] - xs[0][2] == pytest.approx(xs[2][0] - xs[1][2])


def test_it_works_on_the_views_own_plane():
    from serpentine3d.core.cplane import CPlane
    scene, proc, objs = _boxes()
    front = CPlane(origin=(0, 0, 0), normal=(0, -1, 0), xdir=(1, 0, 0))
    proc.ctx.replay_cplane = front
    proc.run("align top")
    tops = [g.bbox(scene.get(o.id).shape)[1][2] for o in objs]
    assert tops == pytest.approx([1, 1, 1], abs=1e-6), "top is up the view, here z"


def test_the_bars_show_for_two_or_more_and_align_on_a_click(tmp_path,
                                                            monkeypatch):
    from serpentine3d.app import MainWindow
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_NO_RECOVER", "1")
    win = MainWindow()
    win.resize(1200, 800)
    win.show()
    QApplication.processEvents()
    try:
        vp = win.viewport
        a = win.scene.add(g.make_box((0, 0, 0), 2, 2, 1))
        b = win.scene.add(g.make_box((5, 3, 0), 4, 1, 1))
        win.selection.set([a.id])
        assert not vp.align_bars.row.isVisible()
        win.selection.set([a.id, b.id])
        bars = vp.align_bars
        assert bars.row.isVisible() and bars.column.isVisible()
        assert not bars.row.buttons["across"].isEnabled(), "needs three"
        bars.row.buttons["left"].click()
        assert g.bbox(win.scene.get(b.id).shape)[0][0] == pytest.approx(0, abs=1e-6)
        assert sorted(win.selection.ids) == sorted([a.id, b.id])
    finally:
        win.processor.cancel()
        win.mark_saved()
        win.close()
