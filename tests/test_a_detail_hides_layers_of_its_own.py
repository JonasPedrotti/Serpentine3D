"""A detail can leave layers out without hiding them anywhere else (#38).

A plan and an enlarged detail on one sheet often want different layers:
the furniture in the plan and not in the stair detail, the grid in neither.
Rhino, Revit and Archicad all set this per view, and so does a detail now:
it keeps a list of the layers it leaves out, a sublayer going with its
parent, and every way a detail is drawn honours it: the hidden-line pass
the screen, the PDF and the DXF all read, and the shaded draw on screen
and in a PDF's raster. The model and every other detail keep showing them.
"""

from __future__ import annotations

import pytest

from serpentine3d.core import geometry as g
from serpentine3d.core.layout import DetailView, Layout
from serpentine3d.ui.camera import STANDARD_VIEWS


@pytest.fixture
def sheet(_qapp):
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w.resize(1200, 800)
    walls = w.scene.layers.create("Walls", color=(1.0, 0.0, 0.0))
    inner = w.scene.layers.create("Interior", parent=walls.id,
                                  color=(1.0, 0.0, 0.0))
    grid = w.scene.layers.create("Grid", color=(0.0, 0.0, 1.0))
    made = {}
    for name, layer, x in (("wall", walls, -60.0), ("inner", inner, -15.0),
                           ("grid", grid, 30.0)):
        obj = w.scene.add(g.make_box((x, -15.0, 0.0), 30.0, 30.0, 30.0))
        w.scene.update(obj.id, layer_id=layer.id)
        made[name] = obj
    az, el = STANDARD_VIEWS["front"]
    det = DetailView(x=20.0, y=40.0, w=240.0, h=150.0, azimuth=az,
                     elevation=el, target=[0.0, 0.0, 15.0], scale_denom=1.0,
                     display_mode="hidden")
    lay = Layout(name="Sheet")
    lay.details.append(det)
    w.scene.layouts.append(lay)
    w.switch_space(lay.id)
    yield w, w.viewport.layout_view, det, made, walls
    w.mark_saved()
    w.close()


def _drawn(lv, det):
    return {oid for oid, _lt, _polys in lv._detail_hlr(det)["visible_by_obj"]}


def test_the_hidden_line_pass_leaves_the_layer_out(sheet):
    w, lv, det, made, walls = sheet
    assert made["wall"].id in _drawn(lv, det)
    det.hidden_layers = [walls.id]
    drawn = _drawn(lv, det)
    assert made["wall"].id not in drawn
    assert made["inner"].id not in drawn, "the sublayer stayed in"
    assert made["grid"].id in drawn


def test_the_model_still_shows_the_layer(sheet):
    w, lv, det, made, walls = sheet
    det.hidden_layers = [walls.id]
    assert w.scene.layers.is_visible(walls.id)
    assert made["wall"].id in {o.id for o in w.scene.visible_objects()}


def test_another_detail_on_the_sheet_keeps_it(sheet):
    w, lv, det, made, walls = sheet
    other = DetailView(**{k: v for k, v in vars(det).items()
                          if k not in ("id", "hidden_layers")})
    w.scene.layouts[0].details.append(other)
    det.hidden_layers = [walls.id]
    assert made["wall"].id in _drawn(lv, other)


def test_a_layer_gone_from_the_table_is_let_go(sheet):
    w, lv, det, made, walls = sheet
    det.hidden_layers = ["no-such-layer"]
    assert made["wall"].id in _drawn(lv, det)


def _has(image, rgb):
    """Whether any pixel is close to `rgb`, read on a coarse grid."""
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            c = image.pixelColor(x, y)
            if all(abs(a - b) < 40 for a, b in
                   zip((c.red(), c.green(), c.blue()), rgb)):
                return True
    return False


def test_a_shaded_detail_draws_without_the_layer(sheet):
    w, lv, det, made, walls = sheet
    vp = w.viewport
    vp.grabFramebuffer()
    if not (vp.isValid() and getattr(vp, "_mesh_prog", 0)):
        pytest.skip("no GL 3.3 to draw with here")
    det.display_mode = "shaded"
    image = vp.render_detail_image(det, 480, 300)
    assert image is not None and _has(image, (230, 40, 40)), \
        "the red walls never drew, so the test proves nothing"
    det.hidden_layers = [walls.id]
    image = vp.render_detail_image(det, 480, 300)
    assert not _has(image, (230, 40, 40)), "the hidden walls were drawn"
    assert _has(image, (40, 40, 230)), "the grid went too"
