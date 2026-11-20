"""A black mesh's edges are drawn grey, so its triangles can be told apart.

Face edges are the object's colour darkened, which for a black mesh was
black on black. A mesh's edges are never darker than a mid grey; a bright
mesh keeps its darkened edge, and a solid keeps the edges it always had.
"""

from __future__ import annotations

import pytest

from serpentine3d.ui.viewport import MESH_EDGE_FLOOR, face_edge_color


def test_a_black_mesh_s_edges_are_grey():
    assert face_edge_color((0.0, 0.0, 0.0), "mesh")[:3] == pytest.approx(
        (MESH_EDGE_FLOOR,) * 3)


def test_a_bright_mesh_keeps_its_darkened_edges():
    assert face_edge_color((1.0, 1.0, 1.0), "mesh")[:3] == pytest.approx(
        (0.35, 0.35, 0.35))


def test_a_black_solid_is_left_as_it_was():
    assert face_edge_color((0.0, 0.0, 0.0), "solid")[:3] == (0.0, 0.0, 0.0)
