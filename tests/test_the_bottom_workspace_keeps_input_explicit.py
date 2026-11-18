"""History, assistant and scripts share a shelf, each opened by its own
switch, over one input that Ask AI points at the assistant.

Exercise the real MainWindow and Qt controls. The labels come from the
approved command-workspace concept; widget classes and settings keys are
deliberately not part of this contract. Only the network boundary is faked.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QLineEdit, QPlainTextEdit, QSplitter, QWidget,
)

from serpentine3d.app import MainWindow
from serpentine3d.commands.base import PointReq, TextReq
from serpentine3d.core.layout import Layout


@pytest.fixture
def windows(tmp_path, monkeypatch):
    monkeypatch.setenv("SERP3D_CONFIG", str(tmp_path / "settings.json"))
    monkeypatch.setenv("SERP3D_NO_RECOVER", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    opened = []

    def create():
        win = MainWindow()
        win.resize(1400, 900)
        opened.append(win)
        _lay_out(win)
        return win

    yield create
    for win in opened:
        win.processor.cancel()
        win.mark_saved()
        win.close()


@pytest.fixture
def win(windows):
    return windows()


def _lay_out(win):
    """Lay out the shelf without showing an offscreen OpenGL viewport."""
    win.layout().activate()
    shelf = win.command_workspace
    shelf.resize(1100, 360)
    for _ in range(2):
        for widget in [shelf, *shelf.findChildren(QWidget)]:
            if widget.layout() is not None:
                widget.layout().invalidate()
                widget.layout().activate()
    QApplication.processEvents()


def _button(win, label):
    shelf = win.command_workspace
    matches = [button for button in shelf.findChildren(QAbstractButton)
               if button.isVisibleTo(shelf)
               and label in (button.text().replace("&", "").strip(),
                             button.accessibleName(), button.toolTip())]
    assert matches, f"The bottom workspace needs a visible {label!r} control"
    assert len(matches) == 1, f"The {label!r} control must be unambiguous"
    return matches[0]


def _click(win, label):
    _button(win, label).click()
    _lay_out(win)


def _ask_ai(win, on):
    """Ask AI is a switch: on sends what is typed to the assistant, off back
    to the command line."""
    if _button(win, "Ask AI").isChecked() != on:
        _click(win, "Ask AI")


def _script_content(win):
    from serpentine3d.ui.console import PythonConsole
    # Keep the current console entrypoint useful; a replacement script
    # editor may identify itself through its public accessibility label.
    matches = [widget for widget in win.findChildren(QWidget)
               if widget.isVisibleTo(win)
               and (isinstance(widget, PythonConsole)
                    or widget.accessibleName() == "Script editor")]
    assert matches, "The Python entrypoint must reveal the script editor"
    return matches[0]


def _open_both(win):
    assistant = win.show_ai_panel()
    win._toggle_console()
    _lay_out(win)
    script = _script_content(win)
    shelf = win.command_workspace
    assert shelf.isAncestorOf(assistant), "Assistant must live in the bottom workspace"
    assert shelf.isAncestorOf(script), "Python must open inside the same bottom workspace"
    return assistant, script


def _left(widget, win):
    return widget.mapTo(win, QPoint(0, 0)).x()


def _fixed_controls_stay_accessible(win):
    for label in ("Assistant", "Script", "History"):
        _button(win, label)
    assert win.command_line.input.isVisibleTo(win), "The shared input must stay accessible"
    assert win.space_tabs.isVisibleTo(win), "Model/layout tabs must stay accessible"


def _record_ai(win, monkeypatch):
    from serpentine3d.ai.agent import Agent
    sent = []
    win.cfg.set("ai", "api_key", "sk-test-workspace")

    def send(agent, prompt):
        sent.append(prompt)
        agent.turnFinished.emit("end_turn")

    monkeypatch.setattr(Agent, "send", send)
    win.show_ai_panel()
    return sent


def _field(win):
    """The existing CAD and assistant inputs may share a stacked region."""
    from serpentine3d.ai.panel import AiPanel
    shelf = win.command_workspace
    candidates = [win.command_line.input]
    candidates.extend(panel.input for panel in win.findChildren(AiPanel))
    candidates.extend(widget for widget in shelf.findChildren(QWidget)
                      if isinstance(widget, (QLineEdit, QPlainTextEdit))
                      and "input" in widget.accessibleName().lower()
                      and any(word in widget.accessibleName().lower()
                              for word in ("ai", "assistant")))
    visible = list(dict.fromkeys(widget for widget in candidates
                                 if shelf.isAncestorOf(widget)
                                 and widget.isVisibleTo(shelf)))
    assert len(visible) == 1, "There must be one visible Command / Ask AI input region"
    return visible[0]


def _text(field):
    return field.toPlainText() if hasattr(field, "toPlainText") else field.text()


def test_existing_entrypoints_open_two_bottom_panes_without_changing_destination(win):
    field = win.command_line.input
    field.setText("circle")
    assistant, script = _open_both(win)
    assert win._cmd_bar.window() is win and win._cmd_bar.y() > win.viewport_area.y()
    assert _left(script, win) < _left(assistant, win)
    assert not _button(win, "Ask AI").isChecked()
    assert field.text() == "circle"
    _fixed_controls_stay_accessible(win)


def test_each_optional_pane_can_be_hidden_without_losing_history_or_tabs(win):
    assistant, script = _open_both(win)
    win.command_line.echo("A previous modeling result")
    _click(win, "Assistant")
    assert not assistant.isVisibleTo(win)
    assert script.isVisibleTo(win)
    _fixed_controls_stay_accessible(win)
    _click(win, "Script")
    assert not script.isVisibleTo(win)
    _fixed_controls_stay_accessible(win)
    _click(win, "Assistant")
    assert assistant.isVisibleTo(win)
    assert not script.isVisibleTo(win)
    _click(win, "History")
    assert win.command_line.echo_view.isVisibleTo(win)
    assert _left(win.command_line.echo_view, win) < _left(assistant, win)
    assert "A previous modeling result" in win.command_line.echo_view.toPlainText()
    assert not _button(win, "Ask AI").isChecked()


def test_panes_keep_their_widths_and_closing_them_all_leaves_only_the_rows(win):
    assistant, script = _open_both(win)
    _click(win, "History")
    history = win.command_line.echo_view
    assert _left(history, win) < _left(script, win) < _left(assistant, win)
    splitters = [splitter for splitter in win.command_workspace.findChildren(QSplitter)
                 if splitter.orientation() == Qt.Orientation.Horizontal
                 and splitter.isAncestorOf(assistant) and splitter.isAncestorOf(script)]
    assert splitters, "The visible panes need a draggable divider"
    splitter = splitters[0]
    before = splitter.sizes()
    assert len(before) >= 2 and min(before) > 0
    requested = list(before)
    requested[0] += 80
    requested[1] -= min(80, requested[1] // 3)
    splitter.setSizes(requested)
    _lay_out(win)
    assert splitter.sizes() != before, "Dragging a divider must give its pane more room"
    widths = splitter.sizes()
    for label in ("History", "Script", "Assistant"):
        _click(win, label)
    shelf = win.command_workspace
    assert not splitter.isVisibleTo(win)
    assert shelf.sizeHint().height() == shelf.minimumSizeHint().height()
    assert win.space_tabs.isVisibleTo(win)
    assert win.command_line.input.isVisibleTo(win)
    for label in ("History", "Script", "Assistant"):
        _click(win, label)
    assert assistant.isVisibleTo(win) and script.isVisibleTo(win)
    assert splitter.sizes() == pytest.approx(widths, abs=3)


def test_only_the_three_pane_switches_sit_beside_the_tabs(win):
    shelf = win.command_workspace
    words = {text for button in shelf.findChildren(QAbstractButton)
             if button.isVisibleTo(shelf)
             for text in (button.text().replace("&", "").strip(),
                          button.accessibleName(), button.toolTip())}
    for gone in ("Collapse workspace", "Restore workspace", "Expand workspace",
                 "Arrange workspace", "Command", "Run command"):
        assert gone not in words


def test_the_last_message_shows_on_the_status_bar_and_opens_the_history(win):
    win.command_line.echo("Nothing picked.")
    note = win.last_message
    assert note.full_text() == "Nothing picked."
    assert note.isVisibleTo(win)
    assert not win.command_line.echo_view.isVisibleTo(win)
    QTest.mouseClick(note, Qt.MouseButton.LeftButton)
    _lay_out(win)
    assert win.command_line.echo_view.isVisibleTo(win)
    assert _button(win, "History").isChecked()


def test_switching_destination_keeps_separate_drafts_and_changes_the_submit_label(win):
    field = win.command_line.input
    field.setText("circle")
    command_hint = field.placeholderText()
    assert not win.command_workspace.submit_button.isVisibleTo(win), \
        "Enter runs a command; there is no button for it"
    _click(win, "Ask AI")
    field = _field(win)
    assert _button(win, "Ask AI").isChecked()
    assert _text(field) == ""
    assert field.placeholderText() != command_hint
    _button(win, "Send to AI")
    QTest.keyClicks(field, "explain this curve")
    assert _text(field) == "explain this curve", "AI words must not trigger CAD completion"
    assert win.command_line.suggestions.isHidden()
    _click(win, "Ask AI")
    assert _text(_field(win)) == "circle"
    assert not win.command_workspace.submit_button.isVisibleTo(win)
    _click(win, "Ask AI")
    assert _text(_field(win)) == "explain this curve"


def test_ai_prose_goes_only_to_the_assistant_even_when_panes_change(win, monkeypatch):
    sent = _record_ai(win, monkeypatch)
    _click(win, "Ask AI")
    field = _field(win)
    QTest.keyClicks(field, "line up these objects with a gap")
    assert sent == [] and not win.processor.busy
    win._toggle_console()
    _click(win, "Assistant")
    assert _button(win, "Ask AI").isChecked()
    win.show_ai_panel()
    _click(win, "History")
    QTest.mouseClick(win.command_line.echo_view.viewport(), Qt.MouseButton.LeftButton)
    assert _button(win, "Ask AI").isChecked()
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert sent == ["line up these objects with a gap"]
    assert not win.processor.busy and not win.scene.all()
    assert _text(field) == ""
    assert "Unknown command" not in win.command_line.echo_view.toPlainText()


def test_asking_ai_during_a_point_prompt_preserves_the_command_and_its_draft(win, monkeypatch):
    sent = _record_ai(win, monkeypatch)
    field = win.command_line.input
    QTest.keyClicks(field, "line")
    QTest.keyClick(field, Qt.Key.Key_Space)
    assert win.processor.busy and isinstance(win.processor.request, PointReq)
    request = win.processor.request
    prompt = win.command_line.prompt_label.text()
    QTest.keyClicks(field, "0,0,")
    _click(win, "Ask AI")
    QTest.keyClicks(_field(win), "what coordinates should I use")
    QTest.keyClick(_field(win), Qt.Key.Key_Return)
    assert sent == ["what coordinates should I use"]
    assert win.processor.request is request and win.processor.busy
    assert not win.processor.picked_points
    _ask_ai(win, False)
    assert field.text() == "0,0,"
    assert win.command_line.prompt_label.text() == prompt
    QTest.keyClicks(field, "0")
    QTest.keyClick(field, Qt.Key.Key_Space)
    assert len(win.processor.picked_points) == 1
    QTest.keyClicks(field, "10,0,0")
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert len(win.scene.all()) == 1


def test_returning_from_ai_keeps_completion_repeat_and_free_text_semantics(win):
    _ask_ai(win, True)
    _ask_ai(win, False)
    field = win.command_line.input
    QTest.keyClicks(field, "deta")
    assert field.text() == "detail" and field.selectedText() == "il"
    QTest.keyClick(field, Qt.Key.Key_Escape)
    QTest.keyClicks(field, "line")
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert isinstance(win.processor.request, PointReq)
    QTest.keyClick(field, Qt.Key.Key_Escape)
    QTest.keyClick(field, Qt.Key.Key_Space)
    assert win.processor.busy and win.processor.active.name == "line"
    QTest.keyClick(field, Qt.Key.Key_Escape)
    win.processor.run("layer")
    win.processor.provide_text("New")
    assert isinstance(win.processor.request, TextReq)
    QTest.keyClicks(field, "Ground floor")
    assert field.text() == "Ground floor"
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert win.scene.layers.find_by_name("Ground floor") is not None


def test_which_panes_are_open_survives_a_window_session(windows):
    win = windows()
    assistant, script = _open_both(win)
    _click(win, "History")
    _click(win, "Assistant")
    assert script.isVisibleTo(win) and not assistant.isVisibleTo(win)
    # Match the existing persistence suite: no need to render GL to exercise
    # the guard that only saves windows a person has actually seen.
    win.isVisible = lambda: True
    win.mark_saved()
    win.close()
    again = windows()
    assert _button(again, "Script").isChecked()
    assert _button(again, "History").isChecked()
    assert not _button(again, "Assistant").isChecked()
    restored_script = _script_content(again)
    restored_assistant = again.show_ai_panel()
    _lay_out(again)
    assert _left(again.command_line.echo_view, again) < _left(restored_script, again)
    assert _left(restored_script, again) < _left(restored_assistant, again)
    _fixed_controls_stay_accessible(again)


def test_model_and_layout_tabs_still_switch_spaces_with_both_panes_open(win):
    _open_both(win)
    layout = Layout(name="Layout 01")
    win.scene.layouts.append(layout)
    win.scene.notify()
    for space in (layout.id, "model"):
        index = next(i for i in range(win.space_tabs.count())
                     if win.space_tabs.tabData(i) == space)
        win.space_tabs.setCurrentIndex(index)
        assert win.space == space
        _fixed_controls_stay_accessible(win)
