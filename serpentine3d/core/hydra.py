"""Hydra: a visual graph of components, in the spirit of Grasshopper. Kept
free of Qt so the graph solves the same in tests and in the editor.

The geometry components each hold model objects of their kind, set by
picking them, and hand them on as a list. A Number Slider hands on one
number, between a range and to as many decimal places as it is set to.

A component with inputs works on one item of each at a time and repeats
for the longest list, reusing the last item of the shorter ones: three
curves and one angle make three rotated curves.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable

from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from . import geometry as g


class HydraError(Exception):
    pass


@dataclass(frozen=True)
class Port:
    name: str
    kind: str     # point | curve | brep | mesh | geometry | number | vector
    # what an input without a wire stands for; None means it needs one
    default: object = None


# Which outputs an input takes: a geometry input any geometry, a point
# input points alone, a number input numbers alone.
_TAKES = {"geometry": ("point", "curve", "brep", "mesh", "geometry"),
          "point": ("point",), "number": ("number",), "vector": ("vector",)}


def takes(input_kind: str, output_kind: str) -> bool:
    return output_kind in _TAKES.get(input_kind, (input_kind,))


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
CATEGORIES = ("Geometry", "Input", "Vector", "Transform")
GEOMETRY_KINDS = ("point", "curve", "brep", "mesh", "geometry")
MAX_DECIMALS = 6


def _geometry(key, title, short, kinds, icon, description):
    COMPONENTS[key] = Component(key, title, "Geometry",
                                outputs=(Port(title, key),), picks=kinds,
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

COMPONENTS["slider"] = Component(
    "slider", "Number Slider", "Input", outputs=(Port("Number", "number"),),
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
    inputs=(Port("X", "number", 0.0), Port("Y", "number", 0.0),
            Port("Z", "number", 0.0)),
    outputs=(Port("Point", "point"),), icon="point",
    solve=lambda X, Y, Z: g.make_point((X, Y, Z)),
    description="A point from its X, Y and Z coordinates")


def _vector(A, B):
    vector = Vector(_coordinates(A), _coordinates(B))
    if vector.length < 1e-12:
        raise HydraError("A and B are the same point")
    return vector


COMPONENTS["vector"] = Component(
    "vector", "Vector", "Vector",
    inputs=(Port("A", "point"), Port("B", "point")),
    outputs=(Port("Vector", "vector"),), icon="vector", solve=_vector,
    sets="Set Vector",
    description="The vector from point A to point B, shown as an arrow")


def _move(G, V):
    if not isinstance(G, TopoDS_Shape):
        return g.translate(G, V.components)
    # Moved, not copied, for the reason Rotate is
    shift = gp_Trsf()
    shift.SetTranslation(gp_Vec(*V.components))
    return G.Moved(TopLoc_Location(shift))


COMPONENTS["move"] = Component(
    "move", "Move", "Transform",
    inputs=(Port("G", "geometry"),
            Port("V", "vector", Vector((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))),
    outputs=(Port("G", "geometry"),), icon="move", solve=_move,
    description="Move geometry G along vector V")


COMPONENTS["rotate"] = Component(
    "rotate", "Rotate", "Transform",
    inputs=(Port("Origin", "point", (0.0, 0.0, 0.0)),
            Port("Geometry", "geometry"),
            Port("Angle", "number", 0.0)),
    outputs=(Port("Geometry", "geometry"),),
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
    "vector": ("vec",), "rotate": ("rot",), "move": ("mv",),
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

    @property
    def component(self) -> Component:
        return COMPONENTS[self.key]


@dataclass(frozen=True)
class Wire:
    source: str
    output: str
    target: str
    input: str


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
                input: str) -> Wire:
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
        # one wire into an input: a new one takes the old one's place
        self.wires = [w for w in self.wires
                      if (w.target, w.input) != (target, input)]
        wire = Wire(source, output, target, input)
        self.wires.append(wire)
        return wire

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
        comp = node.component
        if comp.solve is not None:
            return self._compute(node, results)
        if not comp.picks:
            return Result({comp.outputs[0].name: [node.params["value"]]})
        refs = node.params.get("refs", [])
        found = [obj for obj in map(scene.get, refs) if obj is not None]
        result = Result({comp.outputs[0].name: [o.shape for o in found]})
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

    def input_values(self, node_id: str, port: Port, results) -> tuple:
        """What reaches an input, and whether it comes by wire: the source's
        output if one is wired in; if not, what was set for it by picking in
        the model, or else its default."""
        wire = next((w for w in self.wires if w.target == node_id
                     and w.input == port.name), None)
        if wire is None:
            picked = self.nodes[node_id].params.get("set", {}).get(port.name)
            if picked is not None:
                return [tuple(picked)], False
            return ([] if port.default is None else [port.default]), False
        source = results.get(wire.source)
        return (source.outputs.get(wire.output, []) if source else []), True

    def _compute(self, node: Node, results) -> Result:
        comp = node.component
        empty = {p.name: [] for p in comp.outputs}
        args, missing = {}, []
        for port in comp.inputs:
            values, _wired = self.input_values(node.id, port, results)
            if not values:
                missing.append(port.name)
            args[port.name] = values
        if missing:
            said = "Connect " + " and ".join(missing)
            if comp.sets:
                said += f", or right-click and {comp.sets}..."
            return Result(empty, "warning", said)
        outputs = {p.name: [] for p in comp.outputs}
        for i in range(max(len(v) for v in args.values())):
            item = {name: values[min(i, len(values) - 1)]
                    for name, values in args.items()}
            try:
                value = comp.solve(**item)
            except (HydraError, g.GeometryError, ValueError,
                    RuntimeError) as exc:
                return Result(empty, "error", str(exc) or type(exc).__name__)
            outputs[comp.outputs[0].name].append(value)
        return Result(outputs)

    def preview_shapes(self, results: dict[str, Result]) -> list:
        shapes = []
        for nid, result in results.items():
            if not self.nodes[nid].preview:
                continue
            for port in self.nodes[nid].component.outputs:
                values = result.outputs.get(port.name, [])
                if port.kind in GEOMETRY_KINDS:
                    shapes.extend(values)
                elif port.kind == "vector":
                    shapes.extend(arrow(v.start, v.end) for v in values)
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
