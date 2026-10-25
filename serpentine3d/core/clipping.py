"""Which views a clipping plane cuts.

A clipping plane cuts every view to begin with: each model pane and each
detail on every sheet. It can be switched off in any of them, the way
Rhino lets a clipping plane choose its views, so one model can give a
sheet a plan cut at sill height, a section cut down the middle and an
elevation not cut at all.

A plane's `clip_plane` setting keeps the views it is off in, `off_in`,
beside `enabled`, which still pauses it everywhere at once and leaves
those views as they were. A view is named by a key: a model pane's
(`Viewport.view_key`, "perspective", "top", "front" and "right" for the
four standard panes) or a detail's id.

The views it is off in rather than the ones it is on in, so a plane cuts
a view made after it, the way it always has, and a file from before this
opens with every plane cutting every view.

Hiding a plane, or its layer, only puts it out of sight, as in Rhino: it
goes on cutting, which is how a section is kept without the plane in the
way. Nothing on screen then shows why the model is missing a part, so
everything that lists the planes cutting a view names the hidden ones,
and hiding one that cuts says it still does.
"""

from __future__ import annotations


def cuts(clip_plane: dict | None, view: str | None = None) -> bool:
    """Whether a plane with this setting cuts `view`; with no view named,
    whether it cuts at all."""
    if not clip_plane or not clip_plane.get("enabled"):
        return False
    return view is None or view not in clip_plane.get("off_in", ())


def switched(clip_plane: dict, view: str, on: bool) -> dict:
    """The setting with the plane switched on or off in `view`, as a new
    dict: the scene's undo holds the old one.

    A plane on in every view again carries no list, so a file with no
    plane switched off anywhere is written the way it was before.
    """
    out = dict(clip_plane)
    off = [key for key in out.get("off_in", ()) if key != view]
    if not on:
        off.append(view)
    if off:
        out["off_in"] = off
    else:
        out.pop("off_in", None)
    return out


def switch(scene, plane_id: str, view: str, on: bool, before=None) -> bool:
    """Switch one plane on or off in one view. Returns whether anything
    changed; `before` is called first when something will, which is where
    a caller takes its undo checkpoint."""
    obj = scene.get(plane_id)
    if obj is None or not obj.clip_plane:
        return False
    new = switched(obj.clip_plane, view, on)
    if new == obj.clip_plane:
        return False
    if before is not None:
        before()
    scene.update(plane_id, clip_plane=new)
    return True


def carry_views(scene, pairs) -> None:
    """Switch planes off in new views wherever they are off in the views
    those were copied from: `pairs` is (old key, new key). A duplicated
    sheet's details are cut as the originals were, not by every plane."""
    for obj in scene.all():
        cp = obj.clip_plane
        off = list((cp or {}).get("off_in", ()))
        added = [new for old, new in pairs if old in off and new not in off]
        if added:
            scene.update(obj.id, clip_plane={**cp, "off_in": off + added})


def planes_of(scene) -> list:
    """Every clipping plane in the drawing, hidden ones too: a hidden plane
    cuts as well as one in sight."""
    return [obj for obj in scene.all() if obj.clip_plane]


def hidden(scene, obj) -> bool:
    """Whether a plane is out of sight: hidden itself, or on a layer that
    is off or under one that is."""
    return not (obj.visible and scene.layers.is_visible(obj.layer_id))


def label(scene, obj) -> str:
    """A plane as a list of planes names it, paused or hidden said."""
    notes = [word for word, applies in (
        ("paused", not obj.clip_plane.get("enabled")),
        ("hidden", hidden(scene, obj))) if applies]
    return f"{obj.name} ({', '.join(notes)})" if notes else obj.name


def in_sight(scene) -> set:
    """The planes in sight, by id: taken before a change that hides
    things, for `hidden_since` after it."""
    return {obj.id for obj in planes_of(scene) if not hidden(scene, obj)}


def hidden_since(scene, was_in_sight: set) -> list:
    """The planes of `was_in_sight` out of sight now."""
    return [obj for obj in planes_of(scene)
            if obj.id in was_in_sight and hidden(scene, obj)]


def still_cuts(planes) -> str:
    """What to say of planes just put out of sight that still cut, or ""
    when none do."""
    names = [obj.name for obj in planes if cuts(obj.clip_plane)]
    if not names:
        return ""
    if len(names) == 1:
        return (f"{names[0]} still cuts while hidden; "
                "'disableclippingplane' pauses it.")
    shown = names if len(names) <= 4 else [*names[:3],
                                           f"{len(names) - 3} more"]
    listed = ", ".join(shown[:-1]) + " and " + shown[-1]
    return (f"{listed} still cut while hidden; "
            "'disableclippingplane' pauses them.")
