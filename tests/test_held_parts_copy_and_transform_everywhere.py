"""Every held part of a surface or solid takes every transform, near the
origin or far from it, and a copy of a held part is an object of its own:
a face a surface, faces of one object a polysurface, an edge a curve, a
corner a point."""

from __future__ import annotations

import math

import pytest

import serpentine3d.commands  # registers the commands  # noqa: F401
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager

FAR = [0.0, 100000.0]


@pytest.fixture
def env():
    scene = Scene()
    sel = SelectionManager(scene)
    ctx = CommandContext(scene, sel, History(scene))
    said = []
    ctx.add_echo_listener(said.append)
    return scene, sel, CommandProcessor(ctx), said


def _box(scene, off):
    return scene.add(g.make_box((off, off, 0), 10, 6, 10), name="Box")


def _face(shape, normal):
    for i, f in enumerate(g.faces_of(shape)):
        n = g.face_point_normal(f)[1]
        if all(abs(a - b) < 1e-9 for a, b in zip(n, normal)):
            return i
    raise AssertionError(normal)


def _corners(shape):
    return {tuple(round(c, 6) for c in p) for p in g.vertex_points(shape)}


def _copy(proc, frm, to):
    proc.run("copy")
    proc.provide(frm)
    proc.provide(to)
    proc.provide_text("")
    assert not proc.busy


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
def test_a_copied_face_is_a_surface_of_its_own(env, off):
    scene, sel, proc, said = env
    box = _box(scene, off)
    before = g.shape_to_bytes(box.shape)
    sel.toggle_subobject(box.id, "face", _face(box.shape, (0, 0, 1)))

    _copy(proc, (0, 0, 0), (0, 0, 5))

    new = [o for o in scene.all() if o.id != box.id]
    assert len(new) == 1 and new[0].kind == "surface"
    assert g.surface_area(new[0].shape) == pytest.approx(60.0)
    assert _corners(new[0].shape) == {(off + x, off + y, 15.0)
                                      for x in (0, 10) for y in (0, 6)}
    assert g.shape_to_bytes(scene.get(box.id).shape) == before
    assert sel.subobjects, "the face copied from stays held"


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
def test_copied_faces_of_one_object_are_one_polysurface(env, off):
    scene, sel, proc, _said = env
    box = _box(scene, off)
    sel.toggle_subobject(box.id, "face", _face(box.shape, (0, 0, 1)))
    sel.toggle_subobject(box.id, "face", _face(box.shape, (0, -1, 0)))

    _copy(proc, (0, 0, 0), (20, 0, 0))

    new = [o for o in scene.all() if o.id != box.id]
    assert len(new) == 1
    assert len(g.faces_of(new[0].shape)) == 2
    assert g.surface_area(new[0].shape) == pytest.approx(160.0)


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
def test_a_copied_edge_is_a_curve_and_a_copied_corner_a_point(env, off):
    scene, sel, proc, _said = env
    box = _box(scene, off)
    sel.toggle_subobject(box.id, "edge", 0)
    corner = g.vertex_points(box.shape)[0]
    sel.toggle_subobject(box.id, "vertex", 0)

    _copy(proc, (0, 0, 0), (0, 0, 30))

    kinds = sorted(o.kind for o in scene.all() if o.id != box.id)
    assert kinds == ["curve", "point"]
    point = next(o for o in scene.all() if o.kind == "point")
    assert g.point_coords(point.shape) == pytest.approx(
        (corner[0], corner[1], corner[2] + 30))


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
def test_a_copied_curved_face_is_a_surface_of_its_own(env, off):
    scene, sel, proc, _said = env
    cyl = scene.add(g.make_cylinder((off, off, 0), 5, 10), name="Cylinder")
    wall = next(i for i, f in enumerate(g.faces_of(cyl.shape))
                if abs(g.face_point_normal(f)[1][2]) < 0.5)
    sel.toggle_subobject(cyl.id, "face", wall)

    _copy(proc, (0, 0, 0), (30, 0, 0))

    new = [o for o in scene.all() if o.id != cyl.id]
    assert len(new) == 1 and new[0].kind == "surface"
    assert g.surface_area(new[0].shape) == pytest.approx(math.pi * 100, rel=1e-6)


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
@pytest.mark.parametrize("copy", ["No", "Yes"])
def test_orient_takes_a_held_face(env, off, copy):
    scene, sel, proc, _said = env
    box = _box(scene, off)
    sel.toggle_subobject(box.id, "face", _face(box.shape, (0, 0, 1)))

    proc.run("orient")
    if copy == "Yes":
        assert proc.set_option("Copy", "Yes")
    proc.provide((off, off, 10.0))
    proc.provide((off + 10, off, 10.0))
    proc.provide((off, off, 12.0))
    proc.provide((off + 10, off, 12.0))
    assert not proc.busy

    if copy == "Yes":
        new = [o for o in scene.all() if o.id != box.id]
        assert len(new) == 1 and new[0].kind == "surface"
        assert {p[2] for p in _corners(new[0].shape)} == {12.0}
        assert g.volume(scene.get(box.id).shape) == pytest.approx(600.0)
    else:
        assert len(scene.all()) == 1
        assert g.volume(scene.get(box.id).shape) == pytest.approx(720.0)


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
def test_mirror_with_copy_makes_the_held_face_a_surface_of_its_own(env, off):
    scene, sel, proc, _said = env
    box = _box(scene, off)
    sel.toggle_subobject(box.id, "face", _face(box.shape, (1, 0, 0)))

    proc.run("mirror")
    assert proc.set_option("Copy", "Yes")
    proc.provide((off + 20, off, 0.0))
    proc.provide((off + 20, off + 10, 0.0))
    assert not proc.busy

    new = [o for o in scene.all() if o.id != box.id]
    assert len(new) == 1 and new[0].kind == "surface"
    assert {p[0] for p in _corners(new[0].shape)} == {off + 30.0}
    assert g.volume(scene.get(box.id).shape) == pytest.approx(600.0)


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
def test_setpt_takes_a_held_corner(env, off):
    scene, sel, proc, _said = env
    box = _box(scene, off)
    corners = g.vertex_points(box.shape)
    top = max(range(len(corners)), key=lambda i: (corners[i][2], corners[i][0],
                                                  corners[i][1]))
    x, y, _z = corners[top]
    sel.toggle_subobject(box.id, "vertex", top)

    proc.run("setpt")
    proc.provide((0.0, 0.0, 14.0))
    assert not proc.busy

    shape = scene.get(box.id).shape
    assert g.is_valid(shape) and g.shape_kind(shape) == "solid"
    assert (round(x, 6), round(y, 6), 14.0) in _corners(shape)
    assert sum(1 for p in _corners(shape) if p[2] == 10.0) == 3


def _vaulted(off):
    arc = g.make_arc_3pt((off, off, 10), (off + 5, off, 13), (off + 10, off, 10))
    walls = g.make_polyline([(off + 10, off, 10), (off + 10, off, 0),
                             (off, off, 0), (off, off, 10)])
    return g.extrude(g.join_curves([arc, walls]), (0, 1, 0), 6, cap=True)


def _twisted(off):
    """A block whose top is a curved (twisted) face on straight edges."""
    lo = [(off, off, 0), (off + 10, off, 0), (off + 10, off + 6, 0),
          (off, off + 6, 0)]
    hi = [(off, off, 10), (off + 10, off, 12), (off + 10, off + 6, 10),
          (off, off + 6, 12)]
    faces = [g.planar_face(g.make_polyline(lo, closed=True)),
             g.corner_surface(hi)]
    for i in range(4):
        j = (i + 1) % 4
        faces.append(g.planar_face(g.make_polyline(
            [lo[i], lo[j], hi[j], hi[i]], closed=True)))
    return g.join_surfaces(faces)


def _top_of(shape):
    faces = g.faces_of(shape)
    return max(range(len(faces)), key=lambda i: g.centroid(faces[i])[2])


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
@pytest.mark.parametrize("build,command,answers", [
    (_vaulted, "move", [(0.0, 0.0, 0.0), (1.0, 0.0, 2.0)]),
    (_twisted, "move", [(0.0, 0.0, 0.0), (1.0, 0.0, 2.0)]),
    (_twisted, "rotate", [(5.0, 3.0, 11.0), 5.0]),
    (_twisted, "scale", [(5.0, 3.0, 11.0), 0.8]),
], ids=["vault-move", "twisted-move", "twisted-rotate", "twisted-scale"])
def test_a_curved_face_of_a_polysurface_takes_transforms(env, off, build,
                                                          command, answers):
    scene, sel, proc, _said = env
    obj = scene.add(build(off), name="Curved")
    assert g.shape_kind(obj.shape) == "solid"
    sel.toggle_subobject(obj.id, "face", _top_of(obj.shape))
    before = g.volume(obj.shape)

    proc.run(command)
    for a in answers:
        if isinstance(a, tuple) and command != "move":
            a = (a[0] + off, a[1] + off, a[2])
        proc.provide(a)
    assert not proc.busy

    shape = scene.get(obj.id).shape
    assert g.is_valid(shape) and g.shape_kind(shape) == "solid"
    assert g.volume(shape) != pytest.approx(before)
    assert min(p[2] for p in _corners(shape)) == pytest.approx(0.0)
