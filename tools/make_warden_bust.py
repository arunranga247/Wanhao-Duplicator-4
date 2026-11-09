"""
"Night Warden" - an ORIGINAL low-poly hero bust on a stepped pedestal (design by ARUN /
Duplicator 4 Studio). Two colours by height: white pedestal, black bust.

    python tools/make_warden_bust.py [--height 50]
        -> models/night_warden_bust.stl, models/night_warden_render.png

Faceted ("low-poly") style: bold at small sizes and clean on a 0.4 mm nozzle.
Colour change height = top of the pedestal (printed in the summary).
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import math
import os

from make_test_stl import write_stl

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
N = 12                          # facets around the body: the low-poly look
PEDESTAL_TOP = 11.9             # = a layer boundary (0.3 + 58 x 0.2) at 50 mm height


# ---- geometry helpers ------------------------------------------------------------------
def ring(z, hx, hy, cy=0.0, n=N, power=2.6, rot=0.0):
    """Super-ellipse cross-section (CCW). power > 2 = boxier (chest), 2 = ellipse."""
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n + rot
        c, s = math.cos(t), math.sin(t)
        x = hx * math.copysign(abs(c) ** (2 / power), c)
        y = cy + hy * math.copysign(abs(s) ** (2 / power), s)
        pts.append((x, y, z))
    return pts


def loft(rings):
    """Closed solid through a stack of rings (same point count, CCW, z increasing)."""
    tris = []
    for a, b in zip(rings, rings[1:]):
        n = len(a)
        for i in range(n):
            j = (i + 1) % n
            tris += [(a[i], a[j], b[j]), (a[i], b[j], b[i])]
    bot, top = rings[0], rings[-1]
    cb = tuple(sum(p[k] for p in bot) / len(bot) for k in range(3))
    ct = tuple(sum(p[k] for p in top) / len(top) for k in range(3))
    for i in range(len(bot)):
        j = (i + 1) % len(bot)
        tris.append((cb, bot[j], bot[i]))                     # bottom cap, normal down
        tris.append((ct, top[i], top[j]))                     # top cap, normal up
    return tris


def slab(poly_uv, axis, w0, w1, bevel=0.0):
    """Extrude a CCW polygon drawn in the (u, v) plane along `axis` from w0 to w1.
    axis 'y': u -> x, v -> z (a plate facing front/back); axis 'x': u -> y, v -> z.
    bevel > 0 shrinks the w1 face toward the centre (0.4 = 40 % smaller) so the sides slope:
    sloped sides catch light/shadow, which makes small face details readable when printed."""
    def P(u, v, w):
        return (u, w, v) if axis == "y" else (w, u, v)
    n, tris = len(poly_uv), []
    c = (sum(p[0] for p in poly_uv) / n, sum(p[1] for p in poly_uv) / n)
    top = [(c[0] + (u - c[0]) * (1 - bevel), c[1] + (v - c[1]) * (1 - bevel)) for u, v in poly_uv]
    for i in range(n):
        (u0, v0), (u1, v1) = poly_uv[i], poly_uv[(i + 1) % n]
        (t0, s0), (t1, s1) = top[i], top[(i + 1) % n]
        # caps (fan from the centre; polygons used here are star-shaped around it)
        tris.append((P(*c, w1), P(t0, s0, w1), P(t1, s1, w1)))
        tris.append((P(*c, w0), P(u1, v1, w0), P(u0, v0, w0)))
        tris.append((P(u0, v0, w0), P(u1, v1, w0), P(t1, s1, w1)))
        tris.append((P(u0, v0, w0), P(t1, s1, w1), P(t0, s0, w1)))
    if axis == "y":                       # (u, w, v) mapping mirrors space -> flip winding
        tris = [(a, c_, b) for a, b, c_ in tris]
    return tris


def crescent(cx, cz, r, n=18):
    """Crescent-moon outline (CCW) in the (u, v) plane: outer circle minus an offset circle."""
    pts = []
    a0, a1 = math.radians(60), math.radians(300)
    for k in range(n + 1):                                  # outer arc, left side
        a = a0 + (a1 - a0) * k / n
        pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    ri, off = r * 0.82, r * 0.42                            # inner arc back to the top
    b0 = math.atan2(cz + r * math.sin(a1) - cz, cx + r * math.cos(a1) - (cx + off))
    b1 = math.atan2(cz + r * math.sin(a0) - cz, cx + r * math.cos(a0) - (cx + off))
    if b1 < b0:
        b1 += 2 * math.pi
    for k in range(1, n):
        b = b1 - (b1 - b0) * k / n
        pts.append((cx + off + ri * math.cos(b), cz + ri * math.sin(b)))
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts)))
    return pts if area > 0 else list(reversed(pts))


# ---- sculpted head ----------------------------------------------------------------------
def _smooth(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def _g(dx, dz, sx, sz):
    return math.exp(-(dx * dx) / (sx * sx) - (dz * dz) / (sz * sz))


# head cross-sections: (z, half width, half depth, centre y, squareness)
HEAD_KEYS = [(30.6, 3.3, 3.4, 0.0, 2.0), (33.8, 3.2, 3.4, 0.1, 2.0),          # neck
             (34.4, 3.5, 4.4, 0.5, 2.4), (35.0, 4.1, 5.3, 0.8, 2.8),           # jaw line
             (36.5, 4.6, 5.8, 0.8, 2.7), (38.0, 5.0, 6.0, 0.7, 2.5), (40.0, 5.3, 6.2, 0.5, 2.3),
             (42.0, 5.5, 6.3, 0.3, 2.2), (44.0, 5.3, 6.0, 0.1, 2.1), (46.0, 4.4, 5.0, 0.0, 2.0),
             (47.4, 2.8, 3.2, 0.0, 2.0), (48.1, 0.6, 0.7, 0.0, 2.0)]


def head_section(z):
    """Catmull-Rom interpolation of HEAD_KEYS -> (hx, hy, cy, power)."""
    return _catmull(HEAD_KEYS, z)


def _catmull(k, z):
    i = max(0, min(len(k) - 2, max(j for j in range(len(k)) if k[j][0] <= z) if z >= k[0][0] else 0))
    p0, p1, p2, p3 = k[max(0, i - 1)], k[i], k[i + 1], k[min(len(k) - 1, i + 2)]
    t = min(1.0, max(0.0, (z - p1[0]) / (p2[0] - p1[0])))
    out = []
    for c in range(1, 5):
        a, b, cc, d = p0[c], p1[c], p2[c], p3[c]
        out.append(0.5 * ((2 * b) + (-a + cc) * t + (2 * a - 5 * b + 4 * cc - d) * t * t
                          + (-a + 3 * b - 3 * cc + d) * t ** 3))
    return out


def face_relief(x, z):
    """Forward (+y) relief of the face in mm, sculpted like a real face (stern hero)."""
    ax = math.sqrt(x * x + 0.25)          # smooth |x|: mirrored features meet without a crease
    d = 0.0
    # nose: bridge widening and rising toward a rounded tip, nostril wings
    amp = 1.85 * _smooth(37.55, 38.35, z) * (1 - 0.6 * _smooth(38.7, 41.3, z)) * (1 - _smooth(41.3, 41.9, z))
    w = 0.72 + 0.16 * (41.3 - z)
    d += amp * math.exp(-(x / w) ** 2)
    d += 0.45 * _g(x, z - 38.45, 0.7, 0.45)                     # tip
    d += 0.75 * _g(ax - 0.95, z - 38.15, 0.42, 0.38)            # nostril wings
    # eyes: deep sockets, eyeballs, upper + lower lids, carved pupils (sculptor's trick)
    d -= 1.40 * _g(ax - 2.25, z - 40.55, 1.35, 0.85)
    d += 0.82 * _g(ax - 2.25, z - 40.45, 0.70, 0.44)
    d += 0.28 * _g(ax - 2.25, z - 40.88, 0.85, 0.15)
    d += 0.16 * _g(ax - 2.25, z - 40.05, 0.80, 0.12)
    d -= 0.16 * _g(ax - 2.15, z - 40.45, 0.24, 0.24)
    # stern brow (lower toward the centre) + glabella
    zb = 41.6 - 0.32 * math.exp(-(x / 1.3) ** 2)
    d += 0.75 * _g(ax - 2.1, z - zb, 2.1, 0.42)
    d += 0.35 * _g(x, z - 41.2, 0.7, 0.4)
    # cheekbones, hollow cheeks
    d += 0.62 * _g(ax - 3.4, z - 39.2, 1.1, 0.85)
    d -= 0.30 * _g(ax - 3.3, z - 37.3, 1.0, 0.8)
    # mouth: upper lip, groove, lower lip, chin dimple area
    d += 0.50 * _g(x, z - 37.2, 1.35, 0.42)
    d -= 0.42 * _g(x, z - 36.78, 1.55, 0.14)
    d += 0.45 * _g(x, z - 36.4, 1.2, 0.28)
    d -= 0.20 * _g(x, z - 35.95, 1.0, 0.25)
    # strong square chin
    d += 1.0 * math.exp(-(x / 2.0) ** 4) * _g(0, z - 35.2, 1, 0.7)
    return d


def head_point(theta, z, off=0.0, relief=True):
    hx, hy, cy, pw = head_section(z)
    c, s = math.cos(theta), math.sin(theta)
    x = (hx + off) * math.copysign(abs(c) ** (2 / pw), c)
    y = cy + (hy + off) * math.copysign(abs(s) ** (2 / pw), s)
    if relief and s > 0:
        y += face_relief(x, z) * _smooth(0.15, 0.7, s)
    return x, y, z


def sculpted_head(n=160, dz=0.08):
    zs, z = [], HEAD_KEYS[0][0]
    while z < HEAD_KEYS[-1][0] - 1e-6:
        zs.append(z)
        z += dz
    zs.append(HEAD_KEYS[-1][0])
    # points packed 2.5x denser across the face (front = theta 90 deg) for crisp features
    ths = [t + 0.6 * math.cos(t) for t in (2 * math.pi * k / n for k in range(n))]   # d/dt = 1 - 0.6 sin t
    return loft([[head_point(t, z) for t in ths] for z in zs])


def helmet(n=128, m=36):
    """Smooth guardian helmet over the cranium: rim just above the brow at the front,
    sweeping down over the temples and lower at the back; thick lip at the edge."""
    top = HEAD_KEYS[-1][0]

    def rim(t):
        s = math.sin(t)
        return 39.4 + 2.75 * _smooth(0.0, 0.9, s) if s >= 0 else 39.4 - 1.4 * _smooth(0.0, 1.0, -s)

    ths = [2 * math.pi * k / n for k in range(n)]
    rings = []
    for j, (u, off) in enumerate([(0.0, 0.85), (0.05, 0.85), (0.05, 0.5)] +
                                 [(0.05 + 0.95 * q / m, 0.5) for q in range(1, m + 1)]):
        rings.append([head_point(t, rim(t) + u * (top - rim(t)), off, relief=False) for t in ths])
    return loft(rings)


# ---- sculpted torso: trapezius, collarbones, deltoids, pecs, emblem, back ------------------
TORSO_KEYS = [(11.5, 3.6, 3.0, 0.0, 2.0), (13.5, 3.8, 3.2, 0.2, 2.0),             # socle
              (16.0, 6.5, 4.8, 0.5, 2.3), (19.0, 11.0, 6.4, 0.6, 2.6),            # bust cut
              (22.0, 14.2, 7.6, 0.4, 2.9), (24.5, 16.0, 8.2, 0.2, 3.0),           # arm cut / chest
              (27.0, 16.2, 8.0, 0.0, 2.9), (28.6, 14.8, 7.3, -0.2, 2.7),          # shoulder caps
              (29.8, 12.0, 6.1, -0.3, 2.5), (30.9, 8.4, 4.9, -0.3, 2.3),          # trapezius
              (31.8, 5.6, 4.1, -0.2, 2.1), (32.4, 3.8, 3.7, 0.05, 2.0), (32.9, 3.1, 3.2, 0.1, 2.0)]

SHIELD = [(0.0, 19.2), (4.6, 22.0), (5.2, 26.2), (0.0, 28.2), (-5.2, 26.2), (-4.6, 22.0)]   # CCW (x, z)
CRESCENT_C, CRESCENT_R = (0.0, 24.0), 2.7


def _shield_sd(x, z):
    """Signed distance to the chest shield outline (+ inside)."""
    sd = 1e9
    for (ax_, az), (bx, bz) in zip(SHIELD, SHIELD[1:] + SHIELD[:1]):
        ex, ez = bx - ax_, bz - az
        ln_ = math.hypot(ex, ez)
        sd = min(sd, ((x - ax_) * -ez + (z - az) * ex) / ln_)
    return sd


def _crescent_sd(x, z):
    cx, cz = CRESCENT_C
    r = CRESCENT_R
    d1 = r - math.hypot(x - cx, z - cz)                           # inside the moon disc
    d2 = math.hypot(x - (cx + 0.42 * r), z - cz) - 0.82 * r       # outside the bite
    return min(d1, d2)


def body_relief(x, z, s):
    """Outward relief (mm) of the torso surface. s = sin(theta): +1 front, -1 back."""
    ax = math.sqrt(x * x + 0.25)
    wf, wb = _smooth(0.1, 0.6, s), _smooth(0.1, 0.6, -s)
    d = 0.0
    # deltoids: rounded shoulder muscle capping each arm (wraps front, side and back)
    d += 1.4 * _g(ax - 14.4, z - 26.2, 2.6, 2.4)
    # trapezius ridge running from the neck onto the shoulders
    d += 0.45 * _g(ax - 6.8, z - 30.3, 3.0, 0.9)
    f = 0.0
    f += 1.5 * _g(ax - 5.0, z - 24.6, 4.0, 2.6) * _smooth(20.8, 22.8, z)        # pectorals
    f -= 0.55 * _g(x, z - 24.4, 0.9, 3.2)                                         # sternum line
    zc = 29.1 + 0.07 * (ax - 2.0)                                                 # collarbones
    f += 0.55 * _g(0, z - zc, 1, 0.45) * _smooth(1.5, 3.0, ax) * (1 - _smooth(10.0, 13.0, ax))
    f -= 0.35 * _g(ax - 6.0, z - 30.2, 2.5, 0.5)                                  # hollow above
    f -= 0.50 * _g(x, z - 30.5, 1.0, 0.7)                                         # throat notch
    f -= 0.50 * _g(ax - 11.0, z - 25.4, 0.9, 3.0)                                 # delto-pec groove
    # hero emblem embossed on the suit: shield + crescent moon (follows the chest muscles)
    f += 0.50 * _smooth(-0.22, 0.22, _shield_sd(x, z))
    f += 0.45 * _smooth(-0.2, 0.2, _crescent_sd(x, z))
    bk = 0.0
    bk -= 0.50 * _g(x, z - 25.4, 0.9, 6.0)                                        # spine
    bk += 0.60 * _g(ax - 5.5, z - 25.8, 3.0, 2.5)                                 # shoulder blades
    return d + f * wf + bk * wb


def _section_xy(sec, t, off=0.0):
    hx, hy, cy, pw = sec
    c, s = math.cos(t), math.sin(t)
    return ((hx + off) * math.copysign(abs(c) ** (2 / pw), c),
            cy + (hy + off) * math.copysign(abs(s) ** (2 / pw), s))


def torso_ring(z, n, M=720):
    """One ring of the torso, points spaced by ARC LENGTH (even on the flat chest) and
    packed denser across the front, then pushed out by the anatomical relief."""
    sec = _catmull(TORSO_KEYS, z)
    ts = [2 * math.pi * j / M for j in range(M + 1)]
    pts = [_section_xy(sec, t) for t in ts]
    cum = [0.0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
    total, ring_, j = cum[-1], [], 0
    for k in range(n):
        u = k / n
        f = (u + 0.6 / (2 * math.pi) * (math.cos(2 * math.pi * u) - 1)) * total   # dense at front
        while cum[j + 1] < f:
            j += 1
        a = (f - cum[j]) / ((cum[j + 1] - cum[j]) or 1)
        t = ts[j] + a * (ts[j + 1] - ts[j])
        x, y = _section_xy(sec, t)
        rx, ry = x, y - sec[2]
        rl = math.hypot(rx, ry) or 1
        dd = body_relief(x, z, math.sin(t))
        ring_.append((x + dd * rx / rl, y + dd * ry / rl, z))
    return ring_


def sculpted_torso(n=240, dz=0.1):
    zs, z = [], TORSO_KEYS[0][0]
    while z < TORSO_KEYS[-1][0] - 1e-6:
        zs.append(z)
        z += dz
    zs.append(TORSO_KEYS[-1][0])
    return loft([torso_ring(z, n) for z in zs])


def draped_cape(n=60):
    """Cape draped down the back: inner face sunk into the body (always attached),
    outer face thicker toward the bottom with soft vertical folds."""
    a0, a1 = math.radians(200), math.radians(340)
    rings = []
    for z, thick in ((15.5, 2.4), (18.0, 2.1), (21.0, 1.8), (24.0, 1.5), (26.6, 1.3), (28.8, 1.0)):
        sec = _catmull(TORSO_KEYS, z)
        outer, inner = [], []
        for k in range(n):
            t = a0 + (a1 - a0) * k / (n - 1)
            fold = 0.45 * math.cos(7 * (t - a0)) * _smooth(28.8, 18.0, z)   # folds fade toward the top
            edge = _smooth(0.0, 0.12, min(k, n - 1 - k) / (n - 1))          # thin at the side edges
            x, y = _section_xy(sec, t, (thick + fold) * edge + 0.05)
            outer.append((x, y, z))
        for k in range(n):
            t = a1 - (a1 - a0) * k / (n - 1)
            x, y = _section_xy(sec, t, -0.8)
            inner.append((x, y, z))
        rings.append(outer + inner)
    return loft(rings)


# ---- the design --------------------------------------------------------------------------
def pedestal():
    """Three-tier chamfered octagon pedestal with a fluted column (white)."""
    o = dict(n=8, power=2.0, rot=math.pi / 8)
    t = PEDESTAL_TOP
    rings = [ring(0.0, 17.0, 11.0, **o), ring(2.0, 17.0, 11.0, **o),        # base slab
             ring(2.6, 15.8, 10.2, **o), ring(4.2, 15.8, 10.2, **o),        # second tier
             ring(4.8, 14.2, 9.2, **o), ring(5.4, 11.6, 7.6, **o),          # bevel to the column
             ring(5.4, 8.0, 5.6, **o), ring(t - 1.4, 6.6, 4.8, **o),        # tapered column
             ring(t - 1.4, 8.4, 6.0, **o), ring(t - 0.6, 9.0, 6.4, **o),    # bevelled top plate
             ring(t, 9.0, 6.4, **o)]
    tris = loft(rings)
    for k in range(8):                                                     # fluting ribs
        a = 2 * math.pi * (k + 0.5) / 8
        cx, cy = 7.3 * math.cos(a), 5.1 * math.sin(a)
        rib = [(cx + 0.5 * math.cos(a + d), cy + 0.5 * math.sin(a + d)) for d in (0, 2.1, 4.2)]
        tris += prism_simple(rib, 5.4, t - 1.4)
    return tris


def prism_simple(poly, z0, z1):
    """Small convex prism (fan caps) - used for decorative ribs."""
    area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
               for i in range(len(poly)))
    if area < 0:
        poly = list(reversed(poly))
    rings = [[(x, y, z0) for x, y in poly], [(x, y, z1) for x, y in poly]]
    return loft(rings)


def blob(cx, cy, cz, rx, ry, rz, seg=8, bands=5):
    """Low-poly ellipsoid (faceted) - used for the armoured shoulder pads."""
    rings = []
    for k in range(1, bands + 1):
        a = -math.pi / 2 + math.pi * k / (bands + 1)
        rr = math.cos(a)
        rings.append([(cx + rx * rr * math.cos(2 * math.pi * i / seg),
                       cy + ry * rr * math.sin(2 * math.pi * i / seg),
                       cz + rz * math.sin(a)) for i in range(seg)])
    return loft(rings)


def collar_band(z, r_in, r_out, a0, a1, cy, n=7):  # noqa: D401
    """Closed band (arc wall) behind the neck at height z, CCW, 2n points."""
    outer = [(r_out * math.cos(a0 + (a1 - a0) * k / (n - 1)),
              cy + r_out * math.sin(a0 + (a1 - a0) * k / (n - 1)), z) for k in range(n)]
    inner = [(r_in * math.cos(a1 - (a1 - a0) * k / (n - 1)),
              cy + r_in * math.sin(a1 - (a1 - a0) * k / (n - 1)), z) for k in range(n)]
    return outer + inner


def cape_band(z, rx, ry, cy, thick, a0, a1, n=9):
    """Closed elliptical band behind the body at height z (a slice of the cape), CCW."""
    outer = [((rx + thick) * math.cos(a0 + (a1 - a0) * k / (n - 1)),
              cy + (ry + thick) * math.sin(a0 + (a1 - a0) * k / (n - 1)), z) for k in range(n)]
    inner = [(rx * math.cos(a1 - (a1 - a0) * k / (n - 1)),
              cy + ry * math.sin(a1 - (a1 - a0) * k / (n - 1)), z) for k in range(n)]
    return outer + inner


def bust():
    """Sculpted hero bust (black): realistic shoulders and chest with the embossed emblem,
    draped cape, high collar, sculpted face and guardian helmet with crest."""
    tris = sculpted_torso()                    # trapezius, collarbones, deltoids, pecs, back
    tris += sculpted_head()                    # realistic sculpted face (one smooth surface)
    tris += helmet()
    tris += draped_cape()

    # curved cloak collar standing behind the neck (rooted inside the upper back)
    a0, a1 = math.radians(200), math.radians(340)
    tris += loft([collar_band(27.0, 5.4, 7.4, a0, a1, -0.6, n=17),
                  collar_band(31.0, 6.0, 7.4, a0 - 0.08, a1 + 0.08, -0.9, n=17),
                  collar_band(35.0, 6.6, 7.6, a0 - 0.16, a1 + 0.16, -1.2, n=17)])

    # guardian crest: a bold plume running front to back over the helmet (drawn in y-z)
    tris += slab([(4.6, 44.2), (3.4, 47.4), (0.6, 49.6), (-3.2, 50.4), (-6.6, 48.6),
                  (-7.8, 44.8), (-6.2, 42.6), (-2.0, 45.4)], "x", -0.8, 0.8)
    return tris


def _render_view(tris, W, H, sc, z_center, color_z, yaw_deg=180 - 24, pitch_deg=10):
    """Z-buffered, Lambert-shaded render: every pixel shows the surface nearest the camera,
    so small details (eyes, nose, emblem) are never painted over."""
    from PIL import Image
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    L = (-0.45, -0.70, 0.55)                                  # light: front-left-top
    ln = math.sqrt(sum(v * v for v in L))
    L = tuple(v / ln for v in L)
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)

    def view(p):
        x, y, z = p
        x1 = x * cy - y * sy
        y1 = x * sy + y * cy
        return x1, y1 * cp - (z - z_center) * sp, y1 * sp + (z - z_center) * cp

    bg = (214, 217, 223)
    img = Image.new("RGB", (W, H), bg)
    px = img.load()
    zbuf = [1e9] * (W * H)
    nbuf = [None] * (W * H)                                   # face normal per pixel (outlines)
    sbuf = [None] * (W * H)                                   # smooth normal per pixel (lighting)
    cbuf = [None] * (W * H)                                   # base colour per pixel

    # face normals + smooth vertex normals (smoothing only across gentle angles, so the
    # sculpted face is smooth while the pedestal / crest keep their sharp edges)
    faces, adj = [], {}
    for t in tris:
        v = [view(p) for p in t]
        ux, uy, uz = (v[1][i] - v[0][i] for i in range(3))
        wx, wy, wz = (v[2][i] - v[0][i] for i in range(3))
        nx, ny, nz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
        nl = math.sqrt(nx * nx + ny * ny + nz * nz)
        if nl < 1e-12:
            continue
        fn = (nx / nl, ny / nl, nz / nl)
        keys = [(round(p[0], 4), round(p[1], 4), round(p[2], 4)) for p in t]
        faces.append((t, v, fn, keys))
        for k in keys:
            adj.setdefault(k, []).append(fn)

    def corner_normal(k, fn):
        sx = sy_ = sz = 0.0
        for m in adj[k]:
            if m[0] * fn[0] + m[1] * fn[1] + m[2] * fn[2] > 0.55:
                sx += m[0]; sy_ += m[1]; sz += m[2]
        ln_ = math.sqrt(sx * sx + sy_ * sy_ + sz * sz) or 1
        return sx / ln_, sy_ / ln_, sz / ln_

    for t, v, fn, keys in faces:
        nx, ny, nz = fn
        if ny > 0.05:                                         # back face (camera at -y)
            continue
        zmid = sum(p[2] for p in t) / 3
        base = (236, 236, 232) if zmid < color_z - 0.05 else (92, 97, 110)    # white / graphite
        na, nb, nc = (corner_normal(k, fn) for k in keys)
        s = [(W / 2 + q[0] * sc, H / 2 - q[2] * sc, q[1]) for q in v]
        x0 = max(0, int(min(q[0] for q in s))); x1 = min(W - 1, int(max(q[0] for q in s)) + 1)
        y0 = max(0, int(min(q[1] for q in s))); y1 = min(H - 1, int(max(q[1] for q in s)) + 1)
        (ax, ay, ad), (bx, by, bd), (cx_, cy_, cd) = s
        den = (by - cy_) * (ax - cx_) + (cx_ - bx) * (ay - cy_)
        if abs(den) < 1e-9:
            continue
        for yy in range(y0, y1 + 1):
            fy = yy + 0.5
            for xx in range(x0, x1 + 1):
                fx = xx + 0.5
                w0 = ((by - cy_) * (fx - cx_) + (cx_ - bx) * (fy - cy_)) / den
                w1 = ((cy_ - ay) * (fx - cx_) + (ax - cx_) * (fy - cy_)) / den
                w2 = 1 - w0 - w1
                if w0 < -1e-6 or w1 < -1e-6 or w2 < -1e-6:
                    continue
                d = w0 * ad + w1 * bd + w2 * cd
                k = yy * W + xx
                if d < zbuf[k]:
                    zbuf[k] = d
                    nbuf[k] = fn
                    sbuf[k] = (w0 * na[0] + w1 * nb[0] + w2 * nc[0],
                               w0 * na[1] + w1 * nb[1] + w2 * nc[1],
                               w0 * na[2] + w1 * nb[2] + w2 * nc[2])
                    cbuf[k] = base
    # deferred shading: soft key light + fill + a little plastic-like highlight
    hx, hy, hz = L[0], L[1] - 1.0, L[2]
    hl = math.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx / hl, hy / hl, hz / hl
    for k in range(W * H):
        n = sbuf[k]
        if n is None:
            continue
        l_ = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) or 1
        n0, n1, n2 = n[0] / l_, n[1] / l_, n[2] / l_
        lam = max(0.0, n0 * L[0] + n1 * L[1] + n2 * L[2])
        fill = max(0.0, -n1) * 0.18                           # soft light from the camera
        spec = max(0.0, n0 * hx + n1 * hy + n2 * hz) ** 40 * 0.12
        shade = 0.22 + 0.80 * lam + fill
        b = cbuf[k]
        px[k % W, k // W] = tuple(min(255, int(c * shade + 255 * spec)) for c in b)
    # thin outlines only at silhouettes and sharp creases
    for yy in range(H - 1):
        for xx in range(W - 1):
            k = yy * W + xx
            a = nbuf[k]
            if a is None:
                continue
            for k2 in (k + 1, k + W):
                b = nbuf[k2]
                if b is None or abs(zbuf[k] - zbuf[k2]) > 0.5 or a[0] * b[0] + a[1] * b[1] + a[2] * b[2] < 0.5:
                    r, g, bl = px[xx, yy]
                    px[xx, yy] = (int(r * 0.5), int(g * 0.5), int(bl * 0.5))
                    break
    return img


def render_png(tris, path, color_z):
    """Full view (left) + head close-up (right), z-buffered and shaded."""
    from PIL import Image, ImageDraw, ImageFont
    panels = [("Night Warden - 3/4 view", _render_view(tris, 620, 860, 13.0, 25.0, color_z)),
              ("Front - shoulders & chest", _render_view(tris, 620, 860, 15.0, 28.0, color_z,
                                                         yaw_deg=180, pitch_deg=8)),
              ("Face - 3/4", _render_view(tris, 620, 860, 50.0, 40.6, color_z, yaw_deg=180 - 35, pitch_deg=6))]
    out = Image.new("RGB", (620 * 3 + 40, 920), (214, 217, 223))
    d = ImageDraw.Draw(out)
    try:
        f = ImageFont.truetype("segoeuib.ttf", 28)
    except OSError:
        f = ImageFont.load_default()
    for i, (title, im) in enumerate(panels):
        out.paste(im, (i * 640, 60))
        d.text((i * 640 + 20, 16), title, fill=(40, 44, 52), font=f)
    out.save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--height", type=float, default=50.0, help="total height in mm")
    a = ap.parse_args()
    tris = pedestal() + bust()
    zmax = max(p[2] for t in tris for p in t)
    s = a.height / zmax
    tris = [tuple((p[0] * s, p[1] * s, p[2] * s) for p in t) for t in tris]
    os.makedirs(OUT, exist_ok=True)
    stl = os.path.join(OUT, "night_warden_bust.stl")
    write_stl(stl, tris)
    xs = [p[0] for t in tris for p in t]
    ys = [p[1] for t in tris for p in t]
    color_z = PEDESTAL_TOP * s
    render_png(tris, os.path.join(OUT, "night_warden_render.png"), color_z)
    print("wrote %s: %d triangles" % (os.path.normpath(stl), len(tris)))
    print("size: %.1f wide x %.1f deep x %.1f tall mm" % (max(xs) - min(xs), max(ys) - min(ys), a.height))
    print("colour change at Z %.2f mm: white pedestal below (RIGHT), black bust above (LEFT)" % color_z)
