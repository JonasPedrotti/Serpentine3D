"""Orient and Orient3pt number their reference points, draw no line from
the first one once the references are in, and leave the original alone
unless Copy is asked for."""

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
    sel = SelectionManager(scene)
    proc = CommandProcessor(CommandContext(scene, sel, History(scene)))
    line = scene.add(g.make_line((0, 0, 0), (5, 0, 0)))
    sel.set([line.id])
    return scene, proc


@pytest.mark.parametrize(("command", "refs"), [
    ("orient", ["0,0,0", "5,0,0"]),
    ("orient3pt", ["0,0,0", "5,0,0", "0,5,0"]),
])
def test_the_references_are_numbered_and_no_band_follows(env, command, refs):
    scene, proc = env
    proc.run(command)
    assert "Copy" in proc.request.choices
    for i, p in enumerate(refs):
        proc.provide_text(p)
        labels = [t for _p, t in proc.request.marks]
        assert labels == [str(n) for n in range(1, i + 2)]
    req = proc.request
    assert "First target" in req.prompt
    assert req.rubber_from is None and not req.rubber_pts, \
        "no line from the first reference to the mouse"
    assert req.preview_fn is not None


def test_copy_is_off_until_asked_for(env):
    scene, proc = env
    for p in ("0,0,0", "5,0,0", "10,10,0", "10,15,0"):
        if not proc.busy:
            proc.run("orient")
        proc.provide_text(p)
    assert not proc.busy
    assert len(scene.all()) == 1, "the original moved, no copy was left"
