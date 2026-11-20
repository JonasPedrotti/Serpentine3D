"""A Rhino file's clipping planes, read straight from its .3dm.

rhino3dm hands a clipping plane over as a plain plane surface: which way
it cuts, whether it is on and the views it cuts are not exposed. They are
in the object's record as ON_ClippingPlaneSurface writes it: the plane
surface, then ON_ClippingPlane with its own plane, a viewport id, the
object's id, whether it is enabled and the ids of every viewport it cuts.

Anything this cannot follow answers nothing, and the plane comes in as
the surface it always did.
"""
from __future__ import annotations

import struct
import uuid

from .rhino_mesh_records import (_CLASS, _CLASS_DATA, _CLASS_UUID,
                                 _END_OF_TABLE, _OBJECT_RECORD, _OBJECT_TABLE,
                                 _SHORT)

_CLIPPING = uuid.UUID("dbc5a584-ce3f-4170-98a8-497069ca5c36").bytes_le
_ANONYMOUS = 0x40008000


def clipping_planes(path: str) -> dict:
    """{object id: {"origin", "normal", "enabled", "viewports"}} for every
    clipping plane in the file, `normal` pointing at the side Rhino keeps
    and `viewports` the ids of the views it cuts."""
    out = {}
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if not head.startswith(b"3D Geometry File Format ") or \
                    int(head[24:32]) < 50:
                return out
            while True:
                hdr = f.read(12)
                if len(hdr) < 12:
                    return out
                code, size = struct.unpack("<IQ", hdr)
                if code == _OBJECT_TABLE:
                    end = f.tell() + size
                    break
                if not code & _SHORT:
                    f.seek(size, 1)
            while f.tell() + 12 <= end:
                at = f.tell()
                code, size = struct.unpack("<IQ", f.read(12))
                if code == _END_OF_TABLE:
                    break
                if code & _SHORT:
                    continue
                if code == _OBJECT_RECORD and size < 1 << 16:
                    plane = _plane_of(f.read(size))
                    if plane is not None:
                        out[plane.pop("id")] = plane
                f.seek(at + 12 + size)
    except (OSError, ValueError, struct.error):
        pass
    return out


def _plane_of(record: bytes):
    """The clipping plane in one object record, or None."""
    at = 0
    while at + 12 <= len(record):
        code, size = struct.unpack_from("<IQ", record, at)
        if code == _CLASS:
            break
        at += 12 if code & _SHORT else 12 + size
    else:
        return None
    at += 12
    code, size = struct.unpack_from("<IQ", record, at)
    if code != _CLASS_UUID or record[at + 12:at + 28] != _CLIPPING:
        return None
    at += 12 + size
    code, size = struct.unpack_from("<IQ", record, at)
    if code != _CLASS_DATA:
        return None
    try:
        return _clipping_data(record, at + 12)
    except (IndexError, struct.error, ValueError):
        return None


def _clipping_data(b: bytes, at: int):
    code, _size = struct.unpack_from("<IQ", b, at)
    if code != _ANONYMOUS:
        return None
    at += 12 + 8                                  # chunk, version
    code, size = struct.unpack_from("<IQ", b, at)  # the plane surface
    if code != _ANONYMOUS:
        return None
    at += 12 + size
    code, size = struct.unpack_from("<IQ", b, at)  # ON_ClippingPlane
    if code != _ANONYMOUS:
        return None
    end = at + 12 + size - 4
    at += 12 + 8
    first = uuid.UUID(bytes_le=b[at:at + 16])
    object_id = uuid.UUID(bytes_le=b[at + 16:at + 32])
    at += 32
    plane = struct.unpack_from("<16d", b, at)
    at += 128
    enabled = bool(b[at])
    at += 1
    viewports = [str(first)]
    if at + 12 <= end:
        code, size = struct.unpack_from("<IQ", b, at)
        if code == _ANONYMOUS:
            count = struct.unpack_from("<i", b, at + 20)[0]
            ids = at + 24
            viewports = [str(uuid.UUID(bytes_le=b[ids + 16 * k:
                                                  ids + 16 * k + 16]))
                         for k in range(count)]
    return {"id": str(object_id), "origin": plane[0:3],
            "normal": plane[9:12], "enabled": enabled,
            "viewports": viewports}
