"""Object snaps: end, mid, center, quad, intersection, perpendicular, near.

Static candidates (end/mid/center/quad) are cached per object; intersections
are cached per scene revision; perpendicular and near are computed against
the cursor each query.
"""

from __future__ import annotations

import numpy as np

from . import geometry, occ
from .pointcloud import PointCloudShape
from .spatial import build_index

SNAP_TYPES = ("end", "point", "mid", "center", "quad", "int", "appint", "perp",
              "near")

# priority when several candidates fall inside the pick radius
_PRIORITY = {"end": 0, "point": 0, "int": 1, "appint": 2, "quad": 3, "mid": 4,
             "center": 5, "perp": 6, "near": 7}

# How many screen segments near the cursor get paired up. Every pair is
# tried, so the cost is square, and a drawing dense enough to put more than
# this many edges under one pick radius is one where the answer would be a
# guess anyway.
_APPARENT_LIMIT = 160

# Two crossing segments this close along the line of sight are the same
# point in space, which means they really meet: that is `int`'s answer, and
# it is also what every corner of a polyline looks like from here.
_APPARENT_GAP = 1e-6


def _clip_slack(eq) -> float:
    """How far on the cut side a point may sit and still count as on the
    plane: a corner lying in it is kept, as the shader keeps it.

    Scale the world-distance tolerance by the normal, so translating a
    drawing to survey coordinates never widens the visible half-space.
    """
    return 1e-6 * float(np.linalg.norm(eq[:3]))


def in_sight(points, clip) -> np.ndarray:
    """Which points the clipping planes leave in sight, as a mask.

    `clip` holds the view's clip equations, each kept where it comes out
    positive (`clip_equation` in ui/viewport.py)."""
    pts = np.asarray(points, float).reshape(-1, 3)
    keep = np.ones(len(pts), bool)
    for eq in clip or ():
        eq = np.asarray(eq, float)
        keep &= pts @ eq[:3] + eq[3] >= -_clip_slack(eq)
    return keep


def _clipped_segments(a3, b3, clip):
    """Segments cut back to the part the clipping planes leave in sight.

    Returns the new ends and a mask of the segments with anything left."""
    a3, b3 = np.array(a3, float), np.array(b3, float)
    keep = np.ones(len(a3), bool)
    for eq in clip or ():
        eq = np.asarray(eq, float)
        slack = _clip_slack(eq)
        da = a3 @ eq[:3] + eq[3]
        db = b3 @ eq[:3] + eq[3]
        keep &= (da >= -slack) | (db >= -slack)
        cross = (da < -slack) != (db < -slack)
        t = np.where(cross, da / np.where(cross, da - db, 1.0), 0.0)
        hit = a3 + (b3 - a3) * t[:, None]
        a_out = cross & (da < -slack)
        b_out = cross & (db < -slack)
        a3[a_out] = hit[a_out]
        b3[b_out] = hit[b_out]
    return a3, b3, keep


def _plane_crossings(obj, eq) -> list:
    """Where a clipping plane cuts through an object's edges: the corners
    of the section a solid shows, the points a curve pierces it at."""
    from OCP.TopoDS import TopoDS_Shape
    shape = obj.shape
    eq = np.asarray(eq, float)
    n = -eq[:3]
    if isinstance(shape, TopoDS_Shape):
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        from .occ import gp_Dir, gp_Pln, gp_Pnt
        o = n * eq[3] / float(n @ n)
        try:
            sec = BRepAlgoAPI_Section(shape, gp_Pln(gp_Pnt(*o), gp_Dir(*n)))
            sec.Build()
            if not sec.IsDone():
                return []
            from OCP.TopExp import TopExp_Explorer
            out, exp = [], TopExp_Explorer(sec.Shape(), occ.VERTEX)
            while exp.More():
                out.append(geometry.point_coords(exp.Current()))
                exp.Next()
            return out
        except Exception:                                  # noqa: BLE001
            return []
    # A mesh's edges are straight, so its own segments are exact.
    edges = getattr(obj.mesh, "edge_segments", None)
    if edges is None:
        return []
    e = np.asarray(edges, float)
    if not len(e):
        return []
    da = e[:, 0] @ eq[:3] + eq[3]
    db = e[:, 1] @ eq[:3] + eq[3]
    cross = (da < 0) != (db < 0)
    t = da[cross] / (da[cross] - db[cross])
    a, b = e[cross, 0], e[cross, 1]
    return [tuple(p) for p in a + (b - a) * t[:, None]]


# A mesh offers its corners while it is small enough for that to stay
# quick. Not the middles of its edges, nor Near along them: a terrain or a
# scan is every one of its triangles, and those caught the cursor anywhere.
MESH_SNAPS_UP_TO = 200_000


def _static_snap_points(shape) -> list[tuple[tuple, str]]:
    """point / end / mid / center / quad candidates for one shape."""
    # Cloud samples are queried spatially, never expanded into CAD features.
    if isinstance(shape, PointCloudShape):
        return []
    out = []
    seen = set()

    def add(x, y, z, kind):
        key = (round(x, 6), round(y, 6), round(z, 6), kind)
        if key not in seen:
            seen.add(key)
            out.append(((x, y, z), kind))

    from .picture import PictureShape
    if isinstance(shape, PictureShape):
        for a, b in shape.feature_edges().reshape(-1, 2, 3):
            add(*a, "end")
            add(*b, "end")
            add(*((a + b) / 2), "mid")
        add(*shape.centroid(), "center")
        return out

    from .text_object import TextShape
    from .hatch import HatchShape
    from .dimension import DimensionShape
    if isinstance(shape, (TextShape, HatchShape, DimensionShape)):
        return shape.snap_points()
    # Any other mesh (an OBJ, an STL, a terrain) snaps at its corners, as
    # ends, and only there.
    from .mesh import MeshShape, _weld
    if isinstance(shape, MeshShape):
        if len(shape.vertices) > MESH_SNAPS_UP_TO:
            return []
        points = _weld(shape.vertices)[0]
        return [(tuple(float(c) for c in p), "end") for p in points]

    if shape.ShapeType() == occ.VERTEX:
        x, y, z = geometry.point_coords(shape)
        add(x, y, z, "point")
        return out

    from OCP.GeomAbs import GeomAbs_CurveType
    for edge in geometry.edges_of(shape):
        try:
            ad = occ.edge_adaptor(edge)
            t0, t1 = ad.FirstParameter(), ad.LastParameter()
            p0, p1 = ad.Value(t0), ad.Value(t1)
            closed = p0.Distance(p1) < 1e-9
            if not closed:
                add(p0.X(), p0.Y(), p0.Z(), "end")
                add(p1.X(), p1.Y(), p1.Z(), "end")
            pm = ad.Value((t0 + t1) / 2)
            add(pm.X(), pm.Y(), pm.Z(), "mid")

            ct = ad.GetType()
            circ = None
            if ct == GeomAbs_CurveType.GeomAbs_Circle:
                circ = ad.Circle()
            elif ct == GeomAbs_CurveType.GeomAbs_Ellipse:
                el = ad.Ellipse()
                c = el.Location()
                add(c.X(), c.Y(), c.Z(), "center")
            if circ is not None:
                c = circ.Location()
                add(c.X(), c.Y(), c.Z(), "center")
                if closed:
                    # quadrant points relative to the world axes projected
                    # onto the circle plane
                    n = np.array([circ.Axis().Direction().X(),
                                  circ.Axis().Direction().Y(),
                                  circ.Axis().Direction().Z()])
                    center = np.array([c.X(), c.Y(), c.Z()])
                    r = circ.Radius()
                    ref = np.array([1.0, 0.0, 0.0])
                    qx = ref - np.dot(ref, n) * n
                    if np.linalg.norm(qx) < 1e-9:
                        ref = np.array([0.0, 1.0, 0.0])
                        qx = ref - np.dot(ref, n) * n
                    qx /= np.linalg.norm(qx)
                    qy = np.cross(n, qx)
                    for d in (qx, -qx, qy, -qy):
                        q = center + r * d
                        add(q[0], q[1], q[2], "quad")
        except Exception:
            continue
    return out


def _reaching(objects, camera, px, py, width, height, radius_px,
              boxes=None) -> list:
    """The objects whose box, seen on screen, comes within `radius_px` of
    the cursor. One that is partly behind the eye is kept: its box does
    not say where on screen it is. `boxes` are their boxes, if known."""
    objects = list(objects)
    if not objects:
        return objects
    if boxes is None:
        boxes = np.array([obj.bbox() for obj in objects], float)
    pick = np.array([[x, y, z] for x in (0, 1) for y in (0, 1)
                     for z in (0, 1)])
    corners = boxes[:, pick, [0, 1, 2]]                          # (N, 8, 3)
    scr = np.asarray(camera.project(corners.reshape(-1, 3), width, height),
                     float).reshape(len(objects), 8, 3)
    behind = (scr[:, :, 2] <= 0).any(axis=1)
    lo = scr[:, :, :2].min(axis=1) - radius_px
    hi = scr[:, :, :2].max(axis=1) + radius_px
    over = (lo[:, 0] <= px) & (px <= hi[:, 0]) \
        & (lo[:, 1] <= py) & (py <= hi[:, 1])
    return [obj for obj, keep in zip(objects, behind | over) if keep]


def _intersections(objects) -> list[tuple]:
    """Pairwise curve-curve intersection points (bbox-filtered)."""
    curves = [(o, geometry.bbox(o.shape)) for o in objects
              if o.kind == "curve"]
    pts = []
    checked = 0
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            if checked > 400:
                return pts
            (oa, (amn, amx)), (ob, (bmn, bmx)) = curves[i], curves[j]
            if any(amn[k] > bmx[k] + 1e-6 or bmn[k] > amx[k] + 1e-6
                   for k in range(3)):
                continue
            checked += 1
            pts.extend(_meeting_points(oa.shape, ob.shape))
    return pts


def _meeting_points(a, b) -> list[tuple]:
    """Where two shapes touch, if they do."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    try:
        dist = BRepExtrema_DistShapeShape(a, b)
        if not dist.IsDone() or dist.Value() > 1e-6:
            return []
        return [(p.X(), p.Y(), p.Z()) for p in
                (dist.PointOnShape1(s) for s in range(1, dist.NbSolution() + 1))]
    except Exception:
        return []


def _crossings_of(shape, objects) -> list[tuple]:
    """Where `shape` crosses the curves of the drawing (bbox-filtered)."""
    mn, mx = geometry.bbox(shape)
    pts = []
    for o in objects:
        if o.kind != "curve":
            continue
        omn, omx = geometry.bbox(o.shape)
        if any(mn[k] > omx[k] + 1e-6 or omn[k] > mx[k] + 1e-6
               for k in range(3)):
            continue
        pts.extend(_meeting_points(shape, o.shape))
    return pts


def _world_param(s, da, db, parallel):
    """Where along a segment in space the screen fraction `s` landed.

    Under a parallel projection the two are the same number. A perspective
    one packs the far half of a segment into fewer pixels, so halfway across
    the screen is not halfway along the line, and reading the 3D point off
    `s` would put the snap somewhere the curve does not go.
    """
    if parallel:
        return s
    den = da * s + db * (1.0 - s)
    flat = np.abs(den) < 1e-12
    return np.where(flat, s, s * da / np.where(flat, 1.0, den))


def _misses_the_cursor(mesh, camera, cursor, width, height, pad) -> bool:
    """True if nothing in this mesh can reach the cursor, cheaply.

    Eight corners answered instead of every segment in the object. The
    projection of a box contains the projection of everything inside it, so
    a cursor outside the corners' screen bounds is outside the object. It
    reads the mesh's own cached bounds and never the B-rep, because a
    drawing read from a file holds its shapes unconverted and asking one
    for a bounding box on every mouse move would convert the lot.
    """
    bounds = mesh.bounds() if hasattr(mesh, "bounds") else None
    if bounds is None:
        return False
    lo, hi = np.asarray(bounds[0], float), np.asarray(bounds[1], float)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0])
                        for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    scr = camera.project(corners, width, height)
    if not (scr[:, 2] > 0).all():
        # part of it is behind the eye, where a corner's pixel means
        # nothing; let the segments speak for themselves
        return False
    return bool(scr[:, 0].min() > cursor[0] + pad
                or scr[:, 0].max() < cursor[0] - pad
                or scr[:, 1].min() > cursor[1] + pad
                or scr[:, 1].max() < cursor[1] - pad)


def _cursor_segments(objects, camera, px, py, width, height, radius_px,
                     clip=()):
    """Edges of visible objects passing within the pick radius, on screen.

    Solids come too. The edge of a box is not a curve object and it is still
    a line you can see, so a rail passing over one crosses something. A
    clipping plane cuts them back to what it leaves in sight.

    Every object's edges are projected in one go: one call per object was
    most of a mouse move on a drawing with hundreds near the cursor.
    """
    cursor = np.array([float(px), float(py)])
    r2 = float(radius_px) ** 2
    starts, ends, owners, names = [], [], [], []
    for obj in objects:
        mesh = getattr(obj, "mesh", None)
        edges = getattr(mesh, "edge_segments", None)
        if edges is None or not len(edges):
            continue
        # eight corners to save projecting the segments is only a saving
        # when there are more than eight of them, and a drawing made of
        # single lines has one each
        if len(edges) > 32 and _misses_the_cursor(mesh, camera, cursor,
                                                  width, height, radius_px):
            continue
        e = np.asarray(edges, float)
        a3, b3 = e[:, 0, :], e[:, 1, :]
        if clip:
            a3, b3, cut = _clipped_segments(a3, b3, clip)
            a3, b3 = a3[cut], b3[cut]
        if not len(a3):
            continue
        starts.append(a3)
        ends.append(b3)
        owners.append(np.full(len(a3), len(names)))
        names.append(obj.id)
    if not starts:
        return []
    a3, b3 = np.concatenate(starts), np.concatenate(ends)
    owner = np.concatenate(owners)
    both = camera.project(np.concatenate([a3, b3]), width, height)
    sa, sb = both[:len(a3)], both[len(a3):]
    ab = sb[:, :2] - sa[:, :2]
    ap = cursor[None, :] - sa[:, :2]
    den = np.einsum("ij,ij->i", ab, ab)
    t = np.clip(np.einsum("ij,ij->i", ap, ab)
                / np.where(den < 1e-12, 1e-12, den), 0.0, 1.0)
    d = cursor[None, :] - (sa[:, :2] + ab * t[:, None])
    keep = ((sa[:, 2] > 0) & (sb[:, 2] > 0)
            & (np.einsum("ij,ij->i", d, d) <= r2))
    chosen = np.nonzero(keep)[0][:_APPARENT_LIMIT]
    return [(a3[i], b3[i], sa[i], sb[i], names[owner[i]]) for i in chosen]


def _apparent_crossings(objects, camera, px, py, width, height,
                        radius_px, clip=()) -> list[tuple]:
    """Where two edges cross on screen without meeting in space.

    A rafter passing over a wall never touches it, so `int` has nothing at
    the place the two cross in a Top view, and that place is often the one
    being pointed at. It is made by where the camera stands, so unlike a
    real intersection there is nothing to cache: turn the view and every one
    of these moves. It is worked out per query, over the handful of segments
    the cursor is already on top of.
    """
    segs = _cursor_segments(objects, camera, px, py, width, height,
                            radius_px, clip)
    return _crossings_on_screen(segs, camera, touching=False)


def _real_crossings(objects, camera, px, py, width, height, radius_px,
                    clip=()) -> list[tuple]:
    """Where two curves meet in space, near the cursor: the crossings of
    their drawn segments that agree in depth too. Worked out over the
    segments under the cursor, not every pair of curves in the drawing."""
    curves = [obj for obj in objects if obj.kind == "curve"]
    segs = _cursor_segments(curves, camera, px, py, width, height,
                            radius_px, clip)
    return _crossings_on_screen(segs, camera, touching=True)


def _plane_cuts_near(objects, camera, px, py, width, height, radius_px,
                     clip) -> list[tuple]:
    """Where the clipping planes pass through the edges under the cursor:
    the corners of the section a solid shows, the points a curve pierces
    a plane at."""
    if not clip:
        return []
    cut = [obj for obj in objects if not obj.clip_plane
           and not isinstance(obj.shape, PointCloudShape)]
    segs = _cursor_segments(cut, camera, px, py, width, height, radius_px)
    if not segs:
        return []
    a = np.array([s[0] for s in segs], float)
    b = np.array([s[1] for s in segs], float)
    out = []
    for eq in clip:
        eq = np.asarray(eq, float)
        da = a @ eq[:3] + eq[3]
        db = b @ eq[:3] + eq[3]
        cross = (da < 0) != (db < 0)
        if cross.any():
            t = da[cross] / (da[cross] - db[cross])
            out.extend(tuple(q) for q in
                       a[cross] + (b[cross] - a[cross]) * t[:, None])
    return out


def _crossings_on_screen(segs, camera, touching: bool) -> list[tuple]:
    """Where segments of different objects cross on screen: those that
    meet in depth as well when `touching`, those that pass apart if not."""
    if len(segs) < 2:
        return []
    flat = getattr(camera, "projection", "perspective") == "parallel"
    a3 = np.array([s[0] for s in segs])
    b3 = np.array([s[1] for s in segs])
    sa = np.array([s[2] for s in segs])
    sb = np.array([s[3] for s in segs])

    # every pair at once. A mat of rails over one spot fills the segment
    # budget, and a hundred and sixty of those is thirteen thousand pairs
    # per mouse move, which is a fifth of a second of arithmetic done one
    # pair at a time and under a millisecond done all at once.
    i, j = np.triu_indices(len(segs), k=1)
    if touching:
        # a polyline's own segments meet at every corner it has
        owner = np.array([s[4] for s in segs], object)
        apart = owner[i] != owner[j]
        i, j = i[apart], j[apart]
        if not len(i):
            return []
    p, r = sa[i, :2], sa[j, :2]
    u, v = sb[i, :2] - p, sb[j, :2] - r
    den = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
    # running together on screen: either the same line drawn twice, or so
    # nearly so that where they meet is noise
    live = np.abs(den) >= 1e-6 * (np.hypot(u[:, 0], u[:, 1])
                                  * np.hypot(v[:, 0], v[:, 1]) + 1.0)
    safe = np.where(live, den, 1.0)
    w = r - p
    s1 = (w[:, 0] * v[:, 1] - w[:, 1] * v[:, 0]) / safe
    s2 = (w[:, 0] * u[:, 1] - w[:, 1] * u[:, 0]) / safe
    live &= (s1 >= 0.0) & (s1 <= 1.0) & (s2 >= 0.0) & (s2 <= 1.0)

    da1, db1, da2, db2 = sa[i, 2], sb[i, 2], sa[j, 2], sb[j, 2]
    t1 = _world_param(s1, da1, db1, flat)
    t2 = _world_param(s2, da2, db2, flat)
    d1 = da1 + (db1 - da1) * t1
    d2 = da2 + (db2 - da2) * t2
    # one pixel and one depth is one point in space, so the two agreeing on
    # depth means the curves genuinely touch
    if not touching:
        live &= np.abs(d1 - d2) > _APPARENT_GAP

    k = np.nonzero(live)[0]
    if not len(k):
        return []
    # the near one is the one you can see at that pixel; the far one is
    # behind something you are looking at
    first = d1[k] <= d2[k]
    ki, kj = i[k], j[k]
    on_i = a3[ki] + (b3[ki] - a3[ki]) * t1[k][:, None]
    on_j = a3[kj] + (b3[kj] - a3[kj]) * t2[k][:, None]
    if touching:
        # meeting in space, to the drawing's tolerance: a depth this far
        # out from home is too coarse to say it
        from .tolerance import tol
        met = np.linalg.norm(on_i - on_j, axis=1) <= tol()
        return [tuple((p + q) / 2) for p, q in zip(on_i[met], on_j[met])]
    return [tuple(q) for q in np.where(first[:, None], on_i, on_j)]


class SnapIndex:
    def __init__(self, scene, config=None):
        self.scene = scene
        self._cache: dict[str, tuple[int, list]] = {}
        self._int_cache: tuple[int, list] | None = None
        self._on_cache: tuple | None = None
        self._cloud_cache = {}
        self._cut_cache = {}
        self.enabled = True
        self.types = {t: t in ("end", "point", "mid", "center", "quad", "int")
                      for t in SNAP_TYPES}
        # Project, as in Rhino: every picked point lands at one height,
        # whatever it snapped to. Not dormant with the master switch. For
        # this session only: every launch starts with it off, at 0.
        self.project_enabled = False
        self.project_z = 0.0
        if config is not None:
            osnaps = config.get("osnaps", default={}) or {}
            self.enabled = bool(osnaps.get("enabled", True))
            for t in SNAP_TYPES:
                if t in osnaps:
                    self.types[t] = bool(osnaps[t])

    def projected(self, point):
        """`point` at the Project height when Project is on."""
        if not self.project_enabled or point is None:
            return point
        return (float(point[0]), float(point[1]), float(self.project_z))

    # -- caches --

    def _block(self, objects) -> dict:
        """What the snaps need of these objects that a mouse move does not
        change: kept while the scene and the objects stay as they are.

        The points and boxes come from the shapes, which only change with
        the revision; which objects are in sight changes with it too, or
        with a layer switched, which the revision does not see. So the key
        is those and not every object in the list, which on a survey
        drawing was a millisecond of every mouse move."""
        layers = getattr(self.scene, "layers", None)
        if layers is None:
            # a sheet's stand-in replaces what it changes without counting
            # a revision, and holds few enough objects to name each one
            key = ("each", tuple(map(id, objects)),
                   id(getattr(self, "_features", None)))
        else:
            key = (self.scene.revision, len(objects),
                   objects[0].id if objects else None,
                   objects[-1].id if objects else None,
                   getattr(self.scene, "showing_only", None),
                   tuple((la.id, la.visible, la.parent)
                         for la in layers.all()))
        held = getattr(self, "_held_block", None)
        if held is not None and held["key"] == key:
            return held
        clouds = [o for o in objects if isinstance(o.shape, PointCloudShape)]
        plain = [o for o in objects
                 if not isinstance(o.shape, PointCloudShape)]
        points, kinds = [], []
        for obj in plain:
            for p, kind in self._points(obj):
                points.append(p)
                kinds.append(kind)
        held = {"key": key, "clouds": clouds,
                "points": np.asarray(points, float).reshape(-1, 3),
                "kinds": np.array(kinds, object),
                "boxes": (np.array([o.bbox() for o in objects], float)
                          if objects else np.zeros((0, 2, 3))),
                "by_types": None}
        self._held_block = held
        return held

    def _fixed_points(self, block):
        """The block's fixed points of the kinds switched on."""
        on = tuple(sorted(k for k, v in self.types.items() if v))
        cached = block["by_types"]
        if cached is None or cached[0] != on:
            keep = np.isin(block["kinds"], list(on)) if len(block["kinds"])                 else np.zeros(0, bool)
            cached = (on, block["points"][keep], block["kinds"][keep])
            block["by_types"] = cached
        return cached[1], cached[2]

    def _points(self, obj) -> list:
        entry = self._cache.get(obj.id)
        mesh_key = obj.mesh.uid
        if entry is None or entry[0] != mesh_key:
            entry = (mesh_key, _static_snap_points(obj.shape))
            self._cache[obj.id] = entry
        return entry[1]

    def _intersection_points(self, objects) -> list:
        key = (self.scene.revision, tuple(obj.id for obj in objects))
        if self._int_cache is None or self._int_cache[0] != key:
            self._int_cache = (key, _intersections(objects))
        return self._int_cache[1]

    def _crossings_of(self, curve, objects) -> list:
        rev = (self.scene.revision, tuple(obj.id for obj in objects))
        cached = self._on_cache
        if cached is None or cached[0] is not curve or cached[1] != rev:
            self._on_cache = cached = (curve, rev, _crossings_of(curve, objects))
        return cached[2]

    def _cut_points(self, objects, clip) -> list:
        """Where the clipping planes cut through the objects, kept per
        object and plane until the object changes."""
        cache, pts = {}, []
        for obj in objects:
            if obj.clip_plane or isinstance(obj.shape, PointCloudShape):
                continue
            for eq in clip:
                key = (obj.id, tuple(float(c) for c in eq))
                entry = self._cut_cache.get(key)
                if entry is None or entry[0] != obj.mesh.uid:
                    entry = (obj.mesh.uid, _plane_crossings(obj, eq))
                cache[key] = entry
                pts.extend(entry[1])
        self._cut_cache = cache
        return pts

    def _cloud_point(self, obj, camera, px, py, width, height, radius_px,
                     clip=()):
        """Nearest full-resolution sample, narrowing large scans by chunks.

        Keep only world-space bounds in the cache: every camera pose, zoom,
        viewport size and layout detail projects them afresh. Shapes are
        immutable, so replacement also invalidates a transformed scan.
        """
        shape = obj.shape
        entry = self._cloud_cache.get(obj.id)
        if entry is None or entry[0] is not shape:
            # Indexed where the points are stored, which for a scan at
            # survey coordinates is about its own origin; only the chunk
            # corners come out into the world, and there are eight of them
            # per chunk rather than one per point.
            index = build_index(shape.local[:, None, :])
            corners = None
            if index is not None:
                axes = np.array([[x, y, z] for x in (0, 1)
                                 for y in (0, 1) for z in (0, 1)], bool)
                corners = shape.to_world(
                    np.where(axes[None, :, :], index.maxs[:, None, :],
                             index.mins[:, None, :]))
            entry = (shape, index, corners)
            self._cloud_cache[obj.id] = entry
        _, index, corners = entry
        xyz = shape.local
        if index is not None:
            # Detail-frame clipping belongs to samples, not chunk corners:
            # a box can enclose the whole frame with every corner outside.
            screen = camera.project(corners.reshape(-1, 3), width, height,
                                    clipped=False).reshape(-1, 8, 3)
            front = screen[:, :, 2] > 0
            lo = screen[:, :, :2].min(axis=1)
            hi = screen[:, :, :2].max(axis=1)
            overlaps = ((lo[:, 0] < px + radius_px) &
                        (hi[:, 0] > px - radius_px) &
                        (lo[:, 1] < py + radius_px) &
                        (hi[:, 1] > py - radius_px))
            # A box crossing the eye plane can project beyond its corners.
            keep = front.any(axis=1) & (~front.all(axis=1) | overlaps)
            xyz = xyz[index.gather(keep)]
        if not len(xyz):
            return None
        xyz = shape.to_world(xyz)
        if clip:
            xyz = xyz[in_sight(xyz, clip)]
        screen = camera.project(xyz, width, height)
        d2 = (screen[:, 0] - px) ** 2 + (screen[:, 1] - py) ** 2
        valid = np.flatnonzero((screen[:, 2] > 0) & (d2 < radius_px ** 2))
        if not len(valid):
            return None
        # Pixel distance wins; stacked points then choose the nearest eye depth.
        nearest = valid[np.lexsort((screen[valid, 2], d2[valid]))[0]]
        return tuple(float(v) for v in xyz[nearest])

    # -- query --

    @staticmethod
    def _pending_candidates(chain, picked=None) -> list[tuple[tuple, str]]:
        """Snap candidates on the geometry still being picked.

        `chain` is the run of points the command draws as a connected curve;
        `picked` is simply every point it has taken. Only the chain has
        midpoints worth offering — a box takes two corners in sequence, but
        the line between them is a diagonal and halfway along it is not a
        feature of anything.

        Either way the newest point is left out: it sits under the cursor the
        moment it is placed, so offering it would glue every new leg to zero
        length."""
        def clean(seq):
            return [tuple(float(c) for c in p) for p in (seq or [])]

        run, taken = clean(chain), clean(picked)
        out, seen = [], set()

        def add(p, kind):
            key = (round(p[0], 9), round(p[1], 9), round(p[2], 9), kind)
            if key not in seen:
                seen.add(key)
                out.append((p, kind))

        for p in run[:-1]:
            add(p, "end")
        for p in taken[:-1]:
            add(p, "end")
        for a, b in zip(run, run[1:]):
            add(tuple((x + y) / 2 for x, y in zip(a, b)), "mid")
        return out

    def find(self, camera, px: float, py: float, width: int, height: int,
             radius_px: float = 12.0, base_point=None, pending_points=None,
             picked_points=None, clip=(), exclude_ids=None, extra_points=None,
             on_curve=None, hidden=None):
        """Best snap near the pixel. Returns (point, kind) or None.

        `on_curve` is a curve the point being picked has to lie on, as the
        end of an arc lies on its circle. Its own crossings with the drawing
        are then the intersections that count, not those of the drawing.

        `clip` holds the clip equations of the planes cutting the view:
        what they take away is out of sight, so nothing on it snaps.
        `exclude_ids` leaves objects out, and `extra_points` puts (point,
        kind) candidates in: what a drag is moving cannot be snapped to where
        it is going, but the rest of the shape it was can.

        `hidden` says of a point whether something in front of it covers
        it on screen: what cannot be seen is not snapped to."""
        if not self.enabled:
            return None
        objects = self.scene.visible_objects()
        if exclude_ids:
            objects = [obj for obj in objects if obj.id not in exclude_ids]
        visible_ids = {obj.id for obj in objects}
        self._cloud_cache = {key: value for key, value in self._cloud_cache.items()
                             if key in visible_ids}
        pts, kinds = [], []

        # what you are drawing is not in the scene yet, but you still want to
        # close it back on its start or land a later pick on an earlier one
        for p, kind in self._pending_candidates(pending_points, picked_points):
            if self.types.get(kind):
                pts.append(p)
                kinds.append(kind)
        pending = len(pts)
        for p, kind in extra_points or ():
            if self.types.get(kind):
                pts.append(p)
                kinds.append(kind)

        block = self._block(objects)
        for obj in block["clouds"]:
            if self.types.get("point"):
                p = self._cloud_point(obj, camera, px, py, width, height,
                                      radius_px, clip)
                if p is not None:
                    pts.append(p)
                    kinds.append("point")
        head, head_kinds = pts, kinds
        pts, kinds = [], []
        close = None
        if (self.types.get("int") or self.types.get("appint")
                or self.types.get("near")):
            # Only what reaches the cursor can meet there. Working out
            # every crossing in the drawing took 25 seconds after each
            # edit of a survey file, and a clipping plane's cuts through
            # it 9 more for every step of a drag.
            close = _reaching(objects, camera, px, py, width, height,
                              radius_px, block["boxes"])
        if self.types.get("int"):
            for p in (_real_crossings(close, camera, px, py, width, height,
                                      radius_px, clip) if on_curve is None
                      else self._crossings_of(on_curve, close)):
                pts.append(p)
                kinds.append("int")
            # a clipping plane is a surface too, and where it cuts through
            # a curve, a solid or a mesh is as much an intersection
            for p in _plane_cuts_near(close, camera, px, py, width, height,
                                      radius_px, clip):
                pts.append(p)
                kinds.append("int")
        if self.types.get("appint"):
            for p in _apparent_crossings(close, camera, px, py, width,
                                         height, radius_px, clip):
                pts.append(p)
                kinds.append("appint")
        if self.types.get("perp") and base_point is not None:
            for p in self._perp_feet(objects, base_point):
                pts.append(p)
                kinds.append("perp")

        # the fixed points of every object, gathered once for as long as
        # the objects stay as they are, between what was picked and what
        # this move found
        fixed, fixed_kinds = self._fixed_points(block)
        arr = np.concatenate([np.asarray(head, float).reshape(-1, 3), fixed,
                              np.asarray(pts, float).reshape(-1, 3)])
        kinds = np.concatenate([np.array(head_kinds, object), fixed_kinds,
                                np.array(kinds, object)])
        best = None
        if len(arr):
            scr = camera.project(arr, width, height)
            d2 = (scr[:, 0] - px) ** 2 + (scr[:, 1] - py) ** 2
            d2[scr[:, 2] <= 0] = np.inf
            if clip:
                d2[pending:][~in_sight(arr[pending:], clip)] = np.inf
            in_range = np.nonzero(d2 < radius_px ** 2)[0]
            ranked = sorted(in_range, key=lambda i: (
                _PRIORITY[kinds[i]], d2[i], scr[i, 2]))
            for i in ranked:
                # what is being drawn sits over the model, never behind it
                if i >= pending and hidden is not None and hidden(arr[i]):
                    continue
                best = (tuple(arr[i]), kinds[i])
                break

        if best is None and self.types.get("near"):
            # what reaches the cursor: over empty space, which is when this
            # runs, every edge in the drawing was looked at on every move
            near = self._near(close, camera, px, py, width, height,
                              radius_px, clip, hidden)
            if near is not None:
                best = (near, "near")
        return best

    def _perp_feet(self, objects, base_point) -> list:
        """Feet of perpendiculars from base_point onto visible curves."""
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from .occ import BRepBuilderAPI_MakeVertex, gp_Pnt
        v = BRepBuilderAPI_MakeVertex(
            gp_Pnt(*[float(c) for c in base_point])).Vertex()
        feet = []
        for obj in objects:
            if obj.kind != "curve":
                continue
            try:
                dist = BRepExtrema_DistShapeShape(v, obj.shape)
                if dist.IsDone():
                    for s in range(1, min(dist.NbSolution(), 4) + 1):
                        p = dist.PointOnShape2(s)
                        feet.append((p.X(), p.Y(), p.Z()))
            except Exception:
                continue
        return feet

    def _near(self, objects, camera, px, py, width, height, radius_px,
              clip=(), hidden=None):
        """Closest point on any curve's tessellation, in screen space.

        Not on a mesh: its edges are every triangle of a terrain or a scan,
        and Near on them caught the cursor wherever it went."""
        found = []
        cursor = np.array([px, py])
        for obj in objects:
            if obj.kind == "mesh":
                continue
            mesh = obj.mesh
            if not len(mesh.local_edges):
                continue
            seg = mesh.edge_segments
            a3, b3 = seg[:, 0, :].astype(float), seg[:, 1, :].astype(float)
            cut = np.ones(len(a3), bool)
            if clip:
                a3, b3, cut = _clipped_segments(a3, b3, clip)
            sa = camera.project(a3, width, height)
            sb = camera.project(b3, width, height)
            valid = (sa[:, 2] > 0) & (sb[:, 2] > 0) & cut
            if not valid.any():
                continue
            ab = sb[:, :2] - sa[:, :2]
            ap = cursor[None, :] - sa[:, :2]
            denom = np.einsum("ij,ij->i", ab, ab)
            denom[denom < 1e-12] = 1e-12
            t = np.clip(np.einsum("ij,ij->i", ap, ab) / denom, 0, 1)
            closest = sa[:, :2] + ab * t[:, None]
            d = cursor[None, :] - closest
            d2 = np.einsum("ij,ij->i", d, d)
            d2[~valid] = np.inf
            i = int(np.argmin(d2))
            if d2[i] < radius_px ** 2:
                found.append((d2[i], tuple(a3[i] + (b3[i] - a3[i]) * t[i])))
        for _d2, world in sorted(found, key=lambda f: f[0]):
            if hidden is None or not hidden(world):
                return world
        return None


# kept for backward compatibility with existing tests
def snap_points_for(shape) -> list[tuple[tuple, str]]:
    return [(p, k) for p, k in _static_snap_points(shape)
            if k in ("point", "end", "mid", "center")]
