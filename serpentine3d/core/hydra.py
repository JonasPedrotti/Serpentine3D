"""Hydra: a visual graph of components, in the spirit of Grasshopper. Kept
free of Qt so the graph solves the same in tests and in the editor.

The geometry components each hold model objects of their kind, set by
picking them, and hand them on as a list. A Number Slider hands on one
number, between a range and to as many decimal places as it is set to.

Every wire carries a tree, as in Grasshopper: branches of items, each
branch under a path such as {0} or {0;1}. A plain list is a tree of one
branch, {0}. A component pairs its inputs' branches by the longest list,
then within each pair of branches their items the same way, reusing the
last of the shorter: three curves and one angle make three rotated curves.
Graft, set on a port, puts every item on a branch of its own; Flatten puts
them all on one; Reverse turns each branch round, and goes with either.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from . import geometry as g


class HydraError(Exception):
    pass


@dataclass(frozen=True)
class Port:
    name: str
    # point | curve | brep | mesh | geometry | number | vector | any
    kind: str
    # what an input without a wire stands for; None means it needs one
    default: object = None
    # "item": the component works on one item at a time; "list": it gets a
    # branch's whole list in one go, as List Item's L does
    access: str = "item"
    # an input that may be left empty: its component then works without it
    optional: bool = False
    # what the port is for, said in its tooltip
    description: str = ""
    # what it takes or gives, said first in its tooltip; by its kind if
    # left out
    label: str = ""

    @property
    def what(self) -> str:
        return self.label or _WHAT.get(self.kind, self.kind.title())


_WHAT = {"number": "Number", "point": "Point", "vector": "Vector",
         "geometry": "Geometry", "curve": "Curve", "brep": "Brep",
         "mesh": "Mesh", "any": "Data", "boolean": "Boolean"}


# Which outputs an input takes: a geometry input any geometry, a point
# input points alone, a number input numbers alone.
_TAKES = {"geometry": ("point", "curve", "brep", "mesh", "geometry"),
          "point": ("point",), "vector": ("vector",),
          # a boolean counts as 1 or 0, as in Grasshopper
          "number": ("number", "boolean"), "boolean": ("boolean", "number")}


def takes(input_kind: str, output_kind: str) -> bool:
    # what may carry anything is let in, and its items are checked when the
    # component works on them; an input of any kind lets everything in
    if "any" in (input_kind, output_kind):
        return True
    # geometry of any kind, as a pipeline or a Move hands on, may hold just
    # what a point, curve, brep or mesh input asks for: let in and checked
    if output_kind == "geometry" and input_kind in _SHAPE_KINDS:
        return True
    return output_kind in _TAKES.get(input_kind, (input_kind,))


# what each kind of geometry input takes, among the model's kinds
_SHAPE_KINDS = {"point": ("point",), "curve": ("curve",),
                "brep": ("surface", "solid"), "mesh": ("mesh",)}


def _is_shape(value) -> bool:
    from .mesh import MeshShape
    return isinstance(value, (TopoDS_Shape, MeshShape))


def fits(kind: str, value) -> bool:
    """Whether an item can be used where `kind` is asked for."""
    if kind == "any":
        return True
    if kind == "number":
        return isinstance(value, (int, float)) or (
            isinstance(value, str) and _as_number(value) is not None)
    if kind == "boolean":
        return isinstance(value, (bool, int, float))
    if kind == "vector":
        return isinstance(value, Vector)
    if kind == "point":
        return isinstance(value, tuple) or (
            isinstance(value, TopoDS_Shape) and g.shape_kind(value) == "point")
    if kind in _SHAPE_KINDS:
        return _is_shape(value) and g.shape_kind(value) in _SHAPE_KINDS[kind]
    return _is_shape(value)


def _as_number(value):
    """Text that reads as a number, as that number; None if it does not."""
    try:
        return float(value.strip().replace(",", "."))
    except (AttributeError, ValueError):
        return None


def coerce(kind: str, value):
    """An item made what a port asks for, where it can be: text into a
    number. Everything else as it is."""
    if kind in ("number", "boolean") and isinstance(value, str):
        number = _as_number(value)
        return value if number is None else number
    return value


def said_of(value) -> str:
    """What an item is, for a message saying it does not fit."""
    if isinstance(value, str):
        return "text"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, Vector):
        return "a vector"
    if isinstance(value, tuple):
        return "a point"
    if _is_shape(value):
        return {"point": "a point", "curve": "a curve", "surface": "a brep",
                "solid": "a brep", "mesh": "a mesh"}.get(
                    g.shape_kind(value), "geometry")
    return "geometry"


@dataclass(frozen=True)
class Component:
    key: str
    title: str
    category: str
    inputs: tuple[Port, ...] = ()
    outputs: tuple[Port, ...] = ()
    # the kinds of model object it holds, picked with its Set action
    picks: tuple[str, ...] = ()
    icon: str = ""            # the toolbar icon the editor shows it with
    description: str = ""
    params: dict = field(default_factory=dict)
    # works out one set of outputs from one item of each input
    solve: Callable | None = None
    # the right-click action that sets the inputs by picking in the model
    sets: str = ""

    @property
    def plural(self) -> str:
        noun = self.title.lower()
        return noun + ("es" if noun.endswith("sh") else "s")


COMPONENTS: dict[str, Component] = {}
CATEGORIES = ("Geometry", "Input", "Vector", "Mesh", "Transform", "List")
GEOMETRY_KINDS = ("point", "curve", "brep", "mesh", "geometry")
MAX_DECIMALS = 6


COMPONENTS_PLURAL = {"point": "points", "curve": "curves",
                     "brep": "breps", "mesh": "meshes"}


def _geometry(key, title, short, kinds, icon, description):
    COMPONENTS[key] = Component(key, title, "Geometry",
                                outputs=(Port(title, key, description=(
                                    f"The {COMPONENTS_PLURAL[key]} picked "
                                    "in the model")),), picks=kinds,
                                icon=icon, sets=f"Set {short}",
                                description=description)


# One component for each thing a Grasshopper user reaches for. Line,
# polyline, arc and circle are all one curve, as they are in the model, and
# surfaces, polysurfaces and solids are all one Brep.
_geometry("point", "Point", "Pt", ("point",), "point",
          "Points picked in the model")
_geometry("curve", "Curve", "Crv", ("curve",), "curve",
          "Curves picked in the model: lines, polylines, arcs, circles and "
          "free curves alike")
_geometry("brep", "Brep", "Brep", ("surface", "solid"), "box",
          "Surfaces, polysurfaces and solids picked in the model")
_geometry("mesh", "Mesh", "Mesh", ("mesh",), "mesh",
          "Meshes picked in the model")

COMPONENTS["toggle"] = Component(
    "toggle", "Boolean Toggle", "Input",
    outputs=(Port("Boolean", "boolean", description="True or False"),),
    icon="toggle", params={"value": False},
    description="True or False; double-click it to switch")


# what each type a Geometry Pipeline can take is, among the model's kinds
PIPE_TYPES = {"point": ("point",), "curve": ("curve",),
              "brep": ("surface", "solid"), "mesh": ("mesh",)}

COMPONENTS["pipeline"] = Component(
    "pipeline", "Geometry Pipeline", "Input",
    outputs=(Port("Geometry", "geometry",
                  description="Everything in the model that fits"),),
    icon="pipeline", params={"layer": None, "types": list(PIPE_TYPES)},
    description="Every object in the model on a layer, of the types "
                "chosen, kept up to date as the model changes")


def piped(scene, params) -> list:
    """The model's objects a Geometry Pipeline takes: on its layer, the
    layers under it counted, or on any with none chosen; and of its
    types."""
    kinds = {k for t in params.get("types", ()) for k in PIPE_TYPES.get(t, ())}
    path = params.get("layer")
    layers = None
    if path is not None:
        layer = scene.layers.find_by_path(path)
        if layer is None:
            return []
        layers = scene.layers.with_descendants([layer.id])
    return [obj for obj in scene.all()
            if obj.kind in kinds and not getattr(obj, "clip_plane", None)
            and (layers is None or obj.layer_id in layers)]


COMPONENTS["panel"] = Component(
    "panel", "Panel", "Input",
    inputs=(Port("In", "any", access="list", label="Data",
                 description="Whatever is to be shown"),),
    outputs=(Port("Out", "any", label="Data",
                  description="What comes in, or the text typed, a line an "
                              "item"),),
    icon="panel", params={"text": ""},
    description="Shows what comes in, as Rhino's panel does; with nothing "
                "wired, holds text typed into it, a line an item")


def panel_lines(text: str) -> list:
    """A panel's typed text as items, a line each, blank lines left out."""
    return [line for line in text.splitlines() if line.strip()]


def panel_from_text(text: str):
    """A panel's settings from what was typed into the search after a
    quotation mark, "Hallo or "12; None if it does not start with one."""
    if not text.startswith(('"', "\u201c", "\u201e")):
        return None
    content = text[1:]
    if content.endswith(('"', "\u201d", "\u201c")):
        content = content[:-1]
    return {"text": content}


COMPONENTS["slider"] = Component(
    "slider", "Number Slider", "Input",
    outputs=(Port("Number", "number", description="The slider's number"),),
    icon="sliders", description="A number, set by dragging the slider",
    params={"value": 5.0, "min": 0.0, "max": 10.0, "decimals": 2})


def _coordinates(point) -> tuple:
    """A point's coordinates, whether a point object or a set of three."""
    if isinstance(point, (tuple, list)):
        return tuple(float(c) for c in point)
    from .occ import BRep_Tool, TopoDS
    p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(point))
    return (p.X(), p.Y(), p.Z())


@dataclass(frozen=True)
class Vector:
    """A direction and a length, kept with the place it was drawn from so
    the preview can show it there, as an arrow from start to end."""
    start: tuple
    end: tuple

    @property
    def components(self) -> tuple:
        return tuple(b - a for a, b in zip(self.start, self.end))

    @property
    def length(self) -> float:
        return math.sqrt(sum(c * c for c in self.components))


def arrow(start, end):
    """A line from start to end with a head at the end, as one shape."""
    d = [b - a for a, b in zip(start, end)]
    length = math.sqrt(sum(c * c for c in d))
    if length < 1e-12:
        raise HydraError("The two points of a vector are the same point")
    d = [c / length for c in d]
    # the head opens in the plane of the arrow and the vertical, or of the
    # arrow and X when it points straight up or down
    up = (0.0, 0.0, 1.0) if abs(d[2]) < 0.99 else (1.0, 0.0, 0.0)
    side = [d[1] * up[2] - d[2] * up[1], d[2] * up[0] - d[0] * up[2],
            d[0] * up[1] - d[1] * up[0]]
    norm = math.sqrt(sum(c * c for c in side))
    side = [c / norm for c in side]
    head = length * 0.15
    barbs = [tuple(e - dc * head + sc * head * k * 0.5
                   for e, dc, sc in zip(end, d, side)) for k in (1, -1)]
    return g.make_compound([g.make_line(start, end)]
                           + [g.make_line(b, end) for b in barbs])


def _rotate(Origin, Geometry, Angle):
    center = Origin if isinstance(Origin, tuple) else _coordinates(Origin)
    if not isinstance(Geometry, TopoDS_Shape):
        return g.rotate(Geometry, center, (0.0, 0.0, 1.0), Angle)
    # Moved rather than copied: the result shares its surfaces with what
    # was rotated, so the preview meshes it once and only turns the mesh
    # while a slider is dragged.
    turn = gp_Trsf()
    turn.SetRotation(gp_Ax1(gp_Pnt(*center), gp_Dir(0.0, 0.0, 1.0)),
                     math.radians(Angle))
    return Geometry.Moved(TopLoc_Location(turn))


COMPONENTS["construct_point"] = Component(
    "construct_point", "Construct Point", "Vector",
    inputs=(Port("X", "number", 0.0, description="The point's X"),
            Port("Y", "number", 0.0, description="The point's Y"),
            Port("Z", "number", 0.0, description="The point's Z")),
    outputs=(Port("Point", "point", description="The point at X, Y, Z"),),
    icon="point",
    solve=lambda X, Y, Z: g.make_point((X, Y, Z)),
    description="A point from its X, Y and Z coordinates")


def _vector(A, B):
    vector = Vector(_coordinates(A), _coordinates(B))
    if vector.length < 1e-12:
        raise HydraError("A and B are the same point")
    return vector


COMPONENTS["vector"] = Component(
    "vector", "Vector", "Vector",
    inputs=(Port("A", "point", description="Where the vector starts"),
            Port("B", "point", description="Where the vector points to")),
    outputs=(Port("Vector", "vector",
                  description="The vector from A to B"),),
    icon="vector", solve=_vector,
    sets="Set Vector",
    description="The vector from point A to point B, shown as an arrow")


def _move(G, V):
    if not isinstance(G, TopoDS_Shape):
        return g.translate(G, V.components)
    # Moved, not copied, for the reason Rotate is
    shift = gp_Trsf()
    shift.SetTranslation(gp_Vec(*V.components))
    return G.Moved(TopLoc_Location(shift))


def _delaunay(P, Outline=None):
    from .delaunay import (DelaunayError, inside_outline, triangulate,
                           unique_points)
    from .mesh import MeshShape
    points = unique_points([_coordinates(p) for p in P])
    try:
        faces = triangulate(points[:, :2])
    except DelaunayError as exc:
        raise HydraError(str(exc)) from exc
    if Outline is not None:
        if not g.is_closed_curve(Outline):
            raise HydraError("Outline must be a closed curve")
        from .tessellate import tessellate
        rim = tessellate(Outline).edge_segments.reshape(-1, 2, 3)[:, :, :2]
        # a face stays when its middle, seen from above, is inside
        middles = points[faces][:, :, :2].mean(axis=1)
        faces = faces[inside_outline(middles, rim)]
        if not len(faces):
            raise HydraError("No face of the mesh is inside the outline")
        used, faces = np.unique(faces, return_inverse=True)
        points, faces = points[used], faces.reshape(-1, 3)
    return MeshShape(points, faces)


COMPONENTS["delaunay"] = Component(
    "delaunay", "Delaunay Mesh", "Mesh",
    inputs=(Port("P", "point", access="list", label="Points",
                 description="The points to mesh"),
            Port("Outline", "curve", optional=True, label="Closed curve",
                 description="Faces outside it are left out")),
    outputs=(Port("M", "mesh", label="Mesh",
                  description="The triangles between them"),),
    icon="delaunay", solve=_delaunay,
    description="A mesh of triangles through the points, seen from above: "
                "Delaunay, as Grasshopper's, in the XY plane, the points "
                "keeping their heights; with an Outline, only the faces "
                "inside it")


COMPONENTS["move"] = Component(
    "move", "Move", "Transform",
    inputs=(Port("G", "geometry", description="The geometry to move"),
            Port("V", "vector", Vector((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                 description="How far, and which way, to move it")),
    outputs=(Port("G", "geometry", description="The moved geometry"),),
    icon="move", solve=_move,
    description="Move geometry G along vector V")


COMPONENTS["rotate"] = Component(
    "rotate", "Rotate", "Transform",
    inputs=(Port("Origin", "point", (0.0, 0.0, 0.0),
                 description="The point the vertical axis runs through"),
            Port("Geometry", "geometry", description="The geometry to turn"),
            Port("Angle", "number", 0.0,
                 description="How far to turn it, in degrees")),
    outputs=(Port("Geometry", "geometry",
                  description="The turned geometry"),),
    icon="rotate", solve=_rotate,
    description="Rotate geometry about a vertical axis through Origin, by "
                "Angle in degrees")


# What the search on the canvas offers before anything is typed: the
# components every graph starts from. The rest are found by typing.
QUICK = ("point", "curve", "brep", "mesh", "slider")


# The short names a Grasshopper hand types to find a component.
NICKNAMES = {
    "point": ("pt",), "curve": ("crv",), "mesh": ("msh",),
    "slider": ("num", "sl"), "construct_point": ("pt", "cpt"),
    "toggle": ("bool", "true", "false"), "pipeline": ("pipe",),
    "panel": ("text", "note"),
    "delaunay": ("tri", "triangulate"),
    "vector": ("vec",), "rotate": ("rot",), "move": ("mv",),
    "list_item": ("item", "li"),
    "remove_item": ("cull", "delete", "ri"),
}


def find_components(text: str) -> list[str]:
    """The components a search for `text` finds, best first: those whose
    name starts with it or that go by it for short, then those with a word
    that starts with it, then the rest that have it in their name or
    category."""
    words = text.lower().split()
    if not words:
        return list(QUICK)
    order = list(COMPONENTS)
    found = []
    phrase = " ".join(words)
    for key, comp in COMPONENTS.items():
        title = comp.title.lower()
        short = NICKNAMES.get(key, ())
        said = " ".join((title, comp.category.lower(), key) + short)
        if not all(w in said for w in words):
            continue
        rank = (0 if title.startswith(phrase) or phrase in short
                else 1 if any(t.startswith(words[0]) for t in title.split())
                else 2)
        found.append((rank, order.index(key), key))
    return [key for _rank, _at, key in sorted(found)]


def _list_item(L, i):
    if not L:
        raise HydraError("The list is empty")
    # a fraction is rounded to the nearest place; past either end the
    # index wraps round, so -1 is the last, as in Grasshopper
    return L[int(round(i)) % len(L)]


COMPONENTS["list_item"] = Component(
    "list_item", "List Item", "List",
    inputs=(Port("L", "any", access="list", label="List",
                 description="The list to take an item from"),
            Port("i", "number", 0.0, label="Index",
                 description="Which item: 0 is the first, -1 the last")),
    outputs=(Port("Item", "any", label="Item",
                  description="The item taken"),),
    icon="listitem", solve=_list_item,
    description="The item at index i of list L, counting from 0; -1 is "
                "the last, and an index past the end wraps round")


def _remove_item(L, i):
    # the places to take out, rounded and wrapped round as List Item's are
    gone = {int(round(index)) % len(L) for index in i} if L else set()
    return [item for place, item in enumerate(L) if place not in gone]


COMPONENTS["remove_item"] = Component(
    "remove_item", "Remove Item", "List",
    inputs=(Port("L", "any", access="list", label="List",
                 description="The list to take items out of"),
            Port("i", "number", access="list", label="Index",
                 description="Which items to take out: 0 is the first, "
                             "-1 the last")),
    outputs=(Port("L", "any", access="list", label="List",
                  description="The list without them"),),
    icon="listremove", solve=_remove_item,
    description="List L without the items at the indices i, as Cull Index "
                "does in Grasshopper; -1 is the last")


def set_slider(params: dict, value: float):
    """Put a slider at `value`, kept in its range and to its decimals."""
    value = min(max(float(value), params["min"]), params["max"])
    params["value"] = round(value, params["decimals"])


def set_range(params: dict, low: float, high: float):
    if not low < high:
        raise HydraError("The minimum has to be below the maximum")
    params["min"], params["max"] = float(low), float(high)
    set_slider(params, params["value"])


def set_decimals(params: dict, decimals: int):
    decimals = min(max(int(decimals), 0), MAX_DECIMALS)
    params["decimals"] = decimals
    params["min"] = round(params["min"], decimals)
    params["max"] = round(params["max"], decimals)
    if params["min"] >= params["max"]:
        params["max"] = params["min"] + 10 ** -decimals
    set_slider(params, params["value"])


def format_number(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def describe_item(value) -> str:
    """One item, as a tooltip lists it."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:g}"
    if isinstance(value, Vector):
        return "Vector " + ", ".join(f"{c:g}" for c in value.components)
    if isinstance(value, tuple):
        return "Point " + ", ".join(f"{c:g}" for c in value)
    if isinstance(value, TopoDS_Shape) and g.shape_kind(value) == "point":
        return "Point " + ", ".join(f"{c:g}" for c in _coordinates(value))
    kind = g.shape_kind(value) if _is_shape(value) else type(value).__name__
    return {"solid": "Brep", "surface": "Brep", "curve": "Curve",
            "mesh": "Mesh", "compound": "Geometry"}.get(kind, kind.title())


def list_tree(tree, most: int = 12) -> list:
    """The items of a tree as lines, each after its place in its branch,
    [0], [1]..., the places in line: under a heading for each branch, with
    how much it holds, when there is more than one; at most `most` items,
    the rest counted."""
    lines, shown = [], 0
    several = len(tree.branches) > 1
    widest = len(str(max((len(b) for b in tree.branches.values()),
                         default=1) - 1))
    for path, branch in tree.branches.items():
        if shown >= most:
            break
        if several:
            lines.append("Branch {" + ";".join(str(i) for i in path) + "} · "
                         + count_said(Tree.of(branch)))
        for i, value in enumerate(branch):
            if shown >= most:
                break
            lines.append(("  " if several else "") + f"[{i:>{widest}}] "
                         + describe_item(value))
            shown += 1
    rest = len(tree) - shown
    if rest > 0:
        lines.append(f"… {rest} more")
    return lines


def count_said(tree) -> str:
    """How much a tree holds, in words: "empty", "1 item", "3 items"."""
    count = len(tree)
    if not count:
        return "empty"
    return f"{count} item" + ("" if count == 1 else "s")


def describe(values: list) -> str:
    """What an input holds, said briefly: the numbers or points themselves
    when there are a few, a count of objects otherwise."""
    if not values:
        return "nothing"
    if all(isinstance(v, (int, float)) for v in values):
        shown = ", ".join(f"{v:g}" for v in values[:5])
        return shown + (f" … ({len(values)})" if len(values) > 5 else "")
    if len(values) == 1:
        v = values[0]
        if isinstance(v, tuple):
            return ", ".join(f"{c:g}" for c in v)
        if isinstance(v, TopoDS_Shape) and g.shape_kind(v) == "point":
            return ", ".join(f"{c:g}" for c in _coordinates(v))
        if isinstance(v, Vector):
            return ", ".join(f"{c:g}" for c in v.components)
    noun = "vector" if all(isinstance(v, Vector) for v in values) else "object"
    return f"{len(values)} {noun}" + ("" if len(values) == 1 else "s")


_NUMBER = r"\s*(-?\d+(?:[.,]\d*)?|-?[.,]\d+)\s*"
_RANGE = re.compile(_NUMBER + r"(?:-|–|\.\.|to)" + _NUMBER + r"$")


def type_into_slider(params: dict, text: str) -> str:
    """What is typed straight into a slider: one number sets its value, two
    with a dash between, as in 0.0-12, set its range and decimal places.
    Says which it was, "value" or "range"; ValueError if it was neither."""
    match = _RANGE.match(text)
    if match is not None:
        (low, a), (high, b) = (parse_number(t) for t in match.groups())
        set_range(params, low, high)
        set_decimals(params, max(a, b))
        return "range"
    value, _places = parse_number(text)
    # a value past either end widens the range to reach it
    params["min"] = min(params["min"], value)
    params["max"] = max(params["max"], value)
    set_slider(params, value)
    return "value"


def slider_from_text(text: str):
    """The settings of a slider typed as a number or a range, 7.25 or
    0.0-12, to as many decimal places as typed; None if it is neither."""
    params = dict(COMPONENTS["slider"].params)
    try:
        kind = type_into_slider(params, text)
    except (ValueError, HydraError):
        return None
    if not all(math.isfinite(params[k]) for k in ("value", "min", "max")):
        return None
    if kind == "value":
        value, places = parse_number(text)
        set_decimals(params, places)
        set_slider(params, value)
    return params


def parse_number(text: str) -> tuple[float, int]:
    """A typed number and how many decimal places it was typed to. A
    comma counts as the decimal point, as it is typed in much of Europe."""
    text = text.strip().replace(",", ".")
    value = float(text)
    places = len(text.split(".", 1)[1]) if "." in text else 0
    return value, min(places, MAX_DECIMALS)


@dataclass
class Node:
    id: str
    key: str
    x: float = 0.0
    y: float = 0.0
    params: dict = field(default_factory=dict)
    preview: bool = True
    # internalized data read back from params, kept so it is read once,
    # not on every solve; never saved
    memo: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def component(self) -> Component:
        return COMPONENTS[self.key]

    @property
    def title(self) -> str:
        """The name it was given, or its component's."""
        return self.params.get("name") or self.component.title

    def rename(self, name: str):
        """Give it a name of its own; none, or its component's, takes the
        component's back."""
        name = (name or "").strip()
        if not name or name == self.component.title:
            self.params.pop("name", None)
        else:
            self.params["name"] = name

    def internal(self, key: str):
        """The data internalized under `key`, as a tree, or None."""
        packed = self.params.get("internal", {}).get(key)
        if packed is None:
            return None
        if key not in self.memo:
            self.memo[key] = unpack_tree(packed)
        return self.memo[key]

    def set_internal(self, key: str, tree):
        """Keep `tree` in the graph under `key`, or let it go with None."""
        kept = self.params.setdefault("internal", {})
        self.memo.pop(key, None)
        if tree is None:
            kept.pop(key, None)
        else:
            kept[key] = pack_tree(tree)
        if not kept:
            self.params.pop("internal")


# -- internalized data, as a graph file keeps it ------------------------------

def pack(value):
    """A value as plain data: a number, a point, a vector, or geometry as
    the bytes Serpentine keeps it in."""
    import base64
    if isinstance(value, str):
        return {"text": value}
    if isinstance(value, bool):
        return {"boolean": value}
    if not isinstance(value, (int, float, tuple, Vector)):
        return {"geometry": base64.b64encode(
            g.shape_to_bytes(value)).decode("ascii")}
    if isinstance(value, Vector):
        return {"vector": [list(value.start), list(value.end)]}
    if isinstance(value, tuple):
        return {"point": list(value)}
    return {"number": value}


def unpack(data):
    import base64
    if "text" in data:
        return data["text"]
    if "boolean" in data:
        return bool(data["boolean"])
    if "number" in data:
        return data["number"]
    if "point" in data:
        return tuple(data["point"])
    if "vector" in data:
        start, end = data["vector"]
        return Vector(tuple(start), tuple(end))
    return g.shape_from_bytes(base64.b64decode(data["geometry"]))


def pack_tree(tree) -> dict:
    return {"branches": [[list(path), [pack(v) for v in branch]]
                         for path, branch in tree.branches.items()]}


def unpack_tree(data) -> "Tree":
    return Tree({tuple(path): [unpack(v) for v in branch]
                 for path, branch in data.get("branches", [])})


@dataclass(frozen=True)
class Wire:
    source: str
    output: str
    target: str
    input: str


class Tree:
    """Branches of items under paths, in order. Read as a sequence it is
    every item, branch after branch, so code that wants a list still has
    one."""

    def __init__(self, branches=None):
        self.branches: dict[tuple, list] = {
            tuple(path): list(items)
            for path, items in (branches or {}).items()}

    @classmethod
    def of(cls, items, path=(0,)):
        """A plain list, as a tree of one branch."""
        return cls({path: items})

    @property
    def items(self) -> list:
        return [item for branch in self.branches.values() for item in branch]

    def graft(self) -> "Tree":
        """Every item on a branch of its own, under its branch's path and
        its place in it: {0} with three items becomes {0;0} {0;1} {0;2}."""
        return Tree({path + (i,): [item]
                     for path, branch in self.branches.items()
                     for i, item in enumerate(branch)})

    def flatten(self) -> "Tree":
        return Tree.of(self.items)

    def reverse(self) -> "Tree":
        """Each branch's items the other way round, the branches kept."""
        return Tree({path: branch[::-1]
                     for path, branch in self.branches.items()})

    def merged(self, other: "Tree") -> "Tree":
        """Two trees in one input: a branch under a path both have takes
        both lists, one after the other."""
        out = Tree(self.branches)
        for path, branch in other.branches.items():
            out.branches.setdefault(path, []).extend(branch)
        return out

    def shape(self) -> str:
        """"item", "list" or "tree": what a wire carrying it is drawn as."""
        if len(self.branches) > 1:
            return "tree"
        return "item" if len(self) <= 1 else "list"

    def __len__(self):
        return sum(len(branch) for branch in self.branches.values())

    def __iter__(self):
        return iter(self.items)

    def __getitem__(self, index):
        return self.items[index]

    def __eq__(self, other):
        if isinstance(other, Tree):
            return self.branches == other.branches
        if isinstance(other, list):
            return self.items == other
        return NotImplemented

    def __repr__(self):
        return f"Tree({self.branches!r})"


# in the order they are applied: a branch is turned round, then grafted
# or flattened. Graft and Flatten rule each other out.
FLAGS = ("reverse", "graft", "flatten")


def flag_key(port_name: str, output: bool) -> str:
    """Where a port's Graft, Flatten or Reverse is kept in a node's params."""
    return ("out:" if output else "in:") + port_name


def flags_of(value) -> list:
    """A port's flags, kept as one name or a list of names, in the order
    they are applied."""
    names = [value] if isinstance(value, str) else list(value or ())
    return [f for f in FLAGS if f in names]


def apply_flag(tree: Tree, value) -> Tree:
    for flag in flags_of(value):
        tree = getattr(tree, flag)()
    return tree


@dataclass
class Result:
    outputs: dict = field(default_factory=dict)
    status: str = "ok"            # ok | warning | error
    message: str = ""


class Graph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.wires: list[Wire] = []

    def add_node(self, key: str, x: float = 0.0, y: float = 0.0,
                 params: dict | None = None, node_id: str | None = None):
        if key not in COMPONENTS:
            raise HydraError(f"Unknown component '{key}'")
        comp = COMPONENTS[key]
        values = {"refs": []} if comp.picks else dict(comp.params)
        values.update(params or {})
        node = Node(node_id or uuid.uuid4().hex[:8], key, float(x), float(y),
                    values)
        self.nodes[node.id] = node
        return node

    def remove_node(self, node_id: str):
        self.nodes.pop(node_id, None)
        self.wires = [w for w in self.wires
                      if node_id not in (w.source, w.target)]

    def connect(self, source: str, output: str, target: str,
                input: str, add: bool = False) -> Wire:
        """Wire an output into an input. A new wire takes the place of the
        one already there; with `add` it goes in beside it, and the input
        takes both lists, one after the other, as Shift does in
        Grasshopper."""
        src, dst = self.nodes.get(source), self.nodes.get(target)
        if src is None or dst is None:
            raise HydraError("Both ends of a wire need a component")
        if output not in [p.name for p in src.component.outputs]:
            raise HydraError(f"{src.component.title} has no output {output}")
        if input not in [p.name for p in dst.component.inputs]:
            raise HydraError(f"{dst.component.title} has no input {input}")
        if source == target or self._reaches(target, source):
            raise HydraError("A wire cannot loop back into its own source")
        out_kind = _port(src.component.outputs, output).kind
        in_kind = _port(dst.component.inputs, input).kind
        if not takes(in_kind, out_kind):
            raise HydraError(f"{dst.component.title} {input} takes "
                             f"{_said(in_kind)}, not {_said(out_kind)}")
        wire = Wire(source, output, target, input)
        if not add:
            self.wires = [w for w in self.wires
                          if (w.target, w.input) != (target, input)]
        if wire not in self.wires:
            self.wires.append(wire)
        return wire

    def wire_between(self, source, output, target, input):
        """The wire from that output into that input, if there is one."""
        wire = Wire(source, output, target, input)
        return wire if wire in self.wires else None

    def disconnect(self, wire: Wire):
        if wire in self.wires:
            self.wires.remove(wire)

    def _reaches(self, start: str, goal: str) -> bool:
        stack, seen = [start], set()
        while stack:
            node = stack.pop()
            if node == goal:
                return True
            if node in seen:
                continue
            seen.add(node)
            stack.extend(w.target for w in self.wires if w.source == node)
        return False

    def order(self) -> list[str]:
        """Every component after the ones wired into it."""
        waiting = {nid: 0 for nid in self.nodes}
        for w in self.wires:
            waiting[w.target] += 1
        ready = [nid for nid, n in waiting.items() if n == 0]
        order = []
        while ready:
            nid = ready.pop(0)
            order.append(nid)
            for w in self.wires:
                if w.source == nid:
                    waiting[w.target] -= 1
                    if waiting[w.target] == 0:
                        ready.append(w.target)
        return order

    def solve(self, scene) -> dict[str, Result]:
        results: dict[str, Result] = {}
        for nid in self.order():
            results[nid] = self._solve_node(self.nodes[nid], scene, results)
        return results

    def _solve_node(self, node: Node, scene, results) -> Result:
        result = self._made(node, scene, results)
        # an output's Graft or Flatten, on what it hands on
        flags = node.params.get("flags", {})
        for name, tree in list(result.outputs.items()):
            result.outputs[name] = apply_flag(
                tree, flags.get(flag_key(name, True)))
        return result

    def _made(self, node: Node, scene, results) -> Result:
        comp = node.component
        if comp.solve is not None:
            return self._compute(node, results)
        if node.key == "pipeline":
            return self._pipe(node, scene)
        if node.key == "panel":
            return self._panel(node, results)
        if not comp.picks:
            return Result({comp.outputs[0].name:
                           Tree.of([node.params["value"]])})
        kept = node.internal("out")
        if kept is not None:
            # internalized: the graph's own copy, whatever the model holds
            return Result({comp.outputs[0].name: kept})
        refs = node.params.get("refs", [])
        found = [obj for obj in map(scene.get, refs) if obj is not None]
        result = Result({comp.outputs[0].name:
                         Tree.of([o.shape for o in found])})
        if not refs:
            result.status = "warning"
            result.message = (f"Right-click and {comp.sets}... to pick "
                              f"{comp.plural} in the model")
        elif len(found) < len(refs):
            result.status = "warning"
            gone = len(refs) - len(found)
            result.message = (f"{gone} picked object"
                              + (" is" if gone == 1 else "s are")
                              + " no longer in the model")
        return result

    def _panel(self, node, results) -> Result:
        """What comes in, handed on as it is; with no wire, the text."""
        port = node.component.inputs[0]
        tree, wired = self.input_values(node.id, port, results)
        if wired:
            return Result({"Out": tree})
        return Result({"Out": Tree.of(panel_lines(
            node.params.get("text", "")))})

    def _pipe(self, node, scene) -> Result:
        found = piped(scene, node.params)
        result = Result({"Geometry": Tree.of([o.shape for o in found])})
        path = node.params.get("layer")
        if path is not None and scene.layers.find_by_path(path) is None:
            result.status = "warning"
            result.message = f"There is no layer {path} in the model"
        elif not node.params.get("types"):
            result.status = "warning"
            result.message = "Right-click and choose the types to take"
        return result

    def input_values(self, node_id: str, port: Port, results) -> tuple:
        """What reaches an input, as the component works on it, and whether
        it comes by wire: the source's output if one is wired in; if not,
        what was internalized in it, or set for it by picking in the model,
        or else its default. The input's Graft or Flatten is applied."""
        node = self.nodes[node_id]
        flag = node.params.get("flags", {}).get(flag_key(port.name, False))
        wires = [w for w in self.wires
                 if w.target == node_id and w.input == port.name]
        if not wires:
            kept = node.internal(port.name)
            if kept is not None:
                return apply_flag(kept, flag), False
            picked = node.params.get("set", {}).get(port.name)
            if picked is not None:
                return apply_flag(Tree.of([tuple(picked)]), flag), False
            values = [] if port.default is None else [port.default]
            return apply_flag(Tree.of(values), flag), False
        return apply_flag(self.wired_tree(node_id, port.name, results),
                          flag), True

    def wired_tree(self, node_id, input, results) -> "Tree":
        """What the wires into an input bring, before its own flags:
        several wires' trees in one, in the order they were wired."""
        tree = Tree()
        for wire in self.wires:
            if wire.target == node_id and wire.input == input:
                source = results.get(wire.source)
                if source is not None:
                    tree = tree.merged(source.outputs.get(wire.output,
                                                          Tree()))
        return tree

    # ---------------------------------------------------------- internalize

    def internalize(self, node_id, scene) -> int:
        """Keep a geometry component's objects as the graph's own copy, no
        longer the model's: deleted or changed there, they stay as they
        were here. Returns how many."""
        from ..script_runtime import isolated_copy
        node = self.nodes[node_id]
        found = [obj for obj in map(scene.get, node.params.get("refs", []))
                 if obj is not None]
        if not found:
            raise HydraError("Nothing picked to internalize")
        node.set_internal("out", Tree.of([isolated_copy(o.shape)
                                          for o in found]))
        node.params["refs"] = []
        return len(found)

    def internalize_input(self, node_id, input, results) -> int:
        """Keep what the wires bring into an input as the input's own, and
        take the wires away. Its flags stay and still apply. Returns how
        many items."""
        tree = self.wired_tree(node_id, input, results)
        if not len(tree):
            raise HydraError("No data comes into it to internalize")
        self.nodes[node_id].set_internal(input, tree)
        self.wires = [w for w in self.wires
                      if (w.target, w.input) != (node_id, input)]
        return len(tree)

    def _compute(self, node: Node, results) -> Result:
        comp = node.component
        empty = {p.name: Tree() for p in comp.outputs}
        args, missing = {}, []
        for port in comp.inputs:
            tree, _wired = self.input_values(node.id, port, results)
            if not len(tree) and port.optional:
                tree = Tree.of([None])      # worked without, as asked
            elif not len(tree):
                missing.append(port.name)
            args[port.name] = tree
        if missing:
            said = "Connect " + " and ".join(missing)
            if comp.sets:
                said += f", or right-click and {comp.sets}..."
            return Result(empty, "warning", said)
        # the branches pair by the longest list, and the paths of the input
        # with the most of them name the branches that come out
        branches = {name: list(tree.branches.items())
                    for name, tree in args.items()}
        widest = max(branches.values(), key=len)
        out = Tree()
        for b in range(len(widest)):
            pair = {name: bs[min(b, len(bs) - 1)][1]
                    for name, bs in branches.items()}
            whole = {p.name for p in comp.inputs if p.access == "list"}
            items = {name: values for name, values in pair.items()
                     if name not in whole}
            made = []
            if all(pair.values()):
                # then, within the pair, their items the same way; a list
                # input takes its branch whole, every time
                for i in range(max((len(v) for v in items.values()),
                                   default=1)):
                    kinds = {p.name: p.kind for p in comp.inputs}
                    item = {name: coerce(kinds[name],
                                         values[min(i, len(values) - 1)])
                            for name, values in items.items()}
                    item.update({name: list(pair[name]) for name in whole})
                    wrong = self._misfit(comp, item)
                    if wrong:
                        return Result(empty, "error", wrong)
                    try:
                        value = comp.solve(**item)
                    except (HydraError, g.GeometryError, ValueError,
                            RuntimeError) as exc:
                        return Result(empty, "error",
                                      str(exc) or type(exc).__name__)
                    # an output that gives lists gives its items to the
                    # branch, not the list as one item
                    if comp.outputs[0].access == "list":
                        made.extend(value)
                    else:
                        made.append(value)
            out.branches[widest[b][0]] = made
        return Result({comp.outputs[0].name: out})

    @staticmethod
    def _misfit(comp, item):
        """What is wrong with the items a component is about to work on,
        when something that may carry anything brought the wrong thing."""
        for port in comp.inputs:
            values = (item[port.name] if port.access == "list"
                      else [item[port.name]])
            for value in values:
                if value is None and port.optional:
                    continue            # left empty, as it may be
                if not fits(port.kind, value):
                    return (f"{comp.title} {port.name} takes "
                            f"{_said(port.kind)}, not {said_of(value)}")
        return ""

    def preview_shapes(self, results: dict[str, Result], only=None,
                       hidden=False) -> list:
        """What the components show in the model: the shown ones, or with
        `only` those components, and with `hidden` the hidden among them
        too."""
        shapes = []
        for nid, result in results.items():
            if only is not None and nid not in only:
                continue
            if not (hidden or self.nodes[nid].preview):
                continue
            for port in self.nodes[nid].component.outputs:
                values = result.outputs.get(port.name, [])
                if port.kind in GEOMETRY_KINDS:
                    shapes.extend(values)
                elif port.kind == "vector":
                    shapes.extend(arrow(v.start, v.end) for v in values)
                elif port.kind == "any":
                    # what it carries shows as what it is
                    shapes.extend(v for v in values if _is_shape(v))
                    shapes.extend(arrow(v.start, v.end) for v in values
                                  if isinstance(v, Vector))
        return shapes

    # ------------------------------------------------------------- copying

    def part(self, node_ids) -> dict:
        """Some components and the wires between them, as to_dict writes a
        graph: what Copy puts on the clipboard. Wires from components left
        out stay behind, as they do in Grasshopper."""
        ids = set(node_ids)
        data = self.to_dict()
        data["nodes"] = [n for n in data["nodes"] if n["id"] in ids]
        data["wires"] = [w for w in data["wires"]
                         if w[0] in ids and w[2] in ids]
        return data

    def paste(self, data: dict, dx: float = 0.0, dy: float = 0.0) -> list:
        """Add a copied part as new components, moved by dx and dy, wired
        among themselves as they were. Returns the new components' ids."""
        import copy
        fresh = {}
        for item in data.get("nodes", []):
            if item.get("key") not in COMPONENTS:
                continue
            node = self.add_node(item["key"], item.get("x", 0.0) + dx,
                                 item.get("y", 0.0) + dy,
                                 copy.deepcopy(item.get("params")))
            node.preview = bool(item.get("preview", True))
            fresh[item.get("id")] = node.id
        for source, output, target, input in data.get("wires", []):
            if source in fresh and target in fresh:
                try:
                    self.connect(fresh[source], output, fresh[target], input)
                except HydraError:
                    pass
        return list(fresh.values())

    # ---------------------------------------------------------- persistence

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "nodes": [{"id": n.id, "key": n.key, "x": n.x, "y": n.y,
                       "params": dict(n.params), "preview": n.preview}
                      for n in self.nodes.values()],
            "wires": [[w.source, w.output, w.target, w.input]
                      for w in self.wires],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Graph":
        graph = cls()
        for item in data.get("nodes", []):
            if item.get("key") not in COMPONENTS:
                continue
            node = graph.add_node(item["key"], item.get("x", 0.0),
                                  item.get("y", 0.0), item.get("params"),
                                  node_id=item.get("id"))
            node.preview = bool(item.get("preview", True))
        for wire in data.get("wires", []):
            try:
                graph.connect(*wire)
            except (HydraError, TypeError):
                pass
        return graph


def _port(ports, name) -> Port:
    return next(p for p in ports if p.name == name)


def _said(kind: str) -> str:
    return {"geometry": "geometry", "number": "numbers",
            "mesh": "meshes"}.get(kind, kind + "s")
