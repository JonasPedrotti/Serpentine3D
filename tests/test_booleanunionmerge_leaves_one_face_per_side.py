"""Union two boxes side by side and the spanning sides stay split in two;
booleanunionmerge (right-click on Union) fuses them so the box has six faces."""

from __future__ import annotations

from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


def _run(command):
    scene = Scene()
    sel = SelectionManager(scene)
    proc = CommandProcessor(CommandContext(scene, sel, History(scene)))
    a = scene.add(g.make_box((0.0, 0.0, 0.0), 10.0, 10.0, 10.0))
    b = scene.add(g.make_box((10.0, 0.0, 0.0), 10.0, 10.0, 10.0))
    sel.set([a.id, b.id])
    proc.run(command)
    objs = scene.all()
    assert len(objs) == 1
    return objs[0].shape


def test_plain_union_keeps_the_seam():
    assert len(g.faces_of(_run("booleanunion"))) > 6


def test_union_merge_gives_a_clean_box():
    shape = _run("booleanunionmerge")
    assert len(g.faces_of(shape)) == 6
    assert abs(g.volume(shape) - 2000.0) < 1e-6
