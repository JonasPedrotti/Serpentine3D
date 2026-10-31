"""Construct Point and Vector."""

from __future__ import annotations

from ... import geometry as g
from . import COMPONENTS, Component
from ..kinds import HydraError, Port, Vector, coordinates


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
    vector = Vector(coordinates(A), coordinates(B))
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
