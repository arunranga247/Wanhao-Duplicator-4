"""Write simple watertight test models (binary STL) for the slicer pipeline.

    python tools/make_test_stl.py        -> models/test_nut.stl, models/test_step_tower.stl
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import math
import os
import struct

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")


def write_stl(path, tris):
    with open(path, "wb") as fh:
        fh.write(b"Duplicator 4 Studio test model".ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            ux, uy, uz = (b[i] - a[i] for i in range(3))
            vx, vy, vz = (c[i] - a[i] for i in range(3))
            n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
            ln = math.sqrt(sum(v * v for v in n)) or 1.0
            fh.write(struct.pack("<3f", *(v / ln for v in n)))
            for p in (a, b, c):
                fh.write(struct.pack("<3f", *p))
            fh.write(b"\0\0")


def ring_prism(outer, inner, h):
    """Watertight prism between an outer and an inner loop (same point count, CCW)."""
    n, tris = len(outer), []
    for i in range(n):
        j = (i + 1) % n
        o0, o1, i0, i1 = outer[i], outer[j], inner[i], inner[j]
        O0, O1, I0, I1 = ((*o0, 0), (*o1, 0), (*i0, 0), (*i1, 0))
        T0, T1, U0, U1 = ((*o0, h), (*o1, h), (*i0, h), (*i1, h))
        tris += [(O0, O1, T1), (O0, T1, T0)]          # outer wall (normal outward)
        tris += [(I1, I0, U0), (I1, U0, U1)]          # inner wall (normal inward to hole)
        tris += [(T0, T1, U1), (T0, U1, U0)]          # top
        tris += [(O1, O0, I0), (O1, I0, I1)]          # bottom
    return tris


def hexagon_loop(r, n):
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        # point on a regular hexagon in direction t
        sector = math.pi / 3
        a = (t + sector / 2) % sector - sector / 2
        rr = r * math.cos(sector / 2) / math.cos(a)
        pts.append((rr * math.cos(t), rr * math.sin(t)))
    return pts


def box(x0, y0, z0, x1, y1, z1):
    p = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    f = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    tris = []
    for a, b, c, d in f:
        tris += [(p[a], p[b], p[c]), (p[a], p[c], p[d])]
    return tris


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    n = 72
    outer = hexagon_loop(11.5, n)
    inner = [(4.5 * math.cos(2 * math.pi * k / n), 4.5 * math.sin(2 * math.pi * k / n)) for k in range(n)]
    write_stl(os.path.join(OUT, "test_nut.stl"), ring_prism(outer, inner, 8.0))
    # stepped tower: 3 stacked boxes (tests top surfaces at several heights)
    tris = box(-12, -12, 0, 12, 12, 4) + box(-8, -8, 4, 8, 8, 8) + box(-4, -4, 8, 4, 4, 14)
    write_stl(os.path.join(OUT, "test_step_tower.stl"), tris)
    print("wrote models/test_nut.stl and models/test_step_tower.stl")
