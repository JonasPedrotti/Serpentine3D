"""When the graphics driver gives no OpenGL, the app says so.

On 2026-10-10 a driver update left the loaded kernel module and the newly
installed libraries a version apart, and until a restart no new program
could get an OpenGL context. Serpentine3D opened a window that never
painted: the windows behind showed through it and the splash sat on top
saying Ready, with the reason only in the system log. Now the window
checks, once it is up, that its viewport has a context, and if not it says
what is wrong and what usually fixes it, in a plain message box that needs
no OpenGL itself. Headless, the reason goes to stderr alone, so nothing
waits on a box nobody can see.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from serpentine3d import app as app_module
from serpentine3d.app import MainWindow


@pytest.fixture
def window(_qapp):
    w = MainWindow()
    yield w
    w.mark_saved()
    w.close()


@pytest.fixture
def boxes(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: shown.append(a)))
    return shown


def _on_screen(monkeypatch):
    monkeypatch.setattr(QApplication, "platformName",
                        staticmethod(lambda: "xcb"))


def test_a_viewport_with_no_context_is_reported(window, boxes, monkeypatch,
                                                capsys):
    _on_screen(monkeypatch)
    monkeypatch.setattr(type(window.viewport), "isValid", lambda self: False)
    assert app_module.warn_if_opengl_failed(window) is True
    assert len(boxes) == 1
    _parent, title, text = boxes[0][:3]
    assert "OpenGL" in title
    assert "restart" in text.lower(), "the usual fix was not offered"
    assert "OpenGL" in capsys.readouterr().err, "nothing in the system log"


def test_a_working_viewport_says_nothing(window, boxes, monkeypatch):
    _on_screen(monkeypatch)
    monkeypatch.setattr(type(window.viewport), "isValid", lambda self: True)
    assert app_module.warn_if_opengl_failed(window) is False
    assert boxes == []


def test_headless_it_only_writes_to_stderr(window, boxes, monkeypatch,
                                           capsys):
    monkeypatch.setattr(QApplication, "platformName",
                        staticmethod(lambda: "offscreen"))
    monkeypatch.setattr(type(window.viewport), "isValid", lambda self: False)
    assert app_module.warn_if_opengl_failed(window) is True
    assert boxes == [], "a modal box would hang a headless run"
    assert "OpenGL" in capsys.readouterr().err


def test_the_splash_goes_before_the_box(window, boxes, monkeypatch):
    """It waits for the window to paint, which it never will."""
    _on_screen(monkeypatch)
    monkeypatch.setattr(type(window.viewport), "isValid", lambda self: False)
    closed = []

    class Splash:
        def close(self):
            closed.append(len(boxes))

    app_module.warn_if_opengl_failed(window, Splash())
    assert closed == [0], "the splash stayed up, or went after the box"
