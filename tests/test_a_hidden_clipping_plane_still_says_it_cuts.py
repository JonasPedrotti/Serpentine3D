"""A hidden clipping plane still cuts, and says so.

As in Rhino, hiding a clipping plane, or turning its layer off, only puts
the plane out of sight: it goes on cutting until it is paused or switched
off in a view. That is how a section is kept without the plane in the
way. It is also how a model comes to be missing half of itself with
nothing on screen to say why, a question Rhino's forum is asked again
and again. So a pane a plane cuts says so in its title, every list of
the planes that cut a view names the hidden ones and can bring them
back, and hiding a plane that cuts says that it still does.

A drawing saved before this stopped its planes by hiding them, so a
plane one hid opens paused, and the drawing looks as it was saved.
"""

from __future__ import annotations

import json
import zipfile

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from serpentine3d.core import clipping
from serpentine3d.core import geometry as g
from serpentine3d.core.layout import DetailView, Layout
from serpentine3d.core.scene import Scene

VISIBLE_COL = 1
STILL_CUTS = "still cuts while hidden; 'disableclippingplane' pauses it."


def _plane_rect():
    """A rectangle on the world XY plane that takes away the half above it
    (as in test_a_clipping_plane_caps_what_it_cuts.py)."""
    return g.planar_face(g.make_polyline(
        [(-60, -60, 0), (60, -60, 0), (60, 60, 0), (-60, 60, 0)],
        closed=True))


def _add_plane(scene, name="Clip", layer_id=None, **clip):
    obj = scene.add(_plane_rect(), name=name, layer_id=layer_id)
    scene.update(obj.id, clip_plane={"enabled": True, **clip})
    return scene.get(obj.id)


def _hidden_two_ways(scene):
    """One plane hidden itself, one on a layer under a parent that is off,
    and one in sight."""
    shown = _add_plane(scene, "Shown")
    hid = _add_plane(scene, "Hid")
    scene.update(hid.id, visible=False)
    sections = scene.layers.create("Sections")
    planes = scene.layers.create("Planes", parent=sections.id)
    off = _add_plane(scene, "Off", layer_id=planes.id)
    scene.layers.set_visible(sections.id, False)
    scene.notify()
    return shown, hid, off, sections, planes


@pytest.fixture
def window(_qapp):
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w.resize(1200, 800)
    yield w
    w.mark_saved()
    w.close()


def _clip_menu(w, vp):
    menu = w._viewport_menu(vp)
    for act in menu.actions():
        if act.menu() is not None and act.text() == "Clipping Planes":
            return act.menu()
    return None


def _cut(title: str) -> bool:
    """Whether a pane's title says it is cut: last but for the title bar's
    menu arrow."""
    return title.removesuffix("▾").rstrip().endswith(" · Cut")


# --- which planes are out of sight ---------------------------------------------

def test_a_plane_is_hidden_when_it_or_a_layer_above_it_is():
    scene = Scene()
    shown, hid, off, _sections, _planes = _hidden_two_ways(scene)
    assert [clipping.hidden(scene, scene.get(o.id))
            for o in (shown, hid, off)] == [False, True, True]
    assert [o.name for o in clipping.planes_of(scene)] == ["Shown", "Hid",
                                                           "Off"]


def test_a_list_says_which_planes_are_paused_and_which_hidden():
    scene = Scene()
    shown, hid, _off, _sections, _planes = _hidden_two_ways(scene)
    scene.update(hid.id, clip_plane={"enabled": False})
    assert clipping.label(scene, scene.get(shown.id)) == "Shown"
    assert clipping.label(scene, scene.get(hid.id)) == "Hid (paused, hidden)"


# --- the title -------------------------------------------------------------------

def test_a_pane_a_plane_cuts_says_so_in_its_title(window):
    w = window
    vp = w.viewport
    assert not _cut(w._viewport_title(vp))
    plane = _add_plane(w.scene, "Section A")
    w.scene.update(plane.id, visible=False)
    assert _cut(w._viewport_title(vp)), "hidden, and cutting"

    w.scene.update(plane.id, clip_plane={"enabled": False})
    assert not _cut(w._viewport_title(vp)), "paused"
    w.scene.update(plane.id, clip_plane={"enabled": True,
                                         "off_in": [vp.clip_view()]})
    assert not _cut(w._viewport_title(vp)), "switched off in this pane"


def test_the_title_follows_the_planes_as_they_change(window):
    w = window
    w.set_view_layout("quad")
    QApplication.processEvents()
    top = next(v for v in w.all_viewports() if v.view_key == "top")
    bar = top.parentWidget().titleBarWidget()
    plane = _add_plane(w.scene, "Section A", off_in=["perspective"])
    QApplication.processEvents()
    assert _cut(bar.button.text())
    assert _cut(top.parentWidget().windowTitle())

    w.scene.update(plane.id, clip_plane={"enabled": False})
    QApplication.processEvents()
    assert not _cut(bar.button.text())


def test_a_sheet_s_title_does_not_say_cut(window):
    w = window
    _add_plane(w.scene, "Section A")
    lay = Layout(name="Sheet")
    lay.details.append(DetailView(x=20, y=40, w=180, h=150))
    w.scene.layouts.append(lay)
    w.switch_space(lay.id)
    assert not _cut(w._viewport_title(w.viewport)), \
        "a detail is cut to be drawn so"


# --- the lists -------------------------------------------------------------------

def test_the_pane_menu_lists_hidden_planes_and_shows_them(window):
    w = window
    vp = w.viewport
    shown, hid, off, sections, planes = _hidden_two_ways(w.scene)
    acts = [a for a in _clip_menu(w, vp).actions() if not a.isSeparator()]
    assert [a.text() for a in acts] == ["Shown", "Hid (hidden)",
                                        "Off (hidden)", "Show Hidden Planes"]
    assert [a.isChecked() for a in acts[:3]] == [True, True, True]

    acts[-1].trigger()
    scene = w.scene
    assert not any(clipping.hidden(scene, scene.get(o.id))
                   for o in (shown, hid, off))
    assert scene.layers.is_visible(planes.id)
    w.history.undo()
    assert not scene.get(hid.id).visible, "one undo step"
    assert not scene.layers.get(sections.id).visible


def test_with_none_hidden_the_menu_offers_nothing_to_show(window):
    w = window
    _add_plane(w.scene, "Section A")
    texts = [a.text() for a in _clip_menu(w, w.viewport).actions()]
    assert texts == ["Section A"]


def test_a_detail_lists_a_hidden_plane_too(window):
    w = window
    plane = _add_plane(w.scene, "Section A")
    w.scene.update(plane.id, visible=False)
    lay = Layout(name="Sheet")
    det = DetailView(x=20, y=40, w=180, h=150)
    lay.details.append(det)
    w.scene.layouts.append(lay)
    w.switch_space(lay.id)
    lv = w.viewport.layout_view
    lv.selected = [("detail", det)]
    w.viewport.layoutSelectionChanged.emit()
    QApplication.processEvents()
    props = w.properties
    assert props.form.isRowVisible(props.detail_clips)
    assert props.detail_clips.planes() == [("Section A (hidden)", True)]


# --- hiding one ------------------------------------------------------------------

def test_hiding_a_plane_that_cuts_says_it_still_does(env):
    scene, _sel, _hist, ctx, proc = env
    said = []
    ctx.echo = said.append
    cutting = _add_plane(scene, "Clipping Plane 01")
    paused = _add_plane(scene, "Clipping Plane 02", enabled=False)
    proc.run("hide")
    proc.click_object(cutting.id)
    proc.click_object(paused.id)
    proc.finish_selection()
    assert said[-2:] == ["Hid 2 object(s).", f"Clipping Plane 01 {STILL_CUTS}"]


def test_hiding_several_names_them_all(env):
    scene, _sel, _hist, ctx, proc = env
    said = []
    ctx.echo = said.append
    a = _add_plane(scene, "A")
    b = _add_plane(scene, "B")
    proc.run("hide")
    proc.click_object(a.id)
    proc.click_object(b.id)
    proc.finish_selection()
    assert said[-1] == ("A and B still cut while hidden; "
                        "'disableclippingplane' pauses them.")


def test_isolating_an_object_says_the_planes_it_hid_still_cut(env):
    """Only the ones it put out of sight: a plane on a layer that is off
    was out of sight already."""
    scene, _sel, _hist, ctx, proc = env
    said = []
    ctx.echo = said.append
    box = scene.add(g.make_box((0, 0, 0), 5, 5, 5), name="Box")
    _add_plane(scene, "Section A")
    layer = scene.layers.create("Planes")
    _add_plane(scene, "Section B", layer_id=layer.id)
    scene.layers.set_visible(layer.id, False)
    proc.run("isolate")
    proc.click_object(box.id)
    proc.finish_selection()
    assert said[-1] == f"Section A {STILL_CUTS}"


def test_the_layer_command_says_so_too(env):
    scene, _sel, _hist, ctx, proc = env
    said = []
    ctx.echo = said.append
    layer = scene.layers.create("Planes")
    _add_plane(scene, "Section A", layer_id=layer.id)
    proc.run("layer Hide")
    proc.provide_text("Planes")
    assert said[-2:] == ["Layer 'Planes' hidden.", f"Section A {STILL_CUTS}"]


def _item_for(panel, layer_id):
    for i in range(panel.tree.topLevelItemCount()):
        item = panel.tree.topLevelItem(i)
        if panel._layer_id(item) == layer_id:
            return item
    raise AssertionError("no row for that layer")


def test_turning_a_plane_s_layer_off_says_it_still_cuts(window):
    w = window
    layer = w.scene.layers.create("Planes")
    _add_plane(w.scene, "Section A", layer_id=layer.id)
    w.scene.notify()
    QApplication.processEvents()
    item = _item_for(w.layers_panel, layer.id)

    item.setCheckState(VISIBLE_COL, Qt.CheckState.Unchecked)
    QApplication.processEvents()
    assert not w.scene.layers.get(layer.id).visible
    log = w.command_line.echo_view.toPlainText().splitlines()
    assert log[-1] == f"Section A {STILL_CUTS}"

    item = _item_for(w.layers_panel, layer.id)
    item.setCheckState(VISIBLE_COL, Qt.CheckState.Checked)
    QApplication.processEvents()
    assert w.command_line.echo_view.toPlainText().splitlines() == log, \
        "nothing to say of a plane coming back"


# --- a drawing from before -------------------------------------------------------

def _saved_before(scene, path):
    """`scene` written as a release before hidden planes cut wrote it: all
    of it, but no word on what a hidden plane does."""
    from serpentine3d.fileio.native import save_scene
    save_scene(scene, str(path))
    with zipfile.ZipFile(path) as z:
        members = {name: z.read(name) for name in z.namelist()}
    doc = json.loads(members["document.json"])
    doc.pop("hidden_planes_cut", None)
    members["document.json"] = json.dumps(doc).encode()
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)


def _settings(scene):
    return {o.name: o.clip_plane for o in scene.all() if o.clip_plane}


def test_a_plane_a_drawing_from_before_hid_opens_paused(tmp_path):
    from serpentine3d.fileio.native import load_scene
    scene = Scene()
    _hidden_two_ways(scene)
    path = tmp_path / "before.serp"
    _saved_before(scene, path)

    back = Scene()
    load_scene(back, str(path))
    assert _settings(back) == {"Shown": {"enabled": True},
                               "Hid": {"enabled": False},
                               "Off": {"enabled": False}}


def test_a_drawing_saved_now_keeps_its_hidden_planes_cutting(tmp_path):
    from serpentine3d.fileio.native import load_scene, save_scene
    scene = Scene()
    _hidden_two_ways(scene)
    path = str(tmp_path / "now.serp")
    save_scene(scene, path)

    back = Scene()
    load_scene(back, path)
    assert _settings(back) == {"Shown": {"enabled": True},
                               "Hid": {"enabled": True},
                               "Off": {"enabled": True}}
