"""SetPt levels Ctrl+Shift-held solid parts without moving unheld corners (#62)."""

import math

import pytest

from serpentine3d.commands.base import PointReq
from serpentine3d.core import geometry as g


BASE = [(0, 0, 0), (10, 0, 0), (10, 6, 0), (0, 6, 0)]
TOP = [(0, 0, 10), (10, 0, 10), (10, 6, 10), (0, 6, 10)]
SLOPED_TOP = [(0, 0, 8), (10, 0, 14), (10, 6, 14), (0, 6, 8)]
TARGET = (14.0, 9.0, 15.0)


def _key(point):
    return tuple(round(coordinate, 6) for coordinate in point)


def _corners(shape):
    return frozenset(_key(point) for edge in g.edges_of(shape)
                     for point in g.curve_endpoints(edge))


def _face_with(shape, corners):
    wanted = frozenset(_key(point) for point in corners)
    for index, face in enumerate(g.faces_of(shape)):
        if _corners(face) == wanted:
            return index
    raise AssertionError(f"No face has corners {wanted}")


def _edge_between(shape, a, b):
    for index, edge in enumerate(g.edges_of(shape)):
        p, q = g.curve_endpoints(edge)
        if ((math.dist(p, a) < 1e-6 and math.dist(q, b) < 1e-6)
                or (math.dist(p, b) < 1e-6 and math.dist(q, a) < 1e-6)):
            return index
    raise AssertionError(f"No edge connects {a} to {b}")


def _face_rings(bottom, top):
    return [bottom, top] + [
        [bottom[index], bottom[(index + 1) % 4],
         top[(index + 1) % 4], top[index]]
        for index in range(4)
    ]


def _assert_solid(scene, obj, bottom, top, volume):
    current = scene.get(obj.id)
    assert current is not None, "The solid keeps its scene object identity"
    assert current.kind == "solid"
    assert current.name == obj.name
    assert current.layer_id == obj.layer_id
    shape = current.shape
    assert g.shape_kind(shape) == "solid"
    assert g.is_valid(shape), "The neighboring faces must still form a valid solid"
    assert g.volume(shape) == pytest.approx(volume, abs=1e-6)

    faces = g.faces_of(shape)
    expected_faces = {frozenset(_key(point) for point in ring)
                      for ring in _face_rings(bottom, top)}
    assert len(faces) == len(expected_faces) == 6
    assert {_corners(face) for face in faces} == expected_faces, (
        "Every adjacent face meets the changed corners; unheld corners stay put")

    expected_pairs = [(ring[index], ring[(index + 1) % 4])
                      for ring in (bottom, top) for index in range(4)]
    expected_pairs += list(zip(bottom, top))
    edges = g.edges_of(shape)
    assert len(edges) == len(expected_pairs) == 12
    face_edges = [g.edges_of(face) for face in faces]
    for a, b in expected_pairs:
        edge = edges[_edge_between(shape, a, b)]
        assert g.curve_length(edge) == pytest.approx(math.dist(a, b), abs=1e-6)
        assert sum(any(edge.IsSame(boundary) for boundary in boundaries)
                   for boundaries in face_edges) == 2, (
            "Each edge is shared by its two neighbors, with no detached faces")


def _box(scene, name="Box"):
    obj = scene.add(g.make_box((0, 0, 0), 10, 6, 10), name=name)
    _assert_solid(scene, obj, BASE, TOP, 600)
    return obj


def _wedge(scene):
    section = g.make_polyline([BASE[0], BASE[1], SLOPED_TOP[1], SLOPED_TOP[0]],
                              closed=True)
    obj = scene.add(g.extrude(section, (0, 1, 0), 6, cap=True), name="Sloped roof")
    _assert_solid(scene, obj, BASE, SLOPED_TOP, 660)
    return obj


def _hold_top(selection, obj, mode, top=TOP):
    if mode in ("face", "face-and-rim"):
        selection.toggle_subobject(obj.id, "face", _face_with(obj.shape, top))
    if mode in ("rim", "face-and-rim", "opposite-rim"):
        indices = (0, 2) if mode == "opposite-rim" else range(4)
        for index in indices:
            selection.toggle_subobject(
                obj.id, "edge", _edge_between(obj.shape, top[index],
                                               top[(index + 1) % 4]))


def _start(proc):
    assert proc.run("setpt")
    assert isinstance(proc.request, PointReq), (
        "SetPt must use the held faces or solid edges and ask for the target; "
        f"it instead asks {getattr(proc.request, 'prompt', None)!r}")
    assert set(proc.request.choices) >= {"X", "Y", "Z"}
    for axis in "XYZ":
        assert set(proc.request.choices[axis]) == {"Yes", "No"}


def _setpt(proc, target=TARGET, options=None):
    _start(proc)
    for axis, value in (options or {}).items():
        assert proc.set_option(axis, value)
    proc.provide(tuple(float(coordinate) for coordinate in target))
    assert not proc.busy


@pytest.mark.parametrize("held", ["face", "rim", "face-and-rim"])
def test_held_solid_parts_go_straight_to_the_target_and_axis_choices(env, held):
    scene, selection, _history, _ctx, proc = env
    obj = _box(scene)
    _hold_top(selection, obj, held)

    _start(proc)

    assert proc.option("X", "No") == "No"
    assert proc.option("Y", "No") == "No"
    assert proc.option("Z", "Yes") == "Yes"


@pytest.mark.parametrize("held", ["face", "rim", "opposite-rim", "face-and-rim"])
def test_the_top_and_its_rim_are_set_once_and_the_bottom_stays_put(env, held):
    scene, selection, _history, _ctx, proc = env
    obj = _box(scene)
    other = scene.add(g.make_box((40, 20, 2), 10, 6, 10), name="Unheld solid")
    other_bottom = [(x + 40, y + 20, z + 2) for x, y, z in BASE]
    other_top = [(x + 40, y + 20, z + 2) for x, y, z in TOP]
    _hold_top(selection, obj, held)

    _setpt(proc, target=(91.0, -37.0, 15.0))

    _assert_solid(scene, obj, BASE, [(x, y, 15) for x, y, _z in TOP], 900)
    _assert_solid(scene, other, other_bottom, other_top, 600)
    assert {item.id for item in scene.all()} == {obj.id, other.id}


@pytest.mark.parametrize("held", ["face", "rim"])
def test_a_sloped_top_is_leveled_to_one_z_rather_than_translated(env, held):
    scene, selection, _history, _ctx, proc = env
    obj = _wedge(scene)
    _hold_top(selection, obj, held, SLOPED_TOP)

    _setpt(proc)

    _assert_solid(scene, obj, BASE,
                  [(x, y, 15) for x, y, _z in SLOPED_TOP], 900)
    assert {item.id for item in scene.all()} == {obj.id}


@pytest.mark.parametrize("kind, corner_indices, options, axes, volume", [
    ("face", (1, 2, 5, 6), {"X": "Yes", "Z": "No"},
     (True, False, False), 840),
    ("face", (2, 3, 6, 7), {"Y": "Yes", "Z": "No"},
     (False, True, False), 900),
    ("edge", (5, 6), {"X": "Yes", "Z": "No"},
     (True, False, False), 720),
    ("edge", (6, 7), {"Y": "Yes", "Z": "No"},
     (False, True, False), 750),
    ("edge", (2, 6), {"X": "Yes", "Y": "Yes", "Z": "No"},
     (True, True, False), 870),
    ("edge", (5, 6), {"X": "Yes"}, (True, False, True), 870),
    ("edge", (6, 7), {"Y": "Yes"}, (False, True, True), 900),
], ids=["face-x", "face-y", "edge-x", "edge-y", "edge-xy", "edge-xz", "edge-yz"])
def test_only_enabled_coordinates_of_the_held_part_are_set(
        env, kind, corner_indices, options, axes, volume):
    scene, selection, _history, _ctx, proc = env
    obj = _box(scene)
    corners = BASE + TOP
    held_corners = [corners[index] for index in corner_indices]
    if kind == "face":
        index = _face_with(obj.shape, held_corners)
    else:
        index = _edge_between(obj.shape, *held_corners)
    selection.toggle_subobject(obj.id, kind, index)

    _setpt(proc, options=options)

    expected = list(corners)
    for index in corner_indices:
        expected[index] = tuple(TARGET[axis] if enabled else corners[index][axis]
                                for axis, enabled in enumerate(axes))
    _assert_solid(scene, obj, expected[:4], expected[4:], volume)
    assert {item.id for item in scene.all()} == {obj.id}


def test_faces_and_edges_on_several_solids_share_the_target(env):
    scene, selection, _history, _ctx, proc = env
    first = _box(scene, name="First solid")
    second = scene.add(g.make_box((30, 20, 2), 10, 6, 10), name="Second solid")
    second_bottom = [(x + 30, y + 20, z + 2) for x, y, z in BASE]
    second_top = [(x + 30, y + 20, z + 2) for x, y, z in TOP]
    _assert_solid(scene, second, second_bottom, second_top, 600)
    _hold_top(selection, first, "face-and-rim")
    _hold_top(selection, second, "opposite-rim", second_top)

    _setpt(proc)

    _assert_solid(scene, first, BASE, [(x, y, 15) for x, y, _z in TOP], 900)
    _assert_solid(scene, second, second_bottom,
                  [(x, y, 15) for x, y, _z in second_top], 780)
    assert {item.id for item in scene.all()} == {first.id, second.id}


def test_undo_restores_the_solid_and_all_shared_corners(env):
    scene, selection, history, _ctx, proc = env
    obj = _wedge(scene)
    _hold_top(selection, obj, "face-and-rim", SLOPED_TOP)

    _setpt(proc)
    _assert_solid(scene, obj, BASE, [(x, y, 15) for x, y, _z in SLOPED_TOP], 900)
    assert history.can_undo

    assert proc.run("undo")

    _assert_solid(scene, obj, BASE, SLOPED_TOP, 660)
    assert {item.id for item in scene.all()} == {obj.id}
    assert not history.can_undo


@pytest.mark.parametrize("change_options", [False, True])
def test_cancelling_setpt_keeps_the_original_solid_without_an_undo_entry(
        env, change_options):
    scene, selection, history, _ctx, proc = env
    obj = _wedge(scene)
    _hold_top(selection, obj, "face-and-rim", SLOPED_TOP)

    _start(proc)
    if change_options:
        assert proc.set_option("X", "Yes")
        assert proc.set_option("Z", "No")
    proc.cancel()

    assert not proc.busy
    _assert_solid(scene, obj, BASE, SLOPED_TOP, 660)
    assert {item.id for item in scene.all()} == {obj.id}
    assert not history.can_undo


@pytest.mark.parametrize("held, target, options", [
    ("face", TARGET, {"X": "Yes", "Z": "No"}),
    ("vertical-edge", (20.0, 30.0, 5.0), {}),
    ("face-and-rim", (20.0, 30.0, 0.0), {}),
], ids=["face-collapse", "edge-collapse", "solid-collapse"])
def test_a_collapsing_projection_reports_why_and_keeps_the_solid_and_selection(
        env, held, target, options):
    scene, selection, _history, ctx, proc = env
    obj = _box(scene)
    if held == "vertical-edge":
        selection.toggle_subobject(obj.id, "edge",
                                   _edge_between(obj.shape, BASE[2], TOP[2]))
    else:
        _hold_top(selection, obj, held)
    held_before = list(selection.subobjects)
    messages = []
    ctx.add_echo_listener(messages.append)

    _setpt(proc, target=target, options=options)

    _assert_solid(scene, obj, BASE, TOP, 600)
    assert {item.id for item in scene.all()} == {obj.id}
    assert selection.subobjects == held_before
    diagnostic_words = ("collaps", "degener", "invalid", "cannot", "can't",
                        "could not", "unable", "fail", "zero", "flatten")
    assert any(any(word in message.casefold() for word in diagnostic_words)
               for message in messages), messages


def test_switching_all_axes_off_keeps_the_held_solid_parts_unchanged(env):
    scene, selection, _history, _ctx, proc = env
    obj = _box(scene)
    _hold_top(selection, obj, "face-and-rim")

    _setpt(proc, options={axis: "No" for axis in "XYZ"})

    _assert_solid(scene, obj, BASE, TOP, 600)
    assert {item.id for item in scene.all()} == {obj.id}


@pytest.mark.parametrize("offset", [0.0, 100000.0], ids=["near", "far"])
def test_a_polysurface_made_of_nurbs_faces_is_leveled_near_and_far(env, offset):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

    scene, selection, _history, _ctx, proc = env
    shift = lambda ring, z=None: [(x + offset, y + offset, c if z is None else z)
                                  for x, y, c in ring]
    shape = BRepBuilderAPI_NurbsConvert(
        g.make_box((offset, offset, 0), 10, 6, 10), True).Shape()
    obj = scene.add(shape, name="Imported")
    selection.toggle_subobject(obj.id, "face", _face_with(obj.shape, shift(TOP)))

    _setpt(proc, target=(0.0, 0.0, 15.0))

    _assert_solid(scene, obj, shift(BASE), shift(TOP, 15), 900)


def test_a_flat_face_cut_from_a_bent_surface_can_be_set():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal

    poles = TColgp_Array2OfPnt(1, 3, 1, 2)
    for i, (x, y) in enumerate([(0, 0), (10, 0), (20, 1)], start=1):
        poles.SetValue(i, 1, gp_Pnt(x, y, 0))
        poles.SetValue(i, 2, gp_Pnt(x, y, 10))
    uk, um = TColStd_Array1OfReal(1, 3), TColStd_Array1OfInteger(1, 3)
    for i, (k, m) in enumerate([(0, 2), (1, 1), (2, 2)], start=1):
        uk.SetValue(i, k)
        um.SetValue(i, m)
    vk, vm = TColStd_Array1OfReal(1, 2), TColStd_Array1OfInteger(1, 2)
    for i in (1, 2):
        vk.SetValue(i, i - 1)
        vm.SetValue(i, 2)
    bent = Geom_BSplineSurface(poles, uk, vk, um, vm, 1, 1)
    wall = BRepBuilderAPI_MakeFace(bent, 0.0, 0.8, 0.0, 1.0, 1e-7).Face()
    roof = g.planar_face(g.make_polyline(
        [(0, 0, 10), (8, 0, 10), (8, 5, 10), (0, 5, 10)], closed=True))
    shape = g.join_surfaces([wall, roof])
    held = _face_with(shape, [(0, 0, 10), (8, 0, 10), (8, 5, 10), (0, 5, 10)])

    out = g.set_part_points(shape, [held], [], (0, 0, 4), (False, False, True))

    assert g.is_valid(out)
    assert max(p[2] for e in g.edges_of(out) for p in g.curve_endpoints(e)) == pytest.approx(4)


def _vaulted(offset):
    arc = g.make_arc_3pt((offset, offset, 10), (offset + 5, offset, 13),
                         (offset + 10, offset, 10))
    walls = g.make_polyline([(offset + 10, offset, 10), (offset + 10, offset, 0),
                             (offset, offset, 0), (offset, offset, 10)])
    return g.extrude(g.join_curves([arc, walls]), (0, 1, 0), 6, cap=True)


def _d_shape(offset):
    arc = g.make_arc_3pt((offset, offset, 0), (offset + 5, offset + 5, 0),
                         (offset + 10, offset, 0))
    chord = g.make_polyline([(offset + 10, offset, 0), (offset, offset, 0)])
    return g.extrude(g.join_curves([arc, chord]), (0, 0, 1), 10, cap=True)


@pytest.mark.parametrize("offset", [0.0, 100000.0], ids=["near", "far"])
@pytest.mark.parametrize("build, z, volume", [
    (_vaulted, 15.0, 900.0),
    (_vaulted, 8.0, 480.0),
    (_d_shape, 15.0, 15 * math.pi * 25 / 2),
], ids=["vault-up", "vault-down", "curved-wall"])
def test_curved_faces_and_neighbours_are_set_near_and_far(
        env, offset, build, z, volume):
    scene, selection, _history, _ctx, proc = env
    obj = scene.add(build(offset), name="Curved")
    faces = g.faces_of(obj.shape)
    top = max(range(len(faces)), key=lambda i: g.centroid(faces[i])[2])
    selection.toggle_subobject(obj.id, "face", top)

    _setpt(proc, target=(0.0, 0.0, z))

    shape = scene.get(obj.id).shape
    assert g.shape_kind(shape) == "solid" and g.is_valid(shape)
    assert g.volume(shape) == pytest.approx(volume, rel=1e-6)
    heights = [p[2] for e in g.edges_of(shape) for p in g.curve_endpoints(e)]
    assert min(heights) == pytest.approx(0.0, abs=1e-6)
    assert max(heights) == pytest.approx(z, abs=1e-6)


def _leaning(offset):
    def top(x, y):
        return 8 + 0.2 * x + 0.3 * y

    def lean(y):
        # where the leaning wall x = 10 - z / 10 meets the sloped top
        z = (10 + 0.3 * y) / 1.02
        return 10 - z / 10, z

    (x0, z0), (x6, z6) = lean(0), lean(6)
    corners = {
        "a": (0, 0, 0), "b": (10, 0, 0), "c": (10, 6, 0), "d": (0, 6, 0),
        "e": (0, 0, top(0, 0)), "f": (x0, 0, z0), "g": (x6, 6, z6),
        "h": (0, 6, top(0, 6)),
    }
    corners = {k: (x + offset, y + offset, z) for k, (x, y, z) in corners.items()}
    rings = ["abcd", "efgh", "abfe", "bcgf", "cdhg", "daeh"]
    faces = [g.planar_face(g.make_polyline([corners[k] for k in ring], closed=True))
             for ring in rings]
    return g.join_surfaces(faces), corners


@pytest.mark.parametrize("offset", [0.0, 100000.0], ids=["near", "far"])
def test_a_leaning_wall_twists_when_the_sloped_top_is_leveled(env, offset):
    scene, selection, _history, _ctx, proc = env
    shape, corners = _leaning(offset)
    assert g.shape_kind(shape) == "solid"
    obj = scene.add(shape, name="Leaning")
    selection.toggle_subobject(
        obj.id, "face", _face_with(obj.shape, [corners[k] for k in "efgh"]))

    _setpt(proc, target=(0.0, 0.0, 12.0))

    out = scene.get(obj.id).shape
    assert g.shape_kind(out) == "solid" and g.is_valid(out)
    assert g.volume(out) > g.volume(shape)
    points = {_key(p) for e in g.edges_of(out) for p in g.curve_endpoints(e)}
    for k in "abcd":
        assert _key(corners[k]) in points, "The base stays put"
    for k in "efgh":
        x, y, _z = corners[k]
        assert _key((x, y, 12.0)) in points, "The top corners rise straight up"
