"""Plaster display: the model as a plaster cast, every surface one matte
white under soft light on a light ground, whatever colour its layer is.
Rhino calls this look Arctic and others call it clay, so both names reach
it too. Creases, corners and contacts are darkened by ambient occlusion,
which can be switched off.

The drawing itself needs a real GL surface, so those tests skip without
one (CI runs offscreen); run them with QT_QPA_PLATFORM=xcb on a display.
"""

import numpy as np
import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow
from serpentine3d.ui.display_panel import _MODES
from serpentine3d.utils.config import RHINO_MACRO_MAP


@pytest.fixture
def win(_qapp):
    w = MainWindow()
    yield w
    w.mark_saved()
    w.close()
    w.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("name", ["plaster", "clay", "arctic"])
def test_each_name_turns_plaster_on(win, name):
    win.run_command(name)
    assert win.viewport.display_mode == "plaster"


def test_a_rhino_arctic_macro_lands_on_plaster():
    assert RHINO_MACRO_MAP["setdisplaymode arctic"] == "plaster"


def test_the_display_panel_offers_it():
    assert "plaster" in dict(_MODES)


def test_plaster_leaves_isocurves_off(win):
    win.viewport.set_display_mode("plaster")
    assert not win.viewport.shows_isocurves()
    assert win.viewport.shows_edges()


def test_a_red_box_draws_white_on_a_light_ground(win):
    from serpentine3d.core import geometry as g
    win.set_view_layout("single")
    win.resize(900, 700)
    win.show()
    vp = win.viewport
    vp.grabFramebuffer()
    if not (vp.isValid() and getattr(vp, "_mesh_prog", 0)):
        pytest.skip("no GL 3.3 to draw with here (CI runs offscreen)")
    box = win.scene.add(g.make_box((-20, -20, -20), 40, 40, 40))
    win.scene.update(box.id, color=(1.0, 0.0, 0.0))
    win.scene.notify()
    vp.set_display_mode("plaster")
    vp.set_view("top")
    vp.zoom_extents()
    image = vp.grabFramebuffer()
    face = image.pixelColor(image.width() // 2 + 20, image.height() // 2 + 20)
    ground = image.pixelColor(image.width() - 8, image.height() // 3)
    assert abs(face.red() - face.green()) < 12, \
        f"the layer's red came through: {face.name()}"
    assert face.green() > 170, f"the box is not plaster white: {face.name()}"
    assert ground.lightness() > 180, f"the ground is dark: {ground.name()}"


# -- ambient occlusion --------------------------------------------------------

def test_the_occlusion_kernel_stays_in_the_hemisphere():
    from serpentine3d.ui.ambient_occlusion import KERNEL_SIZE, kernel
    k = kernel()
    assert k.shape == (KERNEL_SIZE, 3)
    assert (k[:, 2] > 0).all(), "a sample looks behind the surface"
    assert (np.linalg.norm(k, axis=1) <= 1.0 + 1e-6).all()


def test_occlusion_shades_plaster_only(win):
    vp = win.viewport
    vp.set_display_mode("shaded")
    assert not vp.shows_ambient_occlusion()
    vp.set_display_mode("plaster")
    assert vp.shows_ambient_occlusion()
    vp.set_ambient_occlusion(False)
    assert not vp.shows_ambient_occlusion()


def test_the_display_panel_switches_occlusion(win):
    from serpentine3d.ui.display_panel import DisplayPanel
    vp = win.viewport
    vp.set_display_mode("plaster")
    panel = DisplayPanel(lambda: vp)
    assert panel.ao_box.isEnabled() and panel.ao_box.isChecked()
    panel.ao_box.setChecked(False)
    assert not vp.ambient_occlusion
    vp.set_display_mode("shaded")
    panel.refresh()
    assert not panel.ao_box.isEnabled()


def test_occlusion_darkens_an_inside_corner(win):
    """A floor where it meets a wall is darker with occlusion than without,
    and the open floor away from the wall is not."""
    from serpentine3d.core import geometry as g
    win.set_view_layout("single")
    win.resize(900, 700)
    win.show()
    vp = win.viewport
    vp.grabFramebuffer()
    if not (vp.isValid() and getattr(vp, "_mesh_prog", 0)):
        pytest.skip("no GL 3.3 to draw with here (CI runs offscreen)")
    win.scene.add(g.make_box((0, 0, 0), 60, 60, 2))
    win.scene.add(g.make_box((0, 50, 2), 60, 10, 30))
    win.scene.notify()
    vp.grid_visible = False
    vp.set_display_mode("plaster")
    vp.set_view("perspective")
    vp.zoom_extents()
    w, h = vp.width(), vp.height()
    corner, open_floor = vp.camera.project(
        np.array([[30.0, 49.5, 2.0], [30.0, 15.0, 2.0]]), w, h)
    ratio = vp.devicePixelRatioF()

    def lightness(image, p):
        return image.pixelColor(int(p[0] * ratio),
                                int(p[1] * ratio)).lightness()

    on = vp.grabFramebuffer()
    vp.set_ambient_occlusion(False)
    off = vp.grabFramebuffer()
    assert not vp._ao_failed
    assert lightness(on, corner) < lightness(off, corner) - 8, \
        "the corner is no darker with occlusion on"
    assert abs(lightness(on, open_floor) - lightness(off, open_floor)) <= 4, \
        "occlusion darkened open floor"


def test_the_ground_is_z0_or_the_lowest_point(win):
    vp = win.viewport
    vp.camera.drawing_bounds = ((0, 0, 5), (10, 10, 20))
    assert vp._ground_z() == 0.0
    vp.camera.drawing_bounds = ((0, 0, -7), (10, 10, 20))
    assert vp._ground_z() == -7.0


def test_the_ground_is_left_out_seen_from_below(win):
    vp = win.viewport
    vp.camera.drawing_bounds = ((0, 0, 0), (10, 10, 10))
    vp._frame_anchor = None
    vp.set_view("perspective")
    assert vp._ao_ground(np.eye(4, dtype=np.float32)) is not None
    vp.camera.elevation = -abs(vp.camera.elevation)
    assert vp._ao_ground(np.eye(4, dtype=np.float32)) is None


def test_a_box_on_the_ground_shades_the_ground_round_its_foot(win):
    """No floor is modelled: the ground at z=0 is what takes the shading."""
    from serpentine3d.core import geometry as g
    win.set_view_layout("single")
    win.resize(900, 700)
    win.show()
    vp = win.viewport
    vp.grabFramebuffer()
    if not (vp.isValid() and getattr(vp, "_mesh_prog", 0)):
        pytest.skip("no GL 3.3 to draw with here (CI runs offscreen)")
    win.scene.add(g.make_box((0, 0, 0), 20, 20, 20))
    win.scene.notify()
    vp.grid_visible = False
    vp.set_display_mode("plaster")
    vp.set_view("perspective")
    vp.zoom_extents()
    w, h = vp.width(), vp.height()
    (foot,) = vp.camera.project(np.array([[10.0, -0.5, 0.0]]), w, h)
    ratio = vp.devicePixelRatioF()
    at = (int(foot[0] * ratio), int(foot[1] * ratio))
    on = vp.grabFramebuffer().pixelColor(*at).lightness()
    vp.set_ambient_occlusion(False)
    off = vp.grabFramebuffer().pixelColor(*at).lightness()
    assert on < off - 10, f"no shading at the box's foot: {on} vs {off}"


# -- plaster color ------------------------------------------------------------

@pytest.mark.parametrize("name", ["plastercolor", "claycolor"])
def test_each_name_turns_plaster_color_on(win, name):
    win.run_command(name)
    assert win.viewport.display_mode == "plastercolor"


def test_plaster_color_is_offered_and_occluded(win):
    assert "plastercolor" in dict(_MODES)
    win.viewport.set_display_mode("plastercolor")
    assert win.viewport.shows_ambient_occlusion()
    assert not win.viewport.shows_isocurves()


def test_plaster_color_keeps_the_objects_colour(win):
    from serpentine3d.core import geometry as g
    win.set_view_layout("single")
    win.resize(900, 700)
    win.show()
    vp = win.viewport
    vp.grabFramebuffer()
    if not (vp.isValid() and getattr(vp, "_mesh_prog", 0)):
        pytest.skip("no GL 3.3 to draw with here (CI runs offscreen)")
    box = win.scene.add(g.make_box((-20, -20, -20), 40, 40, 40))
    win.scene.update(box.id, color=(1.0, 0.0, 0.0))
    win.scene.notify()
    vp.set_display_mode("plastercolor")
    vp.set_view("top")
    vp.zoom_extents()
    image = vp.grabFramebuffer()
    face = image.pixelColor(image.width() // 2 + 20, image.height() // 2 + 20)
    ground = image.pixelColor(image.width() - 8, image.height() // 3)
    assert face.red() > 150 and face.green() < 90, \
        f"the box lost its red: {face.name()}"
    assert ground.lightness() > 180, f"the ground is dark: {ground.name()}"


@pytest.mark.parametrize("colour, white", [((0.0, 0.0, 0.0), True),
                                           ((0.05, 0.05, 0.05), False)])
def test_plaster_color_shows_pure_black_as_plaster(win, colour, white):
    from serpentine3d.core import geometry as g
    win.set_view_layout("single")
    win.resize(900, 700)
    win.show()
    vp = win.viewport
    vp.grabFramebuffer()
    if not (vp.isValid() and getattr(vp, "_mesh_prog", 0)):
        pytest.skip("no GL 3.3 to draw with here (CI runs offscreen)")
    for x in (-60, 20):
        box = win.scene.add(g.make_box((x, -20, -20), 40, 40, 40))
        win.scene.update(box.id, color=colour)
    win.scene.notify()
    vp.set_display_mode("plastercolor")
    vp.set_view("top")
    vp.zoom_extents()
    w, h = vp.width(), vp.height()
    ratio = vp.devicePixelRatioF()
    image = vp.grabFramebuffer()
    for x in (-40.0, 40.0):
        (p,) = vp.camera.project(np.array([[x, 5.0, 20.0]]), w, h)
        face = image.pixelColor(int(p[0] * ratio), int(p[1] * ratio))
        assert (face.lightness() > 170) is white, face.name()
