"""A clipping plane cuts only the view it was drawn in, until another view
is ticked on for it in Properties. A plane from an older file, which keeps
the views it is off in, still cuts every other view."""

from __future__ import annotations

from serpentine3d.core import clipping


def _draw_in(env, view):
    from tests.conftest import StubViewport
    scene, _sel, _h, ctx, proc = env
    ctx.viewport = StubViewport("model")
    ctx.viewport.clip_view = lambda: view
    proc.run("clippingplane")
    proc.provide_text("-5,-5,0")
    proc.provide_text("5,5,0")
    assert not proc.busy
    return [o for o in scene.all() if o.clip_plane][-1]


def test_a_plane_drawn_in_top_cuts_top_alone(env):
    plane = _draw_in(env, "top")

    assert clipping.cuts(plane.clip_plane, "top")
    assert not clipping.cuts(plane.clip_plane, "perspective")
    assert not clipping.cuts(plane.clip_plane, "a-new-pane")


def test_ticking_another_view_on_cuts_it_too_and_off_again(env):
    scene = env[0]
    plane = _draw_in(env, "top")

    clipping.switch(scene, plane.id, "perspective", True)
    assert clipping.cuts(scene.get(plane.id).clip_plane, "perspective")

    clipping.switch(scene, plane.id, "top", False)
    setting = scene.get(plane.id).clip_plane
    assert setting["on_in"] == ["perspective"]
    assert not clipping.cuts(setting, "top")


def test_a_copied_view_is_cut_as_the_one_it_was_copied_from(env):
    scene = env[0]
    plane = _draw_in(env, "d1")

    clipping.carry_views(scene, [("d1", "d2"), ("d3", "d4")])

    assert scene.get(plane.id).clip_plane["on_in"] == ["d1", "d2"]


def test_a_plane_from_an_older_file_still_cuts_every_other_view():
    old = {"enabled": True, "off_in": ["top"]}

    assert clipping.cuts(old, "perspective")
    assert clipping.cuts(old, "a-new-pane")
    assert not clipping.cuts(old, "top")
