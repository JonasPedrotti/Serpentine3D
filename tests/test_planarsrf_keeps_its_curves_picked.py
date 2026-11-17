"""PlanarSrf leaves the curves it was made from picked."""

import serpentine3d.commands  # registers all commands  # noqa: F401
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


def test_the_curves_are_still_picked_once_the_surface_is_made():
    scene = Scene()
    sel = SelectionManager(scene)
    proc = CommandProcessor(CommandContext(scene, sel, History(scene)))
    a = scene.add(g.make_rectangle((0, 0, 0), (5, 5, 0)))
    b = scene.add(g.make_rectangle((10, 0, 0), (15, 5, 0)))
    sel.set([a.id, b.id])
    proc.run("planarsrf")
    assert not proc.busy
    assert [o.kind for o in scene.all()].count("surface") == 2
    assert sorted(sel.ids) == sorted([a.id, b.id])
