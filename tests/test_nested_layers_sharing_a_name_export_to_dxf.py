"""Nested layers that share a name each get a DXF layer of their own.

DXF layers are flat. A drawing with 2D::KOTEN and 3D::KOTEN wrote both as
KOTEN, and the export stopped with "LAYER 'KOTEN' already exists". Layers
whose names clash, in any case, go by their whole path joined with $, as
Rhino writes them; a name no other layer has stays as it was.
"""

from __future__ import annotations

import ezdxf

from serpentine3d import fileio
from serpentine3d.core import geometry as g
from serpentine3d.core.scene import Scene
from serpentine3d.fileio.dxf import dxf_layer_names


def _drawing():
    scene = Scene()
    layers = scene.layers
    two = layers.create("2D")
    three = layers.create("3D")
    flat = layers.create("KOTEN", parent=two.id)
    raised = layers.create("koten", parent=three.id)
    walls = layers.create("Walls", parent=three.id)
    for layer, x in ((flat, 0), (raised, 5), (walls, 10)):
        obj = scene.add(g.make_line((x, 0, 0), (x + 1, 0, 0)))
        scene.update(obj.id, layer_id=layer.id)
    return scene, flat, raised, walls


def test_clashing_names_go_by_their_path():
    scene, flat, raised, walls = _drawing()
    names = dxf_layer_names(scene.layers)
    assert names[flat.id] == "2D$KOTEN"
    assert names[raised.id] == "3D$koten"
    assert names[walls.id] == "Walls"


def test_the_drawing_exports_with_each_object_on_its_own_layer(tmp_path):
    scene, _flat, _raised, _walls = _drawing()
    path = str(tmp_path / "nested.dxf")
    fileio.export_file(scene, path)
    doc = ezdxf.readfile(path)
    on = sorted(e.dxf.layer for e in doc.modelspace())
    assert on == ["2D$KOTEN", "3D$koten", "Walls"]
