"""A polyline kept as one edge is drawn through every one of its kinks.

Rhino keeps a polyline as one edge of degree 1. Sampled by deflection
like any other curve, a long one far from home lost its kinks: the line
drawn ran metres from the points it was made of, though those points were
where they belonged. A curve of degree 1 is the polygon through its knots,
so that is what is drawn.
"""

from __future__ import annotations

import numpy as np
import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.tessellate import tessellate


def _one_edge_polyline(points):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.Geom import Geom_BSplineCurve
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    n = len(points)
    poles = TColgp_Array1OfPnt(1, n)
    knots = TColStd_Array1OfReal(1, n)
    mults = TColStd_Array1OfInteger(1, n)
    run = 0.0
    for i, p in enumerate(points, 1):
        if i > 1:
            run += float(np.linalg.norm(np.subtract(p, points[i - 2])))
        poles.SetValue(i, gp_Pnt(*p))
        knots.SetValue(i, run)
        mults.SetValue(i, 2 if i in (1, n) else 1)
    return BRepBuilderAPI_MakeEdge(
        Geom_BSplineCurve(poles, knots, mults, 1)).Edge()


@pytest.mark.parametrize("x0, y0", [(0.0, 0.0), (683872.0, 5140950.0)])
def test_every_kink_lies_on_the_drawn_line(x0, y0):
    rng = np.random.default_rng(3)
    walk = np.cumsum(rng.normal(0, 1.5, (136, 2)), axis=0)
    points = [(x0 + x, y0 + y, 1373.26) for x, y in walk]
    shape = _one_edge_polyline(points)
    drawn = tessellate(shape).edge_segments.reshape(-1, 3).astype(float)
    for p in g.curve_points(shape):
        gap = float(np.min(np.linalg.norm(drawn - np.asarray(p), axis=1)))
        assert gap < 1e-3, f"a kink is drawn {gap:.3f} away from itself"
