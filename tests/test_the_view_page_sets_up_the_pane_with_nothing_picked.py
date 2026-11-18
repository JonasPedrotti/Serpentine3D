"""With nothing picked, Properties shows the pane you are working in: its
camera (projection, lens, where it stands and looks, a lock), its
background (colour or gradient, a wallpaper shown or grayed, for this pane
or for all of them), its grid and axes, and the drawing's named views.
All of it is kept in the drawing and comes back when it is opened."""

from __future__ import annotations

import math

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from serpentine3d.app import MainWindow
from serpentine3d.core import geometry as g
from serpentine3d.core import view_settings as vs
from serpentine3d.ui.camera import DEFAULT_LENS_MM, Camera
from serpentine3d.ui.viewport import wallpaper_fit


@pytest.fixture
def win(_qapp):
    w = MainWindow()
    w._prop_dock.show()
    w.properties.show()
    QApplication.processEvents()
    yield w
    w.mark_saved()
    w.close()


def _png(tmp_path, name="wall.png") -> str:
    img = QImage(8, 4, QImage.Format.Format_RGB32)
    img.fill(QColor(200, 40, 40))
    path = str(tmp_path / name)
    img.save(path)
    return path


# -- the camera ---------------------------------------------------------------

def test_a_new_camera_has_a_25mm_lens():
    assert Camera().focal_length == pytest.approx(DEFAULT_LENS_MM)


def test_a_locked_camera_does_not_orbit_pan_or_zoom():
    cam = Camera()
    cam.locked = True
    before = cam.state()

    cam.orbit(40, 20)
    cam.pan(30, 10, 600)
    cam.zoom(3)
    cam.zoom_drag(-80)
    cam.zoom_extents(((0, 0, 0), (100, 100, 100)))
    cam.set_standard_view("top")

    assert cam.state() == before


def test_look_from_stands_at_the_point_and_looks_at_the_target():
    cam = Camera()
    assert cam.look_from((10, 0, 0), (0, 0, 0))
    assert np.allclose(cam.position, (10, 0, 0))
    assert np.allclose(cam.target, (0, 0, 0))
    assert not cam.look_from((1, 1, 1), (1, 1, 1))


def test_a_wallpaper_is_fitted_whole_and_centred():
    assert wallpaper_fit(2.0, 1.0) == (1.0, 0.5)
    assert wallpaper_fit(0.5, 1.0) == (0.5, 1.0)


# -- the page -----------------------------------------------------------------

def test_nothing_picked_shows_the_view_page(win):
    win.selection.clear()
    QApplication.processEvents()

    assert win.properties.shown() == "view"
    assert win.properties.pages.currentWidget() is win.properties.view_page
    head = win.properties.view_head
    assert head.kind.text() == "Viewport"
    assert head.title.isHidden() and head.detail.isHidden()


def test_picking_something_shows_the_object_again(win):
    box = win.scene.add(g.make_box((0, 0, 0), 1, 1, 1))
    win.selection.set([box.id])
    QApplication.processEvents()

    assert win.properties.shown() == "objects"


def test_lens_and_projection_edit_the_active_pane(win):
    page = win.properties.view_page
    win.selection.clear()
    page.lens.setValue(50.0)

    assert win.active_viewport.camera.focal_length == pytest.approx(50.0)

    page.projection.setCurrentIndex(page.projection.findData("parallel"))
    assert win.active_viewport.camera.projection == "parallel"
    assert page.lens.isHidden()


def test_the_set_buttons_run_the_camera_command(win):
    asked = []
    win.properties.viewCommandRequested.disconnect()
    win.properties.viewCommandRequested.connect(asked.append)

    win.properties.view_page.camera_set.click()
    win.properties.view_page.target_set.click()

    assert asked == ["camera Position", "camera Target"]


def test_camera_position_keeps_the_target(win):
    vp = win.active_viewport
    vp.camera.target = np.array([1.0, 2.0, 3.0])
    win.run_command("camera Position")
    win.processor.provide_text("1,2,13")

    assert np.allclose(vp.camera.position, (1, 2, 13))
    assert np.allclose(vp.camera.target, (1, 2, 3))


def test_locked_disables_the_camera_rows(win):
    page = win.properties.view_page
    win.selection.clear()
    page.locked.setChecked(True)

    assert win.active_viewport.camera.locked
    assert not page.camera_set.isEnabled()
    assert not page.lens.isEnabled()


def test_a_background_is_the_pane_s_own_until_used_for_all(win):
    page = win.properties.view_page
    vp = win.active_viewport
    other = next(p for p in win._model_panes() if p is not vp)
    win.selection.clear()

    page._set_background(color=(0.5, 0.2, 0.1), gradient=False)
    assert vp.background.color == (0.5, 0.2, 0.1)
    assert other.background.color != (0.5, 0.2, 0.1)

    assert page.for_all.isHidden()
    page._set_background(wallpaper=b"x", wallpaper_name="x.png")
    assert not page.for_all.isHidden()

    page.for_all.setChecked(True)
    assert other.background.color == (0.5, 0.2, 0.1)
    page._set_background(wallpaper_gray=True)
    assert all(p.background.wallpaper_gray for p in win._model_panes())


def test_grid_and_axes_switch_per_pane(win):
    page = win.properties.view_page
    vp = win.active_viewport
    win.selection.clear()

    page.grid_axes.setChecked(False)
    page.world_axes.setChecked(False)
    page.grid.setChecked(False)

    assert not vp.grid_axes_visible
    assert not vp.world_axes_visible
    assert not vp.grid_visible


def test_named_views_are_saved_restored_and_deleted(win, monkeypatch):
    page = win.properties.view_page
    vp = win.active_viewport
    win.selection.clear()
    monkeypatch.setattr(page, "ask_view_name", lambda: "Entrance")
    page.view_save.click()
    assert "Entrance" in win.scene.named_views

    vp.camera.orbit(200, 0)
    item = page.views.item(0)
    page.views.setCurrentItem(item)
    page.views.itemClicked.emit(item)
    assert vp.camera.state() == win.scene.named_views["Entrance"]

    QTest.keyClick(page.views, Qt.Key.Key_Delete)
    assert "Entrance" not in win.scene.named_views
    assert page.views.count() == 0 and page.views.isHidden()


def test_the_list_shows_only_with_views_and_a_cancel_saves_nothing(
        win, monkeypatch):
    page = win.properties.view_page
    win.selection.clear()
    assert page.views.isHidden()

    monkeypatch.setattr(page, "ask_view_name", lambda: "")
    page.view_save.click()
    assert win.scene.named_views == {}


# -- kept in the drawing ------------------------------------------------------

def test_the_settings_survive_a_save_and_an_open(win, tmp_path):
    page = win.properties.view_page
    vp = win.viewport
    win._set_active_viewport(vp)
    win.selection.clear()
    page.load_wallpaper(_png(tmp_path))
    page._set_background(color=(0.3, 0.3, 0.6), wallpaper_gray=True)
    vp.camera.look_from((20, -30, 15), (1, 2, 3))
    vp.camera.set_focal_length(35.0)
    vp.grid_axes_visible = False
    vp.camera.locked = True
    path = str(tmp_path / "kept.serp")
    from serpentine3d import fileio
    fileio.export_file(win.scene, path)

    win._file_new()
    assert not vp.camera.locked
    assert vp.background.wallpaper is None
    win._open_path(path)

    assert vp.camera.locked
    assert np.allclose(vp.camera.position, (20, -30, 15))
    assert np.allclose(vp.camera.target, (1, 2, 3))
    assert vp.camera.focal_length == pytest.approx(35.0)
    assert not vp.grid_axes_visible
    assert vp.background.color == pytest.approx((0.3, 0.3, 0.6))
    assert vp.background.wallpaper_gray
    assert vp.background.wallpaper_name == "wall.png"
    assert QImage.fromData(vp.background.wallpaper).width() == 8


def test_settings_json_round_trips_without_a_window():
    class Blobs(dict):
        def read(self, name):
            return self[name]

    settings = vs.ViewSettings(for_all=True)
    settings.background = vs.Background(wallpaper=b"img", wallpaper_name="a")
    settings.panes["top"] = {"look": vs.PaneLook(grid=False, locked=True),
                             "camera": {"distance": 5.0}}
    blobs = Blobs()

    back = vs.from_json(vs.to_json(settings, blobs), blobs)

    assert back.for_all
    assert back.background.wallpaper == b"img"
    assert back.panes["top"]["look"] == vs.PaneLook(grid=False, locked=True)
    assert back.panes["top"]["camera"] == {"distance": 5.0}


def test_a_file_without_settings_opens_with_the_defaults():
    back = vs.from_json(None)
    assert back.panes == {} and not back.for_all
    assert back.background == vs.Background()


def test_a_long_wallpaper_name_is_cut_short_not_widening_the_panel(
        win, tmp_path):
    page = win.properties.view_page
    win.selection.clear()
    narrow = page.minimumSizeHint().width()

    page.load_wallpaper(_png(tmp_path, "a" * 120 + ".png"))

    assert page.minimumSizeHint().width() == narrow
    assert page.wallpaper_name.full_text() == "a" * 120 + ".png"
    assert page.wallpaper_name.toolTip() == "a" * 120 + ".png"


def test_a_held_target_is_orbited_and_zoomed_toward_but_not_panned():
    cam = Camera()
    cam.target_locked = True
    target = cam.target.copy()

    cam.orbit(40, 10)
    cam.zoom(2)
    cam.pan(30, 30, 600)
    cam.zoom_extents(((5, 5, 5), (9, 9, 9)))

    assert np.allclose(cam.target, target)
    assert cam.distance < 60.0


def test_a_held_camera_looks_around_and_does_not_move():
    cam = Camera()
    cam.position_locked = True
    eye = cam.position.copy()
    target = cam.target.copy()

    cam.orbit(60, 15)
    cam.zoom(2)
    cam.pan(30, 30, 600)
    cam.set_standard_view("top")

    assert np.allclose(cam.position, eye)
    assert not np.allclose(cam.target, target)


def test_both_held_is_the_whole_view_held():
    cam = Camera()
    cam.position_locked = cam.target_locked = True
    before = cam.state()
    cam.orbit(60, 15)
    assert cam.state() == before


def test_the_point_locks_sit_beside_camera_and_target(win):
    page = win.properties.view_page
    vp = win.active_viewport
    win.selection.clear()

    page.camera_lock.setChecked(True)
    assert vp.camera.position_locked
    assert not page.camera_set.isEnabled() and page.target_set.isEnabled()

    page.target_lock.setChecked(True)
    assert vp.camera.target_locked and not page.target_set.isEnabled()

    page.locked.setChecked(True)
    assert not page.camera_lock.isEnabled()
    assert not page.target_lock.isEnabled()


def test_the_point_locks_are_kept_in_the_drawing():
    class Blobs(dict):
        def read(self, name):
            return self[name]
    settings = vs.ViewSettings()
    settings.panes["perspective"] = {
        "look": vs.PaneLook(position_locked=True, target_locked=False)}
    blobs = Blobs()
    back = vs.from_json(vs.to_json(settings, blobs), blobs)
    assert back.panes["perspective"]["look"].position_locked
