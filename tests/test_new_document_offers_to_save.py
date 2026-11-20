"""A new document over unsaved work first asks whether to save it, with the
same prompt as opening a recent one, from File > New and the title bar."""

import pytest

from serpentine3d import app as app_mod
from serpentine3d.ui import save_prompt
from serpentine3d.core import geometry as g


@pytest.fixture
def win():
    w = app_mod.MainWindow()
    w.scene.add(g.make_box((0.0, 0.0, 0.0), 10.0, 10.0, 10.0))
    yield w
    w.mark_saved()
    w.close()


def _answer(monkeypatch, button):
    asked = []

    def ask(parent, name):
        asked.append(name)
        return button
    monkeypatch.setattr(save_prompt, "ask_save_changes", ask)
    return asked


def test_cancel_keeps_the_scene(win, monkeypatch):
    asked = _answer(monkeypatch, save_prompt.CANCEL)
    win._file_new()
    assert asked == ["untitled"]
    assert len(win.scene.all()) == 1


def test_dont_save_starts_an_empty_document(win, monkeypatch):
    _answer(monkeypatch, save_prompt.DISCARD)
    win._file_new()
    assert win.scene.all() == []


def test_a_saved_document_is_not_asked_about(win, monkeypatch):
    asked = _answer(monkeypatch, save_prompt.CANCEL)
    win.mark_saved()
    win._file_new()
    assert asked == [] and win.scene.all() == []


def test_the_title_bar_new_document_asks_too(win, monkeypatch):
    asked = _answer(monkeypatch, save_prompt.CANCEL)
    tb = win._title_bar
    tb._fill_document_menu()
    entry = next(a for a in tb.document_menu.actions()
                 if "New Document" in a.text())
    entry.trigger()
    assert asked and len(win.scene.all()) == 1


def _menu_texts(win):
    tb = win._title_bar
    tb._fill_document_menu()
    return [a.text() for a in tb.document_menu.actions()]


def test_a_blank_document_does_not_offer_a_new_one(win, monkeypatch):
    assert any("New Document" in t for t in _menu_texts(win))
    _answer(monkeypatch, save_prompt.DISCARD)
    win._file_new()
    assert not any("New Document" in t for t in _menu_texts(win))
