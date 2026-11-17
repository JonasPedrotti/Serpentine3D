"""Surface creation commands."""

import numpy as np

from ..core import geometry as g
from .base import NumberReq, PointReq, SelectReq, command, frame_sides


def _corner_surface(pts):
    """The surface the corners make, or None while they make none."""
    try:
        return g.corner_surface(pts)
    except g.GeometryError:
        return None


@command("plane", aliases=("rectsrf",))
def cmd_plane(ctx):
    """A rectangular plane corner to corner; or 3Points to stand it up."""
    c1 = yield PointReq("First corner", extra_options=("3Points",))
    if c1 == "3Points":
        yield from _plane_from_edge(ctx)
        return
    cp = ctx.cplane

    def _plane_to(p):
        u1, v1, w1 = cp.from_world(c1)
        u2, v2, _w = cp.from_world(p)
        return _corner_surface([cp.to_world(u1, v1, w1),
                                cp.to_world(u2, v1, w1),
                                cp.to_world(u2, v2, w1),
                                cp.to_world(u1, v2, w1)])

    c2 = yield PointReq("Other corner", rubber_from=c1, preview_fn=_plane_to,
                        rubber_sides=frame_sides(c1, cp))
    shape = _plane_to(c2)
    if shape is None:
        ctx.echo("Zero width, no plane created.")
        return
    obj = ctx.add(shape)
    ctx.echo(f"Created {obj.name}.")


@command("plane3pt", aliases=("3ptplane", "plane3points"))
def cmd_plane3pt(ctx):
    """A rectangular plane from one edge and a width, standing at any angle."""
    yield from _plane_from_edge(ctx)


def _plane_from_edge(ctx):
    """One edge, then how far the plane reaches square off it.

    The third point is taken in space, not on the CPlane, so Ctrl+click on
    one of the edge's ends and the height picked above it stands the plane
    upright.
    """
    a = yield PointReq("Start of edge")
    b = yield PointReq("End of edge", rubber_from=a)
    pa, pb = np.asarray(a, float), np.asarray(b, float)
    edge = pb - pa
    length2 = float(edge @ edge)
    if length2 < 1e-18:
        ctx.echo("Zero edge, no plane created.")
        return

    def _plane_to(p):
        off = np.asarray(p, float) - pa
        off -= edge * float(off @ edge) / length2
        return _corner_surface([pa, pb, pb + off, pa + off])

    c = yield PointReq("Width (Ctrl+click an end to stand it up)",
                       rubber_pts=[a, b], preview_fn=_plane_to,
                       newest_snaps=True)
    shape = _plane_to(c)
    if shape is None:
        ctx.echo("Zero width, no plane created.")
        return
    obj = ctx.add(shape)
    ctx.echo(f"Created {obj.name}.")


@command("srfpt", aliases=("cornersrf", "surfacefrompoints"))
def cmd_srfpt(ctx):
    """A surface from 3 or 4 corners; Enter after the third makes a triangle."""
    prompts = ("First corner", "Second corner", "Third corner",
               "Fourth corner (Enter or right-click for three)")
    pts = []
    while len(pts) < 4:
        n = len(pts)
        p = yield PointReq(
            prompts[n],
            rubber_from=pts[0] if n == 1 else None,
            rubber_pts=list(pts) if n >= 2 else None,
            allow_empty=n == 3,
            preview_fn=((lambda q, done=list(pts): _corner_surface(done + [q]))
                        if n >= 2 else None))
        if p is None:
            break
        pts.append(p)
    shape = _corner_surface(pts)
    if shape is None:
        ctx.echo("The corners make no surface, none created.")
        return
    obj = ctx.add(shape)
    ctx.echo(f"Created {obj.name}.")


@command("extrude", aliases=("ext", "extrudecrv"))
def cmd_extrude(ctx):
    from ..core.text import TextShape
    curves = yield SelectReq("Select curves to extrude", kinds=("curve",))
    closed = any(isinstance(c.shape, TextShape) or g.is_closed_curve(c.shape)
                 for c in curves)
    direction = tuple(ctx.cplane.normal)

    def _make(dist, cap):
        both = ctx.opt("BothSides", "No") == "Yes"
        shapes = []
        for c in curves:
            shape = c.shape
            if both:
                shape = g.translate(shape,
                                    tuple(-d * dist for d in direction))
            shapes.append(shape)
        return g.extrude_profiles(shapes, direction,
                                  dist * (2 if both else 1), cap=cap)

    choices = {"BothSides": ["No", "Yes"]}
    if closed:
        choices = {"Cap": ["Yes", "No"], **choices}
    base = g.centroid(curves[0].shape)

    def _dist_of(p):
        return sum((c - b) * d for c, b, d in zip(p, base, direction))

    def _preview(p):
        d = _dist_of(p)
        return g.make_compound(_make(d, cap=False)) if abs(d) > 1e-9 \
            else None

    dp = yield PointReq(
        "Extrusion distance (click, or type a number)",
        axis_lock=(base, direction), number_from=(base, direction),
        rubber_from=base, choices=choices,
        default=tuple(b + 10.0 * d for b, d in zip(base, direction)),
        preview_fn=_preview)
    dist = _dist_of(dp)
    if abs(dist) < 1e-9:
        ctx.echo("Zero distance — nothing extruded.")
        return
    cap = closed and ctx.opt("Cap", "Yes") == "Yes"
    both = ctx.opt("BothSides", "No") == "Yes"
    made = [ctx.scene.add(s) for s in _make(dist, cap)]
    if ctx.scene.record_history and not both:
        for result_index, o in enumerate(made):
            ctx.scene.add_record("extrude", [c.id for c in curves], o.id,
                                 direction=list(direction),
                                 dist=float(dist), cap=cap,
                                 result_index=result_index)
    ctx.echo(f"Extruded {len(made)} object(s): "
             + ", ".join(o.name for o in made))


@command("revolve", aliases=("rev",))
def cmd_revolve(ctx):
    curves = yield SelectReq("Select curve to revolve", kinds=("curve",),
                             max_count=1)
    p1 = yield PointReq("Start of revolve axis")
    p2 = yield PointReq("End of revolve axis", rubber_from=p1)
    angle = yield NumberReq("Angle in degrees", default=360.0)
    axis_dir = tuple(b - a for a, b in zip(p1, p2))
    srf = g.revolve(curves[0].shape, p1, axis_dir, angle)
    obj = ctx.scene.add(srf)
    if ctx.scene.record_history:
        ctx.scene.add_record("revolve", [curves[0].id], obj.id,
                             origin=list(p1), axis=list(axis_dir),
                             angle=float(angle))
    ctx.echo(f"Created {obj.name}.")


@command("loft")
def cmd_loft(ctx):
    curves = yield SelectReq("Select 2 or more profile curves in order",
                             kinds=("curve",), min_count=2,
                             choices={"Style": ["Normal", "Ruled"]})
    srf = g.loft([c.shape for c in curves],
                 ruled=(ctx.opt("Style", "Normal") == "Ruled"))
    obj = ctx.scene.add(srf)
    if ctx.scene.record_history:
        ctx.scene.add_record("loft", [c.id for c in curves], obj.id,
                             ruled=(ctx.opt("Style", "Normal") == "Ruled"))
    ctx.echo(f"Lofted {len(curves)} curves into {obj.name}.")


@command("planarsrf", aliases=("planar", "planesrf"))
def cmd_planar(ctx):
    curves = yield SelectReq("Select closed planar curves", kinds=("curve",))
    made = []
    for c in curves:
        made.append(ctx.scene.add(g.planar_face(c.shape)))
    ctx.echo(f"Created {len(made)} planar surface(s).")


@command("sweep1", aliases=("sweep",))
def cmd_sweep1(ctx):
    rails = yield SelectReq("Select rail curve", kinds=("curve",), max_count=1)
    profiles = yield SelectReq("Select profile curve", kinds=("curve",),
                               max_count=1, allow_preselected=False)
    srf = g.sweep1(profiles[0].shape, rails[0].shape)
    obj = ctx.scene.add(srf)
    ctx.echo(f"Created {obj.name}.")


@command("offsetsrf")
def cmd_offsetsrf(ctx):
    objs = yield SelectReq("Select surfaces to offset",
                           kinds=("surface", "solid"))

    from . import dragging
    from .base import PointReq
    # a surface offset runs along its own normal, so that is the way to drag
    origin, normal = g.face_point_normal(g.faces_of(objs[0].shape)[0])
    read = dragging.signed_along(origin, normal)

    def _preview(p):
        d = read(p)
        if abs(d) < 1e-9:
            return None
        try:
            return g.make_compound(
                [g.offset_surface(o.shape, d) for o in objs])
        except g.GeometryError:
            return None

    dp = yield PointReq("Offset distance (click a side, or type a number)",
                        axis_lock=(origin, normal),
                        number_from=(origin, normal),
                        rubber_from=origin, preview_fn=_preview)
    dist = read(dp)
    if abs(dist) < 1e-9:
        ctx.echo("Zero offset — nothing created.")
        return
    made = []
    for o in objs:
        made.append(ctx.scene.add(g.offset_surface(o.shape, dist),
                                  layer_id=o.layer_id))
    ctx.echo(f"Offset {len(made)} surface(s).")


def _held_solid_faces(ctx) -> dict:
    """{obj_id: [face index, ...]} for Ctrl+Shift-clicked faces of solids."""
    held = ctx.held_parts().get("face", {})
    return {oid: idxs for oid, idxs in held.items()
            if ctx.scene.get(oid).kind == "solid"}


@command("shell")
def cmd_shell(ctx):
    """Hollow a solid, leaving it open at the face(s) you pick.

    Click a solid on the face to take away, or Ctrl+Shift-click several
    faces first (before or during the prompt) to open more than one."""
    # read before asking: a select prompt clears the selection
    open_faces = _held_solid_faces(ctx)
    if open_faces:
        objs = [ctx.scene.get(oid) for oid in open_faces]
    else:
        objs = yield SelectReq(
            "Select the face to open (click it on the solid; Ctrl+Shift-"
            "click for several)", kinds=("solid",), want_point=True,
            allow_preselected=False)
        open_faces = _held_solid_faces(ctx)
        for o in objs:
            at = ctx.pick_points.get(o.id)
            if o.id not in open_faces and at is not None:
                open_faces[o.id] = [g.face_index_near(o.shape, at)]
        objs = list({o.id: o for o in objs
                     + [ctx.scene.get(oid) for oid in open_faces]}.values())
        if not open_faces:
            ctx.echo("No face picked — click the solid on the face to open. "
                     "Shelling closed (sealed void inside).")
    from . import dragging
    from .base import PointReq
    # measured off the wall being thickened, so a 1 mm wall is a 1 mm drag
    side = tuple(ctx.cplane.xdir)
    base = dragging.edge_point(objs, side)
    read = dragging.distance_from(base)

    def _shell_to(p):
        t = read(p)
        if t < 1e-9:
            return None
        try:
            return g.make_compound([
                g.shell_solid(o.shape, t, open_faces.get(o.id, ()))
                for o in objs])
        except g.GeometryError:
            return None

    tp = yield PointReq("Wall thickness (click, or type a number)",
                        number_from=(base, side), rubber_from=base,
                        preview_fn=_shell_to)
    thickness = read(tp)
    if thickness < 1e-9:
        ctx.echo("Zero thickness — nothing shelled.")
        return
    for o in objs:
        ctx.scene.replace_shape(o.id, g.shell_solid(
            o.shape, thickness, open_faces.get(o.id, ())))
    # the face indices belong to the old shapes
    ctx.selection.clear()
    ctx.echo(f"Shelled {len(objs)} solid(s) with wall {thickness:g}.")


@command("sweep2")
def cmd_sweep2(ctx):
    rail1 = yield SelectReq("Select first rail", kinds=("curve",),
                            max_count=1)
    rail2 = yield SelectReq("Select second rail", kinds=("curve",),
                            max_count=1, allow_preselected=False)
    profiles = yield SelectReq("Select profile curve", kinds=("curve",),
                               max_count=1, allow_preselected=False)
    srf = g.sweep2(profiles[0].shape, rail1[0].shape, rail2[0].shape)
    obj = ctx.scene.add(srf)
    ctx.echo(f"Created {obj.name}.")
