"""Exporting a selection as .serp writes the selection, not the drawing.

Every other format took only the objects picked; .serp saved the whole
scene. On a large drawing, two small meshes picked for export wrote the
other nine thousand objects too, a minute of the window not answering.
The selection goes with every layer and block it might be on, and the
history that builds one picked object from another, but not the sheets,
which show the whole model.
"""

from __future__ import annotations

from serpentine3d import fileio
from serpentine3d.core import geometry as g
from serpentine3d.core.layout import Layout
from serpentine3d.core.scene import Scene
from serpentine3d.fileio import native


def _drawing():
    scene = Scene()
    picked = [scene.add(g.make_box((0, 0, 0), 1, 1, 1), name="Picked box"),
              scene.add(g.make_line((0, 0, 0), (5, 0, 0)), name="Picked line")]
    for i in range(20):
        scene.add(g.make_box((i * 3, 5, 0), 1, 1, 1), name=f"Other {i}")
    scene.layouts.append(Layout(name="Sheet"))
    return scene, [o.id for o in picked]


def test_only_the_picked_objects_are_written(tmp_path):
    scene, ids = _drawing()
    path = str(tmp_path / "picked.serp")
    fileio.export_file(scene, path, only_ids=ids)
    back = Scene()
    native.load_scene(back, path)
    assert sorted(o.name for o in back.all()) == ["Picked box",
                                                  "Picked line"]
    assert back.layouts == []


def test_history_between_picked_objects_is_kept_and_the_rest_left(tmp_path):
    scene, ids = _drawing()
    other = next(o.id for o in scene.all() if o.id not in ids)
    scene.add_record("copy", [ids[0]], ids[1])
    scene.add_record("copy", [other], ids[1])
    path = str(tmp_path / "picked.serp")
    fileio.export_file(scene, path, only_ids=ids)
    back = Scene()
    native.load_scene(back, path)
    assert [(r["inputs"], r["output"]) for r in back.history_records] == [
        ([ids[0]], ids[1])]


def test_without_a_selection_the_whole_drawing_is_written(tmp_path):
    scene, _ids = _drawing()
    path = str(tmp_path / "all.serp")
    fileio.export_file(scene, path)
    back = Scene()
    native.load_scene(back, path)
    assert len(back.all()) == 22
    assert [lay.name for lay in back.layouts] == ["Sheet"]
