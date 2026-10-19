"""Fillet, the way Rhino asks it.

Run it and the prompt says "Select first curve", with Radius and Trim
beside it. Both stay there, and both can be changed without answering
the prompt: type a number and that is the radius, type t and Trim flips,
and the question still stands. Click the first curve near the corner you
mean, click the second near the same corner, and the fillet is made.

Nothing else is asked, because nothing else has to be: the corner is
where the clicks are, which also says which side of a crossing to keep,
and the radius and Trim are already on the prompt.

Radius 0 is Rhino's sharp corner: the curves are cut back, or carried
out, to the point they cross at, with no arc between them.
"""

from __future__ import annotations

import math

import pytest

from serpentine3d.core import geometry as g


def _two_lines(scene, gap=0.0):
    """A horizontal and a vertical line meeting at (10, 0), or not."""
    a = scene.add(g.make_line((0.0, 0.0, 0.0), (10.0 + gap, 0.0, 0.0)),
                  name="Across")
    b = scene.add(g.make_line((10.0, 0.0 - gap, 0.0), (10.0, 10.0, 0.0)),
                  name="Up")
    return a, b


def _curves(scene):
    return [o for o in scene.all() if o.kind == "curve"]


def _length(scene):
    return sum(g.curve_length(o.shape) for o in _curves(scene))


# -- what the prompt offers ------------------------------------------------

def test_it_opens_on_the_first_curve_with_radius_and_trim(env):
    scene, _sel, _hist, _ctx, proc = env
    _two_lines(scene)

    proc.run("fillet")

    assert "first curve" in proc.request.prompt.lower()
    assert dict(proc.option_chips()) == {"Radius": "0", "Trim": "Yes"}


def test_a_typed_number_is_the_radius_and_the_question_stands(env):
    scene, _sel, _hist, _ctx, proc = env
    _two_lines(scene)
    proc.run("fillet")

    proc.provide_text("2.5")

    assert dict(proc.option_chips())["Radius"] == "2.5"
    assert "first curve" in proc.request.prompt.lower(), \
        "a radius is not an answer to which curve was meant"


def test_t_flips_trim_and_the_question_stands(env):
    scene, _sel, _hist, _ctx, proc = env
    _two_lines(scene)
    proc.run("fillet")

    proc.provide_text("t")

    assert dict(proc.option_chips())["Trim"] == "No"
    assert "first curve" in proc.request.prompt.lower()


def test_both_are_still_there_at_the_second_curve(env):
    scene, _sel, _hist, _ctx, proc = env
    a, _b = _two_lines(scene)
    proc.run("fillet")
    proc.click_object(a.id, at=(9.0, 0.0, 0.0))

    assert "second curve" in proc.request.prompt.lower()
    assert sorted(dict(proc.option_chips())) == ["Radius", "Trim"]

    proc.provide_text("3")
    assert dict(proc.option_chips())["Radius"] == "3"
    assert "second curve" in proc.request.prompt.lower()


# -- and what the second click makes ---------------------------------------

def test_the_fillet_is_made_on_the_second_click(env):
    scene, _sel, _hist, _ctx, proc = env
    a, b = _two_lines(scene)
    proc.run("fillet")
    proc.provide_text("2")
    proc.click_object(a.id, at=(9.0, 0.0, 0.0))
    proc.click_object(b.id, at=(10.0, 1.0, 0.0))

    assert not proc.busy, "it asked for something after the second curve"
    curves = _curves(scene)
    assert len(curves) == 1, "trimmed and joined, as it always did"
    # two legs of 8, plus a quarter circle of radius 2
    assert g.curve_length(curves[0].shape) == pytest.approx(
        16 + math.pi, rel=1e-3)


def test_radius_zero_makes_a_sharp_corner(env):
    scene, _sel, _hist, _ctx, proc = env
    a, b = _two_lines(scene, gap=5.0)      # neither reaches the corner
    proc.run("fillet")
    proc.click_object(a.id, at=(2.0, 0.0, 0.0))
    proc.click_object(b.id, at=(10.0, 5.0, 0.0))

    curves = _curves(scene)
    assert len(curves) == 1
    # carried out to (10, 0): ten across and ten up, no arc
    assert g.curve_length(curves[0].shape) == pytest.approx(20.0, rel=1e-6)


def test_a_crossing_keeps_the_sides_that_were_clicked(env):
    scene, _sel, _hist, _ctx, proc = env
    a = scene.add(g.make_line((-10.0, 0.0, 0.0), (10.0, 0.0, 0.0)))
    b = scene.add(g.make_line((0.0, -10.0, 0.0), (0.0, 10.0, 0.0)))
    proc.run("fillet")
    proc.click_object(a.id, at=(-8.0, 0.0, 0.0))
    proc.click_object(b.id, at=(0.0, -8.0, 0.0))

    assert _length(scene) == pytest.approx(20.0, rel=1e-6), \
        "the two halves that were clicked, cut at the crossing"


def test_trim_no_leaves_the_curves_and_adds_the_arc(env):
    scene, _sel, _hist, _ctx, proc = env
    a, b = _two_lines(scene)
    proc.run("fillet")
    proc.provide_text("2")
    proc.provide_text("t")
    proc.click_object(a.id, at=(9.0, 0.0, 0.0))
    proc.click_object(b.id, at=(10.0, 1.0, 0.0))

    curves = _curves(scene)
    assert len(curves) == 3, "both curves kept, the arc added"
    assert scene.get(a.id) is not None and scene.get(b.id) is not None
    arc = next(o for o in curves if o.id not in (a.id, b.id))
    assert g.curve_length(arc.shape) == pytest.approx(math.pi, rel=1e-3)


def test_trim_no_at_radius_zero_says_there_is_nothing_to_make(env):
    scene, _sel, _hist, ctx, proc = env
    said = []
    ctx.add_echo_listener(said.append)
    a, b = _two_lines(scene)
    proc.run("fillet")
    proc.provide_text("t")
    proc.click_object(a.id, at=(9.0, 0.0, 0.0))
    proc.click_object(b.id, at=(10.0, 1.0, 0.0))

    assert len(_curves(scene)) == 2, "nothing was made, nothing was cut"
    assert any("leaves the curves as they are" in m for m in said), said


# -- and what it remembers -------------------------------------------------

@pytest.fixture(autouse=True)
def _forget_between_tests():
    """Each test starts where a fresh program would."""
    from serpentine3d.commands import edit
    was = dict(edit._FILLET_STICKY)
    edit._FILLET_STICKY.update({"Radius": "0", "Trim": "Yes"})
    yield
    edit._FILLET_STICKY.update(was)


def test_the_radius_is_what_the_next_fillet_opens_on(env):
    """Typed once and it stays, as Rhino keeps a command's options: the
    second corner of a drawing is usually the same size as the first."""
    scene, _sel, _hist, _ctx, proc = env
    a, b = _two_lines(scene)
    proc.run("fillet")
    proc.provide_text("2")
    proc.click_object(a.id, at=(9.0, 0.0, 0.0))
    proc.click_object(b.id, at=(10.0, 1.0, 0.0))

    c = scene.add(g.make_line((0.0, 20.0, 0.0), (10.0, 20.0, 0.0)))
    d = scene.add(g.make_line((10.0, 20.0, 0.0), (10.0, 30.0, 0.0)))
    proc.run("fillet")

    assert dict(proc.option_chips())["Radius"] == "2"
    proc.click_object(c.id, at=(9.0, 20.0, 0.0))
    proc.click_object(d.id, at=(10.0, 21.0, 0.0))
    made = next(o for o in _curves(scene) if o.id == c.id)
    assert g.curve_length(made.shape) == pytest.approx(16 + math.pi, rel=1e-3)


def test_trim_is_remembered_the_same_way(env):
    scene, _sel, _hist, _ctx, proc = env
    a, b = _two_lines(scene)
    proc.run("fillet")
    proc.provide_text("2")
    proc.provide_text("t")
    proc.click_object(a.id, at=(9.0, 0.0, 0.0))
    proc.click_object(b.id, at=(10.0, 1.0, 0.0))

    proc.run("fillet")

    assert dict(proc.option_chips())["Trim"] == "No"


def test_a_fresh_start_is_a_sharp_trimming_corner_again(env):
    """What the module holds dies with the program, which is the whole
    of "until it is started again"."""
    from serpentine3d.commands import edit

    scene, _sel, _hist, _ctx, proc = env
    edit._FILLET_STICKY.update({"Radius": "7", "Trim": "No"})
    edit._FILLET_STICKY.update({"Radius": "0", "Trim": "Yes"})  # a restart
    _two_lines(scene)
    proc.run("fillet")

    assert dict(proc.option_chips()) == {"Radius": "0", "Trim": "Yes"}


# -- without a click to read -----------------------------------------------

def test_curves_named_rather_than_clicked_take_the_nearest_corner(env):
    """Typed, scripted or chosen from a list: no click to read a corner
    off, so the ends that lie nearest each other are the corner meant."""
    scene, _sel, _hist, _ctx, proc = env
    scene.add(g.make_line((0.0, 0.0, 0.0), (10.0, 0.0, 0.0)), name="Across")
    scene.add(g.make_line((10.0, 0.0, 0.0), (10.0, 10.0, 0.0)), name="Up")
    proc.run("fillet")
    proc.provide_text("2")
    proc.provide_text("Across")
    proc.provide_text("Up")

    curves = _curves(scene)
    assert len(curves) == 1
    assert g.curve_length(curves[0].shape) == pytest.approx(
        16 + math.pi, rel=1e-3)
