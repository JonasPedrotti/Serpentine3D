"""The command area takes the height its open panes ask for, and that
room goes to the history.

It used to be a dock with a grip above it to drag it taller; it is now a
bar along the window's foot with no grip, so what is checked here is
the height it asks for and where the room goes once it has some."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

# What the dock has always opened at. Fonts and DPI move it about, so this
# is a range around the shape of it rather than a number off one machine.
START_MIN, START_MAX = 90, 260
UNBOUNDED = 100_000        # Qt's own "no maximum" is 16777215


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_NO_RECOVER", "1")
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w.resize(1400, 900)
    w.layout().activate()
    yield w
    w.close()


def _tall(widget, height):
    """Give a widget the room a separator drag would give it.

    Nobody showed this window, so no resize event is delivered and the
    nested splitters and layouts have to be told to arrange their children.
    """
    widget.resize(widget.width() or 800, height)
    for _ in range(2):
        for child in [widget, *widget.findChildren(QWidget)]:
            QApplication.sendEvent(child, QResizeEvent(child.size(), child.size()))
            if child.layout() is not None:
                child.layout().invalidate()
                child.layout().activate()
    QApplication.processEvents()


def _open_history(win):
    win.command_workspace.show_history()


def test_with_nothing_open_it_is_only_its_rows_tall(win):
    """Being draggable is not an excuse to start out eating the viewport."""
    box = win.command_workspace
    assert box.sizeHint().height() == box.minimumSizeHint().height()
    assert box.sizePolicy().verticalPolicy() is QSizePolicy.Policy.Fixed


def test_with_the_history_open_it_asks_for_the_height_it_always_did(win):
    _open_history(win)
    asked = win.command_workspace.sizeHint().height()
    assert START_MIN <= asked <= START_MAX


def test_nothing_caps_the_history_either(win):
    assert win.command_line.echo_view.maximumHeight() > UNBOUNDED


def test_the_history_grows_into_the_room_the_command_area_is_given(win):
    """Four lines of history in a pane three times that tall would be a
    taller command area with nothing to show for it."""
    _open_history(win)
    cl = win.command_line
    box = win.command_workspace
    _tall(box, box.sizeHint().height())
    before = cl.echo_view.height()
    _tall(box, box.sizeHint().height() + 200)
    assert cl.echo_view.height() >= before + 190


def test_the_prompt_keeps_its_own_height_while_the_history_grows(win):
    """Only the history is worth more room; the row under it should stay
    put rather than share the growth."""
    _open_history(win)
    cl = win.command_line
    box = win.command_workspace
    _tall(box, box.sizeHint().height())
    line = cl.input.height()
    _tall(box, box.sizeHint().height() + 200)
    assert cl.input.height() == line


def test_the_osnap_bar_keeps_its_own_height_too(win):
    _open_history(win)
    box = win.command_workspace
    _tall(box, box.sizeHint().height())
    bar = win.osnap_bar.height()
    _tall(box, box.sizeHint().height() + 200)
    assert win.osnap_bar.height() == bar


def test_the_history_cannot_be_squeezed_away_to_nothing(win):
    """Dragging the other way has a floor: a command line with no line of
    history left on it is not a command line."""
    _open_history(win)
    cl = win.command_line
    floor = win.command_workspace.minimumSizeHint().height()
    one_line = cl.echo_view.minimumSizeHint().height()
    assert floor >= cl.input.sizeHint().height() + one_line
