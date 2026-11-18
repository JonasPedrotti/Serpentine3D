"""Extrude takes surfaces as well as curves and grows them into solids."""

import pytest

from serpentine3d.core import geometry as g


def _square(z=0.0):
    return g.corner_surface([(0, 0, z), (10, 0, z), (10, 10, z), (0, 10, z)])


def test_a_flat_surface_extrudes_into_a_closed_solid(env):
    scene, _sel, _hist, _ctx, proc = env
    srf = scene.add(_square())

    proc.run("extrude")
    proc.click_object(srf.id)
    proc.finish_selection()
    proc.provide_text("5")

    solids = [o for o in scene.all() if o.kind == "solid"]
    assert len(solids) == 1
    assert g.volume(solids[0].shape) == pytest.approx(500, rel=1e-6)
    assert g.is_valid(solids[0].shape)
    assert scene.get(srf.id) is not None


def test_a_standing_surface_grows_along_its_own_normal(env):
    scene, _sel, _hist, _ctx, proc = env
    srf = scene.add(g.corner_surface(
        [(0, 0, 0), (10, 0, 0), (10, 0, 10), (0, 0, 10)]))

    proc.run("extrude")
    proc.click_object(srf.id)
    proc.finish_selection()
    proc.provide_text("4")

    solid = next(o for o in scene.all() if o.kind == "solid")
    assert g.volume(solid.shape) == pytest.approx(400, rel=1e-6)
    lo, hi = g.bbox(solid.shape)
    assert hi[1] - lo[1] == pytest.approx(4, abs=1e-6)
    assert hi[2] - lo[2] == pytest.approx(10, abs=1e-6)


def test_curves_and_surfaces_extrude_together_and_follow_history(env):
    scene, _sel, _hist, _ctx, proc = env
    scene.record_history = True
    srf = scene.add(_square())
    line = scene.add(g.make_line((20, 0, 0), (30, 0, 0)))

    proc.run("extrude")
    proc.click_object(srf.id)
    proc.click_object(line.id)
    proc.finish_selection()
    proc.provide_text("3")

    kinds = sorted(o.kind for o in scene.all()
                   if o.id not in (srf.id, line.id))
    assert kinds == ["solid", "surface"]
    solid = next(o for o in scene.all() if o.kind == "solid")
    scene.replace_shape(srf.id, g.corner_surface(
        [(0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)]))
    assert g.volume(scene.get(solid.id).shape) == pytest.approx(600,
                                                                rel=1e-6)


def test_keep_original_no_removes_what_was_extruded(env):
    scene, _sel, _hist, _ctx, proc = env
    srf = scene.add(_square())
    circle = scene.add(g.make_circle((30, 0, 0), 2))

    proc.run("extrude")
    proc.click_object(srf.id)
    proc.click_object(circle.id)
    proc.finish_selection()
    assert dict(proc.option_chips())["KeepOriginal"] == "Yes"
    proc.provide_text("KeepOriginal=No")
    proc.provide_text("5")

    assert scene.get(srf.id) is None and scene.get(circle.id) is None
    assert sorted(o.kind for o in scene.all()) == ["solid", "solid"]


def test_the_preview_is_capped_when_cap_is_on(env):
    scene, _sel, _hist, _ctx, proc = env
    circle = scene.add(g.make_circle((0, 0, 0), 5))

    proc.run("extrude")
    proc.click_object(circle.id)
    proc.finish_selection()
    ghost = proc.request.preview_fn((0, 0, 10))
    assert g.volume(ghost) == pytest.approx(250 * 3.141592653589793,
                                            rel=1e-4)
    proc.provide_text("Cap=No")
    ghost = proc.request.preview_fn((0, 0, 10))
    assert g.shape_kind(ghost) == "surface"
