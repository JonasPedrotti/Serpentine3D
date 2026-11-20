"""Delete takes the held triangles of a mesh and leaves the rest of it.

A triangle held with Ctrl+Shift is a face like a solid's, and Delete with
one held meant that face. A mesh was sent to the solid's way of taking a
face out, which knows nothing of meshes, so the triangle could only go
with the whole mesh. Now the held triangles go and the mesh stays, until
the last of them goes with it.
"""

from __future__ import annotations

import numpy as np
import pytest

import serpentine3d.commands  # registers all commands  # noqa: F401
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core.history import History
from serpentine3d.core.mesh import MeshShape
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


def _sheet():
    return MeshShape(np.array([(0, 0, 0), (10, 0, 0), (10, 10, 0),
                               (0, 10, 0)], float), [[0, 1, 2], [0, 2, 3]])


@pytest.fixture
def env(_qapp):
    scene = Scene()
    sel = SelectionManager(scene)
    ctx = CommandContext(scene, sel, History(scene))
    return scene, sel, CommandProcessor(ctx)


def test_delete_takes_a_held_triangle_and_leaves_the_mesh(env):
    scene, sel, proc = env
    mesh = scene.add(_sheet())
    sel.set_subobjects([(mesh.id, "face", 0)])
    proc.run("delete")
    left = scene.get(mesh.id)
    assert left is not None and len(left.shape.triangles) == 1
    sel.set_subobjects([(mesh.id, "face", 0)])
    proc.run("delete")
    assert scene.get(mesh.id) is None
