"""Hydra's graph, without its canvas: geometry components that hold model
objects of their kind, and a graph saved and read back."""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry as geo
from serpentine3d.core import hydra
from serpentine3d.core.hydra import COMPONENTS, Graph, HydraError
from serpentine3d.core.scene import Scene


def test_the_geometry_components_and_the_model_kinds_each_one_takes():
    geometry = {k: c for k, c in COMPONENTS.items() if c.picks}
    assert {k: c.picks for k, c in geometry.items()} == {
        "point": ("point",), "curve": ("curve",),
        "brep": ("surface", "solid"), "mesh": ("mesh",)}
    assert {k: c.icon for k, c in geometry.items()} == {
        "point": "point", "curve": "curve", "brep": "box", "mesh": "mesh"}
    assert COMPONENTS["mesh"].plural == "meshes"
    assert COMPONENTS["brep"].plural == "breps"


def test_a_surface_a_polysurface_and_a_solid_are_all_one_brep():
    scene = Scene()
    face = geo.planar_face(geo.make_rectangle((0, 0, 0), (2, 2, 0)))
    side = geo.planar_face(geo.make_polyline(
        [(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2)], closed=True))
    shapes = (face, geo.join_surfaces([face, side]),
              geo.make_box((5, 0, 0), 1, 1, 1))
    objs = [scene.add(shape) for shape in shapes]
    assert [o.kind for o in objs] == ["surface", "surface", "solid"]
    graph = Graph()
    node = graph.add_node("brep", params={"refs": [o.id for o in objs]})
    assert len(graph.solve(scene)[node.id].outputs["Brep"]) == 3


def test_lines_polylines_arcs_and_circles_are_all_one_curve():
    scene = Scene()
    ids = [scene.add(shape).id for shape in (
        geo.make_line((0, 0, 0), (1, 0, 0)),
        geo.make_polyline([(0, 0, 0), (1, 1, 0), (2, 0, 0)]),
        geo.make_arc_3pt((0, 0, 0), (1, 1, 0), (2, 0, 0)),
        geo.make_circle((0, 0, 0), 2))]
    assert {scene.get(i).kind for i in ids} == {"curve"}
    graph = Graph()
    curve = graph.add_node("curve", params={"refs": ids})
    result = graph.solve(scene)[curve.id]
    assert result.status == "ok"
    assert len(result.outputs["Curve"]) == 4


def test_an_empty_component_says_how_to_set_it():
    graph = Graph()
    node = graph.add_node("mesh")
    result = graph.solve(Scene())[node.id]
    assert result.status == "warning"
    assert result.message == ("Right-click and Set Mesh... to pick "
                              "meshes in the model")
    assert result.outputs["Mesh"] == []


def test_a_picked_object_that_is_deleted_is_reported_and_left_out():
    scene = Scene()
    keep = scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    gone = scene.add(geo.make_box((5, 0, 0), 1, 1, 1))
    graph = Graph()
    node = graph.add_node("brep", params={"refs": [keep.id, gone.id]})
    scene.remove(gone.id)
    result = graph.solve(scene)[node.id]
    assert result.status == "warning"
    assert "1 picked object is no longer" in result.message
    assert len(result.outputs["Brep"]) == 1


def test_only_shown_components_preview():
    scene = Scene()
    box = scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    graph = Graph()
    node = graph.add_node("brep", params={"refs": [box.id]})
    assert len(graph.preview_shapes(graph.solve(scene))) == 1
    node.preview = False
    assert graph.preview_shapes(graph.solve(scene)) == []


def test_geometry_components_have_no_inputs_to_wire_into():
    graph = Graph()
    a, b = graph.add_node("curve"), graph.add_node("curve")
    with pytest.raises(HydraError, match="has no input"):
        graph.connect(a.id, "Curve", b.id, "Curve")


def test_a_graph_reads_back_as_it_was_saved():
    graph = Graph()
    node = graph.add_node("curve", 10, 20, {"refs": ["abc", "def"]})
    node.preview = False
    again = Graph.from_dict(graph.to_dict())
    assert again.to_dict() == graph.to_dict()


def test_a_saved_graph_with_an_unknown_component_still_opens():
    data = {"nodes": [{"id": "a", "key": "curve"},
                      {"id": "b", "key": "from_the_future"}],
            "wires": [["b", "X", "a", "Curve"]]}
    graph = Graph.from_dict(data)
    assert list(graph.nodes) == ["a"]
    assert graph.wires == []


# -- the number slider ------------------------------------------------------

def test_a_slider_hands_on_its_value_and_previews_nothing():
    graph = Graph()
    node = graph.add_node("slider")
    assert node.params == {"value": 5.0, "min": 0.0, "max": 10.0,
                           "decimals": 2}
    results = graph.solve(Scene())
    assert results[node.id].outputs == {"Number": [5.0]}
    assert results[node.id].status == "ok"
    assert graph.preview_shapes(results) == []


def test_a_slider_stays_in_its_range_and_to_its_decimals():
    params = dict(COMPONENTS["slider"].params)
    hydra.set_slider(params, 3.14159)
    assert params["value"] == 3.14
    hydra.set_slider(params, 99)
    assert params["value"] == 10.0
    hydra.set_range(params, 0, 2.5)
    assert params["value"] == 2.5
    with pytest.raises(HydraError):
        hydra.set_range(params, 3, 3)


def test_fewer_decimals_round_the_range_and_the_value():
    params = {"value": 1.2345, "min": 0.125, "max": 2.75, "decimals": 4}
    hydra.set_decimals(params, 1)
    assert params == {"value": 1.2, "min": 0.1, "max": 2.8, "decimals": 1}
    hydra.set_decimals(params, 0)
    assert (params["min"], params["max"], params["value"]) == (0.0, 3.0, 1.0)


def test_a_typed_number_keeps_its_decimal_places_with_a_comma_or_a_point():
    assert hydra.parse_number("0,125") == (0.125, 3)
    assert hydra.parse_number(" 2.5 ") == (2.5, 1)
    assert hydra.parse_number("-4") == (-4.0, 0)
    with pytest.raises(ValueError):
        hydra.parse_number("abc")


def _slider():
    return dict(COMPONENTS["slider"].params)


def test_one_typed_number_sets_only_the_value():
    params = _slider()
    assert hydra.type_into_slider(params, "7,5") == "value"
    assert params == {"value": 7.5, "min": 0.0, "max": 10.0, "decimals": 2}


def test_a_typed_number_past_the_range_widens_it_to_reach():
    params = _slider()
    hydra.type_into_slider(params, "-3")
    hydra.type_into_slider(params, "25")
    assert (params["min"], params["max"], params["value"]) == (-3.0, 25.0, 25.0)


@pytest.mark.parametrize("text, low, high, places", [
    ("0.0-12", 0.0, 12.0, 1),
    ("0 - 12", 0.0, 12.0, 0),
    ("0,25-1,5", 0.25, 1.5, 2),
    ("-5-5", -5.0, 5.0, 0),
    ("-10.5 - -2", -10.5, -2.0, 1),
    ("1..3.125", 1.0, 3.125, 3),
])
def test_a_typed_range_sets_the_range_and_its_decimal_places(
        text, low, high, places):
    params = _slider()
    assert hydra.type_into_slider(params, text) == "range"
    assert (params["min"], params["max"], params["decimals"]) == (
        low, high, places)
    assert low <= params["value"] <= high


@pytest.mark.parametrize("text", ["", "abc", "5-", "12-0", "3-3"])
def test_what_is_neither_a_number_nor_a_range_changes_nothing(text):
    params = _slider()
    with pytest.raises((ValueError, HydraError)):
        hydra.type_into_slider(params, text)
    assert params == _slider()


# -- rotate -----------------------------------------------------------------

def _corners(shape):
    from serpentine3d.core.tessellate import tessellate
    return tessellate(shape).edge_segments.reshape(-1, 3)


def _rotate_graph(scene, *shapes, origin=None, angle=None):
    graph = Graph()
    geometry = graph.add_node("curve", params={
        "refs": [scene.add(s).id for s in shapes]})
    rotate = graph.add_node("rotate")
    graph.connect(geometry.id, "Curve", rotate.id, "Geometry")
    if origin is not None:
        point = graph.add_node("point", params={
            "refs": [scene.add(geo.make_point(origin)).id]})
        graph.connect(point.id, "Point", rotate.id, "Origin")
    if angle is not None:
        slider = graph.add_node("slider", params={
            "value": angle, "min": 0.0, "max": 360.0})
        graph.connect(slider.id, "Number", rotate.id, "Angle")
    return graph, rotate


def test_rotate_takes_origin_geometry_and_angle_in_that_order():
    comp = COMPONENTS["rotate"]
    assert [(p.name, p.kind) for p in comp.inputs] == [
        ("Origin", "point"), ("Geometry", "geometry"), ("Angle", "number")]
    assert [(p.name, p.kind) for p in comp.outputs] == [
        ("Geometry", "geometry")]


def test_rotate_turns_geometry_about_the_origin_point_by_the_angle():
    scene = Scene()
    graph, rotate = _rotate_graph(
        scene, geo.make_line((5, 0, 0), (10, 0, 0)), origin=(5, 0, 0),
        angle=90)
    result = graph.solve(scene)[rotate.id]
    assert result.status == "ok"
    pts = _corners(result.outputs["Geometry"][0])
    assert pts[:, 0] == pytest.approx([5, 5], abs=1e-6)
    assert sorted(pts[:, 1]) == pytest.approx([0, 5], abs=1e-6)


def test_without_an_angle_wire_rotate_leaves_geometry_where_it_was():
    scene = Scene()
    graph, rotate = _rotate_graph(scene, geo.make_line((1, 0, 0), (2, 0, 0)))
    result = graph.solve(scene)[rotate.id]
    assert result.status == "ok"
    pts = _corners(result.outputs["Geometry"][0])
    assert sorted(pts[:, 0]) == pytest.approx([1, 2], abs=1e-6)
    assert pts[:, 1] == pytest.approx([0, 0], abs=1e-6)


def test_without_an_origin_wire_rotate_turns_about_the_world_origin():
    scene = Scene()
    graph, rotate = _rotate_graph(scene, geo.make_line((1, 0, 0), (2, 0, 0)),
                                  angle=90)
    pts = _corners(graph.solve(scene)[rotate.id].outputs["Geometry"][0])
    assert pts[:, 0] == pytest.approx([0, 0], abs=1e-6)
    assert sorted(pts[:, 1]) == pytest.approx([1, 2], abs=1e-6)


def test_rotate_without_geometry_asks_for_it():
    graph = Graph()
    rotate = graph.add_node("rotate")
    result = graph.solve(Scene())[rotate.id]
    assert result.status == "warning"
    assert result.message == "Connect Geometry"


def test_the_angle_input_says_what_reaches_it():
    scene = Scene()
    graph, rotate = _rotate_graph(scene, geo.make_line((1, 0, 0), (2, 0, 0)),
                                  angle=45)
    results = graph.solve(scene)
    angle, origin = (next(p for p in COMPONENTS["rotate"].inputs
                          if p.name == n) for n in ("Angle", "Origin"))
    values, wired = graph.input_values(rotate.id, angle, results)
    assert (hydra.describe(values), wired) == ("45", True)
    values, wired = graph.input_values(rotate.id, origin, results)
    assert (hydra.describe(values), wired) == ("0, 0, 0", False)


def test_a_rotated_shape_keeps_its_surfaces_and_changes_only_its_place():
    scene = Scene()
    box = geo.make_box((0, 0, 0), 1, 1, 1)
    graph = Graph()
    brep = graph.add_node("brep", params={"refs": [scene.add(box).id]})
    rotate = graph.add_node("rotate")
    graph.connect(brep.id, "Brep", rotate.id, "Geometry")
    rotate_angle = graph.add_node("slider", params={"value": 30})
    graph.connect(rotate_angle.id, "Number", rotate.id, "Angle")
    turned = graph.solve(scene)[rotate.id].outputs["Geometry"][0]
    assert turned.IsPartner(box) and not turned.IsSame(box)


def test_every_picked_curve_is_rotated_and_previewed():
    scene = Scene()
    graph, rotate = _rotate_graph(
        scene, geo.make_line((1, 0, 0), (2, 0, 0)),
        geo.make_circle((5, 0, 0), 1), angle=45)
    results = graph.solve(scene)
    assert len(results[rotate.id].outputs["Geometry"]) == 2
    assert len(graph.preview_shapes(results)) == 4    # picked and rotated


def test_rotated_geometry_can_be_rotated_again():
    scene = Scene()
    graph, first = _rotate_graph(scene, geo.make_line((1, 0, 0), (2, 0, 0)),
                                 angle=90)
    second = graph.add_node("rotate")
    graph.connect(first.id, "Geometry", second.id, "Geometry")
    slider = next(n for n in graph.nodes.values() if n.key == "slider")
    graph.connect(slider.id, "Number", second.id, "Angle")
    result = graph.solve(scene)[second.id]
    pts = _corners(result.outputs["Geometry"][0])
    assert sorted(pts[:, 0]) == pytest.approx([-2, -1], abs=1e-6)


@pytest.mark.parametrize("source, output, into", [
    ("slider", "Number", "Geometry"),
    ("slider", "Number", "Origin"),
    ("curve", "Curve", "Origin"),
    ("curve", "Curve", "Angle"),
])
def test_a_wire_rotate_cannot_use_is_turned_away(source, output, into):
    graph = Graph()
    a = graph.add_node(source)
    rotate = graph.add_node("rotate")
    with pytest.raises(HydraError, match=f"Rotate {into} takes"):
        graph.connect(a.id, output, rotate.id, into)
    assert graph.wires == []


def test_a_new_wire_into_an_input_takes_the_old_ones_place():
    graph = Graph()
    a, b = graph.add_node("curve"), graph.add_node("brep")
    rotate = graph.add_node("rotate")
    graph.connect(a.id, "Curve", rotate.id, "Geometry")
    graph.connect(b.id, "Brep", rotate.id, "Geometry")
    assert [(w.source, w.input) for w in graph.wires] == [(b.id, "Geometry")]


# -- ids a graph can count on -----------------------------------------------

def test_a_saved_and_opened_model_keeps_its_object_ids(tmp_path):
    from serpentine3d.fileio.native import load_scene, save_scene
    scene = Scene()
    ids = [scene.add(geo.make_line((0, 0, 0), (1, 0, 0))).id,
           scene.add(geo.make_box((0, 0, 0), 1, 1, 1)).id,
           scene.add(geo.make_point((3, 0, 0))).id]
    path = tmp_path / "ids.serp"
    save_scene(scene, str(path))
    again = Scene()
    load_scene(again, str(path))
    assert sorted(o.id for o in again.all()) == sorted(ids)


def test_an_id_that_is_taken_already_is_not_given_twice():
    scene = Scene()
    first = scene.add(geo.make_point((0, 0, 0)), obj_id="abc12345")
    second = scene.add(geo.make_point((1, 0, 0)), obj_id="abc12345")
    assert first.id == "abc12345" and second.id != "abc12345"
    assert len(scene.all()) == 2


def test_importing_a_model_twice_gives_its_objects_new_ids(tmp_path):
    from serpentine3d.fileio.native import merge_scene, save_scene
    scene = Scene()
    scene.add(geo.make_line((0, 0, 0), (1, 0, 0)))
    path = tmp_path / "part.serp"
    save_scene(scene, str(path))
    merge_scene(scene, str(path))
    merge_scene(scene, str(path))
    assert len({o.id for o in scene.all()}) == 3


# -- construct point and vector ----------------------------------------------

def test_construct_point_makes_a_point_from_x_y_and_z():
    graph = Graph()
    x = graph.add_node("slider", params={"value": 3.0})
    point = graph.add_node("construct_point")
    graph.connect(x.id, "Number", point.id, "X")
    result = graph.solve(Scene())[point.id]
    [made] = result.outputs["Point"]
    assert geo.shape_kind(made) == "point"
    assert hydra.describe([made]) == "3, 0, 0"
    assert [p.name for p in COMPONENTS["construct_point"].inputs] == [
        "X", "Y", "Z"]


def test_a_list_of_numbers_makes_a_row_of_points():
    scene = Scene()
    graph = Graph()
    xs = graph.add_node("slider", params={"value": 2.0})
    point = graph.add_node("construct_point")
    graph.connect(xs.id, "Number", point.id, "Y")
    results = graph.solve(scene)
    assert len(graph.preview_shapes(results)) == 1


def test_a_constructed_point_can_be_a_rotates_origin():
    scene = Scene()
    graph = Graph()
    x = graph.add_node("slider", params={"value": 1.0})
    origin = graph.add_node("construct_point")
    graph.connect(x.id, "Number", origin.id, "X")
    curve = graph.add_node("curve", params={
        "refs": [scene.add(geo.make_line((1, 0, 0), (2, 0, 0))).id]})
    angle = graph.add_node("slider", params={"value": 90.0, "max": 360.0})
    rotate = graph.add_node("rotate")
    graph.connect(origin.id, "Point", rotate.id, "Origin")
    graph.connect(curve.id, "Curve", rotate.id, "Geometry")
    graph.connect(angle.id, "Number", rotate.id, "Angle")
    pts = _corners(graph.solve(scene)[rotate.id].outputs["Geometry"][0])
    assert pts[:, 0] == pytest.approx([1, 1], abs=1e-6)
    assert sorted(pts[:, 1]) == pytest.approx([0, 1], abs=1e-6)


def test_a_vector_runs_from_point_a_to_point_b():
    scene = Scene()
    a = scene.add(geo.make_point((1, 1, 0)))
    b = scene.add(geo.make_point((4, 5, 0)))
    graph = Graph()
    pa = graph.add_node("point", params={"refs": [a.id]})
    pb = graph.add_node("point", params={"refs": [b.id]})
    vector = graph.add_node("vector")
    graph.connect(pa.id, "Point", vector.id, "A")
    graph.connect(pb.id, "Point", vector.id, "B")
    [v] = graph.solve(scene)[vector.id].outputs["Vector"]
    assert v.components == (3, 4, 0) and v.length == 5
    assert v.start == (1, 1, 0)


def test_a_vector_without_its_points_says_how_to_set_them():
    graph = Graph()
    vector = graph.add_node("vector")
    result = graph.solve(Scene())[vector.id]
    assert result.status == "warning"
    assert result.message == ("Connect A and B, or right-click and "
                              "Set Vector...")


def test_points_set_in_the_model_stand_in_for_unwired_inputs():
    graph = Graph()
    vector = graph.add_node("vector", params={
        "set": {"A": [0, 0, 0], "B": [0, 0, 2]}})
    [v] = graph.solve(Scene())[vector.id].outputs["Vector"]
    assert v.components == (0, 0, 2)
    # a wire wins over what was set
    b = graph.add_node("construct_point")
    x = graph.add_node("slider", params={"value": 1.0})
    graph.connect(x.id, "Number", b.id, "X")
    graph.connect(b.id, "Point", vector.id, "B")
    [v] = graph.solve(Scene())[vector.id].outputs["Vector"]
    assert v.components == (1, 0, 0)


def test_a_vector_of_no_length_is_an_error():
    graph = Graph()
    vector = graph.add_node("vector", params={
        "set": {"A": [1, 1, 1], "B": [1, 1, 1]}})
    result = graph.solve(Scene())[vector.id]
    assert result.status == "error"
    assert "same point" in result.message


@pytest.mark.parametrize("end", [(5, 0, 0), (0, 0, 5), (0, 0, -5),
                                 (3, 4, 2)])
def test_a_vector_previews_as_a_line_with_a_head_at_its_end(end):
    graph = Graph()
    graph.add_node("vector", params={"set": {"A": [0, 0, 0], "B": list(end)}})
    [shape] = graph.preview_shapes(graph.solve(Scene()))
    segs = _corners(shape).reshape(-1, 2, 3)
    assert len(segs) >= 3
    tips = [s for s in segs if np.allclose(s[1], end) or np.allclose(s[0], end)]
    assert len(tips) >= 3            # the shaft and both barbs meet at B
    length = np.linalg.norm(end)
    barbs = [s for s in segs if np.linalg.norm(s[1] - s[0]) < length * 0.5]
    assert len(barbs) == 2


def test_a_saved_vector_keeps_its_set_points():
    graph = Graph()
    vector = graph.add_node("vector", params={
        "set": {"A": [0, 0, 0], "B": [1, 2, 3]}})
    again = Graph.from_dict(graph.to_dict())
    [v] = again.solve(Scene())[vector.id].outputs["Vector"]
    assert v.components == (1, 2, 3)


# -- copying ------------------------------------------------------------------

def _wired_trio():
    graph = Graph()
    curve = graph.add_node("curve", 0, 0, {"refs": ["abc"]})
    angle = graph.add_node("slider", 0, 80, {"value": 30.0})
    rotate = graph.add_node("rotate", 200, 0)
    graph.connect(curve.id, "Curve", rotate.id, "Geometry")
    graph.connect(angle.id, "Number", rotate.id, "Angle")
    return graph, curve, angle, rotate


def test_a_copied_part_keeps_the_wires_inside_it_and_leaves_the_rest():
    graph, curve, angle, rotate = _wired_trio()
    part = graph.part([angle.id, rotate.id])
    assert sorted(n["key"] for n in part["nodes"]) == ["rotate", "slider"]
    assert part["wires"] == [[angle.id, "Number", rotate.id, "Angle"]]


def test_pasting_makes_new_components_moved_and_wired_like_the_old():
    graph, curve, angle, rotate = _wired_trio()
    fresh = graph.paste(graph.part([curve.id, angle.id, rotate.id]), 30, 40)
    assert len(fresh) == 3
    assert not set(fresh) & {curve.id, angle.id, rotate.id}
    new = {graph.nodes[n].key: graph.nodes[n] for n in fresh}
    assert (new["rotate"].x, new["rotate"].y) == (230, 40)
    assert new["slider"].params == {"value": 30.0, "min": 0.0, "max": 10.0,
                                    "decimals": 2}
    assert new["curve"].params == {"refs": ["abc"]}
    inner = [w for w in graph.wires if w.target == new["rotate"].id]
    assert sorted((graph.nodes[w.source].key, w.input) for w in inner) == [
        ("curve", "Geometry"), ("slider", "Angle")]
    assert len(graph.wires) == 4             # the originals keep theirs


def test_a_pasted_copy_has_its_own_settings():
    graph, curve, angle, rotate = _wired_trio()
    [copy] = graph.paste(graph.part([angle.id]))
    graph.nodes[copy].params["value"] = 99.0
    [again] = graph.paste(graph.part([curve.id]))
    graph.nodes[again].params["refs"].append("more")
    assert angle.params["value"] == 30.0
    assert curve.params["refs"] == ["abc"]


# -- finding a component by name ----------------------------------------------

def test_before_anything_is_typed_the_search_offers_geometry_and_the_slider():
    assert hydra.find_components("") == [
        "point", "curve", "brep", "mesh", "slider"]
    assert hydra.find_components("   ") == hydra.find_components("")


@pytest.mark.parametrize("text, first", [
    ("rot", "rotate"), ("ROT", "rotate"), ("num", "slider"),
    ("slider", "slider"), ("vec", "vector"), ("constr", "construct_point"),
    ("po", "point"), ("me", "mesh"),
])
def test_typing_finds_any_component_best_match_first(text, first):
    assert hydra.find_components(text)[0] == first


def test_a_search_hides_what_does_not_fit():
    assert hydra.find_components("point") == ["point", "construct_point"]
    assert hydra.find_components("nothing like it") == []


def test_every_word_typed_has_to_fit():
    assert hydra.find_components("num sl") == ["slider"]
    assert hydra.find_components("num rot") == []


@pytest.mark.parametrize("text, found", [
    ("pt", ["point", "construct_point"]),
    ("PT", ["point", "construct_point"]),
    ("crv", ["curve"]),
    ("msh", ["mesh"]),
    ("vec", ["vector", "construct_point"]),
    ("rot", ["rotate"]),
    ("cpt", ["construct_point"]),
])
def test_the_short_names_find_their_components_first(text, found):
    assert hydra.find_components(text) == found


def test_every_short_name_belongs_to_a_component():
    assert set(hydra.NICKNAMES) <= set(COMPONENTS)


# -- move ---------------------------------------------------------------------

def _move_graph(scene, shape, vector=None):
    graph = Graph()
    picked = graph.add_node("brep" if geo.shape_kind(shape) != "curve"
                            else "curve",
                            params={"refs": [scene.add(shape).id]})
    move = graph.add_node("move")
    out = "Curve" if picked.key == "curve" else "Brep"
    graph.connect(picked.id, out, move.id, "G")
    if vector is not None:
        v = graph.add_node("vector", params={
            "set": {"A": [0, 0, 0], "B": list(vector)}})
        graph.connect(v.id, "Vector", move.id, "V")
    return graph, move


def test_move_takes_g_and_v_and_gives_g():
    comp = COMPONENTS["move"]
    assert [(p.name, p.kind) for p in comp.inputs] == [
        ("G", "geometry"), ("V", "vector")]
    assert [(p.name, p.kind) for p in comp.outputs] == [("G", "geometry")]
    assert hydra.find_components("mv") == ["move"]
    assert hydra.find_components("move")[0] == "move"


def test_move_shifts_geometry_along_the_vector():
    scene = Scene()
    graph, move = _move_graph(scene, geo.make_line((0, 0, 0), (1, 0, 0)),
                              vector=(0, 5, 2))
    result = graph.solve(scene)[move.id]
    assert result.status == "ok"
    pts = _corners(result.outputs["G"][0])
    assert sorted(pts[:, 0]) == pytest.approx([0, 1])
    assert pts[:, 1] == pytest.approx([5, 5])
    assert pts[:, 2] == pytest.approx([2, 2])


def test_without_a_vector_move_leaves_geometry_where_it_was():
    scene = Scene()
    graph, move = _move_graph(scene, geo.make_line((0, 0, 0), (1, 0, 0)))
    results = graph.solve(scene)
    pts = _corners(results[move.id].outputs["G"][0])
    assert sorted(pts[:, 0]) == pytest.approx([0, 1])
    port = next(p for p in COMPONENTS["move"].inputs if p.name == "V")
    values, wired = graph.input_values(move.id, port, results)
    assert (hydra.describe(values), wired) == ("0, 0, 0", False)


def test_move_without_geometry_asks_for_it():
    graph = Graph()
    move = graph.add_node("move")
    result = graph.solve(Scene())[move.id]
    assert (result.status, result.message) == ("warning", "Connect G")


def test_a_moved_solid_keeps_its_surfaces_and_changes_only_its_place():
    scene = Scene()
    box = geo.make_box((0, 0, 0), 1, 1, 1)
    graph, move = _move_graph(scene, box, vector=(3, 0, 0))
    moved = graph.solve(scene)[move.id].outputs["G"][0]
    assert moved.IsPartner(box) and not moved.IsSame(box)


def test_move_takes_only_a_vector_into_v():
    graph = Graph()
    curve = graph.add_node("curve")
    slider = graph.add_node("slider")
    move = graph.add_node("move")
    for source, output in ((curve, "Curve"), (slider, "Number")):
        with pytest.raises(HydraError, match="Move V takes vectors"):
            graph.connect(source.id, output, move.id, "V")


def test_rotated_then_moved_geometry_does_both():
    scene = Scene()
    graph = Graph()
    curve = graph.add_node("curve", params={
        "refs": [scene.add(geo.make_line((1, 0, 0), (2, 0, 0))).id]})
    angle = graph.add_node("slider", params={"value": 90.0, "max": 360.0})
    rotate = graph.add_node("rotate")
    move = graph.add_node("move")
    v = graph.add_node("vector", params={"set": {"A": [0, 0, 0],
                                                  "B": [0, 0, 4]}})
    graph.connect(curve.id, "Curve", rotate.id, "Geometry")
    graph.connect(angle.id, "Number", rotate.id, "Angle")
    graph.connect(rotate.id, "Geometry", move.id, "G")
    graph.connect(v.id, "Vector", move.id, "V")
    pts = _corners(graph.solve(scene)[move.id].outputs["G"][0])
    assert pts[:, 0] == pytest.approx([0, 0], abs=1e-6)
    assert sorted(pts[:, 1]) == pytest.approx([1, 2], abs=1e-6)
    assert pts[:, 2] == pytest.approx([4, 4], abs=1e-6)


# -- several wires into one input ---------------------------------------------

def _two_boxes_into_move(scene, add=True):
    graph = Graph()
    first = graph.add_node("brep", params={
        "refs": [scene.add(geo.make_box((0, 0, 0), 1, 1, 1)).id]})
    second = graph.add_node("brep", params={
        "refs": [scene.add(geo.make_box((5, 0, 0), 1, 1, 1)).id]})
    v = graph.add_node("vector", params={"set": {"A": [0, 0, 0],
                                                  "B": [0, 0, 3]}})
    move = graph.add_node("move")
    graph.connect(first.id, "Brep", move.id, "G")
    graph.connect(second.id, "Brep", move.id, "G", add=add)
    graph.connect(v.id, "Vector", move.id, "V")
    return graph, first, second, move


def test_a_wire_added_beside_another_feeds_both_into_the_input():
    scene = Scene()
    graph, first, second, move = _two_boxes_into_move(scene)
    assert [w.source for w in graph.wires if w.input == "G"] == [
        first.id, second.id]
    moved = graph.solve(scene)[move.id].outputs["G"]
    assert len(moved) == 2


def test_without_add_a_new_wire_still_takes_the_old_ones_place():
    scene = Scene()
    graph, first, second, move = _two_boxes_into_move(scene, add=False)
    assert [w.source for w in graph.wires if w.input == "G"] == [second.id]
    assert len(graph.solve(scene)[move.id].outputs["G"]) == 1


def test_adding_the_same_wire_twice_makes_one_wire():
    graph = Graph()
    a = graph.add_node("curve")
    move = graph.add_node("move")
    graph.connect(a.id, "Curve", move.id, "G")
    graph.connect(a.id, "Curve", move.id, "G", add=True)
    assert len(graph.wires) == 1


def test_the_input_says_it_holds_what_every_wire_brings():
    scene = Scene()
    graph, first, second, move = _two_boxes_into_move(scene)
    results = graph.solve(scene)
    g = next(p for p in COMPONENTS["move"].inputs if p.name == "G")
    values, wired = graph.input_values(move.id, g, results)
    assert (hydra.describe(values), wired) == ("2 objects", True)


def test_the_wire_between_two_ports_is_found_and_only_that_one():
    scene = Scene()
    graph, first, second, move = _two_boxes_into_move(scene)
    assert graph.wire_between(first.id, "Brep", move.id, "G") is not None
    assert graph.wire_between(first.id, "Brep", move.id, "V") is None


# -- trees ----------------------------------------------------------------------

from serpentine3d.core.hydra import Tree  # noqa: E402


def test_a_plain_list_is_a_tree_of_one_branch_and_reads_as_its_items():
    tree = Tree.of([1, 2, 3])
    assert tree.branches == {(0,): [1, 2, 3]}
    assert list(tree) == [1, 2, 3] and len(tree) == 3 and tree[1] == 2
    assert tree == [1, 2, 3]
    assert tree.shape() == "list"
    assert Tree.of([7]).shape() == "item"


def test_graft_puts_every_item_on_a_branch_of_its_own():
    tree = Tree.of(["a", "b", "c"]).graft()
    assert tree.branches == {(0, 0): ["a"], (0, 1): ["b"], (0, 2): ["c"]}
    assert tree.shape() == "tree"


def test_flatten_puts_every_item_on_one_branch_in_order():
    tree = Tree({(0, 0): ["a"], (0, 1): ["b", "c"]}).flatten()
    assert tree.branches == {(0,): ["a", "b", "c"]}


def test_two_trees_in_one_input_meet_branch_by_branch():
    a = Tree({(0,): [1], (1,): [2]})
    b = Tree({(0,): [3], (2,): [4]})
    assert a.merged(b).branches == {(0,): [1, 3], (1,): [2], (2,): [4]}


def _boxes_and_vectors(scene, flags=None):
    graph = Graph()
    boxes = graph.add_node("brep", params={"refs": [
        scene.add(geo.make_box((4 * i, 0, 0), 1, 1, 1)).id
        for i in range(2)]})
    vectors = []
    for z in (2, 5):
        v = graph.add_node("vector", params={"set": {"A": [0, 0, 0],
                                                      "B": [0, 0, z]}})
        vectors.append(v)
    move = graph.add_node("move", params={"flags": dict(flags or {})})
    graph.connect(boxes.id, "Brep", move.id, "G")
    graph.connect(vectors[0].id, "Vector", move.id, "V")
    graph.connect(vectors[1].id, "Vector", move.id, "V", add=True)
    return graph, move


def _heights(shapes):
    return sorted(round(min(_corners(s)[:, 2]), 6) for s in shapes)


def test_two_boxes_and_two_vectors_pair_up_as_a_list():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene)
    out = graph.solve(scene)[move.id].outputs["G"]
    assert out.branches.keys() == {(0,)}
    assert _heights(out) == [2, 5]                # box 1 by v1, box 2 by v2


def test_grafting_g_moves_every_box_by_every_vector():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene, {"in:G": "graft"})
    out = graph.solve(scene)[move.id].outputs["G"]
    assert list(out.branches) == [(0, 0), (0, 1)]   # a branch for each box
    assert [len(b) for b in out.branches.values()] == [2, 2]
    assert _heights(out) == [2, 2, 5, 5]
    assert len(graph.preview_shapes(graph.solve(scene))) == 2 + 4 + 2


def test_an_output_flag_shapes_what_the_component_hands_on():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene, {"in:G": "graft",
                                             "out:G": "flatten"})
    out = graph.solve(scene)[move.id].outputs["G"]
    assert out.branches.keys() == {(0,)} and len(out) == 4


def test_a_flag_on_a_geometry_components_output_reaches_what_it_feeds():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene)
    boxes = next(n for n in graph.nodes.values() if n.key == "brep")
    boxes.params["flags"] = {"out:Brep": "graft"}
    results = graph.solve(scene)
    assert results[boxes.id].outputs["Brep"].shape() == "tree"
    assert len(results[move.id].outputs["G"]) == 4


def test_an_input_says_what_it_works_on_after_its_flag():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene, {"in:G": "graft"})
    results = graph.solve(scene)
    g = next(p for p in COMPONENTS["move"].inputs if p.name == "G")
    tree, wired = graph.input_values(move.id, g, results)
    assert wired and len(tree.branches) == 2 and len(tree) == 2


def test_an_empty_branch_makes_an_empty_branch_not_an_error():
    graph = Graph()
    move = graph.add_node("move")
    source = graph.add_node("curve")
    graph.connect(source.id, "Curve", move.id, "G")
    result = graph.solve(Scene())[move.id]
    assert result.status == "warning"             # nothing to move at all


def test_flags_are_saved_with_the_graph():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene, {"in:G": "graft"})
    again = Graph.from_dict(graph.to_dict())
    assert again.nodes[move.id].params["flags"] == {"in:G": "graft"}


# -- reverse --------------------------------------------------------------------

def test_reverse_turns_each_branch_round_and_keeps_the_branches():
    tree = Tree({(0,): [1, 2, 3], (1,): ["a", "b"]}).reverse()
    assert tree.branches == {(0,): [3, 2, 1], (1,): ["b", "a"]}


def test_reverse_goes_with_graft_and_is_applied_first():
    tree = hydra.apply_flag(Tree.of(["a", "b", "c"]), ["graft", "reverse"])
    assert tree.branches == {(0, 0): ["c"], (0, 1): ["b"], (0, 2): ["a"]}


def test_a_port_keeps_one_flag_as_a_name_and_several_as_a_list():
    assert hydra.flags_of("graft") == ["graft"]
    assert hydra.flags_of(["flatten", "reverse"]) == ["reverse", "flatten"]
    assert hydra.flags_of(None) == []


def test_reversing_v_pairs_the_first_box_with_the_last_vector():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene, {"in:V": "reverse"})
    out = graph.solve(scene)[move.id].outputs["G"]
    first, second = (min(_corners(s)[:, 0]) for s in out)
    lift = [round(min(_corners(s)[:, 2]), 6) for s in out]
    assert first < second and lift == [5, 2]


# -- internalize ----------------------------------------------------------------

def test_every_kind_of_value_survives_being_kept_in_a_graph_file():
    import json
    shapes = [geo.make_point((1, 2, 3)), geo.make_line((0, 0, 0), (1, 0, 0)),
              geo.make_box((0, 0, 0), 1, 2, 3)]
    from serpentine3d.core.mesh import mesh_from_brep
    tree = Tree({(0,): [2.5, (1.0, 2.0, 3.0),
                        hydra.Vector((0, 0, 0), (0, 0, 4))],
                 (1, 0): shapes + [mesh_from_brep(shapes[2])]})
    again = hydra.unpack_tree(json.loads(json.dumps(hydra.pack_tree(tree))))
    assert list(again.branches) == [(0,), (1, 0)]
    first = again.branches[(0,)]
    assert first[0] == 2.5 and first[1] == (1.0, 2.0, 3.0)
    assert first[2].components == (0, 0, 4)
    assert [geo.shape_kind(s) for s in again.branches[(1, 0)]] == [
        "point", "curve", "solid", "mesh"]


def test_an_internalized_geometry_component_keeps_its_objects_when_they_go():
    scene = Scene()
    box = scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    graph = Graph()
    brep = graph.add_node("brep", params={"refs": [box.id]})
    assert graph.internalize(brep.id, scene) == 1
    assert brep.params["refs"] == []
    scene.remove(box.id)
    result = graph.solve(scene)[brep.id]
    assert result.status == "ok" and len(result.outputs["Brep"]) == 1


def test_an_internalized_geometry_component_opens_with_its_objects():
    import json
    scene = Scene()
    curve = scene.add(geo.make_line((0, 0, 0), (2, 0, 0)))
    graph = Graph()
    node = graph.add_node("curve", params={"refs": [curve.id]})
    graph.internalize(node.id, scene)
    again = Graph.from_dict(json.loads(json.dumps(graph.to_dict())))
    [kept] = again.solve(Scene())[node.id].outputs["Curve"]
    assert geo.curve_length(kept) == pytest.approx(2.0)


def test_nothing_picked_is_nothing_to_internalize():
    graph = Graph()
    node = graph.add_node("brep")
    with pytest.raises(HydraError):
        graph.internalize(node.id, Scene())


def test_an_internalized_input_keeps_what_its_wires_brought_and_drops_them():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene)
    results = graph.solve(scene)
    assert graph.internalize_input(move.id, "V", results) == 2
    assert [w.input for w in graph.wires if w.target == move.id] == ["G"]
    for node in [n for n in graph.nodes.values() if n.key == "vector"]:
        graph.remove_node(node.id)              # the sources may go now
    out = graph.solve(scene)[move.id].outputs["G"]
    assert _heights(out) == [2, 5]


def test_an_internalized_input_keeps_its_tree_and_its_flags_still_apply():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene, {"in:G": "graft"})
    results = graph.solve(scene)
    graph.internalize_input(move.id, "G", results)
    assert len(graph.solve(scene)[move.id].outputs["G"]) == 4


def test_a_wire_into_an_internalized_input_wins_over_what_it_kept():
    scene = Scene()
    graph, move = _boxes_and_vectors(scene)
    graph.internalize_input(move.id, "V", graph.solve(scene))
    v = graph.add_node("vector", params={"set": {"A": [0, 0, 0],
                                                  "B": [0, 0, 9]}})
    graph.connect(v.id, "Vector", move.id, "V")
    assert _heights(graph.solve(scene)[move.id].outputs["G"]) == [9, 9]


def test_an_input_with_no_wire_has_nothing_to_internalize():
    graph = Graph()
    move = graph.add_node("move")
    with pytest.raises(HydraError):
        graph.internalize_input(move.id, "G", graph.solve(Scene()))


def test_internalized_data_is_read_back_once_not_on_every_solve(monkeypatch):
    scene = Scene()
    box = scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    graph = Graph()
    brep = graph.add_node("brep", params={"refs": [box.id]})
    graph.internalize(brep.id, scene)
    again = Graph.from_dict(graph.to_dict())
    reads = []
    real = hydra.unpack_tree
    monkeypatch.setattr(hydra, "unpack_tree",
                        lambda data: reads.append(1) or real(data))
    for _ in range(3):
        again.solve(scene)
    assert len(reads) == 1


# -- list item ------------------------------------------------------------------

def _three_curves_into_list_item(scene, index=None, flags=None):
    graph = Graph()
    curves = graph.add_node("curve", params={"refs": [
        scene.add(geo.make_line((0, y, 0), (1 + y, y, 0))).id
        for y in range(3)]})
    item = graph.add_node("list_item", params={"flags": dict(flags or {})})
    graph.connect(curves.id, "Curve", item.id, "L")
    if index is not None:
        i = graph.add_node("slider", params={"value": index, "min": -10.0,
                                             "max": 10.0})
        graph.connect(i.id, "Number", item.id, "i")
    return graph, curves, item


def _length_of(shape):
    return round(geo.curve_length(shape), 6)


def test_list_item_sits_in_list_with_l_and_i():
    comp = COMPONENTS["list_item"]
    assert comp.category == "List" and "List" in hydra.CATEGORIES
    assert [(p.name, p.kind, p.access) for p in comp.inputs] == [
        ("L", "any", "list"), ("i", "number", "item")]
    assert hydra.find_components("item")[0] == "list_item"


@pytest.mark.parametrize("index, length", [
    (None, 1), (0, 1), (1, 2), (2, 3), (-1, 3), (3, 1), (1.4, 2), (1.6, 3),
])
def test_list_item_takes_the_item_at_i_rounding_and_wrapping(index, length):
    scene = Scene()
    graph, curves, item = _three_curves_into_list_item(scene, index)
    [picked] = graph.solve(scene)[item.id].outputs["Item"]
    assert _length_of(picked) == length


def test_several_indices_take_several_items():
    scene = Scene()
    graph, curves, item = _three_curves_into_list_item(scene)
    i = graph.add_node("slider", params={"value": 0.0})
    j = graph.add_node("slider", params={"value": 2.0})
    graph.connect(i.id, "Number", item.id, "i")
    graph.connect(j.id, "Number", item.id, "i", add=True)
    out = graph.solve(scene)[item.id].outputs["Item"]
    assert [_length_of(s) for s in out] == [1, 3]


def test_list_item_works_branch_by_branch_on_a_tree():
    scene = Scene()
    graph, curves, item = _three_curves_into_list_item(
        scene, 0, {"in:L": "graft"})
    out = graph.solve(scene)[item.id].outputs["Item"]
    # every curve on a branch of its own: the first of each is itself
    assert len(out.branches) == 3
    assert [_length_of(s) for s in out] == [1, 2, 3]


def test_list_item_takes_numbers_points_and_vectors_too():
    graph = Graph()
    numbers = graph.add_node("slider", params={"value": 7.0})
    item = graph.add_node("list_item")
    graph.connect(numbers.id, "Number", item.id, "L")
    assert graph.solve(Scene())[item.id].outputs["Item"] == [7.0]


def test_what_list_item_takes_out_feeds_a_move_and_previews():
    scene = Scene()
    graph, curves, item = _three_curves_into_list_item(scene, 2)
    move = graph.add_node("move")
    graph.connect(item.id, "Item", move.id, "G")
    results = graph.solve(scene)
    assert results[move.id].status == "ok"
    curves.preview = False
    assert len(graph.preview_shapes(graph.solve(scene))) == 2


def test_a_number_taken_out_into_moves_g_says_it_does_not_fit():
    graph = Graph()
    numbers = graph.add_node("slider")
    item = graph.add_node("list_item")
    move = graph.add_node("move")
    graph.connect(numbers.id, "Number", item.id, "L")
    graph.connect(item.id, "Item", move.id, "G")
    result = graph.solve(Scene())[move.id]
    assert result.status == "error"
    assert result.message == "Move G takes geometry, not a number"


def test_list_item_without_a_list_asks_for_one():
    graph = Graph()
    item = graph.add_node("list_item")
    result = graph.solve(Scene())[item.id]
    assert (result.status, result.message) == ("warning", "Connect L")


# -- remove item ------------------------------------------------------------

def _numbers_into_remove_item(values, indices, flags=None):
    graph = Graph()
    remove = graph.add_node("remove_item", params={"flags": dict(flags or {})})
    for v in values:
        s = graph.add_node("slider", params={"value": v, "min": -99.0,
                                             "max": 99.0})
        graph.connect(s.id, "Number", remove.id, "L", add=True)
    for i in indices:
        s = graph.add_node("slider", params={"value": i, "min": -99.0,
                                             "max": 99.0})
        graph.connect(s.id, "Number", remove.id, "i", add=True)
    return graph, remove


def test_remove_item_sits_in_list_and_is_found_as_cull_or_delete():
    comp = COMPONENTS["remove_item"]
    assert comp.category == "List"
    assert [(p.name, p.access) for p in comp.inputs] == [
        ("L", "list"), ("i", "list")]
    assert hydra.find_components("cull") == ["remove_item"]
    assert hydra.find_components("delete") == ["remove_item"]


@pytest.mark.parametrize("indices, left", [
    ([0], [2, 3, 4]), ([1], [1, 3, 4]), ([-1], [1, 2, 3]),
    ([0, 2], [2, 4]), ([4], [2, 3, 4]), ([1.4], [1, 3, 4]),
    ([1, 1], [1, 3, 4]),
])
def test_remove_item_takes_the_items_at_i_out_of_the_list(indices, left):
    graph, remove = _numbers_into_remove_item([1, 2, 3, 4], indices)
    out = graph.solve(Scene())[remove.id].outputs["L"]
    assert out == left and out.branches.keys() == {(0,)}


def test_remove_item_works_branch_by_branch():
    graph, remove = _numbers_into_remove_item([1, 2], [0], {"in:L": "graft"})
    out = graph.solve(Scene())[remove.id].outputs["L"]
    # every number alone on its branch, and the first of each taken out
    assert list(out.branches.values()) == [[], []]


def test_remove_item_asks_for_i_rather_than_taking_the_first_unasked():
    graph, remove = _numbers_into_remove_item([1, 2, 3], [])
    result = graph.solve(Scene())[remove.id]
    assert (result.status, result.message) == ("warning", "Connect i")


def test_removing_every_item_leaves_an_empty_list():
    graph, remove = _numbers_into_remove_item([1, 2], [0, 1])
    result = graph.solve(Scene())[remove.id]
    assert result.status == "ok" and result.outputs["L"] == []


def test_remove_item_leaves_the_models_objects_alone():
    scene = Scene()
    boxes = [scene.add(geo.make_box((3 * k, 0, 0), 1, 1, 1)) for k in range(3)]
    graph = Graph()
    brep = graph.add_node("brep", params={"refs": [b.id for b in boxes]})
    remove = graph.add_node("remove_item")
    i = graph.add_node("slider", params={"value": 1.0})
    graph.connect(brep.id, "Brep", remove.id, "L")
    graph.connect(i.id, "Number", remove.id, "i")
    out = graph.solve(scene)[remove.id].outputs["L"]
    assert len(out) == 2 and len(scene.all()) == 3


def test_a_curve_into_i_says_it_does_not_fit():
    scene = Scene()
    graph = Graph()
    curve = graph.add_node("curve", params={
        "refs": [scene.add(geo.make_line((0, 0, 0), (1, 0, 0))).id]})
    numbers = graph.add_node("slider")
    remove = graph.add_node("remove_item")
    graph.connect(numbers.id, "Number", remove.id, "L")
    items = graph.add_node("list_item")
    graph.connect(curve.id, "Curve", items.id, "L")
    graph.connect(items.id, "Item", remove.id, "i")
    result = graph.solve(scene)[remove.id]
    assert result.status == "error"
    assert result.message == "Remove Item i takes numbers, not a curve"


@pytest.mark.parametrize("text", ["rot", "pt", "", "inf", "nan", "12-0",
                                  "3-3", "5-"])
def test_what_is_no_number_or_range_makes_no_slider(text):
    assert hydra.slider_from_text(text) is None


# -- the panel ------------------------------------------------------------------

def test_a_panel_with_nothing_wired_holds_its_text_a_line_an_item():
    graph = Graph()
    panel = graph.add_node("panel", params={"text": "first\n\n  \nsecond"})
    out = graph.solve(Scene())[panel.id].outputs["Out"]
    assert out == ["first", "second"]
    assert COMPONENTS["panel"].category == "Input"
    assert COMPONENTS["pipeline"].category == "Input"


def test_a_panel_hands_on_what_comes_in_as_it_is():
    scene = Scene()
    graph = Graph()
    curves = graph.add_node("curve", params={"refs": [
        scene.add(geo.make_line((0, y, 0), (1, y, 0))).id for y in range(2)],
        "flags": {"out:Curve": "graft"}})
    panel = graph.add_node("panel", params={"text": "ignored"})
    graph.connect(curves.id, "Curve", panel.id, "In")
    out = graph.solve(scene)[panel.id].outputs["Out"]
    assert len(out) == 2 and list(out.branches) == [(0, 0), (0, 1)]


def test_text_that_reads_as_a_number_goes_into_a_number_input():
    scene = Scene()
    graph = Graph()
    curve = graph.add_node("curve", params={
        "refs": [scene.add(geo.make_line((1, 0, 0), (2, 0, 0))).id]})
    panel = graph.add_node("panel", params={"text": "90"})
    rotate = graph.add_node("rotate")
    graph.connect(curve.id, "Curve", rotate.id, "Geometry")
    graph.connect(panel.id, "Out", rotate.id, "Angle")
    pts = _corners(graph.solve(scene)[rotate.id].outputs["Geometry"][0])
    assert sorted(pts[:, 1]) == pytest.approx([1, 2], abs=1e-6)


def test_text_that_is_no_number_says_so_in_a_number_input():
    scene = Scene()
    graph = Graph()
    curve = graph.add_node("curve", params={
        "refs": [scene.add(geo.make_line((1, 0, 0), (2, 0, 0))).id]})
    panel = graph.add_node("panel", params={"text": "ninety"})
    rotate = graph.add_node("rotate")
    graph.connect(curve.id, "Curve", rotate.id, "Geometry")
    graph.connect(panel.id, "Out", rotate.id, "Angle")
    result = graph.solve(scene)[rotate.id]
    assert (result.status, result.message) == (
        "error", "Rotate Angle takes numbers, not text")


@pytest.mark.parametrize("typed, text", [
    ('"Hallo', "Hallo"), ('"12.5"', "12.5"), ('"', ""), ("„Wort“",
                                                          "Wort"),
])
def test_a_quotation_mark_typed_into_the_search_makes_a_panel(typed, text):
    assert hydra.panel_from_text(typed) == {"text": text}


@pytest.mark.parametrize("typed", ["Hallo", "12", "rot"])
def test_without_a_quotation_mark_no_panel(typed):
    assert hydra.panel_from_text(typed) is None


def test_text_and_booleans_are_kept_when_internalized():
    import json
    tree = Tree.of(["word", True, False, 3.0])
    again = hydra.unpack_tree(json.loads(json.dumps(hydra.pack_tree(tree))))
    assert again == ["word", True, False, 3.0]
    assert isinstance(again[1], bool)


# -- delaunay mesh ----------------------------------------------------------------

def _points_into_delaunay(scene, coords, flags=None):
    graph = Graph()
    points = graph.add_node("point", params={
        "refs": [scene.add(geo.make_point(c)).id for c in coords],
        "flags": dict(flags or {})})
    mesh = graph.add_node("delaunay")
    graph.connect(points.id, "Point", mesh.id, "P")
    return graph, mesh


def test_delaunay_mesh_sits_in_mesh_and_takes_a_list_of_points():
    comp = COMPONENTS["delaunay"]
    assert comp.category == "Mesh" and "Mesh" in hydra.CATEGORIES
    assert [(p.name, p.kind, p.access) for p in comp.inputs] == [
        ("P", "point", "list"), ("Outline", "curve", "item")]
    assert comp.outputs[0].kind == "mesh"


def test_four_corners_make_two_triangles_facing_up():
    scene = Scene()
    graph, mesh = _points_into_delaunay(
        scene, [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
    [made] = graph.solve(scene)[mesh.id].outputs["M"]
    assert geo.shape_kind(made) == "mesh"
    assert len(made.vertices) == 4 and len(made.triangles) == 2
    v = made.vertices[made.triangles]
    normal_z = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])[:, 2]
    assert (normal_z > 0).all()


def test_the_points_keep_their_heights():
    scene = Scene()
    graph, mesh = _points_into_delaunay(
        scene, [(0, 0, 0), (2, 0, 1), (2, 2, 3), (0, 2, 2)])
    [made] = graph.solve(scene)[mesh.id].outputs["M"]
    assert sorted(made.vertices[:, 2]) == [0, 1, 2, 3]


def test_no_point_lies_in_any_triangles_circle():
    from serpentine3d.core.delaunay import triangulate
    rng = np.random.default_rng(7)
    pts = rng.random((300, 2))
    for tri in triangulate(pts):
        (ax, ay), (bx, by), (cx, cy) = pts[tri]
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
        centre = np.array([(a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)),
                           (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax))
                           ]) / d
        r2 = ((pts[tri[0]] - centre) ** 2).sum()
        inside = ((pts - centre) ** 2).sum(axis=1) < r2 * (1 - 1e-9)
        inside[tri] = False
        assert not inside.any()


def test_a_grid_of_points_on_shared_circles_is_meshed_whole():
    from serpentine3d.core.delaunay import triangulate
    grid = np.array([[x, y] for x in range(5) for y in range(5)], float)
    assert len(triangulate(grid)) == 2 * 4 * 4


def test_points_in_a_line_say_they_make_no_mesh():
    scene = Scene()
    graph, mesh = _points_into_delaunay(
        scene, [(0, 0, 0), (1, 1, 0), (2, 2, 0)])
    result = graph.solve(scene)[mesh.id]
    assert (result.status, result.message) == (
        "error", "The points are all in a line")


def test_a_point_standing_on_another_is_counted_once():
    scene = Scene()
    graph, mesh = _points_into_delaunay(
        scene, [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 5)])
    [made] = graph.solve(scene)[mesh.id].outputs["M"]
    assert len(made.vertices) == 3 and len(made.triangles) == 1


def test_each_branch_of_points_makes_a_mesh_of_its_own():
    graph = Graph()
    points = graph.add_node("point")
    points.set_internal("out", Tree({
        (0,): [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        (1,): [(5.0, 0.0, 0.0), (6.0, 0.0, 0.0), (5.0, 1.0, 0.0),
               (6.0, 1.0, 0.0)]}))
    mesh = graph.add_node("delaunay")
    graph.connect(points.id, "Point", mesh.id, "P")
    out = graph.solve(Scene())[mesh.id].outputs["M"]
    assert list(out.branches) == [(0,), (1,)]
    assert [len(m.triangles) for m in out] == [1, 2]


# -- geometry of any kind into an input of one kind ----------------------------

def _pipeline_into_delaunay(scene, types):
    graph = Graph()
    pipe = graph.add_node("pipeline", params={"layer": None, "types": types})
    mesh = graph.add_node("delaunay")
    graph.connect(pipe.id, "Geometry", mesh.id, "P")
    return graph, mesh


def test_a_pipelines_points_go_into_delaunay_mesh():
    scene = Scene()
    for c in ((0, 0, 0), (3, 0, 1), (0, 3, 2), (3, 3, 0)):
        scene.add(geo.make_point(c))
    scene.add(geo.make_line((9, 9, 0), (10, 9, 0)))
    graph, mesh = _pipeline_into_delaunay(scene, ["point"])
    result = graph.solve(scene)[mesh.id]
    assert result.status == "ok"
    assert len(result.outputs["M"][0].triangles) == 2


def test_a_pipeline_that_brings_a_curve_too_says_what_does_not_fit():
    scene = Scene()
    for c in ((0, 0, 0), (3, 0, 0), (0, 3, 0)):
        scene.add(geo.make_point(c))
    scene.add(geo.make_line((9, 9, 0), (10, 9, 0)))
    graph, mesh = _pipeline_into_delaunay(scene, ["point", "curve"])
    result = graph.solve(scene)[mesh.id]
    assert (result.status, result.message) == (
        "error", "Delaunay Mesh P takes points, not a curve")


def test_moved_points_go_into_delaunay_mesh():
    scene = Scene()
    graph = Graph()
    points = graph.add_node("point", params={"refs": [
        scene.add(geo.make_point(c)).id
        for c in ((0, 0, 0), (2, 0, 0), (0, 2, 0))]})
    move = graph.add_node("move")
    mesh = graph.add_node("delaunay")
    graph.connect(points.id, "Point", move.id, "G")
    graph.connect(move.id, "G", mesh.id, "P")
    assert graph.solve(scene)[mesh.id].status == "ok"


@pytest.mark.parametrize("into, kind", [
    ("point", "point"), ("curve", "curve"), ("brep", "brep"),
    ("mesh", "mesh"), ("number", "number")])
def test_which_inputs_take_geometry_of_any_kind(into, kind):
    assert hydra.takes(kind, "geometry") == (into != "number")


# -- delaunay mesh within an outline ----------------------------------------------

def _grid_into_delaunay(scene, outline=None):
    graph = Graph()
    points = graph.add_node("point", params={"refs": [
        scene.add(geo.make_point((x, y, 0))).id
        for x in range(-5, 6) for y in range(-5, 6)]})
    mesh = graph.add_node("delaunay")
    graph.connect(points.id, "Point", mesh.id, "P")
    if outline is not None:
        curve = graph.add_node("curve", params={
            "refs": [scene.add(outline).id]})
        graph.connect(curve.id, "Curve", mesh.id, "Outline")
    return graph, mesh


def test_the_outline_is_optional_and_named_so():
    comp = COMPONENTS["delaunay"]
    assert [(p.name, p.kind, p.optional) for p in comp.inputs] == [
        ("P", "point", False), ("Outline", "curve", True)]
    scene = Scene()
    graph, mesh = _grid_into_delaunay(scene)
    result = graph.solve(scene)[mesh.id]
    assert result.status == "ok" and len(result.outputs["M"][0].triangles) \
        == 200


def test_faces_outside_a_closed_outline_are_left_out():
    scene = Scene()
    graph, mesh = _grid_into_delaunay(
        scene, geo.make_circle((0, 0, 0), 3.5))
    [made] = graph.solve(scene)[mesh.id].outputs["M"]
    middles = made.vertices[made.triangles][:, :, :2].mean(axis=1)
    assert len(made.triangles) < 200
    assert (np.hypot(middles[:, 0], middles[:, 1]) < 3.5).all()
    # and the points no face uses any more are gone with them
    assert len(np.unique(made.triangles)) == len(made.vertices)


def test_a_rectangle_outline_keeps_the_faces_inside_it():
    scene = Scene()
    graph, mesh = _grid_into_delaunay(
        scene, geo.make_rectangle((-2, -2, 7), (2, 2, 7)))   # any height
    [made] = graph.solve(scene)[mesh.id].outputs["M"]
    assert len(made.triangles) == 2 * 4 * 4
    assert (np.abs(made.vertices[:, :2]) <= 2).all()


def test_an_open_curve_as_outline_says_it_must_be_closed():
    scene = Scene()
    graph, mesh = _grid_into_delaunay(
        scene, geo.make_line((0, 0, 0), (3, 0, 0)))
    result = graph.solve(scene)[mesh.id]
    assert (result.status, result.message) == (
        "error", "Outline must be a closed curve")


def test_an_outline_round_none_of_the_faces_says_so():
    scene = Scene()
    graph, mesh = _grid_into_delaunay(
        scene, geo.make_circle((40, 40, 0), 1))
    result = graph.solve(scene)[mesh.id]
    assert (result.status, result.message) == (
        "error", "No face of the mesh is inside the outline")


def test_a_point_is_inside_an_outline_by_an_odd_count_of_crossings():
    from serpentine3d.core.delaunay import inside_outline
    square = np.array([[[0, 0], [4, 0]], [[4, 0], [4, 4]],
                       [[4, 4], [0, 4]], [[0, 4], [0, 0]]], float)
    inside = inside_outline([[2, 2], [5, 2], [-1, -1], [3.9, 0.1]], square)
    assert inside.tolist() == [True, False, False, True]



def test_a_component_given_its_own_name_keeps_it_and_can_lose_it():
    graph = Graph()
    node = graph.add_node("rotate")
    assert node.title == "Rotate"
    node.rename("Turn the roof")
    assert node.title == "Turn the roof"
    node.rename("Rotate")                  # its own name: nothing to keep
    assert "name" not in node.params
