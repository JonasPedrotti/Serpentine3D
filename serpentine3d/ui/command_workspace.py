"""The bottom workspace: history, optional panes, and an explicit composer."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from .workspace_icons import workspace_icon


class CommandWorkspace(QWidget):
    """Keep pane layout independent from the destination of typed input."""

    def __init__(self, window, command_line, tab_row, osnap_bar):
        super().__init__(window)
        self.window = window
        self.command_line = command_line
        self.mode = "command"
        self.assistant = None
        self.console = None
        self._pane_widths = {}
        self.setObjectName("commandWorkspace")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        self.setStyleSheet("""
            QWidget#commandWorkspace { background: #202226; color: #d4d6d5; }
            QFrame#workspaceComposer { background: #242529;
                border-top: 1px solid #383a3c; }
            QFrame#workspaceComposer[mode="ai"] { border-color: #477d73; }
            QPushButton, QToolButton { background: transparent; color: #adb3b4;
                border: 1px solid transparent; border-radius: 3px;
                padding: 3px 8px; }
            QPushButton:hover, QToolButton:hover { background: #33363a;
                color: #e7e7de; }
            QPushButton:disabled, QToolButton:disabled { color: #62676b; }
            QPushButton:checked, QToolButton:checked { background: #39372f; color: #dbc087;
                border-bottom-color: #aa8b49; }
            QPushButton#workspaceAssistant:checked, QPushButton#aiMode:checked { background: #29473f;
                color: #9bd3c3; border-bottom-color: #4c8273; }
            QPushButton#workspaceScript:checked { background: #2c343f;
                color: #bacbdf; border-bottom-color: #657d98; }
            QPushButton#workspaceSubmit { background: #39372f;
                color: #dbc087; padding: 3px 10px; }
            QPushButton#workspaceSubmit[mode="ai"] { background: #294b42;
                color: #a9dfce; border-color: #4c8273; }
            QSplitter::handle { background: #303236; width: 3px; }
            QSplitter::handle:hover { background: #867352; }
            QToolButton::menu-indicator { image: none; width: 0px; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(tab_row)

        # Space tabs and workspace controls share one strip, leaving the
        # vertical room to the drawing and the pane contents.
        toolbar = tab_row.layout()
        toolbar.setContentsMargins(0, 0, 2, 0)
        self.assistant_toggle = self._toggle("Assistant")
        self.script_toggle = self._toggle("Script")
        self.history_toggle = self._toggle("History")
        self.assistant_toggle.setObjectName("workspaceAssistant")
        self.script_toggle.setObjectName("workspaceScript")
        self.assistant_toggle.setIcon(workspace_icon("assistant", active_color="#9bd3c3"))
        self.script_toggle.setIcon(workspace_icon("script", active_color="#bacbdf"))
        self.history_toggle.setIcon(workspace_icon("history", active_color="#dbc087"))
        self.history_toggle.setToolTip("Everything commands, the assistant and "
                                       "scripts have said")
        self._toggles = {"assistant": self.assistant_toggle,
                         "script": self.script_toggle,
                         "history": self.history_toggle}
        for name, button in self._toggles.items():
            button.toggled.connect(
                lambda shown, name=name: self.set_pane_visible(name, shown))
            toolbar.addWidget(button)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(3)
        self.history_pane = QWidget()
        history = QVBoxLayout(self.history_pane)
        history.setContentsMargins(0, 0, 0, 0)
        history.setSpacing(0)
        command_line.echo_view.setAccessibleName("Command history")
        command_line.echo_view.setToolTip("Command history · commands, AI, MCP and scripts")
        # Reparent the existing history instead of copying its document.
        history.addWidget(command_line.echo_view)
        self.script_pane = QWidget()
        script = QVBoxLayout(self.script_pane)
        script.setContentsMargins(4, 0, 4, 0)
        script.setSpacing(0)
        self.assistant_pane = QWidget()
        assistant = QVBoxLayout(self.assistant_pane)
        assistant.setContentsMargins(0, 0, 0, 0)
        self._panes = {"history": self.history_pane,
                       "script": self.script_pane,
                       "assistant": self.assistant_pane}
        for pane in self._panes.values():
            pane.setMinimumWidth(150)
            self.splitter.addWidget(pane)
            pane.hide()
        # With no pane open there is nothing to give room to, and the
        # workspace is just its two rows.
        self.splitter.hide()
        root.addWidget(self.splitter, 1)

        self.composer = QFrame()
        self.composer.setObjectName("workspaceComposer")
        composer = QHBoxLayout(self.composer)
        composer.setContentsMargins(6, 3, 6, 3)
        composer.setSpacing(3)
        self.ai_mode = self._toggle("Ask AI")
        self.ai_mode.setIcon(workspace_icon("assistant", active_color="#9bd3c3"))
        self.ai_mode.setObjectName("aiMode")
        composer.addWidget(self.ai_mode, 0, Qt.AlignmentFlag.AlignVCenter)
        self.ai_mode.clicked.connect(
            lambda on: self.set_mode("ai" if on else "command"))
        shortcut = QShortcut(QKeySequence("Alt+/"), self)
        shortcut.activated.connect(
            lambda: self.set_mode("ai" if self.mode == "command" else "command"))
        command_line.set_compact(True)
        self.inputs = QStackedWidget()
        self.inputs.addWidget(command_line)
        self.ai_input_host = QWidget()
        ai_input_layout = QVBoxLayout(self.ai_input_host)
        ai_input_layout.setContentsMargins(3, 0, 3, 0)
        self.inputs.addWidget(self.ai_input_host)
        composer.addWidget(self.inputs, 1)
        self.submit_button = QPushButton("Run command")
        self.submit_button.setObjectName("workspaceSubmit")
        self.submit_button.clicked.connect(self.submit)
        composer.addWidget(self.submit_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(self.composer)
        root.addWidget(osnap_bar)
        command_line.input.textChanged.connect(self._update_draft_hint)
        command_line.suggestion_anchor = self
        self._update_composer()
        self._fit_height()

    def _fit_height(self):
        # Closed, it is only ever its two rows tall; open, it can be dragged.
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred if self._active_names()
                           else QSizePolicy.Policy.Fixed)

    @staticmethod
    def _toggle(text):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setIconSize(QSize(16, 16))
        return button

    def sizeHint(self):
        if not self._active_names():
            return QSize(1000, self.minimumSizeHint().height())
        if self.script_toggle.isChecked():
            return QSize(1000, min(360, max(280, int(self.window.height() * .34))))
        return QSize(1000, 280 if self.assistant_toggle.isChecked() else 180)

    def _ensure_assistant(self):
        if self.assistant is None:
            from ..ai.panel import AiPanel
            self.assistant = AiPanel(self.window)
            self.assistant_pane.layout().addWidget(self.assistant)
            field = self.assistant.use_external_composer()
            field.setAccessibleName("AI assistant input")
            field.setFixedHeight(48)
            field.setStyleSheet(
                "QPlainTextEdit { background: #202b28; color: #d0e5dc;"
                " border: 1px solid #50766b; border-radius: 4px; padding: 4px; }")
            self.ai_input_host.layout().addWidget(field)
            field.textChanged.connect(self._update_draft_hint)
            field.submitted.connect(self.show_assistant)
            self.assistant.composerStateChanged.connect(self._update_composer)
        return self.assistant

    def _ensure_script(self):
        if self.console is None:
            from .script_editor import ScriptEditor
            self.console = ScriptEditor(self.window)
            self.script_pane.layout().addWidget(self.console, 1)
        return self.console

    def show_assistant(self):
        panel = self._ensure_assistant()
        self.set_pane_visible("assistant", True)
        panel._refresh_mode()
        return panel

    def toggle_script(self):
        self.set_pane_visible("script", not self.script_toggle.isChecked())

    def show_history(self):
        self.set_pane_visible("history", True)

    def set_pane_visible(self, name, shown):
        self._remember_widths()
        if shown and name == "assistant":
            self._ensure_assistant()
        elif shown and name == "script":
            self._ensure_script()
        button = self._toggles[name]
        button.blockSignals(True)
        button.setChecked(shown)
        button.blockSignals(False)
        was_open = bool(self._active_names())
        self._panes[name].setVisible(shown)
        is_open = bool(self._active_names())
        self.splitter.setVisible(is_open)
        self._fit_height()
        self._restore_widths()
        self.layout().activate()
        if not hasattr(self.window, "_cmd_dock"):
            return
        if was_open and not is_open:
            self.window.resizeDocks([self.window._cmd_dock],
                                    [self.minimumSizeHint().height()],
                                    Qt.Orientation.Vertical)
        preferred_height = self.sizeHint().height()
        if shown and self.window.isVisible() and self.height() < preferred_height:
            self.window.resizeDocks([self.window._cmd_dock], [preferred_height],
                                    Qt.Orientation.Vertical)

    def _active_names(self):
        return [name for name in self._ordered_names()
                if not self._panes[name].isHidden()]

    @staticmethod
    def _ordered_names():
        return ["history", "script", "assistant"]

    def _remember_widths(self):
        names = self._active_names()
        widths = {name: self.splitter.sizes()[self.splitter.indexOf(self._panes[name])]
                  for name in names}
        if widths and all(value > 0 for value in widths.values()):
            self._pane_widths[",".join(names)] = widths

    def _restore_widths(self):
        names = self._active_names()
        widths = self._pane_widths.get(",".join(names), {})
        self.splitter.setSizes([widths.get(name, 350) if name in names else 0
                                for name in self._ordered_names()])

    def set_mode(self, mode):
        if mode not in ("command", "ai"):
            return
        self.command_line.suggestions.hide()
        if mode == "ai":
            self.show_assistant()
        self.mode = mode
        self.ai_mode.setChecked(mode == "ai")
        self.inputs.setCurrentIndex(1 if mode == "ai" else 0)
        self._update_composer()
        self.focus_input()

    def focus_input(self):
        field = (self.assistant.input if self.mode == "ai"
                 else self.command_line.input)
        field.setFocus()

    def submit(self):
        if self.mode == "ai":
            self.show_assistant()._send_or_stop()
        else:
            self.command_line.submit_input()
            self.command_line.focus()

    def _update_composer(self):
        ai = self.mode == "ai"
        # QStackedWidget otherwise reserves the hidden multiline AI page's
        # height even in Command mode. Only the active input needs that room.
        for index in range(self.inputs.count()):
            page = self.inputs.widget(index)
            page.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Preferred if index == int(ai)
                               else QSizePolicy.Policy.Ignored)
        self.inputs.updateGeometry()
        busy = bool(ai and self.assistant and self.assistant.agent
                    and self.assistant.agent.busy)
        ready = bool(self.assistant and self.assistant.is_ready())
        label = "Stop" if busy else "Send to AI" if ai else "Run command"
        if busy and self.assistant.btn_send.text() == "Stopping…":
            label = "Stopping…"
        # Enter runs a command; only the assistant needs a button, to stop it.
        self.submit_button.setVisible(ai)
        self.submit_button.setText(label)
        self.submit_button.setEnabled(not ai or busy or (
            ready and not self.assistant._resetting))
        self.submit_button.setToolTip(
            "Choose a connection in Assistant to send" if ai and not ready else label)
        self.submit_button.setIcon(workspace_icon(
            "stop" if busy else "send" if ai else "run",
            color="#a9dfce" if ai else "#dbc087"))
        self.inputs.setToolTip(
            "Enter to send · Shift+Enter for a new line" if ai else
            "Enter to run · Esc to clear")
        for widget in (self.composer, self.submit_button):
            widget.setProperty("mode", self.mode)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self._update_draft_hint()

    def _update_draft_hint(self):
        drafts = [label for label, has_draft in (
            ("command", bool(self.command_line.input.text())),
            ("question", bool(self.assistant
                              and self.assistant.input.toPlainText())))
            if has_draft]
        saved = f" · {' and '.join(drafts)} kept" if drafts else ""
        self.ai_mode.setToolTip(
            f"Ask AI instead of running a command{saved} · Alt+/ switches")

    def save_settings(self):
        self._remember_widths()
        self.window.cfg.set("workspace", {
            **{name: button.isChecked()
               for name, button in self._toggles.items()},
            "widths": self._pane_widths,
        })

    def restore_settings(self):
        cfg = self.window.cfg
        for name in self._toggles:
            self.set_pane_visible(name, bool(cfg.get("workspace", name, default=False)))
        widths = cfg.get("workspace", "widths", default={})
        if isinstance(widths, dict):
            self._pane_widths = {key: value for key, value in widths.items()
                                 if isinstance(value, dict)
                                 and all(isinstance(w, (int, float)) and w > 0
                                         for w in value.values())}
        self._restore_widths()
        QTimer.singleShot(0, self, self._restore_widths)


class LastMessage(QLabel):
    """What the history last said, on the status bar while the history is
    closed. A click opens the history; it fades out of the way on its own."""

    SHOWN_MS = 8000

    def __init__(self, command_line, open_history):
        super().__init__()
        self._open_history = open_history
        self._full = ""
        self.setStyleSheet("color: #c9cacd; padding: 0 6px;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaximumWidth(560)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.say(""))
        command_line.echoed.connect(self.say)

    def say(self, msg: str):
        lines = [line for line in str(msg).splitlines() if line.strip()]
        self._full = lines[-1].strip() if lines else ""
        self.setToolTip(f"{self._full}\nClick to open the history"
                        if self._full else "")
        self._elide()
        if self._full:
            self._timer.start(self.SHOWN_MS)

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideRight, self.maximumWidth()))

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._full:
            self._open_history()
        super().mousePressEvent(ev)
