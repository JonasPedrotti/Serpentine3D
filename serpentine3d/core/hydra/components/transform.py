"""Move and Rotate."""

from __future__ import annotations

import math

from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from ... import geometry as g
from . import COMPONENTS, Component
from ..kinds import Port, Vector, coordinates


def _rotate(Origin, Geometry, Angle):
    center = Origin if isinstance(Origin, tuple) else coordinates(Origin)
    if not isinstance(Geometry, TopoDS_Shape):
        return g.rotate(Geometry, center, (0.0, 0.0, 1.0), Angle)
    # Moved rather than copied: the result shares its surfaces with what
    # was rotated, so the preview meshes it once and only turns the mesh
    # while a slider is dragged.
    turn = gp_Trsf()
    turn.SetRotation(gp_Ax1(gp_Pnt(*center), gp_Dir(0.0, 0.0, 1.0)),
                     math.radians(Angle))
    return Geometry.Moved(TopLoc_Location(turn))


def _move(G, V):
    if not isinstance(G, TopoDS_Shape):
        return g.translate(G, V.components)
    # Moved, not copied, for the reason Rotate is
    shift = gp_Trsf()
    shift.SetTranslation(gp_Vec(*V.components))
    return G.Moved(TopLoc_Location(shift))


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
