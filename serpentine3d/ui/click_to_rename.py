"""A click on the one picked row opens its name for typing, as in a file
browser. It waits out the double-click interval first, so a double-click
still does the row's own job and never lands in the name."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtWidgets import QApplication


class ClickToRename(QObject):

    def __init__(self, tree, column: int, rename):
        super().__init__(tree)
        self._tree = tree
        self._column = column
        self._rename = rename
        self._armed = None          # the item a release may rename
        self._press = QPoint()
        self._pending = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)
        tree.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            self._timer.stop()
            self._armed = self._picked_alone(event)
            self._press = event.position().toPoint()
        elif kind == QEvent.Type.MouseMove and self._armed is not None:
            moved = event.position().toPoint() - self._press
            if moved.manhattanLength() >= QApplication.startDragDistance():
                self._armed = None
        elif kind == QEvent.Type.MouseButtonRelease:
            item = self._armed
            self._armed = None
            if item is not None and self._item_at(event) is item:
                self._pending = item
                self._timer.start(QApplication.doubleClickInterval())
        elif kind == QEvent.Type.MouseButtonDblClick:
            self._timer.stop()
            self._armed = self._pending = None
        return False

    def _item_at(self, event):
        index = self._tree.indexAt(event.position().toPoint())
        if not index.isValid() or index.column() != self._column:
            return None
        return self._tree.itemFromIndex(index)

    def _picked_alone(self, event):
        if (event.button() != Qt.MouseButton.LeftButton
                or event.modifiers() != Qt.KeyboardModifier.NoModifier):
            return None
        item = self._item_at(event)
        picked = self._tree.selectedItems()
        return item if item is not None and picked == [item] else None

    def _fire(self):
        item, self._pending = self._pending, None
        if item is not None and self._tree.selectedItems() == [item]:
            self._rename(item)
