"""Split cuts a curve at picked points, and trim takes a curve that only
touches the cutter away whole."""

from __future__ import annotations

import pytest

import serpentine3d.commands  # registers the commands  # noqa: F401
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


@pytest.fixture
def env():
    scene = Scene()
    selection = SelectionManager(scene)
    ctx = CommandContext(scene, selection, History(scene))
    return scene, CommandProcessor(ctx)


def _lengths(objs):
    return sorted(g.curve_length(o.shape) for o in objs)


def test_points_land_on_the_curve_they_split():
    pieces = g.split_curve_at_points(
        g.make_line((0, 0, 0), (10, 0, 0)), [(3, 1, 0), (7, -2, 0)])

    assert sorted(g.curve_length(p) for p in pieces) == pytest.approx(
        [3, 3, 4], abs=1e-6)


def test_split_with_points_cuts_where_the_points_were_picked(env):
    scene, proc = env
    line = scene.add(g.make_line((0, 0, 0), (10, 0, 0)))

    proc.run("splitpoints")
    proc.click_object(line.id)
    proc.provide_text("4,0,0")
    proc.provide_text("")

    assert not proc.busy
    assert _lengths(scene.all()) == pytest.approx([4, 6], abs=1e-6)


def test_points_at_the_cutter_prompt_goes_straight_to_picking_points(env):
    scene, proc = env
    line = scene.add(g.make_line((0, 0, 0), (10, 0, 0)))

    proc.run("split")
    proc.click_object(line.id)
    assert "Points" in proc.keyword_chips()
    proc.provide_text("Points")
    proc.provide_text("2,0,0")
    proc.provide_text("")

    assert _lengths(scene.all()) == pytest.approx([2, 8], abs=1e-6)


def test_the_pieces_of_a_split_are_left_selected(env):
    scene, proc = env
    line = scene.add(g.make_line((0, 0, 0), (10, 0, 0)))

    proc.run("splitpoints")
    proc.click_object(line.id)
    proc.provide_text("5,0,0")
    proc.provide_text("")

    assert set(proc.ctx.selection.ids) == {o.id for o in scene.all()}


def test_split_still_takes_cutters(env):
    scene, proc = env
    line = scene.add(g.make_line((0, 0, 0), (10, 0, 0)))
    cutter = scene.add(g.make_line((5, -3, 0), (5, 3, 0)))

    proc.run("split")
    proc.click_object(line.id)
    proc.click_object(cutter.id)
    proc.finish_selection()

    assert _lengths(o for o in scene.all() if o.id != cutter.id) == \
        pytest.approx([5, 5], abs=1e-6)


def test_trim_takes_away_a_curve_that_only_touches_the_cutter(env):
    scene, proc = env
    cutter = scene.add(g.make_line((0, 0, 0), (10, 0, 0)))
    touching = scene.add(g.make_line((5, 0, 0), (5, 4, 0)))

    proc.run("trim")
    proc.click_object(cutter.id)
    proc.finish_selection()
    proc.click_object(touching.id, at=(5, 2, 0))
    proc.finish_selection()

    assert [o.id for o in scene.all()] == [cutter.id]


def test_trim_leaves_a_curve_that_does_not_reach_the_cutter(env):
    scene, proc = env
    cutter = scene.add(g.make_line((0, 0, 0), (10, 0, 0)))
    apart = scene.add(g.make_line((5, 1, 0), (5, 4, 0)))

    proc.run("trim")
    proc.click_object(cutter.id)
    proc.finish_selection()
    proc.click_object(apart.id, at=(5, 2, 0))

    assert {o.id for o in scene.all()} == {cutter.id, apart.id}
