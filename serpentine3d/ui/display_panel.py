"""Viewport display controls, opened from that viewport's title menu.

The reusable panel reads its supplied viewport on each refresh. The dialog
binds that source for its lifetime, so activating another viewport never
redirects edits to it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QVBoxLayout, QWidget,
)

#: Mode id to the label people read, in the order the View menu lists them.
_MODES = [
    ("wireframe", "Wireframe"),
    ("shaded", "Shaded"),
    ("ghosted", "Ghosted"),
    ("rendered", "Rendered"),
    ("plaster", "Plaster"),
    ("plastercolor", "Plaster Color"),
    ("technical", "Technical"),
    ("zebra", "Zebra"),
    ("curvature", "Curvature"),
    ("draft", "Draft angle"),
]


class DisplayPanel(QWidget):
    """Display settings for the viewport returned by ``viewport_source``."""

    def __init__(self, viewport_source, parent=None):
        super().__init__(parent)
        self._source = viewport_source
        self._loading = False           # refresh must not look like a click

        self.mode_box = QComboBox()
        for mode_id, label in _MODES:
            self.mode_box.addItem(label, mode_id)
        self.mode_box.currentIndexChanged.connect(self._mode_picked)

        self.iso_box = QCheckBox("Surface isocurves")
        self.iso_box.setToolTip(
            "The wires across a surface. Off in Rendered and Plaster by "
            "default.")
        self.iso_box.toggled.connect(
            lambda on: self._write(lambda vp: vp.set_isocurves(on)))

        self.edge_box = QCheckBox("Surface edges")
        self.edge_box.setToolTip(
            "The outlines of faces. Curves and text are not affected.")
        self.edge_box.toggled.connect(
            lambda on: self._write(lambda vp: vp.set_edges(on)))

        self.ao_box = QCheckBox("Ambient occlusion")
        self.ao_box.setToolTip(
            "Soft shading in creases and corners. Plaster modes only.")
        self.ao_box.toggled.connect(
            lambda on: self._write(lambda vp: vp.set_ambient_occlusion(on)))

        form = QFormLayout()
        form.setContentsMargins(8, 8, 8, 4)
        form.addRow("Mode", self.mode_box)

        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addLayout(form)
        box.addWidget(self.iso_box)
        box.addWidget(self.edge_box)
        box.addWidget(self.ao_box)
        box.addStretch(1)

        self.refresh()

    # -- reading the pane --

    def viewport(self):
        return self._source()

    def refresh(self):
        """Read the supplied viewport without creating display overrides."""
        vp = self.viewport()
        if vp is None:
            return
        self._loading = True
        try:
            i = self.mode_box.findData(vp.display_mode)
            if i >= 0:
                self.mode_box.setCurrentIndex(i)
            self.iso_box.setChecked(vp.shows_isocurves())
            self.edge_box.setChecked(vp.shows_edges())
            self.ao_box.setChecked(vp.ambient_occlusion)
            self.ao_box.setEnabled(vp.display_mode in vp.AO_MODES)
        finally:
            self._loading = False

    # -- and writing back to it --

    def _write(self, fn):
        vp = self.viewport()
        if vp is not None and not self._loading:
            fn(vp)

    def _mode_picked(self, _index):
        mode = self.mode_box.currentData()
        self._write(lambda vp: vp.set_display_mode(mode))

    # -- what the tests and the window talk to --

    def mode(self) -> str:
        return self.mode_box.currentData()

    def set_mode(self, mode: str):
        i = self.mode_box.findData(mode)
        if i >= 0:
            self.mode_box.setCurrentIndex(i)

    def isocurves_checked(self) -> bool:
        return self.iso_box.isChecked()

    def set_isocurves_checked(self, on: bool):
        self.iso_box.setChecked(bool(on))

    def edges_checked(self) -> bool:
        return self.edge_box.isChecked()

    def set_edges_checked(self, on: bool):
        self.edge_box.setChecked(bool(on))


class DisplaySettingsDialog(QDialog):
    """Modeless settings that stay attached to their originating viewport."""

    def __init__(self, viewport, parent=None):
        super().__init__(parent)
        self.viewport = viewport
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(
            f"Display settings · {viewport._view_name.capitalize()}")
        self.setMinimumWidth(300)
        self.panel = DisplayPanel(lambda: viewport, self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.panel)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        # Covers changes made through commands, APIs and the viewport menu,
        # including per-pane edge/isocurve overrides.
        viewport.displayModeChanged.connect(self.panel.refresh)
        viewport.destroyed.connect(self.close)
