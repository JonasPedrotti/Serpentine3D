"""A tooltip comes up sooner, with no fade and no shadow, round at the
corners, and goes when the pointer leaves or a button is pressed."""

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QStyle, QToolButton

from serpentine3d.ui import tooltips


@pytest.fixture
def shower():
    app = QApplication.instance() or QApplication([])
    style = app.style().name()      # setStyle deletes the one it replaces
    s = tooltips.install(app)
    yield s
    s.tip.drop()
    app.removeEventFilter(s)
    app.setStyle(style)
    del app._tooltip_shower


def _hover(button):
    ev = QHelpEvent(QEvent.Type.ToolTip, QPoint(2, 2),
                    button.mapToGlobal(QPoint(2, 2)))
    QApplication.sendEvent(button, ev)


def test_it_wakes_sooner_and_does_not_fade(shower):
    app = QApplication.instance()
    assert app.style().styleHint(
        QStyle.StyleHint.SH_ToolTip_WakeUpDelay) == tooltips.WAKE_UP_MS
    assert not app.isEffectEnabled(Qt.UIEffect.UI_FadeTooltip)
    assert not app.isEffectEnabled(Qt.UIEffect.UI_AnimateTooltip)


def test_it_shows_with_no_shadow_and_clear_corners(shower):
    button = QToolButton()
    button.setToolTip("Line  (line)")
    button.show()
    _hover(button)
    tip = tooltips.showing()
    assert tip is not None and tip.text() == "Line  (line)"
    assert tip.windowFlags() & Qt.WindowType.NoDropShadowWindowHint
    assert tip.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    img = tip.grab().toImage()
    assert img.pixelColor(0, 0).alpha() < 255, "the corner is rounded off"
    assert img.pixelColor(img.width() // 2, 2).alpha() == 255


def test_leaving_the_button_takes_it_away(shower):
    button = QToolButton()
    button.setToolTip("Line  (line)")
    button.show()
    _hover(button)
    QApplication.sendEvent(button, QEvent(QEvent.Type.Leave))
    assert tooltips.showing() is None


def test_a_button_with_no_tooltip_shows_none(shower):
    button = QToolButton()
    button.show()
    _hover(button)
    assert tooltips.showing() is None
