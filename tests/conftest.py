import os

# Headless unless asked otherwise. Many tests build and show real viewports and
# windows; without this a local run opens every one of them on the desktop, as
# CI never does because its workflows set the variable. Set QT_QPA_PLATFORM
# (for example to "xcb") before running to watch them on a real display.
if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # Offscreen still reaches the display's GL driver through GLX. With a
    # desktop GPU driver that gives a context with no framebuffer behind it,
    # and a pane painting into that can crash the whole run (NVIDIA, the text
    # tests). Mesa's software renderer is what CI draws with; use it here too.
    os.environ.setdefault("__GLX_VENDOR_LIBRARY_NAME", "mesa")
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

import pytest  # noqa: E402

import serpentine3d.commands  # registers all commands  # noqa: F401,E402


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path_factory):
    """Settings of its own for every test, so none reads the developer's
    real ones or another test's leavings.

    Per test, not per session: a window that is shown and closed writes its
    geometry back, so one test opening a MainWindow would otherwise size
    every MainWindow after it — which is how the detail-portal tests come
    to fail only when run alongside the rest.
    """
    os.environ["SERP3D_CONFIG"] = str(
        tmp_path_factory.mktemp("settings") / "settings.json")


@pytest.fixture(autouse=True)
def _fresh_fillet_options():
    """Fillet remembers its radius and Trim for as long as the program
    runs; a test is a fresh program, not the one before it."""
    from serpentine3d.commands import edit
    was = dict(edit._FILLET_STICKY)
    yield
    edit._FILLET_STICKY.clear()
    edit._FILLET_STICKY.update(was)


@pytest.fixture(scope="session", autouse=True)
def _isolated_session_data(tmp_path_factory):
    """Journals and autosaves of the suite's own, thrown away after.

    A suite run opens dozens of windows, and each one lands in these
    directories: journals nobody wants to read next to the ones someone
    actually modelled in, and autosave lockfiles with dead pids that the
    next real launch reads as crashes worth recovering.

    Session-scoped: it is the volume that has to be contained, and a
    directory per test would make thousands of them.
    """
    data = tmp_path_factory.mktemp("session_data")
    os.environ["SERP3D_JOURNAL_DIR"] = str(data / "journals")
    os.environ["SERP3D_AUTOSAVE_DIR"] = str(data / "autosave")


@pytest.fixture(scope="session", autouse=True)
def _qapp():
    """A full QApplication before anything creates a QGuiApplication
    (core/text.py would otherwise block widget construction later)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    _deploy_fonts()
    yield app


@pytest.fixture(scope="module", autouse=True)
def _delete_the_windows_a_file_leaves(_qapp):
    """Delete every top-level widget a test file made once it is done.

    Nothing else does, and a worker kept tens of thousands of windows
    alive: memory grew past 9 GB, and every app-wide setStyle or
    setStyleSheet repolished all of them, one call taking minutes.
    """
    from PySide6.QtCore import QEvent
    from shiboken6 import Shiboken
    before = {Shiboken.getCppPointer(w)[0] for w in _qapp.topLevelWidgets()}
    yield
    _qapp.processEvents()       # timers still due would fire on deleted widgets
    for w in _qapp.topLevelWidgets():
        if (Shiboken.isValid(w)
                and Shiboken.getCppPointer(w)[0] not in before):
            w.hide()
            w.deleteLater()
    _qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _deploy_fonts():
    """The offscreen platform loads no system fonts on Windows: the font
    database comes up empty and every family query misses — the monospace
    kind line resolves to a proportional face and the scripted-text tests
    get no glyph outlines at all. Qt asks shipped apps to deploy fonts;
    the test's app deploys this machine's own fixed-pitch ones."""
    from PySide6.QtGui import QFontDatabase
    if QFontDatabase.families():
        return
    import os
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                             "Fonts")
    for name in ("consola.ttf", "consolab.ttf", "cour.ttf"):
        path = os.path.join(fonts_dir, name)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)
from serpentine3d.commands.base import CommandContext, CommandProcessor
from serpentine3d.core.history import History
from serpentine3d.core.scene import Scene
from serpentine3d.core.selection import SelectionManager


@pytest.fixture
def env():
    scene = Scene()
    selection = SelectionManager(scene)
    history = History(scene)
    ctx = CommandContext(scene, selection, history)
    proc = CommandProcessor(ctx)
    return scene, selection, history, ctx, proc


class StubLayoutView:
    """Just enough of ui.layout_view for headless drafting commands."""

    def __init__(self):
        self.entered_detail = None

    def _entered(self):
        return None


class StubViewport:
    def __init__(self, space: str):
        from serpentine3d.core.cplane import CPlane
        self.space = space          # a layout id puts commands on that sheet
        self.layout_view = StubLayoutView()
        self.cplane = CPlane()

    def active_cplane(self):
        """No detail is ever entered here, so it is the world plane."""
        return self.cplane
