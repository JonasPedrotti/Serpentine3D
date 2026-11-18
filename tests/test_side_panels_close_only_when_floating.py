"""Properties and Layers offer their close button only while torn off;
docked they are part of the window."""

from serpentine3d import app as app_mod


def test_the_close_button_shows_only_while_floating():
    win = app_mod.MainWindow()
    try:
        for dock, title in ((win._prop_dock, win._prop_title),
                            (win._layer_dock, win._lists_title)):
            assert not title.close_btn.isVisibleTo(title)
            dock.setFloating(True)
            assert title.close_btn.isVisibleTo(title)
            dock.setFloating(False)
            assert not title.close_btn.isVisibleTo(title)
    finally:
        win.close()
