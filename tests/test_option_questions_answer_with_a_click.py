"""A question with a few answers can be answered with a click.

A question like "Keep original? (Yes/No) <Yes>" could only be answered by typing
or by Enter, which a hand on the mouse has to leave it for. Rhino puts a
prompt's answers on its command line to click, so the answers show as
chips beside the prompt, the default marked, clicking one the same as
typing it (QA, 2026-09-30). A long list, every block or every layout, is
a list to type from rather than a row of buttons, so it gets none.
"""

from __future__ import annotations

import pytest

from serpentine3d.commands.base import OptionReq
from serpentine3d.core import geometry as g


@pytest.fixture
def window():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from serpentine3d.app import MainWindow
    w = MainWindow()
    w.resize(1200, 800)
    try:
        yield w
    finally:
        if w.processor.busy:
            w.processor.cancel()
        w.mark_saved()
        w.close()


def _at_which_end(w):
    line = w.scene.add(g.make_line((10, 0, 0), (20, 0, 0)), name="L")
    w.selection.set([line.id])
    w.run_command("extend")
    assert isinstance(w.processor.request, OptionReq)
    return line


def _chips(w):
    return {c.text(): c for c in w.command_line._keyword_chips}


def test_the_answers_show_as_chips_with_the_default_marked(window):
    _at_which_end(window)

    chips = _chips(window)

    assert list(chips) == ["End", "Start", "Both"]
    assert chips["End"].property("default") is True
    assert chips["Start"].property("default") is not True


def test_clicking_an_answer_answers(window):
    _at_which_end(window)

    _chips(window)["Start"].click()

    assert not isinstance(window.processor.request, OptionReq)
    assert "Start" not in _chips(window)


def test_clicking_the_default_answers_with_it(window):
    _at_which_end(window)

    _chips(window)["End"].click()

    assert not isinstance(window.processor.request, OptionReq)


def test_the_chips_go_when_the_question_is_answered(window):
    _at_which_end(window)
    _chips(window)["Both"].click()

    assert not {"End", "Start", "Both"} & set(_chips(window))


def test_a_long_list_of_answers_gets_no_chips(window):
    w = window
    w.processor.request = OptionReq(
        "Block to insert", options=[f"Block{i}" for i in range(12)],
        default="Block0")
    try:
        assert w.processor.keyword_chips() == []
    finally:
        w.processor.request = None
