"""
TWIST_VASE: a 3D-looking demo for the LEFT extruder of the Duplicator 4.

  * 6-lobed "flower" outline that TWISTS as it rises and BULGES in the middle
  * 3 solid base layers, then a single wall printed in continuous spiral
    ("vase mode"): Z rises smoothly all the way round, no layer seam
  * left extruder only, PLA 210 C, bed NOT heated (faulty bed sensor)
  * slow Z homing (5 mm/s) with heaters off, then heat - same proven sequence
    as LEFT_SQ_HOME; firmware stays on tool 0 (bogus T1 offset)

    python tools/make_vase.py [--height 25] [--radius 14] [--twist 60] [--lobes 6]
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import math
import os
import struct

from make_dual_sample import (FIL_AREA, HOME_MM, SPM, Printer, bead_area, prime_line,
                              travel_to)

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="TWIST_VASE")
ap.add_argument("--temp", type=int, default=210)
ap.add_argument("--height", type=float, default=25.0, help="total height mm")
ap.add_argument("--radius", type=float, default=14.0, help="base radius mm")
ap.add_argument("--lobes", type=int, default=6)
ap.add_argument("--lobe-depth", type=float, default=0.12, help="lobe size as fraction of radius")
ap.add_argument("--twist", type=float, default=60.0, help="total twist in degrees")
ap.add_argument("--bulge", type=float, default=0.15, help="mid-height bulge as fraction of radius")
ap.add_argument("--brim", type=int, default=6, help="brim loops around the first layer (0 = none)")
ap.add_argument("--first-temp", type=int, default=220, help="nozzle temp for the first layer")
ap.add_argument("--first-speed", type=float, default=8.0, help="first layer speed mm/s")
ap.add_argument("--z-offset", type=float, default=-0.08,
                help="shift the whole print in Z (e.g. -0.05 squeezes the first layer more)")
ap.add_argument("--base-layers", type=int, default=3)
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output"))
a = ap.parse_args()

FIRST_H, H = 0.30, 0.20
BASE_LAYERS = a.base_layers
W1, W = 0.55, 0.50                        # line width first layer / rest
BASE_FLOW = 1.05                          # a little extra plastic so the bottom closes up
FIRST_FLOW = 1.10                         # first layer: extra squish for grip on a cold bed
SPACING = 0.90                            # neighbouring base lines overlap 10 %
ZO = a.z_offset
PTS = 120                                 # outline points per revolution
TRAVEL_F = 80.0
CX, CY = 0.0, 0.0                         # LEFT nozzle prints at bed centre


def radius(theta, z):
    """Outline radius at angle theta (rad) and height z: lobes + twist + bulge."""
    frac = min(1.0, max(0.0, z / a.height))
    twist = math.radians(a.twist) * frac
    base = a.radius * (1.0 + a.bulge * math.sin(math.pi * frac))
    return base * (1.0 + a.lobe_depth * math.cos(a.lobes * (theta - twist)))


def outline(z, inset=0.0, n=PTS):
    pts = []
    for i in range(n + 1):
        th = 2 * math.pi * i / n
        r = radius(th, z) - inset
        pts.append((CX + r * math.cos(th), CY + r * math.sin(th)))
    return pts


def scan_fill(poly, spacing, horizontal):
    """Rectilinear fill of a (possibly concave) polygon, returned as segments."""
    segs = []
    if not horizontal:
        poly = [(y, x) for x, y in poly]
    ys = [p[1] for p in poly]
    y = min(ys) + spacing / 2
    while y < max(ys):
        xs = []
        for (x0, y0), (x1, y1) in zip(poly, poly[1:]):
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            if xs[i + 1] - xs[i] > 0.4:
                segs.append(((xs[i], y), (xs[i + 1], y)))
        y += spacing
    if not horizontal:
        segs = [((s[0][1], s[0][0]), (s[1][1], s[1][0])) for s in segs]
    return segs


def spiral_fill(z, w):
    """Solid base: one CLOSED outline ring, then one continuous inward spiral.
    Each turn is a SCALED copy of the flower outline, shrinking evenly to the centre
    (no petal-shaped hole). The closed ring keeps the outer edge complete all the way
    round (a bare spiral leaves a crescent gap where its first turn moves inward).
    Returns (x, y, spacing): spacing = local gap to the next turn in mm, used to
    set the plastic flow point by point so the bottom is closed without ridges."""
    frac = min(1.0, max(0.0, z / a.height))
    rmean = a.radius * (1.0 + a.bulge * math.sin(math.pi * frac))
    fmax = 1.0 + a.lobe_depth
    step = w * 0.95 / fmax                  # mean shrink per turn; widest gap <= 0.95 w
    pts = []
    ring_scale = 1.0 - (w * 0.5) / rmean    # closed outer ring, line edge = outline
    for i in range(PTS + 1):
        th = 2 * math.pi * i / PTS
        r_out = radius(th, z)
        r = r_out * ring_scale
        pts.append((CX + r * math.cos(th), CY + r * math.sin(th), w))
    th = 0.0
    while True:
        # spiral starts ON the ring and moves inward one step per turn
        scale = 1.0 - (w * 0.5 + step * th / (2 * math.pi)) / rmean
        if scale * rmean < step * 0.4:        # reached the centre
            break
        r_out = radius(th, z)
        r = r_out * scale
        # gap to the line outside this one: during the first turn that is the ring,
        # which it is still close to -> flow ramps up from ~0 (no double plastic)
        turn_frac = min(1.0, th / (2 * math.pi))
        gap = step * turn_frac * r_out / rmean
        pts.append((CX + r * math.cos(th), CY + r * math.sin(th), gap))
        # ~0.6 mm long segments everywhere (no micro-segments near the centre)
        th += min(2 * math.pi / 12, max(2 * math.pi / PTS, 0.6 / max(r, 0.3)))
    pts.append((CX, CY, step))                # finish exactly in the middle
    return pts


def extrude_path(p, pts, k, f):
    for x, y in pts[1:]:
        px, py = p.pos[0], p.pos[1]
        p.move(x, y, de=math.hypot(x - px, y - py) * k, f=f)


p = Printer()
p._cmd(struct.pack("<BI", 153, 0) + a.name.encode() + b"\0")
p.percent(0)
p.set_bed(0)
p._cmd(struct.pack("<BB", 134, 0), "T0 ; firmware stays on tool 0 (bogus T1 offset)")
p.set_temp(0, 0)
p.set_temp(1, 0)                           # heaters OFF until homing has worked
p.change_tool(0)
p.home(z_fast=5.0, z_timeout=40)           # slow Z homing - proven safe
p.move(z=5.0, f=5.0)
p.set_temp(1, a.first_temp)                # LEFT nozzle only, hotter for the first layer
p.wait_tool(1)
p.change_tool(1, shift=False)              # head at X end: no shift, go straight to prime
p.move(-60.0, -50.0, f=TRAVEL_F)
prime_line(p, -60.0, -10.0, -50.0, FIRST_H, TRAVEL_F)

# ---- solid base: one clean inward spiral per layer -------------------------------
for li in range(BASE_LAYERS):
    z = FIRST_H + li * H + ZO
    lh = FIRST_H if li == 0 else H
    w = W1 if li == 0 else W
    sp = a.first_speed if li == 0 else 22.0
    flow = FIRST_FLOW if li == 0 else BASE_FLOW
    if li == 1:
        p.set_temp(1, a.temp)                 # back to normal temp after the first layer
    if li == 0 and a.brim > 0:
        # BRIM: rings around the base (outermost first, last ring touches the base)
        kb = bead_area(w, lh) / FIL_AREA * flow
        for bi in reversed(range(a.brim)):
            # innermost ring centre sits w*0.20 outside the outline: it overlaps the
            # base's outer line (centre at -w/2), so the brim is fused to the part
            ring = outline(z - ZO, -(w * 0.20 + w * 0.95 * bi))
            p.comment("brim ring %d" % (bi + 1))
            if bi == a.brim - 1:
                travel_to(p, ring[0][0], ring[0][1], z, TRAVEL_F, 0.6, 1.0)
            else:
                p.move(ring[0][0], ring[0][1], f=sp)
            extrude_path(p, ring, kb, sp)
    pts = spiral_fill(z - ZO, w)
    p.comment("base layer %d z=%.2f: inward spiral, %d points" % (li + 1, z, len(pts)))
    if li == 0 and a.brim > 0:
        p.move(pts[0][0], pts[0][1], f=sp)    # step in from the brim, no retract
    else:
        travel_to(p, pts[0][0], pts[0][1], z, TRAVEL_F, 0.6, 1.0)
    for x, y, gap in pts[1:]:
        # volume to fill one gap-wide strip: length x gap x layer height
        k = lh * max(gap, 0.05) / FIL_AREA * flow
        px, py = p.pos[0], p.pos[1]
        p.move(x, y, de=math.hypot(x - px, y - py) * k, f=sp)
    p.retract(1.0)
    p.percent(3 + 3 * li)

# ---- spiral wall (vase mode) --------------------------------------------------
z0 = FIRST_H + (BASE_LAYERS - 1) * H + ZO     # top of the base
k = bead_area(W, H) / FIL_AREA
turns = int(round((a.height - z0) / H))
start = outline(z0 - ZO + H, W * 0.5)[0]
travel_to(p, start[0], start[1], z0 + H * 0.05, TRAVEL_F, 0.6, 1.0)
p.comment("spiral wall: %d turns" % turns)
for t in range(turns):
    for i in range(1, PTS + 1):
        frac = (t * PTS + i) / PTS                # turns completed, continuous
        z = z0 + frac * H
        th = 2 * math.pi * i / PTS
        r = radius(th, z - ZO) - W * 0.5
        x, y = CX + r * math.cos(th), CY + r * math.sin(th)
        px, py = p.pos[0], p.pos[1]
        p.move(x, y, z=z, de=math.hypot(x - px, y - py) * k, f=20.0)
    if t % 10 == 0:
        p.percent(min(98, 10 + round(88 * t / turns)))

# ---- finish -------------------------------------------------------------------
p.comment("end")
p.retract(2.0)
p.set_temp(0, 0)
p.set_temp(1, 0)
p.set_bed(0)
p.move(z=min(140.0, p.pos[2] + 40.0), f=10.0)   # bed down, away from the vase
p.change_tool(0)
us_xy = round(1e6 / (2500 / 60 * SPM["x"]))
p._cmd(struct.pack("<BBIH", 132, 0x03, us_xy, 60), "G162 X Y F2500")
p._cmd(struct.pack("<BB", 137, 0x1F), "M18 ; motors off")
p.percent(100)
p._cmd(struct.pack("<BB", 154, 0), "M137 ; build end")
struct.pack_into("<I", p.x3g, 1, p.ncmd)

os.makedirs(a.out, exist_ok=True)
out = os.path.join(a.out, a.name + ".x3g")
open(out, "wb").write(p.x3g)
open(os.path.splitext(out)[0] + ".gcode", "w").write("\n".join(p.g) + "\n")
rmax = a.radius * (1 + a.bulge) * (1 + a.lobe_depth)
print("  first layer: %d C, %.0f mm/s, z-offset %+.2f mm, brim %d rings (~%.1f mm wide)"
      % (a.first_temp, a.first_speed, a.z_offset, a.brim, a.brim * W1 * 0.95))
print("wrote %s" % os.path.normpath(out))
print("  %.0f mm tall, up to %.0f mm wide, %d spiral turns, %d commands"
      % (a.height, 2 * rmax, turns, p.ncmd))
print("  left filament %.0f mm (~%.1f g PLA), est. %.0f min after heat-up"
      % (p.e[1], p.e[1] * FIL_AREA * 1.24 / 1000, p.time_s / 60))
