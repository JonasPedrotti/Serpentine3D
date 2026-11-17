"""Every command icon draws. One that raises takes the whole window down
with it, since the tool strip paints them all at start."""

import pytest
from PySide6.QtWidgets import QApplication

from serpentine3d.ui import icons


@pytest.mark.parametrize("name", sorted(icons._DRAWERS))
def test_the_icon_draws(name):
    QApplication.instance() or QApplication([])
    assert not icons.command_icon(name).pixmap(28, 28).isNull()
