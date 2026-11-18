"""A viewport's title tab: a right-click opens its menu, a left click does
nothing, and a double-click switches between that pane maximized and four
panes. Zoom Extents and Single Viewport are off its menu."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import pytest

from serpentine3d.app import MainWindow


@pytest.fixture
def win(_qapp):
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    QApplication.processEvents()
    yield w
    w.close()


def _bar(win):
    return win._primary_dock.titleBarWidget()


def test_a_left_click_opens_nothing(win):
    bar = _bar(win)
    QTest.mouseClick(bar.button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert not bar._menu.isVisible()


def test_a_right_click_opens_the_menu(win):
    bar = _bar(win)
    bar.button.customContextMenuRequested.emit(QPoint(4, 4))
    QApplication.processEvents()
    try:
        assert bar._menu.isVisible()
    finally:
        bar._menu.hide()


def test_a_double_click_on_the_tab_maximizes_and_back(win):
    bar = _bar(win)
    assert all(d.isVisibleTo(win) for d in win.aux_docks)
    QTest.mouseDClick(bar.button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert not any(d.isVisibleTo(win) for d in win.aux_docks)
    QTest.mouseDClick(bar.button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert all(d.isVisibleTo(win) for d in win.aux_docks)


def test_zoom_extents_and_single_viewport_are_off_the_menu(win):
    menu = win._viewport_menu(win.viewport)
    labels = [a.text().replace("&", "") for a in menu.actions()]
    assert "Zoom Extents" not in labels
    assert "Single Viewport" not in labels
    assert "Maximize Viewport" in labels and "Four Viewports" in labels


def test_a_window_opened_on_one_pane_comes_back_to_four(_qapp):
    """Left in a single view, the window opens that way: a double-click on
    the tab then has nothing to maximise, and brings the four panes back."""
    first = MainWindow()
    first.set_view_layout("single")
    first._remember_window()
    first.close()

    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    QApplication.processEvents()
    try:
        assert not any(d.isVisibleTo(w) for d in w.aux_docks)
        QTest.mouseDClick(_bar(w).button, Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert all(d.isVisibleTo(w) for d in w.aux_docks)
    finally:
        w.close()
