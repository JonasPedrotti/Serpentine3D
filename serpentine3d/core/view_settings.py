"""What a model pane looks like and where it looks from, kept in the drawing.

Each pane is known by its `view_key` ("perspective", "top", "front",
"right", or a docked pane's own name). Its camera, background, grid,
axes and lock travel with the file, so a drawing opens looking the way it
was left. A background can be shared by every pane: `for_all` then makes
`background` the one they all draw.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

BG_TOP = (0.16, 0.165, 0.18)
BG_BOTTOM = (0.10, 0.105, 0.12)


@dataclass
class Background:
    color: tuple = BG_BOTTOM        # the whole of it, or the gradient's foot
    gradient: bool = True
    top: tuple = BG_TOP
    wallpaper: bytes | None = None
    wallpaper_name: str = ""
    wallpaper_show: bool = True
    wallpaper_gray: bool = False

    def copy(self) -> "Background":
        return Background(**asdict(self))

    def colors(self) -> tuple:
        """(top, bottom) as the pane paints them."""
        bottom = tuple(self.color)
        return (tuple(self.top) if self.gradient else bottom), bottom

    def shows_wallpaper(self) -> bool:
        return bool(self.wallpaper) and self.wallpaper_show


@dataclass
class PaneLook:
    grid: bool = True
    grid_axes: bool = True
    world_axes: bool = True
    locked: bool = False
    position_locked: bool = False
    target_locked: bool = False


@dataclass
class ViewSettings:
    for_all: bool = False
    background: Background = field(default_factory=Background)
    # view key -> {"camera": state, "background": Background, "look": PaneLook}
    panes: dict = field(default_factory=dict)

    def pane(self, key: str) -> dict:
        return self.panes.setdefault(key, {})


def _rgb(value, default) -> tuple:
    try:
        r, g, b = (float(c) for c in value)
        return (r, g, b)
    except (TypeError, ValueError):
        return default


def background_to_json(bg: Background, blobs: dict) -> dict:
    import hashlib
    out = {"color": list(bg.color), "gradient": bg.gradient,
           "top": list(bg.top), "wallpaper_show": bg.wallpaper_show,
           "wallpaper_gray": bg.wallpaper_gray}
    if bg.wallpaper:
        digest = hashlib.sha256(bg.wallpaper).hexdigest()[:16]
        member = f"wallpapers/{digest}.img"
        blobs[member] = bytes(bg.wallpaper)
        out["wallpaper"] = member
        out["wallpaper_name"] = bg.wallpaper_name
    return out


def background_from_json(data: dict, blobs=None) -> Background:
    bg = Background()
    if not isinstance(data, dict):
        return bg
    bg.color = _rgb(data.get("color"), bg.color)
    bg.top = _rgb(data.get("top"), bg.top)
    bg.gradient = bool(data.get("gradient", bg.gradient))
    bg.wallpaper_show = bool(data.get("wallpaper_show", True))
    bg.wallpaper_gray = bool(data.get("wallpaper_gray", False))
    member = data.get("wallpaper")
    if member and blobs is not None:
        try:
            bg.wallpaper = blobs.read(member)
            bg.wallpaper_name = str(data.get("wallpaper_name", ""))
        except (KeyError, OSError, RuntimeError):
            bg.wallpaper = None
    return bg


def to_json(settings: ViewSettings, blobs: dict) -> dict:
    panes = {}
    for key, pane in settings.panes.items():
        entry = {}
        if pane.get("camera"):
            entry["camera"] = dict(pane["camera"])
        if pane.get("background") is not None:
            entry["background"] = background_to_json(pane["background"],
                                                     blobs)
        if pane.get("look") is not None:
            entry["look"] = asdict(pane["look"])
        panes[key] = entry
    return {"for_all": settings.for_all,
            "background": background_to_json(settings.background, blobs),
            "panes": panes}


def from_json(data, blobs=None) -> ViewSettings:
    settings = ViewSettings()
    if not isinstance(data, dict):
        return settings
    settings.for_all = bool(data.get("for_all", False))
    settings.background = background_from_json(data.get("background"), blobs)
    names = {f.name for f in fields(PaneLook)}
    for key, entry in (data.get("panes") or {}).items():
        if not isinstance(entry, dict):
            continue
        pane = {}
        if isinstance(entry.get("camera"), dict):
            pane["camera"] = dict(entry["camera"])
        if "background" in entry:
            pane["background"] = background_from_json(entry["background"],
                                                       blobs)
        if isinstance(entry.get("look"), dict):
            pane["look"] = PaneLook(**{k: bool(v) for k, v in
                                       entry["look"].items() if k in names})
        settings.panes[str(key)] = pane
    return settings
