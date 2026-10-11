"""A clipping plane cuts away the side toward the view it is drawn in.

Drawn in Top, it should cut downward the way you are looking: what is
above the plane goes and what is below stays, its arrow pointing into the
screen at the visible half. That is Rhino 8's rule ("the initial direction
is away from the active view", made consistent with the Plane command in
RH-56249), and what the user expected.

The plane used to face whichever way its rectangle happened to wind, which
followed the way it was dragged: top-left to bottom-right cut one way,
bottom-left to top-right the other. Now the view decides, the drag does
not, and Flip still turns it round. A parallel view is looked at along its
direction wherever its eye sits; a perspective one from its eye.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from serpentine3d.core.cplane import CPlane
from serpentine3d.ui.camera import STANDARD_VIEWS, Camera
from serpentine3d.ui.viewport import clip_equation, clip_plane_frames


def _view(ctx, name=None, *, elevation=None, azimuth=-90.0,
          projection="parallel", cplane=None, target=(0, 0, 0),
          distance=60.0):
    from tests.conftest import StubViewport
    ctx.viewport = StubViewport("model")
    if cplane is not None:
        ctx.viewport.cplane = cplane
    cam = Camera()
    if name is not None:
        cam.azimuth, cam.elevation = STANDARD_VIEWS[name]
    else:
        cam.azimuth = math.radians(azimuth)
        cam.elevation = math.radians(elevation)
    cam.projection = projection
    cam.target = np.asarray(target, float)
    cam.distance = distance
    ctx.viewport.camera = cam


def _draw(proc, first, second, flip=False):
    proc.run("clippingplane")
    proc.provide_text(",".join(map(str, first)))
    if flip:
        proc.provide_text("Flip=Yes")
    proc.provide_text(",".join(map(str, second)))
    assert not proc.busy


def _cuts(scene, point) -> bool:
    """Whether the newest plane hides this point."""
    (origin, normal, _on), = clip_plane_frames(
        [o for o in scene.all() if o.clip_plane][-1:])
    return float(np.dot(clip_equation(origin, normal),
                        np.array([*point, 1.0]))) < 0


DRAGS = [((-5, -5, 0), (5, 5, 0)), ((5, 5, 0), (-5, -5, 0)),
         ((-5, 5, 0), (5, -5, 0)), ((5, -5, 0), (-5, 5, 0))]


@pytest.mark.parametrize("first, second", DRAGS)
def test_drawn_in_top_it_cuts_away_what_is_above(env, first, second):
    scene, _sel, _h, ctx, proc = env
    _view(ctx, "top")
    _draw(proc, first, second)
    assert _cuts(scene, (0, 0, 3)), "what is above stayed"
    assert not _cuts(scene, (0, 0, -3)), "what is below went"


def test_flip_turns_it_round(env):
    scene, _sel, _h, ctx, proc = env
    _view(ctx, "top")
    _draw(proc, *DRAGS[0], flip=True)
    assert _cuts(scene, (0, 0, -3)) and not _cuts(scene, (0, 0, 3))


def test_drawn_from_below_it_cuts_away_what_is_below(env):
    scene, _sel, _h, ctx, proc = env
    _view(ctx, "bottom")
    _draw(proc, *DRAGS[0])
    assert _cuts(scene, (0, 0, -3)) and not _cuts(scene, (0, 0, 3))


def test_drawn_in_front_it_cuts_away_the_side_toward_the_viewer(env):
    """The construction plane's own normal points away from this viewer
    on purpose: the view decides, not the construction plane's sign."""
    scene, _sel, _h, ctx, proc = env
    _view(ctx, "front", cplane=CPlane(normal=(0, 1, 0)))
    front = Camera()
    front.azimuth, front.elevation = STANDARD_VIEWS["front"]
    toward_viewer = front.position - front.target
    cp = ctx.viewport.cplane
    _draw(proc, cp.to_world(-5, -5, 0), cp.to_world(5, 5, 0))
    assert _cuts(scene, tuple(toward_viewer / np.linalg.norm(toward_viewer)
                              * 3))
    assert not _cuts(scene, tuple(-toward_viewer
                                  / np.linalg.norm(toward_viewer) * 3))


def test_a_parallel_view_is_looked_at_along_its_direction(env):
    """In Top the eye can sit below a plane drawn high up, and it is still
    looked at from above."""
    scene, _sel, _h, ctx, proc = env
    _view(ctx, "top", distance=10.0)
    _draw(proc, (-5, -5, 50), (5, 5, 50))
    assert _cuts(scene, (0, 0, 53)) and not _cuts(scene, (0, 0, 47))


def test_a_perspective_view_is_looked_at_from_its_eye(env):
    """Looking up at a plane from under it, the side toward the eye is
    the side below."""
    scene, _sel, _h, ctx, proc = env
    _view(ctx, elevation=25.0, projection="perspective", distance=60.0)
    _draw(proc, (-5, -5, 100), (5, 5, 100))
    assert _cuts(scene, (0, 0, 97)) and not _cuts(scene, (0, 0, 103))


def test_with_no_camera_it_cuts_the_construction_plane_s_side(env):
    """Scripts and tests drive it with no view: the construction plane's
    normal, which faces the viewer in every standard view, decides."""
    from tests.conftest import StubViewport
    scene, _sel, _h, ctx, proc = env
    ctx.viewport = StubViewport("model")
    _draw(proc, *DRAGS[2])
    assert _cuts(scene, (0, 0, 3)) and not _cuts(scene, (0, 0, -3))


def test_the_arrow_points_into_the_screen_in_top(env):
    from serpentine3d.ui.viewport import clip_normal_arrows
    scene, _sel, _h, ctx, proc = env
    _view(ctx, "top")
    _draw(proc, *DRAGS[1])
    frames = clip_plane_frames([o for o in scene.all() if o.clip_plane])
    (segments, _color), = clip_normal_arrows(frames, ctx.viewport.camera,
                                             800, 600)
    base, tip = segments[0], segments[1]
    assert tip[2] < base[2], "the arrow points out of the screen"
