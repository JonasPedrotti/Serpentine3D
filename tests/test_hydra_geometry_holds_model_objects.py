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
    geometry = {k: c for k, c in COMPONENTS.items() if c.category == "Geometry"}
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
