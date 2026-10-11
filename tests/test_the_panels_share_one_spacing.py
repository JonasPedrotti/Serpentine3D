"""Properties and Layers take their spacing from one place.

Set side by side with the layers mockup at the same size, the panels
were close but not quite: rows 24 px tall where the mockup's were 28, the
page standing 8 px in where the mockup stood 10, the kind line in the body
font where the design system asks app section labels to be monospace and
tracked, the fields running straight on from the header with nothing to
say where one ends, and Select objects a heavy button where a link would
do. Each part had its own number; now they share theme's.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont, QFontInfo
from PySide6.QtWidgets import QApplication, QWidget

from serpentine3d.core import geometry as g
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager
from serpentine3d.ui import theme
from serpentine3d.ui.layers_panel import LayersPanel
from serpentine3d.ui.properties import PropertiesPanel


def _setup():
    scene = Scene()
    selection = SelectionManager(scene)
    history = History(scene)
    props = PropertiesPanel(scene, selection, history)
    panel = LayersPanel(scene, history, selection=selection)
    props.follow_layers(panel)
    props.resize(300, 700)
    panel.resize(300, 400)
    props.show()
    panel.show()
    walls = scene.layers.create("Walls")
    box = scene.add(g.make_box((0, 0, 0), 5, 5, 5))
    scene.update(box.id, layer_id=walls.id)
    scene.notify()
    QApplication.processEvents()
    for i in range(panel.tree.topLevelItemCount()):
        item = panel.tree.topLevelItem(i)
        item.setSelected(panel._layer_id(item) == walls.id)
    QApplication.processEvents()
    return scene, props, panel


def test_a_layer_row_is_the_shared_row_height():
    _scene, _props, panel = _setup()
    tree = panel.tree
    for i in range(tree.topLevelItemCount()):
        assert (tree.visualItemRect(tree.topLevelItem(i)).height()
                == theme.LIST_ROW_HEIGHT)


def test_the_kind_line_is_a_tracked_monospace_label():
    _scene, props, _panel = _setup()
    font = props.layer_head.kind.font()
    assert QFontInfo(font).fixedPitch(), "the kind line is not monospace"
    assert font.letterSpacingType() == QFont.SpacingType.AbsoluteSpacing
    assert font.letterSpacing() == 1.5


def test_every_page_stands_in_by_the_shared_inset():
    _scene, props, _panel = _setup()
    for page, form, field in ((props.layer_page, props.layer_form,
                               props.layer_name),
                              (props.object_head.parentWidget(), props.form,
                               props.name_edit)):
        label = form.labelForField(field)
        assert label.mapTo(page, QPoint(0, 0)).x() == theme.PANEL_INSET


def test_a_seam_closes_the_header_off_from_the_fields():
    _scene, props, _panel = _setup()
    page = props.layer_page
    seam = page.findChild(QWidget, "seam")
    assert seam is not None, "no seam under the layer page's header"
    head_bottom = props.layer_select.mapTo(page, QPoint(0, 0)).y() \
        + props.layer_select.height()
    first_row = props.layer_form.labelForField(props.layer_name)
    seam_y = seam.mapTo(page, QPoint(0, 0)).y()
    assert head_bottom <= seam_y < first_row.mapTo(page, QPoint(0, 0)).y()
    assert seam.height() == 1


def test_the_layer_page_s_actions_are_links():
    scene, props, _panel = _setup()
    for button in (props.layer_select, props.layer_move_here):
        assert button.property("link") is True
