"""The window's own title bar: logo, menus, the document button in the middle
and the window buttons on the right, in place of the system frame."""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QHBoxLayout, QLabel, QMenu, QMenuBar, QPushButton,
    QWidget,
)

from . import popups

BAR_HEIGHT = 38
GRIP = 5
DOCUMENT_WIDTH = 440
_BG = "#2b2c30"

_STYLE = f"""
#titleBar {{ background: {_BG}; border-bottom: 1px solid #1b1c1f; }}
#titleBar QMenuBar {{ background: transparent; }}
#titleBar QMenuBar::item {{ padding: 6px 10px; border-radius: 3px; }}
#documentButton {{
    background: #34353a; border: 1px solid #45464c; border-radius: 6px;
    padding: 0 10px; color: #cfd0d2; text-align: center;
}}
#documentButton:hover {{ background: #3a3b41; border-color: #55565c; }}
#documentButton[popupOpen="true"] {{ border-color: #8a6a2f; }}
"""


class _WindowButton(QAbstractButton):
    """Minimise, maximise/restore or close, drawn as thin line glyphs."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.maximized = False
        self.setFixedSize(46, BAR_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def sizeHint(self):
        return QSize(46, BAR_HEIGHT)

    def paintEvent(self, _ev):
        p = QPainter(self)
        hover = self.underMouse()
        if hover or self.isDown():
            if self.kind == "close":
                bg = QColor("#c42b1c" if hover and not self.isDown()
                            else "#a82418")
            else:
                bg = QColor("#3a3b41" if not self.isDown() else "#45464c")
            p.fillRect(self.rect(), bg)
        fg = QColor("#ffffff" if hover and self.kind == "close"
                    else "#cfd0d2")
        # every glyph on the same pixel grid, an 11 px square, drawn sharp
        p.setPen(QPen(fg, 1))
        n = 10
        l, t = self.width() // 2 - n // 2, self.height() // 2 - n // 2
        if self.kind == "min":
            p.drawLine(l, t + n // 2, l + n, t + n // 2)
        elif self.kind == "max":
            if self.maximized:
                p.drawRect(l, t + 2, n - 2, n - 2)
                p.drawLine(l + 2, t, l + n, t)
                p.drawLine(l + n, t, l + n, t + n - 2)
            else:
                p.drawRect(l, t, n, n)
        else:
            p.drawLine(l, t, l + n, t + n)
            p.drawLine(l, t + n, l + n, t)
        p.end()


class TitleBar(QWidget):
    """Logo and menus on the left, the open document in the middle as a
    button whose menu starts a new one or opens a recent one, and the
    window buttons on the right."""

    def __init__(self, window, new_document, recent_files, open_recent,
                 is_blank=lambda: False):
        super().__init__(window)
        self._window = window
        self._new_document = new_document
        self._is_blank = is_blank
        self._recent_files = recent_files
        self._open_recent = open_recent
        self.setObjectName("titleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(_STYLE)
        self.setFixedHeight(BAR_HEIGHT)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 0, 0)
        row.setSpacing(6)

        self.logo = QLabel(self)
        self.logo.setPixmap(_logo_pixmap(20, self.devicePixelRatioF()))
        self.logo.setToolTip("Serpentine3D")
        row.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignVCenter)

        self.menu_bar = QMenuBar(self)
        self.menu_bar.setNativeMenuBar(False)
        row.addWidget(self.menu_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

        self.min_button = _WindowButton("min", self)
        self.min_button.setToolTip("Minimize")
        self.min_button.clicked.connect(window.showMinimized)
        self.max_button = _WindowButton("max", self)
        self.max_button.clicked.connect(self.toggle_maximized)
        self.close_button = _WindowButton("close", self)
        self.close_button.setToolTip("Close")
        self.close_button.clicked.connect(window.close)
        for b in (self.min_button, self.max_button, self.close_button):
            row.addWidget(b)

        self.document_button = QPushButton(self)
        self.document_button.setObjectName("documentButton")
        self.document_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.document_button.setFixedHeight(26)
        self.document_button.clicked.connect(self._show_document_menu)
        self.document_menu = QMenu(self.document_button)
        self.document_menu.setToolTipsVisible(True)
        self.document_menu.aboutToShow.connect(
            lambda: self._popup_open(True))
        self.document_menu.aboutToHide.connect(
            lambda: self._popup_open(False))
        self.document_button.setToolTip(
            "New document or a recently opened one")
        self.set_document_title("untitled")
        self.sync_window_state()

    def set_document_title(self, title: str):
        if self.document_button.text() != title:
            self.document_button.setText(title)

    def _popup_open(self, shown: bool):
        b = self.document_button
        b.setProperty("popupOpen", shown)
        b.style().unpolish(b)
        b.style().polish(b)

    def _show_document_menu(self):
        b, menu = self.document_button, self.document_menu
        menu.setMinimumWidth(b.width() + 2 * popups.SHADOW)
        self._fill_document_menu()
        below = b.mapToGlobal(QPoint(b.width() // 2, b.height() + 3))
        menu.popup(QPoint(below.x() - menu.sizeHint().width() // 2
                          + popups.SHADOW,
                          below.y()))

    def _fill_document_menu(self):
        menu = self.document_menu
        menu.clear()
        if not self._is_blank():
            menu.addAction("+  New Document", self._new_document)
            menu.addSeparator()
        files = self._recent_files()
        if not files:
            menu.addAction("(no recent documents)").setEnabled(False)
            return
        for path in files:
            act = menu.addAction(os.path.basename(path),
                                 lambda checked=False, p=path:
                                 self._open_recent(p))
            act.setToolTip(path)

    def _place_document_button(self):
        b = self.document_button
        left = self.menu_bar.geometry().right() + 12
        right = self.min_button.geometry().left() - 12
        b.setFixedWidth(max(160, min(DOCUMENT_WIDTH, right - left)))
        x = (self.width() - b.width()) // 2
        x = max(left, min(x, right - b.width()))
        b.move(x, (self.height() - b.height()) // 2)
        b.setVisible(right - left >= b.width())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._place_document_button()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._place_document_button()

    def toggle_maximized(self):
        w = self._window
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    def sync_window_state(self):
        maxed = self._window.isMaximized()
        self.max_button.maximized = maxed
        self.max_button.setToolTip("Restore Down" if maxed else "Maximize")
        self.max_button.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None and handle.startSystemMove():
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)


def _logo_pixmap(height: int, dpr: float):
    from .splash import mark_pixmap
    pm = mark_pixmap(round(height * 176 / 164 * dpr))
    pm.setDevicePixelRatio(dpr)
    return pm


class _EdgeGrip(QWidget):
    """A thin strip along a window edge or corner that resizes it."""

    def __init__(self, window, edges, cursor):
        super().__init__(window)
        self.edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(f"background: {_BG};")

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemResize(self.edges)
                ev.accept()
                return
        super().mousePressEvent(ev)


class FramelessFrame(QObject):
    """Takes the system frame off a main window, puts a TitleBar in the
    menu bar's place and keeps a thin border around it to resize from.

    On Windows the frame is only hidden, not taken away: the window keeps
    its caption and sizing styles and tells Windows which parts of the
    title bar count as caption, so dragging it to a screen edge still
    snaps and the borders resize natively."""

    def __init__(self, window, title_bar: TitleBar):
        super().__init__(window)
        self.window = window
        self.title_bar = title_bar
        self.native = QGuiApplication.platformName() == "windows"
        self._styled = False
        window.setWindowFlags(
            window.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowSystemMenuHint)
        window.setMenuWidget(title_bar)
        E, C = Qt.Edge, Qt.CursorShape
        self.grips = [] if self.native else [
            _EdgeGrip(window, E.LeftEdge, C.SizeHorCursor),
            _EdgeGrip(window, E.RightEdge, C.SizeHorCursor),
            _EdgeGrip(window, E.TopEdge, C.SizeVerCursor),
            _EdgeGrip(window, E.BottomEdge, C.SizeVerCursor),
            _EdgeGrip(window, E.TopEdge | E.LeftEdge, C.SizeFDiagCursor),
            _EdgeGrip(window, E.BottomEdge | E.RightEdge, C.SizeFDiagCursor),
            _EdgeGrip(window, E.TopEdge | E.RightEdge, C.SizeBDiagCursor),
            _EdgeGrip(window, E.BottomEdge | E.LeftEdge, C.SizeBDiagCursor),
        ]
        window.installEventFilter(self)
        self._sync()

    def eventFilter(self, obj, ev):
        if obj is self.window and ev.type() in (
                QEvent.Type.Resize, QEvent.Type.WindowStateChange,
                QEvent.Type.Show):
            if (self.native and not self._styled
                    and ev.type() == QEvent.Type.Show):
                self._styled = True
                _win32.add_frame_styles(int(self.window.winId()))
            self._sync()
        return False

    def _sync(self):
        w = self.window
        edgeless = self.native or bool(w.windowState() & (
            Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen))
        m = 0 if edgeless else GRIP
        w.setContentsMargins(m, m, m, m)
        self.title_bar.sync_window_state()
        W, H, g = w.width(), w.height(), GRIP
        rects = [
            (0, g, g, H - 2 * g), (W - g, g, g, H - 2 * g),
            (g, 0, W - 2 * g, g), (g, H - g, W - 2 * g, g),
            (0, 0, g, g), (W - g, H - g, g, g),
            (W - g, 0, g, g), (0, H - g, g, g),
        ]
        for grip, r in zip(self.grips, rects):
            grip.setGeometry(*r)
            grip.setVisible(not edgeless)
            grip.raise_()

    def native_event(self, event_type, message):
        """The result for MainWindow.nativeEvent, or None to leave it to Qt."""
        if not self._styled or bytes(event_type) != b"windows_generic_MSG":
            return None
        return _win32.handle(self, int(message))

    def is_caption(self, pos: QPoint) -> bool:
        tb = self.title_bar
        if not tb.geometry().contains(pos):
            return False
        child = tb.childAt(pos - tb.pos())
        return child is None or child is tb.logo


class _Win32:
    WM_NCCALCSIZE = 0x0083
    WM_NCHITTEST = 0x0084
    HTCAPTION = 2
    EDGE = 6
    # (left, right, top, bottom) -> HTLEFT ... HTBOTTOMRIGHT
    _EDGES = {
        (True, False, False, False): 10, (False, True, False, False): 11,
        (False, False, True, False): 12, (True, False, True, False): 13,
        (False, True, True, False): 14, (False, False, False, True): 15,
        (True, False, False, True): 16, (False, True, False, True): 17,
    }

    def __init__(self):
        self.user32 = None

    def _load(self):
        if self.user32 is None:
            import ctypes
            from ctypes import wintypes
            self.ct, self.wt = ctypes, wintypes
            self.user32 = ctypes.windll.user32
            self.user32.GetWindowLongW.restype = ctypes.c_long
            self.user32.SetWindowLongW.argtypes = [
                wintypes.HWND, ctypes.c_int, ctypes.c_long]
            self.user32.MonitorFromWindow.restype = wintypes.HMONITOR
            self.user32.MonitorFromWindow.argtypes = [
                wintypes.HWND, wintypes.DWORD]

    def add_frame_styles(self, hwnd: int):
        self._load()
        style = self.user32.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF
        style &= ~0x80000000                                 # WS_POPUP
        # WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        style |= 0x00C00000 | 0x00040000 | 0x00080000 | 0x00030000
        self.user32.SetWindowLongW(hwnd, -16, self.ct.c_long(style).value)
        # SWP_FRAMECHANGED | NOMOVE | NOSIZE | NOZORDER | NOACTIVATE
        self.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                                 0x20 | 0x2 | 0x1 | 0x4 | 0x10)

    def handle(self, frame, address: int):
        msg = self.wt.MSG.from_address(address)
        if msg.message == self.WM_NCCALCSIZE and msg.wParam:
            if self.user32.IsZoomed(msg.hWnd):
                self._fit_to_work_area(msg)
            return 0
        if msg.message == self.WM_NCHITTEST:
            return self._hit_test(frame, msg)
        return None

    def _fit_to_work_area(self, msg):
        """A maximised window hangs its hidden frame over the screen edge;
        keep it inside the monitor's work area instead."""
        ct, wt = self.ct, self.wt

        class MONITORINFO(ct.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                        ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

        mon = self.user32.MonitorFromWindow(msg.hWnd, 2)
        info = MONITORINFO()
        info.cbSize = ct.sizeof(MONITORINFO)
        if mon and self.user32.GetMonitorInfoW(mon, ct.byref(info)):
            rect = wt.RECT.from_address(msg.lParam)
            work = info.rcWork
            rect.left, rect.top = work.left, work.top
            rect.right, rect.bottom = work.right, work.bottom

    def _hit_test(self, frame, msg):
        ct, wt = self.ct, self.wt
        x = ct.c_short(msg.lParam & 0xFFFF).value
        y = ct.c_short((msg.lParam >> 16) & 0xFFFF).value
        r = wt.RECT()
        self.user32.GetWindowRect(msg.hWnd, ct.byref(r))
        window = frame.window
        dpr = window.devicePixelRatioF()
        if not self.user32.IsZoomed(msg.hWnd):
            e = round(self.EDGE * dpr)
            hit = self._EDGES.get((x < r.left + e, x >= r.right - e,
                                   y < r.top + e, y >= r.bottom - e))
            if hit is not None:
                return hit
        pos = QPoint(int((x - r.left) / dpr), int((y - r.top) / dpr))
        return self.HTCAPTION if frame.is_caption(pos) else None


_win32 = _Win32()
