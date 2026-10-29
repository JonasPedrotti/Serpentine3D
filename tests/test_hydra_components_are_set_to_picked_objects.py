"""Hydra in the real window: a geometry component is set to objects picked
in the model, shows them in the preview, and follows them when they change."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from serpentine3d.app import MainWindow
from serpentine3d.core import geometry as geo
from serpentine3d.core.hydra import Graph
from serpentine3d.core.mesh import mesh_from_brep


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_NO_RECOVER", "1")
    win = MainWindow()
    win.resize(1400, 900)
    yield win
    win.processor.cancel()
    win.mark_saved()
    win.close()
    QApplication.processEvents()


def _set_to(win, editor, node, objs):
    """Set Crv... (or the like) from the component's menu, then click
    and press Enter."""
    menu = editor.node_menu(editor.canvas.node_items[node.id])
    [action] = [a for a in menu.actions()
                if a.text() == node.component.sets + "..."]
    action.trigger()
    assert win.processor.busy
    for obj in objs:
        win.processor.click_object(obj.id)
    win.processor.finish_selection()


def test_the_command_opens_hydra_floating_and_the_menu_names_it(win):
    win.run_command("hydra")
    assert win.hydra is not None
    assert win._hydra_dock.isFloating() and win._hydra_dock.isVisible()
    labels = [a.text() for m in win.menuBar().actions() if m.menu()
              for a in m.menu().actions()]
    assert "Hydra" in labels


def test_the_add_menu_offers_the_geometries_with_their_icons(win):
    editor = win.show_hydra()
    actions = [a for a in editor.component_menu(None).actions()
               if not a.isSeparator()]
    assert [a.text() for a in actions] == [
        "Point", "Curve", "Brep", "Mesh", "Number Slider",
        "Construct Point", "Vector", "Move", "Rotate"]
    assert all(not a.icon().isNull() for a in actions)


def test_set_to_takes_the_picked_curves_and_previews_them(win):
    editor = win.show_hydra()
    line = win.scene.add(geo.make_line((0, 0, 0), (10, 0, 0)))
    circle = win.scene.add(geo.make_circle((0, 0, 0), 3))
    node = editor.add_component("curve", (0, 0))
    editor.solve()
    assert editor.results[node.id].status == "warning"
    _set_to(win, editor, node, [line, circle])
    assert not win.processor.busy
    assert node.params["refs"] == [line.id, circle.id]
    assert editor.results[node.id].status == "ok"
    assert editor.canvas.node_items[node.id].summary() == "2 curves"
    assert len(win.scene.hydra_preview[1])
    assert len(win.scene.all()) == 2           # picking adds nothing


def test_set_to_only_takes_objects_of_the_components_kind(win):
    editor = win.show_hydra()
    box = win.scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    line = win.scene.add(geo.make_line((0, 0, 0), (10, 0, 0)))
    node = editor.add_component("curve", (0, 0))
    _set_to(win, editor, node, [box, line])
    assert node.params["refs"] == [line.id]


def test_a_brep_takes_surfaces_and_solids_and_a_mesh_only_meshes(win):
    editor = win.show_hydra()
    face = win.scene.add(geo.planar_face(
        geo.make_rectangle((0, 0, 0), (2, 2, 0))))
    box = win.scene.add(geo.make_box((5, 0, 0), 1, 1, 1))
    mesh = win.scene.add(mesh_from_brep(geo.make_box((9, 0, 0), 1, 1, 1)))
    brep = editor.add_component("brep", (0, 0))
    meshes = editor.add_component("mesh", (0, 120))
    _set_to(win, editor, brep, [face, box, mesh])
    _set_to(win, editor, meshes, [face, box, mesh])
    assert brep.params["refs"] == [face.id, box.id]
    assert meshes.params["refs"] == [mesh.id]
    assert editor.canvas.node_items[meshes.id].summary() == "1 mesh"
    assert win.scene.hydra_preview is not None


def _choose_set_to(editor, node):
    menu = editor.node_menu(editor.canvas.node_items[node.id])
    [a for a in menu.actions() if a.text() == "Set Crv..."][0].trigger()


def test_set_to_takes_what_is_already_selected_straight_away(win):
    editor = win.show_hydra()
    line = win.scene.add(geo.make_line((0, 0, 0), (10, 0, 0)))
    circle = win.scene.add(geo.make_circle((0, 0, 0), 3))
    node = editor.add_component("curve", (0, 0))
    win.selection.set([line.id, circle.id])
    _choose_set_to(editor, node)
    assert not win.processor.busy
    assert node.params["refs"] == [line.id, circle.id]


def test_set_to_takes_only_the_selected_objects_of_its_kind(win):
    editor = win.show_hydra()
    line = win.scene.add(geo.make_line((0, 0, 0), (10, 0, 0)))
    box = win.scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    node = editor.add_component("curve", (0, 0))
    win.selection.set([line.id, box.id])
    _choose_set_to(editor, node)
    assert not win.processor.busy
    assert node.params["refs"] == [line.id]


def test_with_nothing_of_its_kind_selected_set_to_waits_for_a_pick(win):
    editor = win.show_hydra()
    box = win.scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    line = win.scene.add(geo.make_line((0, 0, 0), (10, 0, 0)))
    node = editor.add_component("curve", (0, 0))
    win.selection.set([box.id])
    _choose_set_to(editor, node)
    assert win.processor.busy
    win.processor.click_object(line.id)
    win.processor.finish_selection()
    assert node.params["refs"] == [line.id]


def test_escape_leaves_the_component_as_it_was(win):
    editor = win.show_hydra()
    line = win.scene.add(geo.make_line((0, 0, 0), (10, 0, 0)))
    node = editor.add_component("curve", (0, 0))
    _set_to(win, editor, node, [line])
    menu = editor.node_menu(editor.canvas.node_items[node.id])
    [a for a in menu.actions() if a.text() == "Set Crv..."][0].trigger()
    win.processor.cancel()
    assert node.params["refs"] == [line.id]


def test_the_component_follows_its_objects_when_they_move_or_go(win):
    editor = win.show_hydra()
    line = win.scene.add(geo.make_line((0, 0, 0), (10, 0, 0)))
    node = editor.add_component("curve", (0, 0))
    _set_to(win, editor, node, [line])
    line.shape = geo.translate(line.shape, (0, 5, 0))
    win.scene.notify("objects")
    editor.solve()
    assert win.scene.hydra_preview[1][:, 1].min() == pytest.approx(5.0)
    win.scene.remove(line.id)
    editor.solve()
    assert editor.results[node.id].status == "warning"
    assert win.scene.hydra_preview is None


def test_closing_hydra_takes_its_preview_away_and_reopening_brings_it_back(win):
    win.show()
    editor = win.show_hydra()
    box = win.scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    editor.set_references(editor.add_component("brep", (0, 0)).id, [box.id])
    win._hydra_dock.close()
    QApplication.processEvents()
    assert win.scene.hydra_preview is None
    win.show_hydra()
    QApplication.processEvents()
    assert win.scene.hydra_preview is not None


def test_delete_removes_the_selected_component_not_the_models_selection(win):
    win.show()
    editor = win.show_hydra()
    obj = win.scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    win.selection.set([obj.id])
    node = editor.add_component("brep", (0, 0))
    editor.canvas.node_items[node.id].setSelected(True)
    editor.canvas.setFocus()
    QApplication.processEvents()
    QTest.keyClick(editor.canvas, Qt.Key.Key_Delete)
    assert node.id not in editor.graph.nodes
    assert win.scene.get(obj.id) is not None


def _right(view, kind, at, held):
    event = QMouseEvent(kind, QPointF(at), QPointF(view.mapToGlobal(at)),
                        Qt.MouseButton.RightButton
                        if kind != QEvent.Type.MouseMove
                        else Qt.MouseButton.NoButton,
                        Qt.MouseButton.RightButton if held
                        else Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), event)


@pytest.fixture
def menus(win, monkeypatch):
    shown = []
    editor = win.show_hydra()
    monkeypatch.setattr(editor, "show_menu",
                        lambda scene_pos, screen_pos: shown.append(scene_pos))
    win.show()
    QApplication.processEvents()
    return editor, shown


def test_dragging_with_the_right_button_pans_and_opens_no_menu(menus):
    editor, shown = menus
    view = editor.canvas
    before = view.mapToScene(view.viewport().rect().center())
    start = view.viewport().rect().center()
    _right(view, QEvent.Type.MouseButtonPress, start, True)
    for step in range(1, 6):
        _right(view, QEvent.Type.MouseMove, start + QPoint(20 * step, 0), True)
    _right(view, QEvent.Type.MouseButtonRelease, start + QPoint(100, 0), False)
    after = view.mapToScene(view.viewport().rect().center())
    assert after.x() == pytest.approx(before.x() - 100, abs=2)
    assert shown == []


def test_a_right_click_without_dragging_opens_the_menu(menus):
    editor, shown = menus
    view = editor.canvas
    at = view.viewport().rect().center()
    _right(view, QEvent.Type.MouseButtonPress, at, True)
    _right(view, QEvent.Type.MouseMove, at + QPoint(1, 1), True)
    _right(view, QEvent.Type.MouseButtonRelease, at + QPoint(1, 1), False)
    assert len(shown) == 1


# -- the number slider ------------------------------------------------------

def _menu_texts(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_a_sliders_menu_offers_change_range_with_decimal_places_below(win):
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    menu = editor.node_menu(editor.canvas.node_items[node.id])
    texts = _menu_texts(menu)
    assert texts[:2] == ["Change Range...", "Decimal Places"]
    places = [a for a in menu.actions() if a.text() == "Decimal Places"][0]
    choices = places.menu().actions()
    assert [a.text() for a in choices] == [str(n) for n in range(7)]
    assert [a.isChecked() for a in choices].index(True) == 2


def test_choosing_decimal_places_changes_what_the_slider_shows(win):
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    item = editor.canvas.node_items[node.id]
    menu = editor.node_menu(item)
    places = [a for a in menu.actions() if a.text() == "Decimal Places"][0]
    places.menu().actions()[0].trigger()
    assert node.params["decimals"] == 0
    assert item.value_text() == "5"
    editor.set_decimals(item, 3)
    assert item.value_text() == "5.000"


def test_change_range_takes_a_typed_range_with_its_decimals(win, monkeypatch):
    from serpentine3d.ui import hydra_editor
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    item = editor.canvas.node_items[node.id]

    def typed(dialog):
        dialog.low.setText("0,125")
        dialog.high.setText("2,5")
        return hydra_editor.QDialog.DialogCode.Accepted
    monkeypatch.setattr(hydra_editor.RangeDialog, "exec", typed)
    editor.change_range(item)
    assert (node.params["min"], node.params["max"]) == (0.125, 2.5)
    assert node.params["decimals"] == 3
    assert node.params["value"] == 2.5
    assert item.value_text() == "2.500"


def test_the_range_dialog_will_not_take_a_range_that_is_not_one(win):
    from serpentine3d.ui.hydra_editor import QDialogButtonBox, RangeDialog
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    dialog = RangeDialog(node.params, editor)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert dialog.low.text() == "0.00" and dialog.high.text() == "10.00"
    assert ok.isEnabled()
    dialog.high.setText("-1")
    assert not ok.isEnabled() and "below" in dialog.hint.text()
    dialog.high.setText("zehn")
    assert not ok.isEnabled()
    dialog.high.setText("12,75")
    assert ok.isEnabled()


def test_dragging_the_knob_sets_the_value_to_the_sliders_decimals(win):
    win.show()
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    item = editor.canvas.node_items[node.id]
    view = editor.canvas
    view.centerOn(item)
    QApplication.processEvents()
    x0, x1 = item._rail()
    y = item.boundingRect().center().y()
    start = view.mapFromScene(item.mapToScene(QPointF(x0, y)))
    end = view.mapFromScene(item.mapToScene(QPointF(x0 + (x1 - x0) * 0.3, y)))
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert node.params["value"] == pytest.approx(3.0, abs=0.1)
    assert node.params["value"] == round(node.params["value"], 2)
    assert (node.x, node.y) == (0, 0)          # the knob moved, not the node
    editor.solve()
    assert editor.results[node.id].outputs["Number"] == [node.params["value"]]


def _double_click_slider(win, editor, node):
    win.show()
    # as after a click into it: the Hydra window is the active one
    win._hydra_dock.activateWindow()
    item = editor.canvas.node_items[node.id]
    view = editor.canvas
    view.centerOn(item)
    QApplication.processEvents()
    at = view.mapFromScene(item.mapToScene(item.value_rect().center()))
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=at)
    QApplication.processEvents()
    assert editor.value_field is not None and editor.value_field.isVisible()
    assert editor.value_field.hasFocus()
    return item, editor.value_field


def test_double_clicking_a_slider_types_a_value_into_it(win):
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    item, field = _double_click_slider(win, editor, node)
    assert field.text() == "5.00"
    field.setText("7,25")
    QTest.keyClick(field, Qt.Key.Key_Return)
    QApplication.processEvents()
    assert editor.value_field is None
    assert node.params == {"value": 7.25, "min": 0.0, "max": 10.0,
                           "decimals": 2}
    assert item.value_text() == "7.25"


def test_typing_a_range_into_a_slider_sets_its_range_and_decimals(win):
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    item, field = _double_click_slider(win, editor, node)
    field.setText("0.0-12")
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert (node.params["min"], node.params["max"]) == (0.0, 12.0)
    assert node.params["decimals"] == 1
    assert item.value_text() == "5.0"


def test_escape_leaves_the_slider_as_it_was(win):
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    _item, field = _double_click_slider(win, editor, node)
    field.setText("9")
    QTest.keyClick(field, Qt.Key.Key_Escape)
    QApplication.processEvents()
    assert editor.value_field is None
    assert node.params["value"] == 5.0


def test_something_that_is_no_number_keeps_the_field_open_to_fix_it(win):
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    _item, field = _double_click_slider(win, editor, node)
    field.setText("zwölf")
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert editor.value_field is field
    assert "0.0-12" in editor.status.text()
    field.setText("3")
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert node.params["value"] == 3.0


def test_clicking_elsewhere_keeps_what_was_typed(win):
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    _item, field = _double_click_slider(win, editor, node)
    field.setText("2")
    editor.canvas.setFocus()
    QApplication.processEvents()
    assert editor.value_field is None
    assert node.params["value"] == 2.0


def test_dragging_a_wire_from_an_output_draws_no_selection_box(win):
    win.show()
    editor = win.show_hydra()
    node = editor.add_component("slider", (0, 0))
    view = editor.canvas
    view.centerOn(editor.canvas.node_items[node.id])
    QApplication.processEvents()
    port = view.node_items[node.id].port("Number", True)
    start = view.mapFromScene(port.scenePos())

    def send(kind, at, button, held):
        QApplication.sendEvent(view.viewport(), QMouseEvent(
            kind, QPointF(at), QPointF(view.mapToGlobal(at)), button, held,
            Qt.KeyboardModifier.NoModifier))

    left = Qt.MouseButton.LeftButton
    send(QEvent.Type.MouseButtonPress, start, left, left)
    for step in range(1, 6):
        send(QEvent.Type.MouseMove, start + QPoint(25 * step, 15 * step),
             Qt.MouseButton.NoButton, left)
        assert view.rubberBandRect().isEmpty()
    end = start + QPoint(125, 75)
    send(QEvent.Type.MouseButtonRelease, end, left, Qt.MouseButton.NoButton)
    assert view.rubberBandRect().isEmpty()


# -- rotate -----------------------------------------------------------------

def _wire_by_mouse(editor, source, output, target, input):
    view = editor.canvas
    out = view.node_items[source.id].port(output, True)
    inp = view.node_items[target.id].port(input, False)
    a = view.mapFromScene(out.scenePos())
    b = view.mapFromScene(inp.scenePos())
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=a)
    QTest.mouseMove(view.viewport(), (a + b) / 2)
    QTest.mouseMove(view.viewport(), b)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=b)


def test_a_rotate_has_a_port_and_a_name_for_each_input(win):
    editor = win.show_hydra()
    node = editor.add_component("rotate", (0, 0))
    item = editor.canvas.node_items[node.id]
    ys = [p.y() for p in item.inputs]
    assert [p.port.name for p in item.inputs] == ["Origin", "Geometry",
                                                   "Angle"]
    assert ys == sorted(ys) and min(b - a for a, b in zip(ys, ys[1:])) >= 16
    assert all(0 < y < item.height for y in ys)
    assert item.outputs[0].y() == pytest.approx(item.height / 2)


def test_curves_wired_into_rotate_preview_turned(win):
    win.show()
    editor = win.show_hydra()
    line = win.scene.add(geo.make_line((1, 0, 0), (2, 0, 0)))
    curve = editor.add_component("curve", (-200, 0))
    rotate = editor.add_component("rotate", (40, -20))
    editor.set_references(curve.id, [line.id])
    curve_item = editor.canvas.node_items[curve.id]
    editor.set_preview(curve.id, False)
    editor.canvas.centerOn(0, 0)
    QApplication.processEvents()
    _wire_by_mouse(editor, curve, "Curve", rotate, "Geometry")
    assert [(w.source, w.input) for w in editor.graph.wires] == [
        (curve.id, "Geometry")]
    angle = editor.add_component("slider", (-200, 120))
    angle.params.update(value=90.0, max=360.0)
    editor.connect(angle.id, "Number", rotate.id, "Angle")
    editor.solve()
    assert editor.results[rotate.id].status == "ok"
    segs = win.scene.hydra_preview[1]
    assert segs[:, 0] == pytest.approx(0, abs=1e-6)
    assert sorted(segs[:, 1]) == pytest.approx([1, 2], abs=1e-6)
    assert curve_item.result.status == "ok"


def test_an_inputs_tooltip_shows_what_reaches_it_now(win):
    editor = win.show_hydra()
    slider = editor.add_component("slider", (-300, 0))
    rotate = editor.add_component("rotate", (40, -20))
    editor.solve()
    angle = editor.canvas.node_items[rotate.id].port("Angle", False)
    assert angle.toolTip() == "Angle: 0 (default)"
    editor.connect(slider.id, "Number", rotate.id, "Angle")
    editor.solve()
    assert angle.toolTip() == "Angle: 5"
    editor.canvas.node_items[slider.id].slide_to(10_000)
    editor.solve()
    assert angle.toolTip() == "Angle: 10"
    geometry = editor.canvas.node_items[rotate.id].port("Geometry", False)
    assert geometry.toolTip() == "Geometry: nothing"


def test_a_waiting_components_input_names_are_drawn_white(win):
    from serpentine3d.ui import hydra_editor
    editor = win.show_hydra()
    rotate = editor.add_component("rotate", (0, 0))
    editor.solve()
    item = editor.canvas.node_items[rotate.id]
    assert item.result.status == "warning"
    pens = []

    class Spy:
        def __getattr__(self, name):
            return lambda *a, **k: None

        def setPen(self, pen):
            pens.append(pen)

        def font(self):
            return QFont()
    item._paint_labels(Spy())
    assert hydra_editor.QColor(pens[0]) == hydra_editor._TEXT


def test_a_slider_dropped_on_rotates_geometry_is_turned_away_and_says_why(win):
    win.show()
    editor = win.show_hydra()
    slider = editor.add_component("slider", (-300, 0))
    rotate = editor.add_component("rotate", (40, -20))
    editor.canvas.centerOn(-60, 0)
    QApplication.processEvents()
    _wire_by_mouse(editor, slider, "Number", rotate, "Geometry")
    assert editor.graph.wires == []
    assert "takes geometry" in editor.status.text()
    _wire_by_mouse(editor, slider, "Number", rotate, "Angle")
    assert [w.input for w in editor.graph.wires] == ["Angle"]


def test_the_graph_is_there_again_after_a_restart(win):
    editor = win.show_hydra()
    editor.add_component("curve", (0, 0))
    editor.add_component("mesh", (0, 120))
    win.mark_saved()
    win.close()
    again = MainWindow()
    try:
        editor = again.show_hydra()
        assert sorted(n.key for n in editor.graph.nodes.values()) == [
            "curve", "mesh"]
    finally:
        again.mark_saved()
        again.close()


def test_sliding_an_angle_turns_the_preview_without_meshing_it_again(
        win, monkeypatch):
    from serpentine3d.ui import hydra_editor
    meshed = []
    real = hydra_editor._mesh_arrays
    monkeypatch.setattr(hydra_editor, "_mesh_arrays",
                        lambda shape: meshed.append(shape) or real(shape))
    editor = win.show_hydra()
    box = win.scene.add(geo.make_box((1, 0, 0), 1, 1, 1))
    brep = editor.add_component("brep", (-200, 0))
    editor.set_references(brep.id, [box.id])
    slider = editor.add_component("slider", (-200, 80))
    slider.params.update(max=360.0)
    rotate = editor.add_component("rotate", (60, 0))
    editor.connect(brep.id, "Brep", rotate.id, "Geometry")
    editor.connect(slider.id, "Number", rotate.id, "Angle")
    editor.solve()
    first = len(meshed)
    item = editor.canvas.node_items[slider.id]
    before = win.scene.hydra_preview[0].copy()
    for x in range(60, 200, 20):
        item.slide_to(x)
        editor.solve()
    assert len(meshed) == first
    assert not np.allclose(win.scene.hydra_preview[0], before)


# -- a graph saved and opened again ------------------------------------------

def test_a_saved_graph_opens_with_its_links_to_a_reopened_model(
        win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from serpentine3d.fileio.native import save_scene
    editor = win.show_hydra()
    line = win.scene.add(geo.make_line((1, 0, 0), (2, 0, 0)))
    origin = win.scene.add(geo.make_point((1, 0, 0)))
    curve = editor.add_component("curve", (-200, 0))
    point = editor.add_component("point", (-200, -60))
    slider = editor.add_component("slider", (-200, 80))
    rotate = editor.add_component("rotate", (60, 0))
    editor.set_references(curve.id, [line.id])
    editor.set_references(point.id, [origin.id])
    slider.params.update(value=90.0, max=360.0)
    editor.connect(point.id, "Point", rotate.id, "Origin")
    editor.connect(curve.id, "Curve", rotate.id, "Geometry")
    editor.connect(slider.id, "Number", rotate.id, "Angle")
    model, graph = tmp_path / "model.serp", tmp_path / "graph.hydra"
    save_scene(win.scene, str(model))
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(graph), ""))
    editor.save_graph()
    win.mark_saved()
    win.close()

    again = MainWindow()
    try:
        again._open_path(str(model))
        editor = again.show_hydra()
        editor.new_graph()
        monkeypatch.setattr(QFileDialog, "getOpenFileName",
                            lambda *a, **k: (str(graph), ""))
        editor.open_graph()
        assert len(editor.graph.wires) == 3
        assert all(r.status == "ok" for r in editor.results.values())
        turned = editor.results[rotate.id].outputs["Geometry"][0]
        from serpentine3d.core.tessellate import tessellate
        pts = tessellate(turned).edge_segments.reshape(-1, 3)
        assert pts[:, 0] == pytest.approx([1, 1], abs=1e-6)
        assert sorted(pts[:, 1]) == pytest.approx([0, 1], abs=1e-6)
    finally:
        again.mark_saved()
        again.close()


def test_a_slider_dragged_without_a_pause_updates_while_it_moves(win):
    editor = win.show_hydra()
    solves = []
    real = editor.solve
    editor._timer.timeout.disconnect()
    editor._timer.timeout.connect(lambda: solves.append(1) or real())
    for _ in range(20):
        editor.changed()
        QTest.qWait(5)
    QTest.qWait(30)
    assert len(solves) >= 3


# -- save into the graph's own file -------------------------------------------

@pytest.fixture
def dialogs(monkeypatch, tmp_path):
    """Counts the file dialogs, answering each with `answer`."""
    from PySide6.QtWidgets import QFileDialog
    asked = {"save": 0, "open": 0, "answer": str(tmp_path / "graph.hydra")}

    def save(*a, **k):
        asked["save"] += 1
        return asked["answer"], ""

    def open_(*a, **k):
        asked["open"] += 1
        return asked["answer"], ""
    monkeypatch.setattr(QFileDialog, "getSaveFileName", save)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", open_)
    return asked


def _saved_keys(path):
    import json
    with open(path, encoding="utf-8") as fh:
        return sorted(n["key"] for n in json.load(fh)["nodes"])


def test_save_asks_where_only_the_first_time(win, dialogs):
    editor = win.show_hydra()
    editor.add_component("curve", (0, 0))
    editor.save_graph()
    assert dialogs["save"] == 1
    editor.add_component("slider", (0, 80))
    editor.save_graph()
    assert dialogs["save"] == 1
    assert _saved_keys(dialogs["answer"]) == ["curve", "slider"]
    assert win._hydra_dock.windowTitle() == "Hydra · graph.hydra"


def test_a_graph_opened_from_a_file_saves_back_into_it(win, dialogs, tmp_path):
    editor = win.show_hydra()
    editor.add_component("curve", (0, 0))
    editor.save_graph()
    editor.new_graph()
    assert win._hydra_dock.windowTitle() == "Hydra"
    editor.open_graph()
    editor.add_component("rotate", (100, 0))
    editor.save_graph()
    assert dialogs["save"] == 1
    assert _saved_keys(dialogs["answer"]) == ["curve", "rotate"]


def test_save_as_always_asks_and_saves_from_then_on_into_the_new_file(
        win, dialogs, tmp_path):
    editor = win.show_hydra()
    editor.add_component("curve", (0, 0))
    editor.save_graph()
    dialogs["answer"] = str(tmp_path / "copy.hydra")
    editor.save_graph_as()
    assert dialogs["save"] == 2
    editor.add_component("mesh", (0, 80))
    editor.save_graph()
    assert dialogs["save"] == 2
    assert _saved_keys(tmp_path / "copy.hydra") == ["curve", "mesh"]
    assert _saved_keys(tmp_path / "graph.hydra") == ["curve"]


def test_a_new_graph_or_a_file_gone_missing_asks_again(win, dialogs):
    import os
    editor = win.show_hydra()
    editor.save_graph()
    editor.new_graph()
    editor.save_graph()
    assert dialogs["save"] == 2
    os.remove(dialogs["answer"])
    editor.save_graph()
    assert dialogs["save"] == 3


def test_the_graphs_file_is_still_its_file_after_a_restart(win, dialogs):
    editor = win.show_hydra()
    editor.save_graph()
    win.mark_saved()
    win.close()
    again = MainWindow()
    try:
        editor = again.show_hydra()
        assert again._hydra_dock.windowTitle() == "Hydra · graph.hydra"
        editor.add_component("curve", (0, 0))
        editor.save_graph()
        assert dialogs["save"] == 1
        assert _saved_keys(dialogs["answer"]) == ["curve"]
    finally:
        again.mark_saved()
        again.close()


# -- vector -----------------------------------------------------------------

def _set_vector(win, editor, node, a, b):
    menu = editor.node_menu(editor.canvas.node_items[node.id])
    [action] = [x for x in menu.actions() if x.text() == "Set Vector..."]
    action.trigger()
    assert win.processor.busy
    win.processor.provide_text(",".join(str(c) for c in a))
    ghost = win.processor.request.preview_fn(b)
    win.processor.provide_text(",".join(str(c) for c in b))
    return ghost


def test_set_vector_takes_two_points_picked_in_the_model(win):
    editor = win.show_hydra()
    node = editor.add_component("vector", (0, 0))
    editor.solve()
    assert editor.results[node.id].status == "warning"
    ghost = _set_vector(win, editor, node, (1, 0, 0), (1, 3, 0))
    assert not win.processor.busy
    assert geo.shape_kind(ghost) == "curve"          # the arrow, while picking
    assert node.params["set"] == {"A": [1.0, 0.0, 0.0], "B": [1.0, 3.0, 0.0]}
    assert editor.results[node.id].status == "ok"
    [v] = editor.results[node.id].outputs["Vector"]
    assert v.components == (0, 3, 0)
    item = editor.canvas.node_items[node.id]
    assert item.port("B", False).toolTip() == "B: 1, 3, 0 (set in the model)"
    assert item.summary() == "1 vector"
    segs = win.scene.hydra_preview[1]
    assert segs[:, 1].max() == pytest.approx(3.0)
    assert len(win.scene.all()) == 0                  # setting adds nothing


def test_escape_while_setting_a_vector_keeps_the_one_it_had(win):
    editor = win.show_hydra()
    node = editor.add_component("vector", (0, 0))
    _set_vector(win, editor, node, (0, 0, 0), (2, 0, 0))
    menu = editor.node_menu(editor.canvas.node_items[node.id])
    [x for x in menu.actions() if x.text() == "Set Vector..."][0].trigger()
    win.processor.provide_text("5,5,5")
    win.processor.cancel()
    assert node.params["set"]["B"] == [2.0, 0.0, 0.0]


def test_only_a_vector_offers_set_vector(win):
    editor = win.show_hydra()
    for key in ("construct_point", "rotate", "slider", "curve"):
        node = editor.add_component(key, (0, 0))
        texts = [a.text() for a in
                 editor.node_menu(editor.canvas.node_items[node.id]).actions()]
        assert "Set Vector..." not in texts


def test_construct_point_has_x_y_z_inputs_that_default_to_zero(win):
    editor = win.show_hydra()
    node = editor.add_component("construct_point", (0, 0))
    editor.solve()
    item = editor.canvas.node_items[node.id]
    assert [p.toolTip() for p in item.inputs] == [
        "X: 0 (default)", "Y: 0 (default)", "Z: 0 (default)"]
    assert editor.results[node.id].status == "ok"
    assert len(win.scene.hydra_preview[2]) == 1        # one point shown


# -- the logo ----------------------------------------------------------------

def test_hydra_sits_at_the_foot_of_the_tool_strip_with_its_logo(win):
    from PySide6.QtWidgets import QToolButton
    win.resize(1400, 700)                  # shorter than the tools need
    win.show()
    QApplication.processEvents()
    bar = win._tools_toolbar
    host = bar.findChild(QWidget, "hydraButton")
    button = host.findChild(QToolButton)
    assert not button.icon().isNull()
    assert "Hydra" in button.toolTip()
    bottom = host.mapTo(bar, QPoint(0, host.height())).y()
    assert bar.height() - bottom <= 8
    strip = bar.findChild(QWidget, "toolStrip")
    assert strip.mapTo(bar, QPoint(0, 0)).y() < host.mapTo(bar, QPoint(0, 0)).y()
    button.click()
    assert win._hydra_dock is not None and win._hydra_dock.isVisible()


def test_the_logo_is_hydras_window_icon(win):
    win.show_hydra()
    assert not win._hydra_dock.windowIcon().isNull()


def test_a_hydra_file_handed_to_the_app_opens_in_hydra(win, tmp_path):
    import json
    from serpentine3d.app import _open_launch_args
    path = tmp_path / "launched.hydra"
    graph = {"nodes": [{"id": "a", "key": "curve"}], "wires": []}
    path.write_text(json.dumps(graph), encoding="utf-8")
    box = win.scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    _open_launch_args(win, [str(path)])
    assert win._hydra_dock.isVisible()
    assert list(win.hydra.graph.nodes) == ["a"]
    assert win.hydra.path == str(path)
    assert [o.id for o in win.scene.all()] == [box.id]    # model untouched


def test_opening_a_hydra_file_as_a_document_opens_it_in_hydra(win, tmp_path):
    import json
    path = tmp_path / "graph.hydra"
    path.write_text(json.dumps({"nodes": [{"id": "b", "key": "mesh"}]}),
                    encoding="utf-8")
    box = win.scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    win._open_path(str(path))
    assert list(win.hydra.graph.nodes) == ["b"]
    assert win.scene.get(box.id) is not None


# -- copy, paste and Alt-drag -------------------------------------------------

def _shown(win):
    win.show()
    editor = win.show_hydra()
    win._hydra_dock.activateWindow()
    QApplication.processEvents()
    return editor


def test_ctrl_c_and_ctrl_v_copy_the_selected_components(win):
    editor = _shown(win)
    curve = editor.add_component("curve", (0, 0))
    rotate = editor.add_component("rotate", (200, 0))
    editor.connect(curve.id, "Curve", rotate.id, "Geometry")
    box = win.scene.add(geo.make_box((0, 0, 0), 1, 1, 1))
    win.selection.set([box.id])
    editor.canvas.scene().clearSelection()
    for nid in (curve.id, rotate.id):
        editor.canvas.node_items[nid].setSelected(True)
    editor.canvas.setFocus()
    QTest.keyClick(editor.canvas, Qt.Key.Key_C,
                   Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(editor.canvas, Qt.Key.Key_V,
                   Qt.KeyboardModifier.ControlModifier)
    assert sorted(n.key for n in editor.graph.nodes.values()) == [
        "curve", "curve", "rotate", "rotate"]
    assert len(editor.graph.wires) == 2
    pasted = set(editor.selected_ids())
    assert len(pasted) == 2 and not pasted & {curve.id, rotate.id}
    # the model was left alone by the keys
    assert len(win.scene.all()) == 1 and win.selection.ids == [box.id]


def test_pasting_twice_makes_two_copies(win):
    editor = _shown(win)
    node = editor.add_component("slider", (0, 0))
    editor.canvas.node_items[node.id].setSelected(True)
    editor.copy_selected()
    editor.paste()
    editor.paste()
    assert [n.key for n in editor.graph.nodes.values()] == ["slider"] * 3


def test_alt_dragging_a_component_pulls_a_copy_off_it(win):
    editor = _shown(win)
    curve = editor.add_component("curve", (0, 0))
    rotate = editor.add_component("rotate", (220, 0))
    editor.connect(curve.id, "Curve", rotate.id, "Geometry")
    view = editor.canvas
    view.centerOn(100, 0)
    QApplication.processEvents()
    item = view.node_items[rotate.id]
    start = view.mapFromScene(item.mapToScene(
        QPointF(item.width * 0.6, item.height / 2)))
    end = start + QPoint(0, 120)
    alt = Qt.KeyboardModifier.AltModifier
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, alt, start)
    QTest.mouseMove(view.viewport(), start + QPoint(0, 60))
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, alt, end)
    assert (rotate.x, rotate.y) == (220, 0)          # the original stayed
    [copy] = [n for n in editor.graph.nodes.values()
              if n.key == "rotate" and n.id != rotate.id]
    assert copy.x == pytest.approx(220, abs=2)
    assert copy.y == pytest.approx(120 / view.transform().m11(), abs=3)
    # the wire from outside stays with the original
    assert [w.target for w in editor.graph.wires] == [rotate.id]


def _drag_wire(view, start_scene, end_scene, check=None):
    a = view.mapFromScene(start_scene)
    b = view.mapFromScene(end_scene)
    left = Qt.MouseButton.LeftButton

    def send(kind, at, button, held):
        QApplication.sendEvent(view.viewport(), QMouseEvent(
            kind, QPointF(at), QPointF(view.mapToGlobal(at)), button, held,
            Qt.KeyboardModifier.NoModifier))
    send(QEvent.Type.MouseButtonPress, a, left, left)
    send(QEvent.Type.MouseMove, (a + b) / 2, Qt.MouseButton.NoButton, left)
    send(QEvent.Type.MouseMove, b, Qt.MouseButton.NoButton, left)
    if check is not None:
        check()
    send(QEvent.Type.MouseButtonRelease, b, left, Qt.MouseButton.NoButton)


def test_a_wire_docks_on_an_input_it_ends_near_and_lights_it_first(win):
    editor = _shown(win)
    slider = editor.add_component("slider", (-300, 0))
    rotate = editor.add_component("rotate", (40, -20))
    view = editor.canvas
    view.centerOn(-60, 0)
    QApplication.processEvents()
    out = view.node_items[slider.id].port("Number", True)
    angle = view.node_items[rotate.id].port("Angle", False)
    near = angle.scenePos() + QPointF(-14, 7)        # beside it, not on it
    seen = []
    _drag_wire(view, out.scenePos(), near,
               lambda: seen.append(angle._hover))
    assert seen == [True]
    assert not angle._hover                          # put out once docked
    assert [(w.source, w.input) for w in editor.graph.wires] == [
        (slider.id, "Angle")]


def test_a_wire_let_go_on_a_component_docks_on_the_input_that_takes_it(win):
    editor = _shown(win)
    curve = editor.add_component("curve", (-300, 0))
    slider = editor.add_component("slider", (-300, 120))
    rotate = editor.add_component("rotate", (40, -20))
    view = editor.canvas
    view.centerOn(-60, 40)
    QApplication.processEvents()
    item = view.node_items[rotate.id]
    middle = item.mapToScene(QPointF(item.width * 0.7, 4))   # top of the body
    _drag_wire(view, view.node_items[curve.id].port("Curve", True).scenePos(),
               middle)
    _drag_wire(view, view.node_items[slider.id].port("Number", True).scenePos(),
               middle)
    assert sorted((editor.graph.nodes[w.source].key, w.input)
                  for w in editor.graph.wires) == [
        ("curve", "Geometry"), ("slider", "Angle")]


def test_a_port_can_be_caught_a_little_way_off_its_dot(win):
    editor = _shown(win)
    slider = editor.add_component("slider", (0, 0))
    view = editor.canvas
    view.centerOn(100, 0)
    QApplication.processEvents()
    out = view.node_items[slider.id].port("Number", True)
    found = view.scene()._port_at(out.scenePos() + QPointF(8, 6))
    assert found is out


# -- the search on the canvas -------------------------------------------------

def _listed(search):
    return [search.list.item(i).text() for i in range(search.list.count())]


def test_double_clicking_the_canvas_opens_a_search_to_type_into(win):
    editor = _shown(win)
    view = editor.canvas
    QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton,
                      pos=view.viewport().rect().center())
    QApplication.processEvents()
    search = editor.search
    assert search is not None and search.isVisible()
    assert search.field.hasFocus()
    assert _listed(search) == ["Point", "Curve", "Brep", "Mesh",
                               "Number Slider"]
    search.close()


def test_a_right_click_on_the_canvas_opens_the_same_search(win):
    from serpentine3d.ui.hydra_editor import ComponentSearch
    editor = _shown(win)
    editor.show_menu(QPointF(0, 0), QPoint(200, 200))
    assert isinstance(editor.search, ComponentSearch)
    assert editor.search.isVisible()
    editor.search.close()


def test_typing_hides_the_components_that_do_not_fit(win):
    editor = _shown(win)
    search = editor.find_component(QPointF(0, 0), QPoint(200, 200))
    QTest.keyClicks(search.field, "rot")
    assert _listed(search) == ["Rotate"]
    search.field.clear()
    QTest.keyClicks(search.field, "point")
    assert _listed(search) == ["Point", "Construct Point"]
    search.field.clear()
    QTest.keyClicks(search.field, "crv")
    assert _listed(search) == ["Curve"]
    search.close()


def test_enter_adds_the_chosen_component_where_the_canvas_was_clicked(win):
    editor = _shown(win)
    search = editor.find_component(QPointF(120, 80), QPoint(200, 200))
    QTest.keyClicks(search.field, "point")
    QTest.keyClick(search.field, Qt.Key.Key_Down)
    QTest.keyClick(search.field, Qt.Key.Key_Return)
    [node] = editor.graph.nodes.values()
    assert node.key == "construct_point"
    assert (node.x, node.y) == (120, 80)
    assert not search.isVisible()


def test_a_click_on_a_listed_component_adds_it(win):
    editor = _shown(win)
    search = editor.find_component(QPointF(0, 0), QPoint(200, 200))
    item = search.list.item(1)
    rect = search.list.visualItemRect(item)
    QTest.mouseClick(search.list.viewport(), Qt.MouseButton.LeftButton,
                     pos=rect.center())
    assert [n.key for n in editor.graph.nodes.values()] == ["curve"]


def test_escape_closes_the_search_and_adds_nothing(win):
    editor = _shown(win)
    search = editor.find_component(QPointF(0, 0), QPoint(200, 200))
    QTest.keyClicks(search.field, "rot")
    QTest.keyClick(search.field, Qt.Key.Key_Escape)
    assert not search.isVisible()
    assert editor.graph.nodes == {}


def test_the_toolbar_still_lists_every_component(win):
    editor = win.show_hydra()
    titles = [a.text() for a in editor.component_menu(None).actions()
              if not a.isSeparator()]
    assert "Rotate" in titles and "Vector" in titles


# -- where Hydra opens ------------------------------------------------------

def test_hydra_opens_where_it_was_docked_last_time(win):
    win.show()
    win.show_hydra()
    dock = win._hydra_dock
    dock.setFloating(False)
    win.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    QApplication.processEvents()
    win.mark_saved()
    win.close()
    for opens in (False, True):           # a session without Hydra between
        again = MainWindow()
        try:
            again.show()
            QApplication.processEvents()
            if opens:
                again.show_hydra()
                QApplication.processEvents()
                assert not again._hydra_dock.isFloating()
                assert again.dockWidgetArea(again._hydra_dock) == (
                    Qt.DockWidgetArea.LeftDockWidgetArea)
        finally:
            again.mark_saved()
            again.close()


def test_hydra_floats_where_it_floated_last_time(win):
    win.show()
    win.show_hydra()
    dock = win._hydra_dock
    dock.setFloating(True)
    dock.setGeometry(140, 160, 720, 430)
    QApplication.processEvents()
    size = dock.size()
    win.mark_saved()
    win.close()
    again = MainWindow()
    try:
        again.show()
        again.show_hydra()
        QApplication.processEvents()
        assert again._hydra_dock.isFloating()
        assert again._hydra_dock.size() == size
    finally:
        again.mark_saved()
        again.close()


def test_the_first_time_hydra_opens_floating(win):
    win.show()
    win.show_hydra()
    assert win._hydra_dock.isFloating()


def test_a_vector_wired_into_move_moves_the_preview(win):
    editor = win.show_hydra()
    line = win.scene.add(geo.make_line((0, 0, 0), (1, 0, 0)))
    curve = editor.add_component("curve", (-300, 0))
    editor.set_references(curve.id, [line.id])
    editor.set_preview(curve.id, False)
    vector = editor.add_component("vector", (-300, 100))
    editor.set_inputs(vector.id, {"A": (0, 0, 0), "B": (0, 3, 0)})
    editor.set_preview(vector.id, False)
    move = editor.add_component("move", (0, 0))
    editor.connect(curve.id, "Curve", move.id, "G")
    editor.connect(vector.id, "Vector", move.id, "V")
    editor.solve()
    segs = win.scene.hydra_preview[1]
    assert segs[:, 1] == pytest.approx(3.0)
    item = editor.canvas.node_items[move.id]
    assert [p.port.name for p in item.inputs] == ["G", "V"]
    assert item.port("V", False).toolTip() == "V: 0, 3, 0"


# -- cast ---------------------------------------------------------------------

def _menu_action(editor, node, text):
    menu = editor.node_menu(editor.canvas.node_items[node.id])
    found = [a for a in menu.actions() if a.text() == text]
    return found[0] if found else None


def _rotated_lines(win, editor, count=2):
    lines = [win.scene.add(geo.make_line((1 + i, 0, 0), (2 + i, 0, 0)))
             for i in range(count)]
    curve = editor.add_component("curve", (-300, 0))
    editor.set_references(curve.id, [l.id for l in lines])
    angle = editor.add_component("slider", (-300, 100))
    angle.params.update(value=90.0, max=360.0)
    rotate = editor.add_component("rotate", (0, 0))
    editor.connect(curve.id, "Curve", rotate.id, "Geometry")
    editor.connect(angle.id, "Number", rotate.id, "Angle")
    editor.solve()
    return lines, curve, angle, rotate


def _answer_cast(monkeypatch, layer=None, group=None, seen=None):
    from serpentine3d.ui import hydra_editor

    def answer(dialog):
        if seen is not None:
            seen.append(dialog)
        if layer is not None:
            dialog.layers.setCurrentIndex(dialog.layers.findData(layer))
        if group is not None:
            dialog.group.setChecked(group)
        return hydra_editor.QDialog.DialogCode.Accepted
    monkeypatch.setattr(hydra_editor.CastDialog, "exec", answer)


def test_cast_is_in_the_menu_of_components_that_make_geometry(win):
    editor = win.show_hydra()
    lines, curve, angle, rotate = _rotated_lines(win, editor)
    for node in (curve, rotate):
        assert _menu_action(editor, node, "Cast...") is not None
    for key in ("slider", "vector"):
        node = editor.add_component(key, (0, 200))
        assert _menu_action(editor, node, "Cast...") is None


def test_cast_is_greyed_out_while_a_component_makes_nothing(win):
    editor = win.show_hydra()
    rotate = editor.add_component("rotate", (0, 0))
    editor.solve()
    assert not _menu_action(editor, rotate, "Cast...").isEnabled()


def test_cast_adds_what_the_component_makes_onto_the_chosen_layer(
        win, monkeypatch):
    editor = win.show_hydra()
    lines, curve, angle, rotate = _rotated_lines(win, editor)
    layer_id = win.scene.layers.create("Hydra output").id
    assert layer_id != win.scene.layers.current_id
    _answer_cast(monkeypatch, layer=layer_id, group=False)
    _menu_action(editor, rotate, "Cast...").trigger()
    new = [o for o in win.scene.all() if o.id not in {l.id for l in lines}]
    assert len(new) == 2
    assert {o.layer_id for o in new} == {layer_id}
    assert {o.kind for o in new} == {"curve"}
    assert all(o.group_id is None for o in new)
    assert sorted(win.selection.ids) == sorted(o.id for o in new)
    # turned as the preview showed them, and the model's own lines untouched
    from serpentine3d.core.tessellate import tessellate
    for obj in new:
        pts = tessellate(obj.shape).edge_segments.reshape(-1, 3)
        assert pts[:, 0] == pytest.approx(0, abs=1e-6)
    for line in lines:
        pts = tessellate(line.shape).edge_segments.reshape(-1, 3)
        assert pts[:, 1] == pytest.approx(0, abs=1e-6)


def test_cast_can_group_its_objects(win, monkeypatch):
    editor = win.show_hydra()
    lines, curve, angle, rotate = _rotated_lines(win, editor, count=3)
    _answer_cast(monkeypatch, group=True)
    objects = editor.cast(rotate.id)
    assert len(objects) == 3
    groups = {win.scene.get(o.id).group_id for o in objects}
    assert len(groups) == 1 and None not in groups


def test_the_group_box_only_shows_for_more_than_one_object(win, monkeypatch):
    editor = win.show_hydra()
    seen = []
    _answer_cast(monkeypatch, seen=seen)
    lines, curve, angle, rotate = _rotated_lines(win, editor, count=1)
    editor.cast(rotate.id)
    assert not seen[-1].group.isVisibleTo(seen[-1])
    more, curve2, angle2, rotate2 = _rotated_lines(win, editor, count=2)
    editor.cast(rotate2.id)
    assert seen[-1].group.isVisibleTo(seen[-1])
    assert "2 objects" in seen[-1].group.text()


def test_the_dialog_offers_every_layer_and_starts_on_the_current_one(win):
    from serpentine3d.ui.hydra_editor import CastDialog
    editor = win.show_hydra()
    layers = win.scene.layers
    dialog = CastDialog(layers, 2, False, editor)
    offered = [dialog.layers.itemData(i) for i in range(dialog.layers.count())]
    assert offered == [layer.id for layer in layers.all()]
    assert dialog.layer_id() == layers.current_id


def test_a_cast_is_one_undo_step(win, monkeypatch):
    editor = win.show_hydra()
    lines, curve, angle, rotate = _rotated_lines(win, editor, count=3)
    _answer_cast(monkeypatch, group=True)
    editor.cast(rotate.id)
    assert len(win.scene.all()) == 6
    win.history.undo()
    assert sorted(o.id for o in win.scene.all()) == sorted(l.id for l in lines)


def test_cancelling_the_dialog_casts_nothing(win, monkeypatch):
    from serpentine3d.ui import hydra_editor
    editor = win.show_hydra()
    lines, curve, angle, rotate = _rotated_lines(win, editor)
    monkeypatch.setattr(hydra_editor.CastDialog, "exec",
                        lambda dialog: hydra_editor.QDialog.DialogCode.Rejected)
    assert editor.cast(rotate.id) == []
    assert len(win.scene.all()) == 2


def test_cast_objects_stay_put_when_the_graph_changes(win, monkeypatch):
    editor = win.show_hydra()
    lines, curve, angle, rotate = _rotated_lines(win, editor, count=1)
    _answer_cast(monkeypatch)
    [cast] = editor.cast(rotate.id)
    before = cast.shape
    editor.canvas.node_items[angle.id].slide_to(10)
    editor.solve()
    assert win.scene.get(cast.id).shape is before


def test_casting_with_several_components_selected_casts_them_all(
        win, monkeypatch):
    editor = win.show_hydra()
    lines, curve, angle, rotate = _rotated_lines(win, editor, count=1)
    move = editor.add_component("move", (0, 150))
    editor.connect(rotate.id, "Geometry", move.id, "G")
    editor.solve()
    for node in (rotate, move):
        editor.canvas.node_items[node.id].setSelected(True)
    _answer_cast(monkeypatch)
    assert len(editor.cast(move.id)) == 2


def test_cast_remembers_whether_to_group(win, monkeypatch):
    editor = win.show_hydra()
    seen = []
    lines, curve, angle, rotate = _rotated_lines(win, editor, count=2)
    _answer_cast(monkeypatch, group=True, seen=seen)
    editor.cast(rotate.id)
    _answer_cast(monkeypatch, seen=seen)
    editor.cast(rotate.id)
    assert seen[-1].group.isChecked()


@pytest.mark.parametrize("key, label", [
    ("point", "Set Pt..."), ("curve", "Set Crv..."), ("brep", "Set Brep..."),
    ("mesh", "Set Mesh..."), ("vector", "Set Vector..."),
])
def test_each_component_names_what_it_is_set_to(win, key, label):
    editor = win.show_hydra()
    node = editor.add_component(key, (0, 0))
    texts = [a.text() for a in
             editor.node_menu(editor.canvas.node_items[node.id]).actions()]
    assert label in texts and "Set to..." not in texts


# -- hide ---------------------------------------------------------------------

def _two_breps(win, editor):
    boxes = [win.scene.add(geo.make_box((3 * i, 0, 0), 1, 1, 1))
             for i in range(2)]
    nodes = []
    for i, box in enumerate(boxes):
        node = editor.add_component("brep", (0, 80 * i))
        editor.set_references(node.id, [box.id])
        nodes.append(node)
    editor.solve()
    return boxes, nodes


def test_hide_in_the_menu_takes_a_component_out_of_the_viewports(win):
    editor = win.show_hydra()
    boxes, (a, b) = _two_breps(win, editor)
    full = len(win.scene.hydra_preview[0])
    _menu_action(editor, a, "Hide").trigger()
    editor.solve()
    assert not a.preview and b.preview
    assert 0 < len(win.scene.hydra_preview[0]) < full
    assert editor.canvas.node_items[a.id].is_hidden()
    # and the menu offers to show it again
    _menu_action(editor, a, "Show").trigger()
    editor.solve()
    assert a.preview and len(win.scene.hydra_preview[0]) == full


def test_ctrl_h_hides_the_selection_and_ctrl_shift_h_shows_it(win):
    editor = _shown(win)
    boxes, (a, b) = _two_breps(win, editor)
    for node in (a, b):
        editor.canvas.node_items[node.id].setSelected(True)
    editor.canvas.setFocus()
    ctrl = Qt.KeyboardModifier.ControlModifier
    shift = Qt.KeyboardModifier.ShiftModifier
    QTest.keyClick(editor.canvas, Qt.Key.Key_H, ctrl)
    editor.solve()
    assert not a.preview and not b.preview
    assert win.scene.hydra_preview is None
    # a second Ctrl+H hides, it does not show
    QTest.keyClick(editor.canvas, Qt.Key.Key_H, ctrl)
    assert not a.preview and not b.preview
    QTest.keyClick(editor.canvas, Qt.Key.Key_H, ctrl | shift)
    editor.solve()
    assert a.preview and b.preview
    # the model kept its own objects visible: the keys were Hydra's here
    assert all(win.scene.get(box.id).visible for box in boxes)


def test_ctrl_shift_h_with_nothing_selected_shows_every_hidden_one(win):
    editor = _shown(win)
    boxes, (a, b) = _two_breps(win, editor)
    editor.hide([a.id, b.id])
    editor.canvas.scene().clearSelection()
    editor.canvas.setFocus()
    QTest.keyClick(editor.canvas, Qt.Key.Key_H,
                   Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.ShiftModifier)
    assert a.preview and b.preview


def test_ctrl_shift_h_shows_only_the_selected_when_some_are(win):
    editor = win.show_hydra()
    boxes, (a, b) = _two_breps(win, editor)
    editor.hide([a.id, b.id])
    editor.canvas.node_items[a.id].setSelected(True)
    editor.show_hidden()
    assert a.preview and not b.preview


def test_ctrl_h_on_a_mixed_selection_hides_them_all(win):
    editor = win.show_hydra()
    boxes, (a, b) = _two_breps(win, editor)
    editor.set_preview(a.id, False)
    for node in (a, b):
        editor.canvas.node_items[node.id].setSelected(True)
    editor.hide()
    assert not a.preview and not b.preview


def test_the_menu_names_the_keys_for_hide_and_show(win):
    editor = win.show_hydra()
    boxes, (a, b) = _two_breps(win, editor)
    hide = _menu_action(editor, a, "Hide")
    assert hide.shortcut().toString() == "Ctrl+H"
    editor.hide([a.id])
    show = _menu_action(editor, a, "Show")
    assert show.shortcut().toString() == "Ctrl+Shift+H"


def test_hide_from_the_menu_takes_the_whole_selection(win):
    editor = win.show_hydra()
    boxes, (a, b) = _two_breps(win, editor)
    for node in (a, b):
        editor.canvas.node_items[node.id].setSelected(True)
    _menu_action(editor, b, "Hide").trigger()
    assert not a.preview and not b.preview


def test_what_shows_nothing_in_the_viewports_has_nothing_to_hide(win):
    editor = win.show_hydra()
    slider = editor.add_component("slider", (0, 0))
    assert _menu_action(editor, slider, "Hide") is None
    item = editor.canvas.node_items[slider.id]
    slider.preview = False
    assert not item.is_hidden()
    for key in ("vector", "move", "construct_point"):
        node = editor.add_component(key, (0, 100))
        assert _menu_action(editor, node, "Hide") is not None


def test_a_hidden_component_is_drawn_darker_than_a_shown_one(win):
    from PySide6.QtGui import QImage, QPainter
    editor = win.show_hydra()
    boxes, (a, b) = _two_breps(win, editor)
    editor.set_preview(a.id, False)

    def brightness(node):
        item = editor.canvas.node_items[node.id]
        image = QImage(int(item.width), int(item.height),
                       QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        item.paint(painter, None)
        painter.end()
        pixels = [image.pixelColor(x, y).lightness()
                  for x in range(4, image.width() - 4, 3)
                  for y in range(4, image.height() - 4, 3)]
        return sum(pixels) / len(pixels)
    assert brightness(a) < brightness(b) * 0.8


def test_a_hidden_component_stays_hidden_in_a_saved_graph(win):
    editor = win.show_hydra()
    boxes, (a, b) = _two_breps(win, editor)
    editor.hide([a.id])
    again = Graph.from_dict(editor.graph.to_dict())
    assert not again.nodes[a.id].preview and again.nodes[b.id].preview


# -- the start page -------------------------------------------------------------

def _save_graphs(win, dialogs, tmp_path, names):
    """Save one small graph under each name, through Save As."""
    editor = win.show_hydra()
    for i, name in enumerate(names):
        editor.new_graph()
        for k in range(i + 1):
            editor.add_component("curve", (0, 60 * k))
        dialogs["answer"] = str(tmp_path / f"{name}.hydra")
        editor.save_graph_as()
    return editor


def _reopen(win):
    win._hydra_dock.close()
    QApplication.processEvents()
    return win.show_hydra()


def test_opening_hydra_shows_the_recent_graphs_as_cards(
        win, dialogs, tmp_path):
    _save_graphs(win, dialogs, tmp_path, ["first", "second"])
    editor = _reopen(win)
    assert editor.starting()
    titles = [card.title for card in editor.start.cards]
    assert titles == ["Continue", "second", "first"]      # newest first


def test_double_clicking_a_card_opens_that_graph(win, dialogs, tmp_path):
    _save_graphs(win, dialogs, tmp_path, ["one", "two"])
    editor = _reopen(win)
    [one] = [c for c in editor.start.cards if c.title == "one"]
    QTest.mouseDClick(one, Qt.MouseButton.LeftButton)
    assert not editor.starting()
    assert editor.path == str(tmp_path / "one.hydra")
    assert [n.key for n in editor.graph.nodes.values()] == ["curve"]


def test_continue_goes_back_to_the_graph_being_worked_on(
        win, dialogs, tmp_path):
    editor = _save_graphs(win, dialogs, tmp_path, ["saved"])
    editor.add_component("rotate", (300, 0))          # not saved yet
    editor = _reopen(win)
    QTest.mouseDClick(editor.start.cards[0], Qt.MouseButton.LeftButton)
    assert not editor.starting()
    assert "rotate" in [n.key for n in editor.graph.nodes.values()]


def test_escape_on_the_start_page_continues(win, dialogs, tmp_path):
    _save_graphs(win, dialogs, tmp_path, ["saved"])
    editor = _reopen(win)
    QTest.keyClick(editor.start, Qt.Key.Key_Escape)
    assert not editor.starting()


def test_without_saved_graphs_hydra_opens_on_the_canvas(win):
    editor = win.show_hydra()
    assert not editor.starting()


def test_raising_hydra_while_it_is_open_keeps_the_canvas(
        win, dialogs, tmp_path):
    editor = _save_graphs(win, dialogs, tmp_path, ["saved"])
    editor.show_canvas()
    win.show_hydra()
    assert not editor.starting()


def test_a_graph_gone_from_disk_has_no_card(win, dialogs, tmp_path):
    import os
    _save_graphs(win, dialogs, tmp_path, ["kept", "gone"])
    os.remove(tmp_path / "gone.hydra")
    editor = _reopen(win)
    assert [c.title for c in editor.start.cards] == ["Continue", "kept"]


def test_adding_a_component_leaves_the_start_page(win, dialogs, tmp_path):
    _save_graphs(win, dialogs, tmp_path, ["saved"])
    editor = _reopen(win)
    editor.add_component("mesh", (0, 0))
    assert not editor.starting()


def test_an_opened_graph_is_a_recent_one_too(win, dialogs, tmp_path):
    import json
    path = tmp_path / "from_outside.hydra"
    path.write_text(json.dumps({"nodes": [{"id": "a", "key": "brep"}]}),
                    encoding="utf-8")
    editor = win.show_hydra()
    editor.open_path(str(path))
    assert editor.recent()[0] == str(path)


def test_a_cards_picture_shows_the_graph(win):
    from serpentine3d.ui.hydra_editor import graph_preview
    graph = Graph()
    a = graph.add_node("curve", 0, 0)
    b = graph.add_node("rotate", 300, 40)
    graph.connect(a.id, "Curve", b.id, "Geometry")
    drawn = graph_preview(graph.to_dict(), 210, 118).toImage()
    empty = graph_preview({}, 210, 118).toImage()
    background = drawn.pixelColor(2, 2)
    painted = sum(drawn.pixelColor(x, y) != background
                  for x in range(0, 210, 3) for y in range(0, 118, 3))
    assert painted > 100
    assert drawn != empty


# -- what comes back from the session before -----------------------------------

def _restart(win):
    win.mark_saved()
    win.close()
    again = MainWindow()
    again.show()
    return again


def test_a_graph_whose_file_was_deleted_does_not_come_back(
        win, dialogs, tmp_path):
    import os
    editor = win.show_hydra()
    editor.add_component("rotate", (0, 0))
    editor.save_graph()
    os.remove(dialogs["answer"])
    again = _restart(win)
    try:
        editor = again.show_hydra()
        assert editor.graph.nodes == {}
        assert editor.path is None
        assert again._hydra_dock.windowTitle() == "Hydra"
        assert not editor.starting()          # nothing to offer: the canvas
    finally:
        again.mark_saved()
        again.close()


def test_unsaved_work_is_offered_to_continue_on_the_start_page(win):
    editor = win.show_hydra()
    editor.add_component("curve", (0, 0))     # never saved to a file
    again = _restart(win)
    try:
        editor = again.show_hydra()
        assert editor.starting()
        assert [c.title for c in editor.start.cards] == ["Continue"]
        QTest.mouseDClick(editor.start.cards[0], Qt.MouseButton.LeftButton)
        assert [n.key for n in editor.graph.nodes.values()] == ["curve"]
    finally:
        again.mark_saved()
        again.close()


def test_a_graph_whose_file_is_still_there_is_offered_with_it(
        win, dialogs, tmp_path):
    editor = win.show_hydra()
    editor.add_component("mesh", (0, 0))
    editor.save_graph()
    again = _restart(win)
    try:
        editor = again.show_hydra()
        assert editor.starting()
        assert [c.title for c in editor.start.cards] == ["Continue", "graph"]
        assert editor.path == dialogs["answer"]
    finally:
        again.mark_saved()
        again.close()


def test_reopening_hydra_in_the_same_session_starts_on_the_cards(win):
    editor = win.show_hydra()
    editor.add_component("brep", (0, 0))
    editor = _reopen(win)
    assert editor.starting()
    assert [c.title for c in editor.start.cards] == ["Continue"]


def test_the_search_has_no_scroll_bar_and_shows_every_entry_whole(win):
    editor = _shown(win)
    search = editor.find_component(QPointF(0, 0), QPoint(200, 200))
    QApplication.processEvents()
    for text in ("", "po", "rot"):
        search.field.setText(text)
        QApplication.processEvents()
        lst = search.list
        assert not lst.verticalScrollBar().isVisible()
        assert not lst.horizontalScrollBar().isVisible()
        last = lst.visualItemRect(lst.item(lst.count() - 1))
        assert lst.viewport().rect().contains(last)
    search.close()
