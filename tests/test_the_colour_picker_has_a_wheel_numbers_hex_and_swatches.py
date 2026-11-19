import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from serpentine3d.ui import color_picker
from serpentine3d.ui.color_picker import (
    HISTORY_SIZE, ColorPicker, _disc_to_square, _square_to_disc, parse_hex,
)

app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _own_history(tmp_path, monkeypatch):
    monkeypatch.setattr(color_picker, "_history_path",
                        lambda: str(tmp_path / "color_history.json"))


def _picker(name="#336699"):
    return ColorPicker(QColor(name), None, "Colour")


def test_hex_is_read_with_or_without_hash_and_short():
    assert parse_hex("#FF8000").name() == "#ff8000"
    assert parse_hex(" ff8000 ").name() == "#ff8000"
    assert parse_hex("#f80").name() == "#ff8800"
    assert parse_hex("ff80") is None
    assert parse_hex("zzzzzz") is None


def test_pasting_a_hex_code_sets_the_colour():
    picker = _picker()
    picker.hex.setText("#00ff00")
    picker.hex.textEdited.emit("#00ff00")
    assert picker.color().name() == "#00ff00"
    assert [b.value() for b in picker.fields[:3]] == [0, 255, 0]


def test_the_copy_button_puts_the_hex_code_on_the_clipboard():
    picker = _picker("#123456")
    picker.copy_button.click()
    assert QApplication.clipboard().text() == "#123456"
    assert picker.copy_button.icon().cacheKey() ==         picker._check_icon.cacheKey(), "copying showed no tick"
    picker._copied.timeout.emit()
    assert picker.copy_button.icon().cacheKey() ==         picker._copy_icon.cacheKey()


def test_rgb_shows_three_fields_and_cmyk_four():
    picker = _picker()
    assert [b.isVisibleTo(picker) for b in picker.fields] == \
        [True, True, True, False]
    picker.mode.setCurrentText("CMYK")
    assert all(b.isVisibleTo(picker) for b in picker.fields)
    picker.mode.setCurrentText("RGB")
    assert not picker.fields[3].isVisibleTo(picker)


def test_typing_numbers_changes_the_colour_in_every_mode():
    picker = _picker()
    picker.fields[0].setValue(255)
    picker.fields[1].setValue(0)
    picker.fields[2].setValue(0)
    assert picker.color().name() == "#ff0000"
    assert picker.hex.text() == "#FF0000"

    picker.mode.setCurrentText("HSV")
    picker.fields[0].setValue(120)
    assert picker.color().name() == "#00ff00"

    picker.mode.setCurrentText("CMYK")
    for box, value in zip(picker.fields, (0, 100, 100, 0)):
        box.setValue(value)
    assert picker.color().name() == "#ff0000"


def test_the_disc_mapping_reaches_every_corner():
    for x, y in ((1, 1), (-1, -1), (1, -1), (0.3, -0.6)):
        u, v = _square_to_disc(x, y)
        assert u * u + v * v <= 1 + 1e-9
        bx, by = _disc_to_square(u, v)
        assert abs(bx - x) < 1e-6 and abs(by - y) < 1e-6


def test_the_wheel_picks_hue_on_the_ring_and_shade_in_the_disc():
    picker = _picker("#ff0000")
    wheel = picker.wheel
    c = wheel._center()
    outer, width = wheel._ring()
    wheel._drag = "ring"
    # red sits on top, so the bottom of the ring is half way round: cyan
    wheel._apply(QPointF(c.x(), c.y() + (outer - width / 2)))
    assert picker.color().name() == "#00ffff"
    wheel._drag = "disc"
    wheel._apply(c)
    h, s, v, _a = picker.color().getHsvF()
    assert abs(s - 0.5) < 0.01 and abs(v - 0.5) < 0.01


def test_a_grey_keeps_the_hue_it_had():
    picker = _picker("#00ff00")
    picker.hex.textEdited.emit("#808080")
    assert abs(picker.wheel.h - 1 / 3) < 0.01


def test_accepting_puts_the_colour_first_in_the_history():
    for name in ("#111111", "#222222", "#111111"):
        picker = _picker()
        picker.set_color(QColor(name))
        picker.accept()
    assert color_picker.load_history()[:2] == ["#111111", "#222222"]
    assert _picker().history.names[:2] == ["#111111", "#222222"]


def test_the_history_keeps_eight():
    for i in range(HISTORY_SIZE + 3):
        color_picker.remember(QColor(i * 10, 0, 0))
    assert len(color_picker.load_history()) == HISTORY_SIZE


def test_a_fixed_swatch_sets_the_colour_and_a_double_click_takes_it():
    picker = _picker()
    picker.fixed[1].picked.emit(QColor(picker.fixed[1].names[0]))
    assert picker.color().name() == "#000000"
    picker.fixed[0].chosen.emit(QColor("#0000ff"))
    assert picker.result() == ColorPicker.DialogCode.Accepted
    assert picker.color().name() == "#0000ff"


def test_two_fixed_rows_with_browns_and_greys():
    rows = color_picker.FIXED_COLORS
    assert len(rows) == 2 and all(len(r) == HISTORY_SIZE for r in rows)
    assert {"#000000", "#808080", "#ffffff"} <= set(rows[1])


def test_the_eyedropper_follows_and_escape_puts_it_back():
    picker = _picker("#336699")
    dropper = picker.eyedropper
    dropper.started.emit()
    dropper.hovered.emit(QColor("#abcdef"))
    assert picker.color().name() == "#abcdef"
    dropper.cancelled.emit()
    assert picker.color().name() == "#336699"


def test_holding_the_eyedropper_rings_the_pointer_in_the_colour_under_it(
        monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    monkeypatch.setattr(color_picker, "screen_color",
                        lambda pos: QColor("#abcdef"))
    picker = _picker("#336699")
    picker.show()
    dropper = picker.eyedropper
    QTest.mousePress(dropper, Qt.MouseButton.LeftButton)
    ring = dropper.ring
    assert ring.isVisible()
    assert ring.color.name() == "#abcdef"
    assert ring.WIDTH == 5
    centre = ring.geometry().center()
    assert (centre - dropper.mapToGlobal(dropper.rect().center())
            ).manhattanLength() <= 2
    QTest.mouseRelease(dropper, Qt.MouseButton.LeftButton)
    assert not ring.isVisible()
    assert picker.color().name() == "#abcdef"
    picker.close()


def _picking(monkeypatch, name, accept):
    """Stand in for a person: pick `name`, wait for the live preview to
    catch up, then press OK or Cancel."""
    import time

    def run(dialog):
        dialog.set_color(QColor(name))
        end = time.monotonic() + 1
        while time.monotonic() < end and not seen:
            QApplication.processEvents()
        return (ColorPicker.DialogCode.Accepted if accept
                else ColorPicker.DialogCode.Rejected)
    seen = []
    monkeypatch.setattr(ColorPicker, "exec", run)
    return seen


def test_the_colour_shows_live_and_is_put_back_on_close(monkeypatch):
    seen = _picking(monkeypatch, "#ff0000", accept=True)
    got = color_picker.get_color(QColor("#336699"), None, "Colour",
                                 lambda c: seen.append(c and c.name()))
    assert seen[0] == "#ff0000", "no live preview while picking"
    assert seen[-1] is None, "the preview was not put back on close"
    assert got.name() == "#ff0000"


def test_cancelling_the_picker_puts_the_layer_colour_back(monkeypatch):
    from serpentine3d.core.history import History
    from serpentine3d.core.scene import Scene
    from serpentine3d.ui.layers_panel import _COLOR_COL, LayersPanel
    scene = Scene()
    panel = LayersPanel(scene, History(scene))
    layer = scene.layers.create("A").id
    scene.notify()
    before = scene.layers.get(layer).color
    lives = []
    scene.add_listener(
        lambda *a: lives.append(scene.layers.get(layer).color))
    seen = _picking(monkeypatch, "#ff0000", accept=False)
    scene.add_listener(lambda *a: seen.append(True))
    item = next(panel.tree.topLevelItem(i)
                for i in range(panel.tree.topLevelItemCount())
                if panel._layer_id(panel.tree.topLevelItem(i)) == layer)
    panel._item_clicked(item, _COLOR_COL)
    assert (1.0, 0.0, 0.0) in lives, "the layer never showed the colour live"
    assert scene.layers.get(layer).color == before


def test_a_click_outside_the_ring_changes_nothing():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    picker = _picker("#336699")
    picker.show()
    wheel = picker.wheel
    c = wheel._center()
    outer, width = wheel._ring()
    QTest.mouseClick(wheel, Qt.MouseButton.LeftButton, pos=QPoint(
        round(c.x() + outer + 3), round(c.y())))
    assert picker.color().name() == "#336699"
    QTest.mouseClick(wheel, Qt.MouseButton.LeftButton, pos=QPoint(
        round(c.x() + outer - width / 2), round(c.y())))
    assert picker.color().name() != "#336699", "the ring itself stopped working"
    picker.close()
