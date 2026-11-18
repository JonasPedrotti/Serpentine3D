"""Opening a recent document over unsaved work first asks whether to save it,
from the title bar's document menu and from File > Open Recent alike."""

import pytest

from serpentine3d import app as app_mod
from serpentine3d.ui import save_prompt
from serpentine3d.core import geometry as g


@pytest.fixture
def win(monkeypatch, tmp_path):
    w = app_mod.MainWindow()
    w.scene.add(g.make_box((0.0, 0.0, 0.0), 10.0, 10.0, 10.0))
    target = tmp_path / "other.serp"
    target.write_text("")
    opened = []
    monkeypatch.setattr(w, "_open_path", opened.append)
    w.opened, w.target = opened, str(target)
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


def test_cancel_keeps_the_unsaved_document(win, monkeypatch):
    asked = _answer(monkeypatch, save_prompt.CANCEL)
    win._open_recent(win.target)
    assert asked == ["untitled"]
    assert win.opened == []


def test_discard_opens_the_other_document(win, monkeypatch):
    _answer(monkeypatch, save_prompt.DISCARD)
    win._open_recent(win.target)
    assert win.opened == [win.target]


def test_a_saved_document_is_not_asked_about(win, monkeypatch):
    asked = _answer(monkeypatch, save_prompt.CANCEL)
    win.mark_saved()
    win._open_recent(win.target)
    assert asked == [] and win.opened == [win.target]


def test_the_title_bar_menu_opens_through_the_same_check(win, monkeypatch):
    asked = _answer(monkeypatch, save_prompt.CANCEL)
    monkeypatch.setattr(win, "recent_files", lambda: [win.target])
    tb = win._title_bar
    tb._fill_document_menu()
    entry = next(a for a in tb.document_menu.actions()
                 if a.text() == "other.serp")
    entry.trigger()
    assert asked and win.opened == []


def test_the_prompt_names_the_document_and_answers(win):
    dlg = save_prompt.SavePrompt(None, "part.serp")
    labels = [w.text() for w in dlg.findChildren(save_prompt.QLabel)]
    assert any("part.serp" in t for t in labels)
    assert dlg.answer == save_prompt.CANCEL
    dlg._finish(save_prompt.DISCARD)
    assert dlg.answer == save_prompt.DISCARD
