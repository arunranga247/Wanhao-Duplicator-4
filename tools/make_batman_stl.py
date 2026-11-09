"""
Two-colour bat-emblem badge for the Duplicator 4 (design by ARUN / Duplicator 4 Studio).

    python tools/make_batman_stl.py      -> models/batman_badge.stl  (+ models/batman_outline.png)

Layout (one STL, colour chosen by height when printing):
  * 0 .. BASE mm         : white oval plate                      -> RIGHT extruder (white)
  * BASE .. BASE+RELIEF  : black bat silhouette + black oval rim -> LEFT extruder (black)
Only ONE colour change per print = clean colours on a dual-nozzle machine.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import math
import os

from make_test_stl import write_stl

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")

OVAL_W, OVAL_H = 70.0, 42.0      # badge size (mm)
RIM = 3.0                        # black rim width (mm)
BASE = 2.3                       # white plate thickness = a layer boundary (0.3 + 10 x 0.2)
RELIEF = 1.2                     # black parts stand this much above the plate
BAT_SCALE = 1.0                  # bat drawn for a 70 x 42 oval


def bezier(p0, c, p1, n=18):
    """Quadratic Bezier from p0 to p1 with control c (excludes p0)."""
    out = []
    for i in range(1, n + 1):
        t = i / n
        a, b, d = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        out.append((a * p0[0] + b * c[0] + d * p1[0], a * p0[1] + b * c[1] + d * p1[1]))
    return out


def arc(p0, p1, sag, n=16):
    """Circular arc from p0 to p1 (excludes p0) bulging UPWARD (+y side) by `sag` mm.
    Shallow arcs meeting at an angle give the crisp scallop points of a bat wing."""
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    half = math.hypot(dx, dy) / 2
    nx, ny = -dy / (2 * half), dx / (2 * half)              # unit normal
    if ny < 0:
        nx, ny = -nx, -ny                                    # point it upward (into the wing)
    r = (half * half + sag * sag) / (2 * sag)
    cx, cy = mx - nx * (r - sag), my - ny * (r - sag)        # centre lies below the chord
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    da = a1 - a0
    while da > math.pi:
        da -= 2 * math.pi
    while da < -math.pi:
        da += 2 * math.pi
    return [(cx + r * math.cos(a0 + da * i / n), cy + r * math.sin(a0 + da * i / n)) for i in range(1, n + 1)]


def bat_outline():
    """Original bat silhouette, counter-clockwise, about 57 x 25 mm, centred on (0, 0)."""
    s = BAT_SCALE
    # right half, from the notch between the ears clockwise round the right wing to the tail tip
    right = [(0.0, 6.6)]
    right += [(1.6, 7.0)]                                   # inner side of the right ear
    right += [(3.0, 12.2)]                                  # right ear tip
    right += [(4.3, 7.1), (5.3, 6.4)]                       # outer side of the ear, head
    right += bezier((5.3, 6.4), (15.5, 3.0), (28.4, 11.6), 28)        # wing top edge (sags)
    right += bezier((28.4, 11.6), (29.2, 3.0), (25.4, -3.0), 14)      # wing tip, outer edge
    right += arc((25.4, -3.0), (18.4, -6.6), 2.1)                     # first scallop -> sharp point
    right += arc((18.4, -6.6), (11.2, -10.6), 2.1)                    # second scallop -> sharp point
    right += arc((11.2, -10.6), (0.0, -13.0), 2.4, 20)                # body down to the tail tip
    # mirror for the left half (reverse order so the path stays continuous)
    left = [(-x, y) for x, y in reversed(right[1:-1])]
    pts = right + left
    pts = [(x * s, y * s) for x, y in pts]
    # make it counter-clockwise
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    return pts if area > 0 else list(reversed(pts))


def ellipse(a, b, n=160):
    return [(a * math.cos(2 * math.pi * k / n), b * math.sin(2 * math.pi * k / n)) for k in range(n)]


def triangulate(poly):
    """Ear clipping for a simple counter-clockwise polygon -> list of index triples."""
    idx = list(range(len(poly)))
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0

    guard = 0
    while len(idx) > 3 and guard < 100000:
        guard += 1
        n = len(idx)
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if cross(a, b, c) <= 1e-12:
                continue                                      # reflex or flat corner
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            raise ValueError("triangulation failed (self-intersecting outline?)")
    tris.append(tuple(idx))
    return tris


def prism(poly, z0, z1):
    """Closed solid: simple CCW polygon extruded from z0 to z1."""
    tris = []
    for i0, i1, i2 in triangulate(poly):
        a, b, c = poly[i0], poly[i1], poly[i2]
        tris.append(((*a, z1), (*b, z1), (*c, z1)))         # top (normal up)
        tris.append(((*a, z0), (*c, z0), (*b, z0)))         # bottom (normal down)
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        tris.append(((*p, z0), (*q, z0), (*q, z1)))
        tris.append(((*p, z0), (*q, z1), (*p, z1)))
    return tris


def ring(outer, inner, z0, z1):
    """Closed solid between two CCW loops with the same point count."""
    n, tris = len(outer), []
    for i in range(n):
        j = (i + 1) % n
        o0, o1, i0, i1 = outer[i], outer[j], inner[i], inner[j]
        tris += [((*o0, z0), (*o1, z0), (*o1, z1)), ((*o0, z0), (*o1, z1), (*o0, z1))]
        tris += [((*i1, z0), (*i0, z0), (*i0, z1)), ((*i1, z0), (*i0, z1), (*i1, z1))]
        tris += [((*o0, z1), (*o1, z1), (*i1, z1)), ((*o0, z1), (*i1, z1), (*i0, z1))]
        tris += [((*o1, z0), (*o0, z0), (*i0, z0)), ((*o1, z0), (*i0, z0), (*i1, z0))]
    return tris


def preview_png(path, bat):
    from PIL import Image, ImageDraw
    sc, W, H = 9, 70 * 9 + 60, 42 * 9 + 60
    img = Image.new("RGB", (W, H), (240, 240, 240))
    d = ImageDraw.Draw(img)
    T = lambda p: (W / 2 + p[0] * sc, H / 2 - p[1] * sc)
    d.polygon([T(p) for p in ellipse(OVAL_W / 2, OVAL_H / 2)], fill=(20, 20, 20))
    d.polygon([T(p) for p in ellipse(OVAL_W / 2 - RIM, OVAL_H / 2 - RIM)], fill=(250, 250, 250))
    d.polygon([T(p) for p in bat], fill=(20, 20, 20))
    img.save(path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    bat = bat_outline()
    oval_out = ellipse(OVAL_W / 2, OVAL_H / 2)
    oval_in = ellipse(OVAL_W / 2 - RIM, OVAL_H / 2 - RIM)
    top = BASE + RELIEF
    tris = prism(oval_out, 0.0, BASE)                        # white plate
    tris += ring(oval_out, oval_in, BASE, top)               # black rim
    tris += prism(bat, BASE, top)                            # black bat
    stl = os.path.join(OUT, "batman_badge.stl")
    write_stl(stl, tris)
    preview_png(os.path.join(OUT, "batman_outline.png"), bat)
    xs, ys = [p[0] for p in bat], [p[1] for p in bat]
    print("wrote %s: %d triangles, badge %.0f x %.0f x %.1f mm, bat %.1f x %.1f mm"
          % (os.path.normpath(stl), len(tris), OVAL_W, OVAL_H, top, max(xs) - min(xs), max(ys) - min(ys)))
    print("colour change at Z %.1f mm: white plate below (RIGHT extruder), black bat + rim above (LEFT)" % BASE)
