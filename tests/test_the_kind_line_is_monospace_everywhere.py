"""The Properties kind line is monospace on Windows too.

The kind line ("LAYER", "OBJECT") is the design system's section label, in
a monospace face. Its style sheet named the face `monospace`, which is a
fontconfig alias: Linux resolves it, but Windows has no font by that name,
and a style sheet's font-family carries no style hint to fall back on, so
on Windows the label drew in the proportional default. The Windows suite
caught it. The style sheet now names a fixed-pitch family that is really
installed.
"""

from __future__ import annotations

import re

import pytest
from PySide6.QtGui import QFontDatabase, QFontInfo

from serpentine3d.ui import theme


def _named_family(widget) -> str:
    m = re.search(r'font-family:\s*"?([^";]+)"?\s*;', widget.styleSheet())
    assert m, "the kind line's style sheet names no family"
    return m.group(1).strip()


def _installed_fixed(family) -> bool:
    return (QFontDatabase.hasFamily(family)
            and QFontDatabase.isFixedPitch(family))


@pytest.fixture
def props(_qapp):
    from serpentine3d.core.history import History
    from serpentine3d.core.scene import Scene
    from serpentine3d.core.selection import SelectionManager
    from serpentine3d.ui.properties import PropertiesPanel
    scene = Scene()
    return PropertiesPanel(scene, SelectionManager(scene), History(scene))


def test_the_style_sheet_names_an_installed_fixed_pitch_family(props):
    family = _named_family(props.layer_head.kind)
    assert _installed_fixed(family), (
        f"{family!r} is not an installed fixed-pitch family")


def test_the_drawn_font_is_fixed_pitch(props):
    kind = props.layer_head.kind
    kind.ensurePolished()
    assert QFontInfo(kind.font()).fixedPitch()


def test_where_monospace_names_nothing_a_real_face_is_found(monkeypatch):
    """Windows: the alias resolves to the proportional default."""
    if not any(_installed_fixed(f) for f in theme.MONO_FAMILIES):
        pytest.skip("none of the fallback faces is installed here")
    monkeypatch.setattr(theme, "_monospace_alias", lambda: None)
    assert _installed_fixed(theme.mono_family())


def test_where_the_alias_works_it_is_kept(monkeypatch):
    """Linux: a monospace face someone set in fontconfig is theirs."""
    monkeypatch.setattr(theme, "_monospace_alias", lambda: "Some Mono")
    assert theme.mono_family() == "Some Mono"
