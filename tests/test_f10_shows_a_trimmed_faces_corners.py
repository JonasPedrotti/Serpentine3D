"""PointsOn (F10) on a face cut out of a bigger surface shows the face's
corners, in the order its boundary runs, rather than the four control
points of the plane it was cut from; dragging one moves that corner and
the face keeps its cut. A surface that is the whole of its own surface
keeps its control points."""

from __future__ import annotations

import pytest

from serpentine3d.core import geometry as g

FAR = [0.0, 100000.0]


def _face(points, off):
    return g.planar_face(g.make_polyline(
        [(x + off, y + off, z) for x, y, z in points], closed=True))


L_SHAPE = [(0, 0, 0), (6, 0, 0), (6, 2, 0), (2, 2, 0), (2, 5, 0), (0, 5, 0)]
# a rectangle with points along its edges, as a face split in Rhino keeps
DOTTED = [(0, 0, 0), (3, 0, 0), (6, 0, 0), (6, 2, 0), (6, 4, 0), (3, 4, 0),
          (0, 4, 0), (0, 2, 0)]


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
@pytest.mark.parametrize("outline", [L_SHAPE, DOTTED], ids=["l", "dotted"])
def test_a_cut_face_shows_every_corner_in_order(off, outline):
    face = _face(outline, off)
    pts, grid = g.surface_control_points(face)
    assert grid == ("ring", len(outline))
    expect = [(x + off, y + off, z) for x, y, z in outline]
    start = min(range(len(pts)),
                key=lambda i: sum((a - b) ** 2 for a, b in zip(pts[i], expect[0])))
    ring = pts[start:] + pts[:start]
    if ring[1] != pytest.approx(expect[1]):
        ring = [ring[0]] + ring[1:][::-1]
    for got, want in zip(ring, expect):
        assert got == pytest.approx(want)


@pytest.mark.parametrize("off", FAR, ids=["near", "far"])
def test_dragging_a_corner_keeps_the_cut(off):
    face = _face(L_SHAPE, off)
    pts, _grid = g.surface_control_points(face)
    i = min(range(len(pts)), key=lambda k: abs(pts[k][0] - off - 2)
            + abs(pts[k][1] - off - 2))
    moved = g.move_surface_control_point(face, i, (off + 3, off + 3, 0))
    assert g.shape_kind(moved) == "surface" and g.is_valid(moved)
    assert len(g.faces_of(moved)) == 1
    after, grid = g.surface_control_points(moved)
    assert grid == ("ring", 6)
    assert any(p == pytest.approx((off + 3, off + 3, 0)) for p in after)
    assert g.surface_area(moved) == pytest.approx(21.5)   # shoelace


def test_a_whole_surface_keeps_its_control_points():
    plane = g.faces_of(g.make_box((0, 0, 0), 2, 2, 2))[0]
    assert g.surface_control_points(plane)[1] == (2, 2)
    cone = g.faces_of(g.loft([g.make_circle((0, 0, 0), 4),
                              g.make_circle((0, 0, 8), 2)]))[0]
    _pts, grid = g.surface_control_points(cone)
    assert grid[0] != "ring"
