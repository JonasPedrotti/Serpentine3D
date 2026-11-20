"""A flat face its surface cannot be trimmed on is trimmed on its plane.

Rhino keeps a flat face as a degree 1 surface, and some edges run over it
as polylines whose parameter crawls along one stretch and races along the
next. Trimmed by a loop of such edges, the surface gave an invalid face:
OpenCascade could not lay the edges on it in its parameters. The importer
then fell back to Rhino's render mesh for that face, and a closed
polysurface came in as an open one with a mesh beside it. The face's own
plane takes the same loop exactly, so it is tried before the mesh.
"""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry
from serpentine3d.fileio import rhino

L_SHAPE = [(0, 0), (3, 0), (3, 0.5), (0.5, 0.5), (0.5, 4), (0, 4)]


class _Trim:
    def __init__(self, index):
        self.EdgeIndex = index
        self.IsReversed = False


class _Loop:
    LoopType = "BrepLoopType.Outer"

    def __init__(self, count):
        self.Trims = [_Trim(i) for i in range(count)]
        self.TrimCount = count


class _Face:
    """The little of a rhino3dm face the loop path reads."""

    def __init__(self, count):
        self.Loops = [_Loop(count)]


def _surface(x0, y0, z, bulge=0.0):
    """A surface over the L's box, as Rhino keeps a flat face: degree 2
    so `bulge` can lift its middle off the plane."""
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    poles = TColgp_Array2OfPnt(1, 3, 1, 3)
    for i, x in enumerate((x0 - 1, x0 + 1.5, x0 + 4), 1):
        for j, y in enumerate((y0 - 1, y0 + 2, y0 + 5), 1):
            lift = bulge if (i, j) == (2, 2) else 0.0
            poles.SetValue(i, j, gp_Pnt(x, y, z + lift))
    knots = TColStd_Array1OfReal(1, 2)
    knots.SetValue(1, 0.0)
    knots.SetValue(2, 1.0)
    mults = TColStd_Array1OfInteger(1, 2)
    mults.SetValue(1, 3)
    mults.SetValue(2, 3)
    return Geom_BSplineSurface(poles, knots, knots, mults, mults, 2, 2)


def test_a_flat_surface_has_a_plane_and_a_curved_one_none():
    from OCP.Geom import Geom_Plane
    plane = rhino._plane_of(_surface(683872.0, 5140950.0, 1373.26))
    assert isinstance(plane, Geom_Plane)
    assert abs(plane.Pln().Axis().Direction().Z()) == pytest.approx(1.0)
    assert rhino._plane_of(_surface(0.0, 0.0, 0.0, bulge=1.0)) is None


@pytest.mark.parametrize("x0, y0", [(0.0, 0.0), (683872.0, 5140950.0)])
def test_a_loop_the_surface_refuses_is_trimmed_on_its_plane(monkeypatch,
                                                           x0, y0):
    from OCP.Geom import Geom_Plane
    on_surface = rhino._trim_by_loops

    def refuses_all_but_planes(surf, *args):
        if not isinstance(surf, Geom_Plane):
            return None             # as the surface did, for those edges
        return on_surface(surf, *args)

    monkeypatch.setattr(rhino, "_trim_by_loops", refuses_all_but_planes)
    z = 1373.26
    c = [(x0 + x, y0 + y, z) for x, y in L_SHAPE]
    table = {i: geometry.make_line(a, b)
             for i, (a, b) in enumerate(zip(c, c[1:] + c[:1]))}
    face = rhino._face_from_edge_loops(_Face(len(table)),
                                       _surface(x0, y0, z), table)
    assert face is not None, "the face fell back to its render mesh"
    assert geometry.is_valid(face)
    assert geometry.surface_area(face) == pytest.approx(3.25, rel=1e-6)
    lo, hi = geometry.bbox(face)
    assert np.allclose(lo, (x0, y0, z), atol=1e-6)
    assert np.allclose(hi, (x0 + 3, y0 + 4, z), atol=1e-6)


def test_a_curved_surface_that_refuses_its_loop_still_gives_none(
        monkeypatch):
    monkeypatch.setattr(rhino, "_trim_by_loops", lambda *a: None)
    c = [(x, y, 0.0) for x, y in L_SHAPE]
    table = {i: geometry.make_line(a, b)
             for i, (a, b) in enumerate(zip(c, c[1:] + c[:1]))}
    assert rhino._face_from_edge_loops(
        _Face(len(table)), _surface(0, 0, 0, bulge=1.0), table) is None
