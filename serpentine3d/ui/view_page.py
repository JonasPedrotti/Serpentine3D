"""The Properties page of the pane you are working in, shown with nothing
picked: its camera, its background, its grid and the drawing's named
views. Whatever is set here is kept in the drawing (core/view_settings.py).
"""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QSignalBlocker, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QHBoxLayout, QLabel, QListWidget, QMenu, QPushButton, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)

from . import color_picker, icons, theme

PROJECTIONS = (("Perspective", "perspective"), ("Parallel", "parallel"))
WALLPAPER_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"
_ROW_PX = 22            # a named view's row, which the list grows by
_SWATCH = QSize(32, 20)

_QSS = (
    "QToolButton#chip { padding: 1px 8px; border: 1px solid #3a3b40;"
    f" border-radius: 3px; color: {theme.TEXT_MUTED}; }}"
    "QToolButton#chip:checked { color: #e8e9ea; background: #34353a;"
    " border-color: #55565e; }"
    "QToolButton#swatchChip { padding: 0; border: 1px solid #3a3b40;"
    " border-radius: 2px; }"
    "QToolButton#swatchChip:checked { background: #34353a;"
    " border-color: #55565e; }"
    "QToolButton#glyph { border: none; padding: 1px; }"
    "QToolButton#glyph:hover { background: #2f3035; border-radius: 3px; }"
)


def _xyz(point) -> str:
    return ", ".join(f"{float(c):.2f}" for c in point)


def _muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
    return label


def _row(*widgets, top: int = 0) -> QHBoxLayout:
    """Widgets side by side; a label without a fixed width among them
    takes the spare room."""
    row = QHBoxLayout()
    row.setContentsMargins(0, top, 0, 0)
    row.setSpacing(6)
    for w in widgets:
        grows = isinstance(w, QLabel) and w.minimumWidth() != w.maximumWidth()
        row.addWidget(w, 1 if grows else 0)
    return row


def _captions(*texts) -> list:
    """Labels for a column of rows, as wide as the widest of them."""
    labels = [_muted(t) for t in texts]
    for label in labels:
        label.ensurePolished()      # measured in the theme's font
    width = max(label.fontMetrics().horizontalAdvance(t)
                for label, t in zip(labels, texts))
    for label in labels:
        label.setFixedWidth(width + 2)
    return labels


class _Elided(QLabel):
    """A label that cuts a long text short with an ellipsis instead of
    widening the panel; the whole of it is in the tooltip."""

    def __init__(self):
        super().__init__()
        self._full = ""
        self.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def set_full_text(self, text: str):
        self._full = text
        self.setToolTip(text)
        self._elide()

    def full_text(self) -> str:
        return self._full

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideMiddle, max(self.width(), 0)))


def _section(text: str, *extras) -> QHBoxLayout:
    """A section's heading, with its few controls at the right."""
    label = QLabel(text)
    font = QFont(theme.mono_family())
    font.setPixelSize(11)
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
    label.setFont(font)
    label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
    return _row(label, *extras, top=8)


def _chip(text: str, tip: str) -> QToolButton:
    """A switch that is a word, lit while on."""
    button = QToolButton()
    button.setObjectName("chip")
    button.setText(text)
    button.setToolTip(tip)
    button.setCheckable(True)
    return button


class _Glyph(QToolButton):
    """A small icon button. A checkable one shows `toggle(on)` as its
    icon, so its state reads like a layer's switch."""

    def __init__(self, tip: str, glyph=None, toggle=None):
        super().__init__()
        self.setObjectName("glyph")
        self.setToolTip(tip)
        self.setIconSize(QSize(16, 16))
        self._toggle = toggle
        if toggle is not None:
            self.setCheckable(True)
            self.toggled.connect(self._show)
            self._show(False)
        else:
            # faint while disabled, as a locked view's pick buttons are
            icon = QIcon(icons.view_glyph(glyph))
            icon.addPixmap(icons.view_glyph(glyph, False),
                           QIcon.Mode.Disabled)
            self.setIcon(icon)

    def _show(self, on: bool):
        self.setIcon(QIcon(self._toggle(on)))


class _Swatch(QPushButton):
    def __init__(self, tip: str):
        super().__init__()
        self.setFixedSize(_SWATCH)
        self.setToolTip(tip)
        self.rgb = (0.0, 0.0, 0.0)

    def show_rgb(self, rgb):
        self.rgb = tuple(rgb)
        self.setStyleSheet(
            "QPushButton { background: rgb(%d,%d,%d); border: 1px solid"
            " #55565e; border-radius: 2px; }"
            % tuple(int(round(c * 255)) for c in self.rgb))


class ViewPage(QWidget):
    """`viewport()` is the pane being worked in, `viewports()` every model
    pane, and `run(command)` runs a command, as the pick buttons do."""

    def __init__(self, scene, header, viewport, viewports, run):
        super().__init__()
        self.scene = scene
        self.head = header
        self._viewport = viewport
        self._viewports = viewports
        self._run = run
        self._updating = False
        self.setStyleSheet(_QSS)

        self.locked = _Glyph(
            "Lock this view: orbit, pan and zoom leave it as it is",
            toggle=lambda on: icons.view_glyph(
                "locked" if on else "unlocked"))
        self.locked.toggled.connect(self._set_locked)
        self.projection = QComboBox()
        for label, value in PROJECTIONS:
            self.projection.addItem(label, value)
        self.projection.currentIndexChanged.connect(self._set_projection)
        self.lens = QDoubleSpinBox()
        self.lens.setRange(1.0, 2000.0)
        self.lens.setDecimals(1)
        self.lens.setSuffix(" mm")
        self.lens.setKeyboardTracking(False)
        self.lens.setToolTip("Lens length on the camera's sensor; "
                             "shorter is wider")
        self.lens.valueChanged.connect(self._set_lens)
        self.camera_at = QLabel()
        self.camera_set = _Glyph("Pick where the camera stands; it keeps "
                                 "looking at its target",
                                 "target")
        self.camera_set.clicked.connect(lambda: self._run("camera Position"))
        self.camera_lock = _Glyph(
            "Keep the camera where it stands: orbit looks around from it, "
            "pan and zoom are off",
            toggle=lambda on: icons.view_glyph("locked" if on
                                               else "unlocked"))
        self.camera_lock.toggled.connect(
            lambda on: self._set_point_lock("position_locked", on))
        self.target_at = QLabel()
        self.target_set = _Glyph("Pick what the camera looks at; it stays "
                                 "where it stands",
                                 "target")
        self.target_set.clicked.connect(lambda: self._run("camera Target"))
        self.target_lock = _Glyph(
            "Keep the target where it is: orbit and zoom turn about it, "
            "pan is off",
            toggle=lambda on: icons.view_glyph("locked" if on
                                               else "unlocked"))
        self.target_lock.toggled.connect(
            lambda on: self._set_point_lock("target_locked", on))

        self.for_all = QCheckBox("All views")
        self.for_all.setToolTip("Every model pane draws this background")
        self.for_all.toggled.connect(self._set_for_all)
        self.bg_color = _Swatch("Background colour, or the foot of the "
                                "gradient")
        self.bg_color.clicked.connect(lambda: self._pick_color("color"))
        self.bg_gradient = _chip("", "Fade up to a second colour at the top")
        self.bg_gradient.setObjectName("swatchChip")
        self.bg_gradient.setFixedSize(_SWATCH)
        self.bg_gradient.setIcon(QIcon(icons.view_glyph("arrow")))
        self.bg_gradient.setIconSize(QSize(16, 16))
        self.bg_gradient.toggled.connect(
            lambda on: self._set_background(gradient=on))
        self.bg_top = _Swatch("The colour at the top of the gradient")
        self.bg_top.clicked.connect(lambda: self._pick_color("top"))
        self.wallpaper_name = _Elided()
        self.wallpaper_show = _Glyph(
            "Show the wallpaper",
            toggle=lambda on: icons.switch_glyph("visible",
                                                 "on" if on else "off"))
        self.wallpaper_show.toggled.connect(
            lambda on: self._set_background(wallpaper_show=on))
        self.wallpaper_gray = _Glyph(
            "Draw the wallpaper faded and without colour, to trace over",
            toggle=lambda on: icons.view_glyph("gray", on))
        self.wallpaper_gray.toggled.connect(
            lambda on: self._set_background(wallpaper_gray=on))
        self.wallpaper_open = _Glyph("Open an image to show behind the "
                                     "model; it is kept in the drawing",
                                     "folder")
        self.wallpaper_open.clicked.connect(self._open_wallpaper)
        self.wallpaper_remove = _Glyph("Remove the wallpaper",
                                       "remove")
        self.wallpaper_remove.clicked.connect(
            lambda: self._set_background(wallpaper=None, wallpaper_name=""))

        self.grid = _chip("Grid", "The construction plane's grid")
        self.grid.toggled.connect(lambda on: self._set_look("grid_visible",
                                                            on))
        self.grid_axes = _chip("Axes", "The grid's red and green lines "
                                       "through the origin")
        self.grid_axes.toggled.connect(
            lambda on: self._set_look("grid_axes_visible", on))
        self.world_axes = _chip("Icon", "The small X, Y, Z in the corner")
        self.world_axes.toggled.connect(
            lambda on: self._set_look("world_axes_visible", on))

        self.view_save = _Glyph("Save this view under a name, in the "
                                "drawing", "add")
        self.view_save.clicked.connect(self._save_view)
        self.views = QListWidget()
        self.views.setToolTip("Click to go to a view; right-click or Delete "
                              "to remove it")
        self.views.itemClicked.connect(lambda _i: self._restore_view())
        self.views.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.views.customContextMenuRequested.connect(self._view_menu)
        self.views.installEventFilter(self)

        column = QVBoxLayout()
        column.setContentsMargins(theme.PANEL_INSET, 0, theme.PANEL_INSET,
                                  theme.PANEL_INSET)
        column.setSpacing(5)
        column.addLayout(_section("Camera", self.locked))
        # Shared out over the whole width, so the lens ends where the
        # glyphs below do.
        lens_row = _row(self.projection, self.lens)
        lens_row.setStretch(0, 1)
        lens_row.setStretch(1, 1)
        column.addLayout(lens_row)
        camera, target = _captions("Camera", "Target")
        column.addLayout(_row(camera, self.camera_at, self.camera_set,
                              self.camera_lock))
        column.addLayout(_row(target, self.target_at, self.target_set,
                              self.target_lock))
        column.addLayout(_section("Background"))
        column.addLayout(_row(self.bg_color, self.bg_gradient, self.bg_top,
                              _muted()))
        column.addLayout(_row(self.wallpaper_name, self.wallpaper_show,
                              self.wallpaper_gray, self.wallpaper_open,
                              self.wallpaper_remove))
        column.addWidget(self.for_all)
        column.addLayout(_section("Grid"))
        column.addLayout(_row(self.grid, self.grid_axes, self.world_axes,
                              _muted()))
        column.addLayout(_section("Named views", self.view_save))
        column.addWidget(self.views)

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addWidget(header)
        page.addLayout(column)
        page.addStretch(1)

    # -------------------------------------------------------------- showing

    def pane(self):
        vp = self._viewport()
        return vp if vp is not None and vp.space == "model" else None

    def refresh(self):
        vp = self.pane()
        if vp is None:
            return
        self._updating = True
        try:
            cam = vp.camera
            locked = cam.locked
            with QSignalBlocker(self.projection):
                self.projection.setCurrentIndex(
                    max(0, self.projection.findData(cam.projection)))
            with QSignalBlocker(self.lens):
                self.lens.setValue(round(cam.focal_length, 1))
            self.lens.setVisible(cam.projection == "perspective")
            for widget in (self.projection, self.lens, self.camera_lock,
                           self.target_lock):
                widget.setEnabled(not locked)
            self.camera_set.setEnabled(not (locked or cam.position_locked))
            self.target_set.setEnabled(not (locked or cam.target_locked))
            self.views.setEnabled(not (locked or cam.position_locked
                                       or cam.target_locked))
            self.camera_at.setText(_xyz(cam.position))
            self.target_at.setText(_xyz(cam.target))

            bg = vp.background
            has = bool(bg.wallpaper)
            self.bg_color.show_rgb(bg.color)
            self.bg_top.show_rgb(bg.top)
            self.bg_top.setVisible(bg.gradient)
            self.wallpaper_name.set_full_text(
                (bg.wallpaper_name or "Image") if has else "No wallpaper")
            for glyph in (self.wallpaper_show, self.wallpaper_gray,
                          self.wallpaper_remove, self.for_all):
                glyph.setVisible(has)
            for box, on in ((self.locked, locked),
                            (self.camera_lock, cam.position_locked),
                            (self.target_lock, cam.target_locked),
                            (self.bg_gradient, bg.gradient),
                            (self.wallpaper_show, bg.wallpaper_show),
                            (self.wallpaper_gray, bg.wallpaper_gray),
                            (self.for_all, self.scene.view_settings.for_all),
                            (self.grid, vp.grid_visible),
                            (self.grid_axes, vp.grid_axes_visible),
                            (self.world_axes, vp.world_axes_visible)):
                with QSignalBlocker(box):
                    box.setChecked(on)
                if isinstance(box, _Glyph):
                    box._show(on)

            names = sorted(self.scene.named_views, key=str.lower)
            if [self.views.item(i).text()
                    for i in range(self.views.count())] != names:
                with QSignalBlocker(self.views):
                    self.views.clear()
                    self.views.addItems(names)
            self.views.setVisible(bool(names))
            self.views.setFixedHeight(min(len(names), 8) * _ROW_PX + 4)
        finally:
            self._updating = False

    def refresh_camera(self):
        """Only what a moving camera changes, as it moves."""
        vp = self.pane()
        if vp is None or not self.isVisible():
            return
        self.camera_at.setText(_xyz(vp.camera.position))
        self.target_at.setText(_xyz(vp.camera.target))
        if not self.lens.hasFocus():
            with QSignalBlocker(self.lens):
                self.lens.setValue(round(vp.camera.focal_length, 1))
        with QSignalBlocker(self.projection):
            self.projection.setCurrentIndex(
                max(0, self.projection.findData(vp.camera.projection)))
        self.lens.setVisible(vp.camera.projection == "perspective")

    # -------------------------------------------------------------- editing

    def _changed(self, vp=None):
        """Something kept in the drawing changed: it has unsaved work."""
        for pane in ([vp] if vp is not None else self._viewports()):
            pane.update()
        self.scene.notify("view")
        self.refresh()

    def _set_projection(self, _index=None):
        vp = self.pane()
        if vp is None or self._updating or vp.camera.locked:
            return
        vp.camera.projection = self.projection.currentData()
        self._changed(vp)

    def _set_lens(self, mm: float):
        vp = self.pane()
        if vp is None or self._updating or vp.camera.locked:
            return
        vp.camera.set_focal_length(mm)
        self._changed(vp)

    def _set_locked(self, on: bool):
        vp = self.pane()
        if vp is None or self._updating:
            return
        vp.camera.locked = on
        self._changed(vp)

    def _set_point_lock(self, attr: str, on: bool):
        vp = self.pane()
        if vp is None or self._updating:
            return
        setattr(vp.camera, attr, on)
        self._changed(vp)

    def _set_look(self, attr: str, on: bool):
        vp = self.pane()
        if vp is None or self._updating:
            return
        setattr(vp, attr, on)
        self._changed(vp)

    def _set_background(self, **change):
        """Change the pane's background, or every pane's when they share."""
        vp = self.pane()
        if vp is None or self._updating:
            return
        settings = self.scene.view_settings
        bg = vp.background.copy()
        for key, value in change.items():
            setattr(bg, key, value)
        if settings.for_all:
            settings.background = bg
            for pane in self._viewports():
                pane.background = bg.copy()
            self._changed()
        else:
            vp.background = bg
            self._changed(vp)

    def _set_for_all(self, on: bool):
        vp = self.pane()
        if vp is None or self._updating:
            return
        settings = self.scene.view_settings
        settings.for_all = on
        if on:
            settings.background = vp.background.copy()
            for pane in self._viewports():
                pane.background = vp.background.copy()
        self._changed()

    def _pick_color(self, which: str):
        vp = self.pane()
        if vp is None:
            return
        rgb = getattr(vp.background, which)
        color = color_picker.get_color(QColor.fromRgbF(*rgb), self,
                                       "Background colour")
        if color.isValid():
            self._set_background(**{which: (color.redF(), color.greenF(),
                                            color.blueF())})

    def _open_wallpaper(self):
        path, _ = QFileDialog.getOpenFileName(self, "Wallpaper", "",
                                              WALLPAPER_FILTER)
        if path:
            self.load_wallpaper(path)

    def load_wallpaper(self, path: str) -> bool:
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return False
        self._set_background(wallpaper=data,
                             wallpaper_name=os.path.basename(path),
                             wallpaper_show=True)
        return True

    # ---------------------------------------------------------- named views

    def _picked_view(self) -> str | None:
        item = self.views.currentItem()
        return item.text() if item is not None else None

    def ask_view_name(self) -> str:
        """The name to save the view under, asked in a popup; "" when
        cancelled."""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save view", "Name")
        return name.strip() if ok else ""

    def _save_view(self):
        vp = self.pane()
        if vp is None:
            return
        name = self.ask_view_name()
        if not name:
            return
        self.scene.named_views[name] = vp.camera.state()
        self.scene.notify()
        self.refresh()

    def _restore_view(self):
        vp = self.pane()
        name = self._picked_view()
        state = self.scene.named_views.get(name) if name else None
        cam = vp.camera if vp is not None else None
        if state is None or cam is None or (
                cam.locked or cam.position_locked or cam.target_locked):
            return
        vp.camera.restore(state)
        vp.update()
        self.refresh()

    def delete_view(self, name: str | None = None):
        name = name or self._picked_view()
        if name is None or self.scene.named_views.pop(name, None) is None:
            return
        self.scene.notify()
        self.refresh()

    def _view_menu(self, pos):
        item = self.views.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        menu.addAction("Delete", lambda name=item.text():
                       self.delete_view(name))
        menu.exec(self.views.viewport().mapToGlobal(pos))

    def eventFilter(self, obj, ev):
        if (obj is self.views and ev.type() == QEvent.Type.KeyPress
                and ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)):
            self.delete_view()
            return True
        return super().eventFilter(obj, ev)
